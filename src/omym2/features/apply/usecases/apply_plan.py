"""
Summary: Applies reviewed Plans through durable operation logs.
Why: Mutates Library files only after recorded PlanActions and FileEvents exist.
"""

from __future__ import annotations

from dataclasses import dataclass, replace
from pathlib import PurePath
from typing import TYPE_CHECKING

from omym2.config import FILE_EVENT_SEQUENCE_START, FILE_EVENT_SEQUENCE_STEP
from omym2.domain.models.file_event import FileEvent, FileEventStatus, FileEventType
from omym2.domain.models.library import Library, LibraryStatus
from omym2.domain.models.plan import Plan, PlanStatus, PlanType
from omym2.domain.models.plan_action import ActionStatus, ActionType, PlanAction, PlanActionReason
from omym2.domain.models.run import Run, RunStatus
from omym2.domain.models.track import Track, TrackStatus

if TYPE_CHECKING:
    from datetime import datetime

    from omym2.domain.models.file_snapshot import FileSnapshot
    from omym2.features.apply.dto import ApplyPlanRequest
    from omym2.features.apply.ports import ApplyPlanPorts
    from omym2.features.common_ports import FileSystemPath, UnitOfWork
    from omym2.shared.ids import PlanId

APPLY_FAILED_SUMMARY = "Apply failed."
APPLY_NOT_CONFIRMED_MESSAGE = "Apply was not confirmed."
INCOMPLETE_MOVE_ACTION_SUMMARY = "Planned move action is missing source or target path."
EXTERNAL_RESTORE_WITHOUT_TRACK_SUMMARY = "External restore action is missing a managed Track ID."
INVALID_EXTERNAL_RESTORE_SUMMARY = "External restore action is not backed by durable undo history."
LIBRARY_NOT_FOUND_MESSAGE = "Plan Library was not found."
LIBRARY_ROOT_CHANGED_SUMMARY = "Library root changed during apply."
MOVE_FAILED_ERROR_CODE = "move_failed"
PLAN_NOT_FOUND_MESSAGE = "Plan was not found."
PLAN_NOT_READY_MESSAGE = "Plan is not ready and cannot be applied."
SUMMARY_SEPARATOR = "; "
SOURCE_PRECONDITION_SNAPSHOT_MISSING_MESSAGE = "Successful source precondition did not return a snapshot."


