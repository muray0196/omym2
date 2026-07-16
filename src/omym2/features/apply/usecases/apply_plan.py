"""
Summary: Applies reviewed Plans through durable operation logs.
Why: Mutates Library files only after recorded PlanActions and FileEvents exist.
"""

from __future__ import annotations

import os
from dataclasses import dataclass, replace
from datetime import timedelta
from pathlib import Path, PurePath
from typing import TYPE_CHECKING

from omym2.config import (
    FILE_EVENT_SEQUENCE_START,
    FILE_EVENT_SEQUENCE_STEP,
    OPERATION_RESULT_RETENTION_HOURS,
    OPERATION_TOMBSTONE_RETENTION_DAYS,
)
from omym2.domain.models.companion_asset import CompanionAsset, CompanionAssetKind, CompanionAssetStatus
from omym2.domain.models.file_event import FileEvent, FileEventStatus, FileEventType
from omym2.domain.models.library import Library, LibraryStatus
from omym2.domain.models.operation import (
    Operation,
    OperationError,
    OperationErrorCode,
    OperationKind,
    OperationStatus,
    RunCompletedResult,
)
from omym2.domain.models.plan import Plan, PlanStatus, PlanType
from omym2.domain.models.plan_action import ActionStatus, ActionType, PlanAction, PlanActionReason
from omym2.domain.models.run import Run, RunStatus
from omym2.domain.models.track import Track, TrackStatus
from omym2.domain.services.unprocessed_collection import validate_unprocessed_path_layout
from omym2.features.common_ports import FileObservationChangedError, FileObservationInvalidPathError

if TYPE_CHECKING:
    from datetime import datetime

    from omym2.domain.models.file_snapshot import FileContentSnapshot, FileSnapshot
    from omym2.features.apply.dto import ApplyPlanRequest
    from omym2.features.apply.ports import ApplyPlanPorts
    from omym2.features.common_ports import FileSystemPath, UnitOfWork
    from omym2.shared.ids import EventId, OperationId, PlanId, RunId, TrackId

APPLY_FAILED_SUMMARY = "Apply failed."
APPLY_NOT_CONFIRMED_MESSAGE = "Apply was not confirmed."
CLAIMED_APPLY_STATE_INVALID_MESSAGE = "Claimed Apply state is no longer executable."
COMPANION_ASSET_ID_MISSING_SUMMARY = "Planned companion move is missing its preallocated asset ID."
COMPANION_DEPENDENCY_FAILED_SUMMARY = "A recorded companion dependency or owner did not apply successfully."
COMPANION_EXTERNAL_TARGET_SUMMARY = "Companion moves require a Library-relative target path."
INVALID_COMPANION_UNDO_SUMMARY = "Companion restore action is not backed by durable undo history."
COMPANION_SOURCE_ROOT_MISSING_SUMMARY = "Planned external companion source is missing its recorded source root."
COMPANION_STATE_CHANGED_SUMMARY = "Managed companion state changed after planning."
INCOMPLETE_MOVE_ACTION_SUMMARY = "Planned move action is missing source or target path."
EXTERNAL_RESTORE_WITHOUT_TRACK_SUMMARY = "External restore action is missing a managed Track ID."
INVALID_EXTERNAL_RESTORE_SUMMARY = "External restore action is not backed by durable undo history."
INVALID_PATH_MOVE_FAILURE_MESSAGE = "The file move failed because its path was rejected."
INVALID_UNPROCESSED_MOVE_SUMMARY = "Unprocessed move is not backed by valid recorded source-root provenance."
LIBRARY_NOT_FOUND_MESSAGE = "Plan Library was not found."
LIBRARY_ROOT_CHANGED_SUMMARY = "Library root changed during apply."
MOVE_FAILED_ERROR_CODE = "move_failed"
MOVE_FAILED_MESSAGE = "The file move failed."
PLAN_NOT_FOUND_MESSAGE = "Plan was not found."
PLAN_NOT_READY_MESSAGE = "Plan is not ready and cannot be applied."
SOURCE_MISSING_MOVE_FAILURE_MESSAGE = "The file move failed because its source was unavailable."
SUMMARY_SEPARATOR = "; "
SOURCE_PRECONDITION_SNAPSHOT_MISSING_MESSAGE = "Successful source precondition did not return a snapshot."
TARGET_EXISTS_MOVE_FAILURE_MESSAGE = "The file move failed because its target already exists."

COMPANION_ACTION_TYPES = frozenset({ActionType.MOVE_LYRICS, ActionType.MOVE_ARTWORK})
FILESYSTEM_OBSERVING_ACTION_TYPES = frozenset(
    {
        ActionType.MOVE,
        ActionType.MOVE_LYRICS,
        ActionType.MOVE_ARTWORK,
        ActionType.MOVE_UNPROCESSED,
        ActionType.REFRESH_METADATA,
    }
)


@dataclass(frozen=True, slots=True)
class ApplyPlanUseCase:
    """Apply reviewed Plans using recorded actions and durable FileEvents."""

    ports: ApplyPlanPorts

    def execute(self, request: ApplyPlanRequest) -> Run:
        """Execute one already-claimed Apply and return its terminal Run."""
        _require_confirmed(request)

        with self.ports.uow.usecase_scope():
            return self._execute_confirmed(request)

    def _execute_confirmed(self, request: ApplyPlanRequest) -> Run:
        """Apply one confirmed request inside a shared UnitOfWork resource scope."""

        started_apply = self._load_claimed_apply(request)
        if not self._library_root_still_matches(started_apply.plan):
            return self._finish_apply(
                started_apply.plan,
                started_apply.run,
                _ApplyCompletion(
                    success_count=0,
                    failure_count=1,
                    failure_summaries=(LIBRARY_ROOT_CHANGED_SUMMARY,),
                    operation_failed=True,
                ),
                request.operation_id,
            )

        move_success_count = 0
        move_failure_count = 0
        failure_summaries: list[str] = []
        sequence_no = FILE_EVENT_SEQUENCE_START
        operation_failed = False

        for action in started_apply.actions:
            if action.status == ActionStatus.BLOCKED:
                continue

            if action.status != ActionStatus.PLANNED:
                continue

            if action.action_type == ActionType.SKIP:
                self._mark_action_applied(action)
                continue

            result = self._process_filesystem_observing_action(started_apply, action, sequence_no)
            if result is None:
                continue
            if result.event_created:
                sequence_no += FILE_EVENT_SEQUENCE_STEP

            if result.succeeded:
                move_success_count += 1
            else:
                move_failure_count += 1
                failure_summaries.append(result.failure_summary)
                if result.should_stop:
                    operation_failed = True
                    break

        return self._finish_apply(
            started_apply.plan,
            started_apply.run,
            _ApplyCompletion(
                success_count=move_success_count,
                failure_count=move_failure_count,
                failure_summaries=tuple(failure_summaries),
                operation_failed=operation_failed,
            ),
            request.operation_id,
        )

    def _process_filesystem_observing_action(  # noqa: PLR0911  # Closed action kinds dispatch to distinct safety paths.
        self,
        started_apply: _StartedApply,
        action: PlanAction,
        sequence_no: int,
    ) -> _ActionApplyResult | None:
        if action.action_type not in FILESYSTEM_OBSERVING_ACTION_TYPES:
            return None

        if not self._library_root_still_matches(started_apply.plan):
            return _ActionApplyResult.root_changed()

        if not self._dependencies_are_applied(action):
            self._mark_action_failed(action, PlanActionReason.COMPANION_DEPENDENCY_FAILED)
            return _ActionApplyResult(
                succeeded=False,
                event_created=False,
                failure_summary=COMPANION_DEPENDENCY_FAILED_SUMMARY,
            )

        if action.action_type == ActionType.REFRESH_METADATA:
            return self._process_metadata_refresh_action(started_apply.library, action)

        if action.action_type in COMPANION_ACTION_TYPES:
            return self._process_companion_move_action(
                started_apply.run,
                started_apply.plan,
                started_apply.library,
                action,
                sequence_no,
            )

        if action.action_type is ActionType.MOVE_UNPROCESSED:
            return self._process_unprocessed_move_action(
                started_apply.run,
                started_apply.plan,
                action,
                sequence_no,
            )

        return self._process_move_action(
            started_apply.run,
            started_apply.plan,
            started_apply.library,
            action,
            sequence_no,
        )

    def _load_claimed_apply(self, request: ApplyPlanRequest) -> _StartedApply:
        with self.ports.uow as uow:
            plan = uow.plans.get(request.plan_id)
            run = uow.runs.get(request.run_id)
            operation = uow.operations.lookup(request.operation_id)
            if (
                plan is None
                or plan.status is not PlanStatus.APPLYING
                or run is None
                or run.status is not RunStatus.RUNNING
                or run.plan_id != plan.plan_id
                or run.library_id != plan.library_id
                or not isinstance(operation, Operation)
                or operation.kind is not OperationKind.APPLY_PLAN
                or operation.status is not OperationStatus.RUNNING
                or operation.library_id != plan.library_id
                or operation.plan_id != plan.plan_id
                or operation.run_id != run.run_id
            ):
                raise ApplyPlanError(CLAIMED_APPLY_STATE_INVALID_MESSAGE)
            library = uow.libraries.get(plan.library_id)
            if library is None:
                raise ApplyPlanError(LIBRARY_NOT_FOUND_MESSAGE)
            actions = tuple(uow.plan_actions.list_by_plan(plan.plan_id))
        return _StartedApply(plan=plan, library=library, run=run, actions=actions)

    def _process_move_action(
        self,
        run: Run,
        plan: Plan,
        library: Library,
        action: PlanAction,
        sequence_no: int,
    ) -> _ActionApplyResult:
        source_path = action.source_path
        target_path = action.target_path
        if source_path is None or target_path is None:
            self._mark_action_failed(action)
            return _ActionApplyResult(
                succeeded=False,
                event_created=False,
                failure_summary=INCOMPLETE_MOVE_ACTION_SUMMARY,
            )
        target_is_absolute = PurePath(target_path).is_absolute()
        if target_is_absolute and not self._absolute_target_is_verified_undo(plan, action):
            self._mark_action_failed(action, PlanActionReason.INVALID_PATH)
            return _ActionApplyResult(
                succeeded=False,
                event_created=False,
                failure_summary=INVALID_EXTERNAL_RESTORE_SUMMARY,
            )

        source_filesystem_path = self._resolve_source_path(library, source_path)
        target_filesystem_path = self._resolve_target_path(library, target_path)

        precondition = self._verify_source_preconditions(action, source_filesystem_path)
        if not precondition.passed:
            self._mark_action_failed(action, precondition.reason)
            return _ActionApplyResult(
                succeeded=False,
                event_created=False,
                failure_summary=precondition.failure_summary,
            )

        event = self._record_pending_file_event(
            run=run,
            action=action,
            source_path=source_path,
            target_path=target_path,
            sequence_no=sequence_no,
        )

        try:
            snapshot = precondition.snapshot
            if snapshot is None:
                raise AssertionError(SOURCE_PRECONDITION_SNAPSHOT_MISSING_MESSAGE)
            target_root = plan.source_root_at_plan if target_is_absolute else library.root_path
            if target_root is None:
                raise AssertionError(INVALID_EXTERNAL_RESTORE_SUMMARY)
            self.ports.file_mover.move(
                source_filesystem_path,
                target_filesystem_path,
                source_root=None if PurePath(source_path).is_absolute() else library.root_path,
                target_root=target_root,
                expected_source_identity=snapshot.filesystem_identity,
                expected_source_content_hash=snapshot.content_hash,
            )
        except (OSError, ValueError) as exc:
            reason = _move_failure_reason(exc)
            failure_message = _move_failure_message(reason)
            self._record_failed_file_event(event, action, reason, failure_message)
            return _ActionApplyResult(
                succeeded=False,
                event_created=True,
                failure_summary=failure_message,
            )

        self._record_successful_move(event, action, snapshot, target_path)
        return _ActionApplyResult(succeeded=True, event_created=True, failure_summary="")

    def _process_unprocessed_move_action(
        self,
        run: Run,
        plan: Plan,
        action: PlanAction,
        sequence_no: int,
    ) -> _ActionApplyResult:
        """Apply one trackless, source-root-anchored collection or reversal move."""
        source_path = action.source_path
        target_path = action.target_path
        source_root = plan.source_root_at_plan
        if (
            source_path is None
            or target_path is None
            or source_root is None
            or not self._unprocessed_move_is_verified(plan, action)
        ):
            self._mark_action_failed(action, PlanActionReason.INVALID_PATH)
            return _ActionApplyResult(
                succeeded=False,
                event_created=False,
                failure_summary=INVALID_UNPROCESSED_MOVE_SUMMARY,
            )

        precondition = self._verify_content_source_preconditions(
            action,
            source_path,
            root=source_root,
        )
        if not precondition.passed:
            self._mark_action_failed(action, precondition.reason)
            return _ActionApplyResult(
                succeeded=False,
                event_created=False,
                failure_summary=precondition.failure_summary,
            )

        event = self._record_pending_file_event(
            run=run,
            action=action,
            source_path=source_path,
            target_path=target_path,
            sequence_no=sequence_no,
        )
        snapshot = precondition.snapshot
        if snapshot is None:
            raise AssertionError(SOURCE_PRECONDITION_SNAPSHOT_MISSING_MESSAGE)
        try:
            self.ports.file_mover.move(
                source_path,
                target_path,
                source_root=source_root,
                target_root=source_root,
                expected_source_identity=snapshot.filesystem_identity,
                expected_source_content_hash=snapshot.content_hash,
            )
        except (OSError, ValueError) as exc:
            reason = _move_failure_reason(exc)
            failure_message = _move_failure_message(reason)
            self._record_failed_file_event(event, action, reason, failure_message)
            return _ActionApplyResult(
                succeeded=False,
                event_created=True,
                failure_summary=failure_message,
            )

        self._record_successful_unprocessed_move(event, action)
        return _ActionApplyResult(succeeded=True, event_created=True, failure_summary="")

    def _process_companion_move_action(
        self,
        run: Run,
        plan: Plan,
        library: Library,
        action: PlanAction,
        sequence_no: int,
    ) -> _ActionApplyResult:
        input_result = self._companion_move_input(plan, library, action)
        if input_result.move_input is None:
            self._mark_action_failed(action, input_result.reason)
            return _ActionApplyResult(
                succeeded=False,
                event_created=False,
                failure_summary=input_result.failure_summary,
            )
        move_input = input_result.move_input

        context_result = self._load_companion_context(plan, action)
        if context_result.context is None:
            self._mark_action_failed(action, context_result.reason)
            return _ActionApplyResult(
                succeeded=False,
                event_created=False,
                failure_summary=context_result.failure_summary,
            )

        source_filesystem_path = self._resolve_source_path(library, move_input.source_path)
        target_filesystem_path = self._resolve_target_path(library, move_input.target_path)
        precondition = self._verify_content_source_preconditions(
            action,
            source_filesystem_path,
            root=move_input.source_root,
        )
        if not precondition.passed:
            self._mark_action_failed(action, precondition.reason)
            return _ActionApplyResult(
                succeeded=False,
                event_created=False,
                failure_summary=precondition.failure_summary,
            )

        event = self._record_pending_file_event(
            run=run,
            action=action,
            source_path=move_input.source_path,
            target_path=move_input.target_path,
            sequence_no=sequence_no,
        )

        return self._move_companion_file(
            _CompanionMoveExecution(
                event=event,
                action=action,
                source_filesystem_path=source_filesystem_path,
                target_filesystem_path=target_filesystem_path,
                move_input=move_input,
                target_root=move_input.target_root,
                snapshot=precondition.snapshot,
                context=context_result.context,
            )
        )

    def _move_companion_file(
        self,
        execution: _CompanionMoveExecution,
    ) -> _ActionApplyResult:
        snapshot = execution.snapshot
        try:
            if snapshot is None:
                raise AssertionError(SOURCE_PRECONDITION_SNAPSHOT_MISSING_MESSAGE)
            self.ports.file_mover.move(
                execution.source_filesystem_path,
                execution.target_filesystem_path,
                source_root=execution.move_input.source_root,
                target_root=execution.target_root,
                expected_source_identity=snapshot.filesystem_identity,
                expected_source_content_hash=snapshot.content_hash,
            )
        except (OSError, ValueError) as exc:
            reason = _move_failure_reason(exc)
            failure_message = _move_failure_message(reason)
            self._record_failed_file_event(execution.event, execution.action, reason, failure_message)
            return _ActionApplyResult(
                succeeded=False,
                event_created=True,
                failure_summary=failure_message,
            )

        self._record_successful_companion_move(
            execution.event,
            execution.action,
            snapshot,
            execution.move_input.target_path,
            execution.context,
        )
        return _ActionApplyResult(succeeded=True, event_created=True, failure_summary="")

    def _companion_move_input(
        self,
        plan: Plan,
        library: Library,
        action: PlanAction,
    ) -> _CompanionMoveInputResult:
        source_path = action.source_path
        target_path = action.target_path
        if source_path is None or target_path is None:
            return _CompanionMoveInputResult.failed(None, INCOMPLETE_MOVE_ACTION_SUMMARY)
        if action.companion_asset_id is None:
            return _CompanionMoveInputResult.failed(None, COMPANION_ASSET_ID_MISSING_SUMMARY)
        if plan.plan_type is PlanType.UNDO and not self._companion_undo_is_verified(plan, action):
            return _CompanionMoveInputResult.failed(
                PlanActionReason.INVALID_PATH,
                INVALID_COMPANION_UNDO_SUMMARY,
            )
        if PurePath(target_path).is_absolute() and plan.plan_type is not PlanType.UNDO:
            return _CompanionMoveInputResult.failed(
                PlanActionReason.INVALID_PATH,
                COMPANION_EXTERNAL_TARGET_SUMMARY,
            )

        source_root = plan.source_root_at_plan if PurePath(source_path).is_absolute() else library.root_path
        target_root = plan.source_root_at_plan if PurePath(target_path).is_absolute() else library.root_path
        if source_root is None or target_root is None:
            return _CompanionMoveInputResult.failed(
                PlanActionReason.INVALID_PATH,
                COMPANION_SOURCE_ROOT_MISSING_SUMMARY,
            )
        return _CompanionMoveInputResult.passed_with(
            _CompanionMoveInput(
                source_path=source_path,
                target_path=target_path,
                source_root=source_root,
                target_root=target_root,
            )
        )

    def _process_metadata_refresh_action(
        self,
        library: Library,
        action: PlanAction,
    ) -> _ActionApplyResult:
        source_path = action.source_path
        target_path = action.target_path
        if source_path is None or target_path is None:
            self._mark_action_failed(action)
            return _ActionApplyResult(
                succeeded=False,
                event_created=False,
                failure_summary=INCOMPLETE_MOVE_ACTION_SUMMARY,
            )

        source_filesystem_path = self._resolve_source_path(library, source_path)
        precondition = self._verify_source_preconditions(action, source_filesystem_path)
        if not precondition.passed:
            self._mark_action_failed(action, precondition.reason)
            return _ActionApplyResult(
                succeeded=False,
                event_created=False,
                failure_summary=precondition.failure_summary,
            )

        snapshot = precondition.snapshot
        if snapshot is None:
            raise AssertionError(SOURCE_PRECONDITION_SNAPSHOT_MISSING_MESSAGE)

        self._record_successful_metadata_refresh(action, snapshot, target_path)
        return _ActionApplyResult(succeeded=True, event_created=False, failure_summary="")

    def _absolute_target_is_verified_undo(self, plan: Plan, action: PlanAction) -> bool:
        if (
            plan.plan_type != PlanType.UNDO
            or plan.source_run_id is None
            or action.track_id is None
            or action.reverses_event_id is None
        ):
            return False
        if action.source_path is None or action.target_path is None:
            return False

        with self.ports.uow as uow:
            # The restore source is the Track's current Library path, which may
            # differ from the original import target after later in-Library
            # moves, so it is verified against the Track instead of the event.
            track = uow.tracks.get(action.track_id)
            event = uow.file_events.get(action.reverses_event_id)
            source_run = uow.runs.get(plan.source_run_id)
            if track is None or event is None or source_run is None:
                return False
            source_action = uow.plan_actions.get(event.plan_action_id)
            if source_action is None:
                return False
            source_plan = uow.plans.get(source_action.plan_id)
            if source_plan is None:
                return False

        source_plan_status_is_terminal = source_plan.status in {
            PlanStatus.APPLIED,
            PlanStatus.PARTIAL_FAILED,
            PlanStatus.FAILED,
        }
        source_run_status_is_terminal = source_run.status in {
            RunStatus.SUCCEEDED,
            RunStatus.PARTIAL_FAILED,
            RunStatus.FAILED,
        }
        return (
            action.plan_id == plan.plan_id
            and action.library_id == plan.library_id
            and action.action_type is ActionType.MOVE
            and action.status is ActionStatus.PLANNED
            and track.library_id == plan.library_id
            and track.status is TrackStatus.ACTIVE
            and track.current_path == action.source_path
            and event.event_type is FileEventType.MOVE_FILE
            and event.status is FileEventStatus.SUCCEEDED
            and event.completed_at is not None
            and event.completed_at <= plan.created_at
            and event.run_id == source_run.run_id == plan.source_run_id
            and event.library_id == plan.library_id
            and event.plan_action_id == source_action.action_id
            and event.source_path == source_action.source_path == action.target_path
            and event.target_path == source_action.target_path
            and source_action.plan_id == source_run.plan_id == source_plan.plan_id
            and source_action.library_id == plan.library_id
            and source_action.track_id == action.track_id
            and source_action.action_type is ActionType.MOVE
            and source_action.status is ActionStatus.APPLIED
            and source_run.library_id == plan.library_id
            and source_run_status_is_terminal
            and source_run.completed_at is not None
            and source_run.completed_at <= plan.created_at
            and source_plan.library_id == plan.library_id
            and source_plan.plan_type is PlanType.ADD
            and source_plan_status_is_terminal
            and source_plan.config_hash == plan.config_hash
            and plan.source_root_at_plan is not None
            and PurePath(plan.source_root_at_plan).is_absolute()
            and source_plan.source_root_at_plan == plan.source_root_at_plan
            and _path_is_within_root(action.target_path, plan.source_root_at_plan)
            and PurePath(source_action.source_path or "").is_absolute()
            and not PurePath(source_action.target_path or "").is_absolute()
        )

    def _companion_undo_is_verified(  # noqa: C901, PLR0911, PLR0912  # Provenance fails closed per durable boundary.
        self,
        plan: Plan,
        action: PlanAction,
    ) -> bool:
        if (
            plan.plan_type is not PlanType.UNDO
            or plan.source_run_id is None
            or action.reverses_event_id is None
            or action.action_type not in COMPANION_ACTION_TYPES
            or action.companion_asset_id is None
            or action.track_id is None
            or action.source_path is None
            or action.target_path is None
        ):
            return False

        with self.ports.uow as uow:
            event = uow.file_events.get(action.reverses_event_id)
            source_run = uow.runs.get(plan.source_run_id)
            asset = uow.companion_assets.get(action.companion_asset_id)
            if event is None or source_run is None or asset is None:
                return False
            source_action = uow.plan_actions.get(event.plan_action_id)
            if source_action is None:
                return False
            source_plan = uow.plans.get(source_action.plan_id)
            if source_plan is None:
                return False
            source_dependencies = tuple(uow.plan_action_dependencies.list_by_action(source_action.action_id))
            source_dependency_actions = {
                dependency_action.action_id: dependency_action
                for dependency_action in uow.plan_actions.list_by_ids(
                    tuple(dependency.depends_on_action_id for dependency in source_dependencies)
                )
            }
            source_events_by_action_id = {
                source_event.plan_action_id: source_event
                for source_event in uow.file_events.list_by_run(source_run.run_id)
                if source_event.status is FileEventStatus.SUCCEEDED
            }
            undo_actions = tuple(uow.plan_actions.list_by_plan(plan.plan_id))
            inverse_actions_by_event_id = {
                inverse_action.reverses_event_id: inverse_action
                for inverse_action in undo_actions
                if inverse_action.reverses_event_id is not None
            }
            inverse_dependencies_by_action_id = {
                inverse_action.action_id: tuple(uow.plan_action_dependencies.list_by_action(inverse_action.action_id))
                for inverse_action in undo_actions
            }
            durably_reversed_event_ids = _durably_reversed_source_event_ids(
                uow,
                source_run.run_id,
                excluding_plan_id=plan.plan_id,
            )

        event_completed_at = event.completed_at
        source_run_completed_at = source_run.completed_at
        if event_completed_at is None or source_run_completed_at is None:
            return False
        if not (
            action.plan_id == plan.plan_id
            and action.library_id == plan.library_id
            and action.status is ActionStatus.PLANNED
            and action.metadata_hash_at_plan is None
            and action.content_hash_at_plan == asset.content_hash
            and event.event_type is _file_event_type(action.action_type)
            and event.status is FileEventStatus.SUCCEEDED
            and event_completed_at <= plan.created_at
            and event.run_id == source_run.run_id == plan.source_run_id
            and event.library_id == plan.library_id
            and event.companion_asset_id == action.companion_asset_id
            and event.plan_action_id == source_action.action_id
            and event.source_path == source_action.source_path == action.target_path
            and event.target_path == source_action.target_path
            and source_action.plan_id == source_run.plan_id == source_plan.plan_id
            and source_action.library_id == plan.library_id
            and source_action.track_id == action.track_id == asset.owner_track_id
            and source_action.action_type is action.action_type
            and source_action.status is ActionStatus.APPLIED
            and source_action.companion_asset_id == action.companion_asset_id
            and source_action.content_hash_at_plan is not None
            and source_action.metadata_hash_at_plan is None
            and source_run.library_id == plan.library_id
            and source_run.status in {RunStatus.SUCCEEDED, RunStatus.PARTIAL_FAILED, RunStatus.FAILED}
            and source_run_completed_at <= plan.created_at
            and source_plan.library_id == plan.library_id
            and source_plan.status in {PlanStatus.APPLIED, PlanStatus.PARTIAL_FAILED, PlanStatus.FAILED}
            and source_plan.config_hash == plan.config_hash
            and source_plan.source_root_at_plan == plan.source_root_at_plan
            and asset.library_id == plan.library_id
            and asset.kind is _companion_asset_kind(action.action_type)
            and asset.status is CompanionAssetStatus.ACTIVE
            and asset.current_path == action.source_path
        ):
            return False

        dependency_action_ids = {dependency.depends_on_action_id for dependency in source_dependencies}
        if any(
            dependency.plan_id != source_plan.plan_id
            or dependency.action_id != source_action.action_id
            or (dependency_action := source_dependency_actions.get(dependency.depends_on_action_id)) is None
            or dependency_action.plan_id != source_plan.plan_id
            or dependency_action.library_id != plan.library_id
            or dependency_action.action_type is not ActionType.MOVE
            or dependency_action.status is not ActionStatus.APPLIED
            for dependency in source_dependencies
        ):
            return False

        source_owner_action_id = source_action.owner_action_id
        expected_inverse_owner_action_id = None
        if source_owner_action_id is not None:
            source_owner = source_dependency_actions.get(source_owner_action_id)
            owner_event = source_events_by_action_id.get(source_owner_action_id)
            if (
                source_owner is None
                or source_owner_action_id not in dependency_action_ids
                or source_owner.track_id != action.track_id
                or owner_event is None
                or owner_event.event_type is not FileEventType.MOVE_FILE
            ):
                return False
            inverse_owner = inverse_actions_by_event_id.get(owner_event.event_id)
            if inverse_owner is not None:
                expected_inverse_owner_action_id = inverse_owner.action_id
            elif owner_event.event_id not in durably_reversed_event_ids:
                return False
        if action.owner_action_id != expected_inverse_owner_action_id:
            return False

        for dependency in source_dependencies:
            source_dependency_event = source_events_by_action_id.get(dependency.depends_on_action_id)
            source_dependency_action = source_dependency_actions[dependency.depends_on_action_id]
            if (
                source_dependency_event is None
                or source_dependency_event.library_id != plan.library_id
                or source_dependency_event.event_type is not FileEventType.MOVE_FILE
                or source_dependency_event.completed_at is None
                or source_dependency_event.completed_at > plan.created_at
                or source_dependency_event.source_path != source_dependency_action.source_path
                or source_dependency_event.target_path != source_dependency_action.target_path
                or source_dependency_event.companion_asset_id is not None
            ):
                return False
            inverse_dependency_action = inverse_actions_by_event_id.get(source_dependency_event.event_id)
            if inverse_dependency_action is None:
                if source_dependency_event.event_id not in durably_reversed_event_ids:
                    return False
                continue
            if (
                inverse_dependency_action.plan_id != plan.plan_id
                or inverse_dependency_action.library_id != plan.library_id
                or inverse_dependency_action.action_type is not ActionType.MOVE
                or inverse_dependency_action.track_id != source_dependency_action.track_id
            ):
                return False
            inverse_dependencies = inverse_dependencies_by_action_id[inverse_dependency_action.action_id]
            if not any(
                inverse_dependency.plan_id == plan.plan_id
                and inverse_dependency.action_id == inverse_dependency_action.action_id
                and inverse_dependency.depends_on_action_id == action.action_id
                for inverse_dependency in inverse_dependencies
            ):
                return False

        if PurePath(action.target_path).is_absolute():
            return (
                source_plan.plan_type is PlanType.ADD
                and plan.source_root_at_plan is not None
                and PurePath(plan.source_root_at_plan).is_absolute()
                and _path_is_within_root(action.target_path, plan.source_root_at_plan)
            )
        return not PurePath(action.source_path).is_absolute()

    def _unprocessed_move_is_verified(self, plan: Plan, action: PlanAction) -> bool:  # noqa: PLR0911  # Durable provenance fails closed at each boundary.
        """Authorize only exact recorded collection layouts and their proven inverse."""
        source_root = plan.source_root_at_plan
        if (
            source_root is None
            or action.plan_id != plan.plan_id
            or action.library_id != plan.library_id
            or action.action_type is not ActionType.MOVE_UNPROCESSED
            or action.status is not ActionStatus.PLANNED
            or action.reason is not None
            or action.track_id is not None
            or action.source_path is None
            or action.target_path is None
            or action.content_hash_at_plan is None
            or action.metadata_hash_at_plan is not None
            or action.artist_name_diagnostics is not None
            or action.companion_asset_id is not None
            or action.owner_action_id is not None
        ):
            return False

        with self.ports.uow as uow:
            action_dependencies = tuple(uow.plan_action_dependencies.list_by_action(action.action_id))
            if action_dependencies:
                return False
            if plan.plan_type is PlanType.ADD:
                return (
                    plan.source_run_id is None
                    and action.reverses_event_id is None
                    and validate_unprocessed_path_layout(
                        source_root,
                        action.source_path,
                        action.target_path,
                        excluded_root=plan.library_root_at_plan,
                    )
                    is not None
                )
            if plan.plan_type is not PlanType.UNDO or plan.source_run_id is None or action.reverses_event_id is None:
                return False

            event = uow.file_events.get(action.reverses_event_id)
            source_run = uow.runs.get(plan.source_run_id)
            if event is None or source_run is None:
                return False
            source_action = uow.plan_actions.get(event.plan_action_id)
            if source_action is None:
                return False
            source_plan = uow.plans.get(source_action.plan_id)
            if source_plan is None:
                return False
            source_dependencies = tuple(uow.plan_action_dependencies.list_by_action(source_action.action_id))
            source_action_event_count = sum(
                source_event.plan_action_id == source_action.action_id
                for source_event in uow.file_events.list_by_run(source_run.run_id)
            )
            reversed_event_ids = _durably_reversed_source_event_ids(
                uow,
                source_run.run_id,
                excluding_plan_id=plan.plan_id,
            )

        event_completed_at = event.completed_at
        run_completed_at = source_run.completed_at
        return (
            not source_dependencies
            and event.event_id not in reversed_event_ids
            and event_completed_at is not None
            and run_completed_at is not None
            and source_plan.plan_type is PlanType.ADD
            and source_plan.source_run_id is None
            and source_plan.status in {PlanStatus.APPLIED, PlanStatus.PARTIAL_FAILED, PlanStatus.FAILED}
            and source_plan.library_id == plan.library_id
            and source_plan.source_root_at_plan == source_root
            and source_plan.config_hash == plan.config_hash
            and source_run.plan_id == source_plan.plan_id
            and source_run.library_id == plan.library_id
            and source_run.status in {RunStatus.SUCCEEDED, RunStatus.PARTIAL_FAILED, RunStatus.FAILED}
            and source_plan.created_at <= source_run.started_at
            and source_run.started_at <= event.started_at <= event_completed_at
            and event_completed_at <= run_completed_at <= plan.created_at
            and event.run_id == source_run.run_id == plan.source_run_id
            and event.library_id == plan.library_id
            and event.plan_action_id == source_action.action_id
            and event.event_type is FileEventType.MOVE_UNPROCESSED_FILE
            and event.status is FileEventStatus.SUCCEEDED
            and event.source_path == source_action.source_path == action.target_path
            and event.target_path == source_action.target_path == action.source_path
            and event.companion_asset_id is None
            and source_action.plan_id == source_plan.plan_id
            and source_action.library_id == plan.library_id
            and source_action.action_type is ActionType.MOVE_UNPROCESSED
            and source_action.status is ActionStatus.APPLIED
            and source_action.reason is None
            and source_action.track_id is None
            and source_action.content_hash_at_plan is not None
            and action.content_hash_at_plan == source_action.content_hash_at_plan
            and source_action.metadata_hash_at_plan is None
            and source_action.reverses_event_id is None
            and source_action.artist_name_diagnostics is None
            and source_action.companion_asset_id is None
            and source_action.owner_action_id is None
            and source_action_event_count == 1
            and validate_unprocessed_path_layout(
                source_root,
                source_action.source_path or "",
                source_action.target_path or "",
                excluded_root=source_plan.library_root_at_plan,
            )
            is not None
        )

    def _verify_source_preconditions(
        self,
        action: PlanAction,
        source_filesystem_path: FileSystemPath,
    ) -> _SourcePreconditionResult:
        try:
            snapshot = self.ports.file_snapshot_reader.capture(source_filesystem_path)
        except FileNotFoundError:
            return _SourcePreconditionResult.failed(PlanActionReason.SOURCE_MISSING)
        except OSError, ValueError:
            return _SourcePreconditionResult.failed(PlanActionReason.SOURCE_CHANGED)

        if action.content_hash_at_plan is None or snapshot.content_hash != action.content_hash_at_plan:
            return _SourcePreconditionResult.failed(PlanActionReason.SOURCE_CHANGED)
        if action.metadata_hash_at_plan is None or snapshot.metadata_hash != action.metadata_hash_at_plan:
            return _SourcePreconditionResult.failed(PlanActionReason.SOURCE_CHANGED)
        if snapshot.filesystem_identity is None:
            return _SourcePreconditionResult.failed(PlanActionReason.SOURCE_CHANGED)

        return _SourcePreconditionResult.passed_with(snapshot)

    def _dependencies_are_applied(self, action: PlanAction) -> bool:
        """Require every recorded dependency before any filesystem observation."""
        with self.ports.uow as uow:
            dependencies = tuple(uow.plan_action_dependencies.list_by_action(action.action_id))
            dependency_ids = tuple(dependency.depends_on_action_id for dependency in dependencies)
            dependency_actions = tuple(uow.plan_actions.list_by_ids(dependency_ids))
            dependency_actions_by_id = {dependency.action_id: dependency for dependency in dependency_actions}
        return len(dependency_actions_by_id) == len(dependency_ids) and all(
            dependency.plan_id == action.plan_id
            and dependency.action_id == action.action_id
            and (dependency_action := dependency_actions_by_id.get(dependency.depends_on_action_id)) is not None
            and dependency_action.plan_id == action.plan_id
            and dependency_action.library_id == action.library_id
            and dependency_action.status is ActionStatus.APPLIED
            for dependency in dependencies
        )

    def _load_companion_context(self, plan: Plan, action: PlanAction) -> _CompanionContextResult:
        """Resolve semantic ownership independently from execution dependencies."""
        with self.ports.uow as uow:
            owner_track_id = action.track_id
            if action.owner_action_id is not None:
                owner_action = uow.plan_actions.get(action.owner_action_id)
                owner_status_is_valid = owner_action is not None and (
                    (
                        plan.plan_type is PlanType.UNDO
                        and owner_action.status in {ActionStatus.PLANNED, ActionStatus.BLOCKED}
                    )
                    or (plan.plan_type is not PlanType.UNDO and owner_action.status is ActionStatus.APPLIED)
                )
                owner_track_id = (
                    owner_action.track_id
                    if owner_action is not None
                    and owner_status_is_valid
                    and owner_action.plan_id == action.plan_id == plan.plan_id
                    and owner_action.library_id == action.library_id == plan.library_id
                    and owner_action.action_type is ActionType.MOVE
                    and owner_action.track_id is not None
                    and (action.track_id is None or action.track_id == owner_action.track_id)
                    else None
                )
            if owner_track_id is None:
                return _CompanionContextResult.failed(
                    PlanActionReason.COMPANION_DEPENDENCY_FAILED,
                    COMPANION_DEPENDENCY_FAILED_SUMMARY,
                )

            if plan.plan_type is not PlanType.UNDO and action.owner_action_id is not None:
                dependencies = tuple(uow.plan_action_dependencies.list_by_action(action.action_id))
                if action.owner_action_id not in {dependency.depends_on_action_id for dependency in dependencies}:
                    return _CompanionContextResult.failed(
                        PlanActionReason.COMPANION_DEPENDENCY_FAILED,
                        COMPANION_DEPENDENCY_FAILED_SUMMARY,
                    )

            owner_track = uow.tracks.get(owner_track_id)
            if action.companion_asset_id is None:
                raise AssertionError(COMPANION_ASSET_ID_MISSING_SUMMARY)
            existing_asset = uow.companion_assets.get(action.companion_asset_id)

        removed_owner_is_verified = (
            owner_track is not None
            and owner_track.status is TrackStatus.REMOVED
            and plan.plan_type is PlanType.UNDO
            and action.owner_action_id is None
            and self._companion_undo_is_verified(plan, action)
        )
        if (
            owner_track is None
            or owner_track.library_id != action.library_id
            or (owner_track.status is not TrackStatus.ACTIVE and not removed_owner_is_verified)
        ):
            return _CompanionContextResult.failed(
                PlanActionReason.COMPANION_DEPENDENCY_FAILED,
                COMPANION_DEPENDENCY_FAILED_SUMMARY,
            )

        if plan.plan_type is PlanType.UNDO and existing_asset is None:
            return _CompanionContextResult.failed(
                PlanActionReason.SOURCE_CHANGED,
                COMPANION_STATE_CHANGED_SUMMARY,
            )
        if existing_asset is not None and (
            existing_asset.library_id != action.library_id
            or existing_asset.kind is not _companion_asset_kind(action.action_type)
            or existing_asset.owner_track_id != owner_track_id
            or existing_asset.status is not CompanionAssetStatus.ACTIVE
            or existing_asset.current_path != action.source_path
        ):
            return _CompanionContextResult.failed(
                PlanActionReason.SOURCE_CHANGED,
                COMPANION_STATE_CHANGED_SUMMARY,
            )
        return _CompanionContextResult.passed_with(
            _CompanionContext(owner_track_id=owner_track_id, existing_asset=existing_asset)
        )

    def _verify_content_source_preconditions(
        self,
        action: PlanAction,
        source_filesystem_path: FileSystemPath,
        *,
        root: FileSystemPath,
    ) -> _CompanionSourcePreconditionResult:
        try:
            snapshot = self.ports.file_content_snapshot_reader.capture(source_filesystem_path, root=root)
        except FileNotFoundError:
            return _CompanionSourcePreconditionResult.failed(PlanActionReason.SOURCE_MISSING)
        except FileObservationChangedError, OSError:
            return _CompanionSourcePreconditionResult.failed(PlanActionReason.SOURCE_CHANGED)
        except FileObservationInvalidPathError, ValueError:
            return _CompanionSourcePreconditionResult.failed(PlanActionReason.INVALID_PATH)

        if action.content_hash_at_plan is None or snapshot.content_hash != action.content_hash_at_plan:
            return _CompanionSourcePreconditionResult.failed(PlanActionReason.SOURCE_CHANGED)
        return _CompanionSourcePreconditionResult.passed_with(snapshot)

    def _record_pending_file_event(
        self,
        *,
        run: Run,
        action: PlanAction,
        source_path: str,
        target_path: str,
        sequence_no: int,
    ) -> FileEvent:
        event = FileEvent(
            event_id=self.ports.id_generator.new_event_id(),
            library_id=run.library_id,
            run_id=run.run_id,
            plan_action_id=action.action_id,
            event_type=_file_event_type(action.action_type),
            source_path=source_path,
            target_path=target_path,
            status=FileEventStatus.PENDING,
            started_at=self.ports.clock.now(),
            completed_at=None,
            error_code=None,
            error_message=None,
            sequence_no=sequence_no,
            companion_asset_id=action.companion_asset_id,
        )

        with self.ports.uow as uow:
            uow.file_events.save(event)
            uow.commit()

        return event

    def _record_successful_move(
        self,
        event: FileEvent,
        action: PlanAction,
        snapshot: FileSnapshot,
        target_path: str,
    ) -> None:
        timestamp = self.ports.clock.now()
        with self.ports.uow as uow:
            track = self._track_after_success(uow, action, snapshot, target_path, timestamp)
            action_with_track = replace(action, track_id=track.track_id)
            uow.file_events.save(event.mark_succeeded(timestamp))
            uow.tracks.save(track)
            uow.plan_actions.save(action_with_track.mark_applied())
            uow.commit()

    def _record_successful_companion_move(
        self,
        event: FileEvent,
        action: PlanAction,
        snapshot: FileContentSnapshot,
        target_path: str,
        context: _CompanionContext,
    ) -> None:
        timestamp = self.ports.clock.now()
        companion_asset_id = action.companion_asset_id
        if companion_asset_id is None:
            raise AssertionError(COMPANION_ASSET_ID_MISSING_SUMMARY)
        existing_asset = context.existing_asset
        restores_external_source = PurePath(target_path).is_absolute()
        if restores_external_source and existing_asset is None:
            raise AssertionError(COMPANION_STATE_CHANGED_SUMMARY)
        managed_source_path = action.source_path
        if managed_source_path is None:
            raise AssertionError(INCOMPLETE_MOVE_ACTION_SUMMARY)
        companion_asset = CompanionAsset(
            companion_asset_id=companion_asset_id,
            library_id=action.library_id,
            kind=_companion_asset_kind(action.action_type),
            owner_track_id=context.owner_track_id,
            current_path=managed_source_path if restores_external_source else target_path,
            canonical_path=(
                existing_asset.canonical_path
                if restores_external_source and existing_asset is not None
                else target_path
            ),
            content_hash=snapshot.content_hash,
            size=snapshot.size,
            mtime=snapshot.mtime,
            status=CompanionAssetStatus.REMOVED if restores_external_source else CompanionAssetStatus.ACTIVE,
            first_seen_at=timestamp if existing_asset is None else existing_asset.first_seen_at,
            last_seen_at=timestamp,
            updated_at=timestamp,
        )
        action_with_owner = replace(action, track_id=context.owner_track_id)
        with self.ports.uow as uow:
            uow.file_events.save(event.mark_succeeded(timestamp))
            uow.companion_assets.save(companion_asset)
            uow.plan_actions.save(action_with_owner.mark_applied())
            uow.commit()

    def _record_successful_unprocessed_move(
        self,
        event: FileEvent,
        action: PlanAction,
    ) -> None:
        """Commit confirmed unprocessed mutation evidence without managed-file state."""
        timestamp = self.ports.clock.now()
        with self.ports.uow as uow:
            uow.file_events.save(event.mark_succeeded(timestamp))
            uow.plan_actions.save(action.mark_applied())
            uow.commit()

    def _record_successful_metadata_refresh(
        self,
        action: PlanAction,
        snapshot: FileSnapshot,
        target_path: str,
    ) -> None:
        timestamp = self.ports.clock.now()
        with self.ports.uow as uow:
            uow.plan_actions.save(action.mark_applied())
            uow.tracks.save(self._track_after_success(uow, action, snapshot, target_path, timestamp))
            uow.commit()

    def _record_failed_file_event(
        self,
        event: FileEvent,
        action: PlanAction,
        reason: PlanActionReason | None,
        error_message: str,
    ) -> None:
        timestamp = self.ports.clock.now()
        error_code = MOVE_FAILED_ERROR_CODE if reason is None else reason.value
        with self.ports.uow as uow:
            uow.file_events.save(event.mark_failed(timestamp, error_code, error_message))
            uow.plan_actions.save(action.mark_failed(reason))
            uow.commit()

    def _track_after_success(
        self,
        uow: UnitOfWork,
        action: PlanAction,
        snapshot: FileSnapshot,
        target_path: str,
        timestamp: datetime,
    ) -> Track:
        existing_track = None if action.track_id is None else uow.tracks.get(action.track_id)
        track_id = self.ports.id_generator.new_track_id() if action.track_id is None else action.track_id
        if PurePath(target_path).is_absolute():
            if existing_track is None or action.source_path is None:
                raise AssertionError(EXTERNAL_RESTORE_WITHOUT_TRACK_SUMMARY)
            return Track(
                track_id=track_id,
                library_id=action.library_id,
                current_path=action.source_path,
                canonical_path=existing_track.canonical_path,
                content_hash=snapshot.content_hash,
                metadata_hash=snapshot.metadata_hash,
                size=snapshot.size,
                mtime=snapshot.mtime,
                metadata=snapshot.metadata,
                status=TrackStatus.REMOVED,
                first_seen_at=existing_track.first_seen_at,
                last_seen_at=timestamp,
                updated_at=timestamp,
            )

        return Track(
            track_id=track_id,
            library_id=action.library_id,
            current_path=target_path,
            canonical_path=target_path,
            content_hash=snapshot.content_hash,
            metadata_hash=snapshot.metadata_hash,
            size=snapshot.size,
            mtime=snapshot.mtime,
            metadata=snapshot.metadata,
            status=TrackStatus.ACTIVE,
            first_seen_at=timestamp if existing_track is None else existing_track.first_seen_at,
            last_seen_at=timestamp,
            updated_at=timestamp,
        )

    def _mark_action_applied(self, action: PlanAction) -> None:
        with self.ports.uow as uow:
            uow.plan_actions.save(action.mark_applied())
            uow.commit()

    def _mark_action_failed(self, action: PlanAction, reason: PlanActionReason | None = None) -> None:
        with self.ports.uow as uow:
            uow.plan_actions.save(action.mark_failed(reason))
            uow.commit()

    def _finish_apply(
        self,
        plan: Plan,
        run: Run,
        completion: _ApplyCompletion,
        operation_id: OperationId,
    ) -> Run:
        timestamp = self.ports.clock.now()
        error_summary = _combined_failure_summary(completion.failure_summaries)

        if completion.failure_count == 0:
            final_run = run.mark_succeeded(timestamp)
            final_plan = plan.mark_applied()
        elif completion.success_count > 0:
            final_run = run.mark_partial_failed(timestamp, error_summary)
            final_plan = plan.mark_partial_failed()
        else:
            final_run = run.mark_failed(timestamp, error_summary)
            final_plan = plan.mark_failed()

        with self.ports.uow as uow:
            uow.runs.save(final_run)
            uow.plans.save(final_plan)
            if final_plan.status == PlanStatus.APPLIED:
                self._register_successful_organize_plan(uow, final_plan, timestamp)
            operation = uow.operations.lookup(operation_id)
            if not isinstance(operation, Operation) or operation.status is not OperationStatus.RUNNING:
                raise ApplyPlanError(CLAIMED_APPLY_STATE_INVALID_MESSAGE)
            if completion.operation_failed:
                uow.operations.save(
                    operation.mark_failed(
                        error=OperationError(
                            code=OperationErrorCode.OPERATION_FAILED,
                            message=LIBRARY_ROOT_CHANGED_SUMMARY,
                            retryable=False,
                        ),
                        completed_at=timestamp,
                        result_expires_at=timestamp + timedelta(hours=OPERATION_RESULT_RETENTION_HOURS),
                        tombstone_expires_at=timestamp + timedelta(days=OPERATION_TOMBSTONE_RETENTION_DAYS),
                    )
                )
            else:
                uow.operations.save(
                    operation.mark_succeeded(
                        result=RunCompletedResult(final_run.run_id),
                        completed_at=timestamp,
                        result_expires_at=timestamp + timedelta(hours=OPERATION_RESULT_RETENTION_HOURS),
                        tombstone_expires_at=timestamp + timedelta(days=OPERATION_TOMBSTONE_RETENTION_DAYS),
                    )
                )
            uow.commit()

        return final_run

    def _register_successful_organize_plan(self, uow: UnitOfWork, plan: Plan, timestamp: datetime) -> None:
        if plan.plan_type != PlanType.ORGANIZE:
            return

        actions = uow.plan_actions.list_by_plan(plan.plan_id)
        if any(action.status == ActionStatus.BLOCKED for action in actions):
            return

        library = uow.libraries.get(plan.library_id)
        if library is None:
            return

        uow.libraries.save(
            Library(
                library_id=library.library_id,
                root_path=library.root_path,
                path_policy_hash=library.path_policy_hash,
                registered_at=timestamp,
                status=LibraryStatus.REGISTERED,
                created_at=library.created_at,
                updated_at=timestamp,
            )
        )

    def _library_root_still_matches(self, plan: Plan) -> bool:
        with self.ports.uow as uow:
            current_library = uow.libraries.get(plan.library_id)
            return current_library is not None and current_library.root_path == plan.library_root_at_plan

    def _resolve_source_path(self, library: Library, source_path: str) -> FileSystemPath:
        if PurePath(source_path).is_absolute():
            return source_path
        return self.ports.path_resolver.resolve_library_path(library.root_path, source_path)

    def _resolve_target_path(self, library: Library, target_path: str) -> FileSystemPath:
        if PurePath(target_path).is_absolute():
            return target_path
        return self.ports.path_resolver.resolve_library_path(library.root_path, target_path)