@dataclass(frozen=True, slots=True)
class ApplyPlanUseCase:
    """Apply reviewed Plans using recorded actions and durable FileEvents."""

    ports: ApplyPlanPorts

    def execute(self, request: ApplyPlanRequest) -> Run | None:
        """Apply a reviewed Plan and return its Run when one is created."""
        _require_confirmed(request)

        started_apply = self._start_apply(request.plan_id)
        if started_apply is None:
            return None

        move_success_count = 0
        move_failure_count = 0
        failure_summaries: list[str] = []
        sequence_no = FILE_EVENT_SEQUENCE_START

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
                    break

        return self._finish_apply(
            started_apply.plan,
            started_apply.run,
            move_success_count,
            move_failure_count,
            tuple(failure_summaries),
        )

    def _process_filesystem_observing_action(
        self,
        started_apply: _StartedApply,
        action: PlanAction,
        sequence_no: int,
    ) -> _ActionApplyResult | None:
        if action.action_type not in {ActionType.MOVE, ActionType.REFRESH_METADATA}:
            return None

        if not self._library_root_still_matches(started_apply.library):
            return _ActionApplyResult.root_changed()

        if action.action_type == ActionType.REFRESH_METADATA:
            return self._process_metadata_refresh_action(started_apply.library, action)

        return self._process_move_action(
            started_apply.run, started_apply.plan, started_apply.library, action, sequence_no
        )

    def _start_apply(self, plan_id: PlanId) -> _StartedApply | None:
        with self.ports.uow as uow:
            plan = uow.plans.get(plan_id)
            if plan is None:
                raise PlanNotFoundError(PLAN_NOT_FOUND_MESSAGE)
            if plan.status != PlanStatus.READY:
                raise PlanCannotBeAppliedError(PLAN_NOT_READY_MESSAGE)

            library = uow.libraries.get(plan.library_id)
            if library is None:
                raise ApplyPlanError(LIBRARY_NOT_FOUND_MESSAGE)

            if library.root_path != plan.library_root_at_plan:
                uow.plans.save(plan.mark_expired())
                uow.commit()
                return None

            run = Run(
                run_id=self.ports.id_generator.new_run_id(),
                plan_id=plan.plan_id,
                library_id=plan.library_id,
                status=RunStatus.RUNNING,
                started_at=self.ports.clock.now(),
            )
            applying_plan = plan.mark_applying()
            actions = tuple(uow.plan_actions.list_by_plan(plan.plan_id))

            uow.runs.save(run)
            uow.plans.save(applying_plan)
            uow.commit()

            return _StartedApply(plan=applying_plan, library=library, run=run, actions=actions)

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
        if PurePath(target_path).is_absolute() and not self._absolute_target_is_verified_undo(plan, action):
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
            self.ports.file_mover.move(source_filesystem_path, target_filesystem_path)
        except OSError as exc:
            reason = _move_failure_reason(exc)
            self._record_failed_file_event(event, action, reason, exc)
            return _ActionApplyResult(
                succeeded=False,
                event_created=True,
                failure_summary=_failure_summary(exc),
            )

        snapshot = precondition.snapshot
        if snapshot is None:
            raise AssertionError(SOURCE_PRECONDITION_SNAPSHOT_MISSING_MESSAGE)

        self._record_successful_move(event, action, snapshot, target_path)
        return _ActionApplyResult(succeeded=True, event_created=True, failure_summary="")

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
        """Return whether an absolute target is backed by prior add history."""
        if plan.plan_type != PlanType.UNDO or action.track_id is None:
            return False
        if action.source_path is None or action.target_path is None:
            return False
        if not PurePath(action.target_path).is_absolute():
            return True

        with self.ports.uow as uow:
            # Absolute undo restores are only safe when they exactly reverse a
            # succeeded event whose source action imported an external file.
            for event in uow.file_events.list_by_library(action.library_id):
                if event.status != FileEventStatus.SUCCEEDED:
                    continue
                if event.source_path != action.target_path or event.target_path != action.source_path:
                    continue
                source_action = uow.plan_actions.get(event.plan_action_id)
                if source_action is None:
                    continue
                source_plan = uow.plans.get(source_action.plan_id)
                if (
                    source_plan is not None
                    and source_plan.plan_type == PlanType.ADD
                    and source_action.track_id == action.track_id
                    and source_action.source_path == event.source_path
                    and source_action.target_path == event.target_path
                    and PurePath(source_action.source_path or "").is_absolute()
                    and not PurePath(source_action.target_path or "").is_absolute()
                ):
                    return True
        return False

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

        if action.content_hash_at_plan is not None and snapshot.content_hash != action.content_hash_at_plan:
            return _SourcePreconditionResult.failed(PlanActionReason.SOURCE_CHANGED)
        if action.metadata_hash_at_plan is not None and snapshot.metadata_hash != action.metadata_hash_at_plan:
            return _SourcePreconditionResult.failed(PlanActionReason.SOURCE_CHANGED)

        return _SourcePreconditionResult.passed_with(snapshot)

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
            event_type=FileEventType.MOVE_FILE,
            source_path=source_path,
            target_path=target_path,
            status=FileEventStatus.PENDING,
            started_at=self.ports.clock.now(),
            completed_at=None,
            error_code=None,
            error_message=None,
            sequence_no=sequence_no,
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
        exc: OSError,
    ) -> None:
        timestamp = self.ports.clock.now()
        error_code = MOVE_FAILED_ERROR_CODE if reason is None else reason.value
        with self.ports.uow as uow:
            uow.file_events.save(event.mark_failed(timestamp, error_code, _failure_summary(exc)))
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
        move_success_count: int,
        move_failure_count: int,
        failure_summaries: tuple[str, ...],
    ) -> Run:
        timestamp = self.ports.clock.now()
        error_summary = _combined_failure_summary(failure_summaries)

        if move_failure_count == 0:
            final_run = run.mark_succeeded(timestamp)
            final_plan = plan.mark_applied()
        elif move_success_count > 0:
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

    def _library_root_still_matches(self, library: Library) -> bool:
        with self.ports.uow as uow:
            current_library = uow.libraries.get(library.library_id)
            return current_library is not None and current_library.root_path == library.root_path

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


class ApplyPlanError(ValueError):
    """Raised when apply cannot safely start or complete."""


class PlanNotFoundError(ApplyPlanError):
    """Raised when a requested Plan does not exist."""


class PlanCannotBeAppliedError(ApplyPlanError):
    """Raised when a Plan is no longer in the ready state."""


class ApplyNotConfirmedError(ApplyPlanError):
    """Raised when apply is requested without confirmation."""


def _move_failure_reason(exc: OSError) -> PlanActionReason | None:
    if isinstance(exc, FileExistsError):
        return PlanActionReason.TARGET_EXISTS
    if isinstance(exc, FileNotFoundError):
        return PlanActionReason.SOURCE_MISSING
    return None


def _require_confirmed(request: ApplyPlanRequest) -> None:
    if not request.options.yes:
        raise ApplyNotConfirmedError(APPLY_NOT_CONFIRMED_MESSAGE)


def _failure_summary(exc: OSError) -> str:
    message = str(exc)
    return MOVE_FAILED_ERROR_CODE if message == "" else message


def _combined_failure_summary(failure_summaries: tuple[str, ...]) -> str:
    meaningful_summaries = tuple(summary for summary in failure_summaries if summary != "")
    if len(meaningful_summaries) == 0:
        return APPLY_FAILED_SUMMARY
    return SUMMARY_SEPARATOR.join(meaningful_summaries)