@dataclass(frozen=True, slots=True)
class _StartedApply:
    """State captured after apply has created a Run."""

    plan: Plan
    library: Library
    run: Run
    actions: tuple[PlanAction, ...]


@dataclass(frozen=True, slots=True)
class _ApplyCompletion:
    """Confirmed action evidence used for one terminal Apply transaction."""

    success_count: int
    failure_count: int
    failure_summaries: tuple[str, ...]
    operation_failed: bool


@dataclass(frozen=True, slots=True)
class _ActionApplyResult:
    """Outcome for one eligible move action."""

    succeeded: bool
    event_created: bool
    failure_summary: str
    should_stop: bool = False

    @classmethod
    def root_changed(cls) -> _ActionApplyResult:
        return cls(
            succeeded=False,
            event_created=False,
            failure_summary=LIBRARY_ROOT_CHANGED_SUMMARY,
            should_stop=True,
        )


@dataclass(frozen=True, slots=True)
class _CompanionMoveInput:
    """Validated paths and immutable roots for one companion mutation."""

    source_path: str
    target_path: str
    source_root: FileSystemPath
    target_root: FileSystemPath


@dataclass(frozen=True, slots=True)
class _CompanionMoveInputResult:
    """Structural companion validation result before dependency loading."""

    move_input: _CompanionMoveInput | None
    reason: PlanActionReason | None
    failure_summary: str

    @classmethod
    def passed_with(cls, move_input: _CompanionMoveInput) -> _CompanionMoveInputResult:
        """Return a structurally valid companion mutation input."""
        return cls(move_input=move_input, reason=None, failure_summary="")

    @classmethod
    def failed(cls, reason: PlanActionReason | None, failure_summary: str) -> _CompanionMoveInputResult:
        """Return a structural failure that forbids event creation and mutation."""
        return cls(move_input=None, reason=reason, failure_summary=failure_summary)


@dataclass(frozen=True, slots=True)
class _CompanionMoveExecution:
    """Verified state passed to the mutation-and-recording boundary."""

    event: FileEvent
    action: PlanAction
    source_filesystem_path: FileSystemPath
    target_filesystem_path: FileSystemPath
    move_input: _CompanionMoveInput
    target_root: FileSystemPath
    snapshot: FileContentSnapshot | None
    context: _CompanionContext


@dataclass(frozen=True, slots=True)
class _CompanionContext:
    """Durable asset and owner state verified before companion mutation."""

    owner_track_id: TrackId
    existing_asset: CompanionAsset | None


@dataclass(frozen=True, slots=True)
class _CompanionContextResult:
    """Dependency and managed-state outcome before filesystem observation."""

    context: _CompanionContext | None
    reason: PlanActionReason | None
    failure_summary: str

    @classmethod
    def passed_with(cls, context: _CompanionContext) -> _CompanionContextResult:
        """Return verified dependency, ownership, and existing-asset state."""
        return cls(context=context, reason=None, failure_summary="")

    @classmethod
    def failed(cls, reason: PlanActionReason | None, failure_summary: str) -> _CompanionContextResult:
        """Return a failed companion context without authorizing mutation."""
        return cls(context=None, reason=reason, failure_summary=failure_summary)


@dataclass(frozen=True, slots=True)
class _SourcePreconditionResult:
    """Source verification outcome before any mutation event is created."""

    passed: bool
    snapshot: FileSnapshot | None
    reason: PlanActionReason | None
    failure_summary: str

    @classmethod
    def passed_with(cls, snapshot: FileSnapshot) -> _SourcePreconditionResult:
        """Return a successful precondition result with the observed source."""
        return cls(passed=True, snapshot=snapshot, reason=None, failure_summary="")

    @classmethod
    def failed(cls, reason: PlanActionReason) -> _SourcePreconditionResult:
        """Return a failed precondition result with a domain reason."""
        return cls(passed=False, snapshot=None, reason=reason, failure_summary=reason.value)


@dataclass(frozen=True, slots=True)
class _CompanionSourcePreconditionResult:
    """Metadata-free companion source verification before event creation."""

    passed: bool
    snapshot: FileContentSnapshot | None
    reason: PlanActionReason | None
    failure_summary: str

    @classmethod
    def passed_with(cls, snapshot: FileContentSnapshot) -> _CompanionSourcePreconditionResult:
        """Return a successful companion source result with live identity."""
        return cls(passed=True, snapshot=snapshot, reason=None, failure_summary="")

    @classmethod
    def failed(cls, reason: PlanActionReason) -> _CompanionSourcePreconditionResult:
        """Return a failed companion source result without mutation evidence."""
        return cls(passed=False, snapshot=None, reason=reason, failure_summary=reason.value)


class ApplyPlanError(ValueError):
    """Raised when apply cannot safely start or complete."""


class PlanNotFoundError(ApplyPlanError):
    """Raised when a requested Plan does not exist."""


class PlanCannotBeAppliedError(ApplyPlanError):
    """Raised when a Plan is no longer in the ready state."""


class ApplyNotConfirmedError(ApplyPlanError):
    """Raised when apply is requested without confirmation."""


def _durably_reversed_source_event_ids(
    uow: UnitOfWork,
    source_run_id: RunId,
    *,
    excluding_plan_id: PlanId,
) -> frozenset[EventId]:
    reversed_event_ids: set[EventId] = set()
    for prior_plan in uow.plans.list_by_source_run(source_run_id):
        if prior_plan.plan_id == excluding_plan_id:
            continue
        prior_actions = {
            prior_action.action_id: prior_action for prior_action in uow.plan_actions.list_by_plan(prior_plan.plan_id)
        }
        for prior_run in uow.runs.list_by_plan(prior_plan.plan_id):
            for prior_event in uow.file_events.list_by_run(prior_run.run_id):
                prior_action = prior_actions.get(prior_event.plan_action_id)
                if (
                    prior_event.status is FileEventStatus.SUCCEEDED
                    and prior_event.library_id == prior_plan.library_id
                    and prior_action is not None
                    and prior_action.plan_id == prior_plan.plan_id
                    and prior_action.library_id == prior_plan.library_id
                    and prior_action.reverses_event_id is not None
                ):
                    reversed_event_ids.add(prior_action.reverses_event_id)
    return frozenset(reversed_event_ids)


def _path_is_within_root(path: str, root: str) -> bool:
    normalized_path = Path(os.path.abspath(Path(path).expanduser()))  # noqa: PTH100  # Lexical only; do not follow links.
    normalized_root = Path(os.path.abspath(Path(root).expanduser()))  # noqa: PTH100  # Match Add root normalization.
    try:
        _ = normalized_path.relative_to(normalized_root)
    except ValueError:
        return False
    return True


def _move_failure_reason(exc: OSError | ValueError) -> PlanActionReason | None:
    if isinstance(exc, FileExistsError):
        return PlanActionReason.TARGET_EXISTS
    if isinstance(exc, FileNotFoundError):
        return PlanActionReason.SOURCE_MISSING
    if isinstance(exc, ValueError):
        return PlanActionReason.INVALID_PATH
    return None


def _companion_asset_kind(action_type: ActionType) -> CompanionAssetKind:
    if action_type is ActionType.MOVE_LYRICS:
        return CompanionAssetKind.LYRICS
    if action_type is ActionType.MOVE_ARTWORK:
        return CompanionAssetKind.ARTWORK
    raise AssertionError(action_type)


def _file_event_type(action_type: ActionType) -> FileEventType:
    if action_type is ActionType.MOVE:
        return FileEventType.MOVE_FILE
    if action_type is ActionType.MOVE_LYRICS:
        return FileEventType.MOVE_LYRICS_FILE
    if action_type is ActionType.MOVE_ARTWORK:
        return FileEventType.MOVE_ARTWORK_FILE
    if action_type is ActionType.MOVE_UNPROCESSED:
        return FileEventType.MOVE_UNPROCESSED_FILE
    raise AssertionError(action_type)


def _require_confirmed(request: ApplyPlanRequest) -> None:
    if not request.options.yes:
        raise ApplyNotConfirmedError(APPLY_NOT_CONFIRMED_MESSAGE)


def _move_failure_message(reason: PlanActionReason | None) -> str:
    if reason is PlanActionReason.TARGET_EXISTS:
        return TARGET_EXISTS_MOVE_FAILURE_MESSAGE
    if reason is PlanActionReason.SOURCE_MISSING:
        return SOURCE_MISSING_MOVE_FAILURE_MESSAGE
    if reason is PlanActionReason.INVALID_PATH:
        return INVALID_PATH_MOVE_FAILURE_MESSAGE
    return MOVE_FAILED_MESSAGE


def _combined_failure_summary(failure_summaries: tuple[str, ...]) -> str:
    meaningful_summaries = tuple(summary for summary in failure_summaries if summary != "")
    if len(meaningful_summaries) == 0:
        return APPLY_FAILED_SUMMARY
    return SUMMARY_SEPARATOR.join(meaningful_summaries)
