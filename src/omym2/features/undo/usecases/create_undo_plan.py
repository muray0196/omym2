"""
Summary: Implements undo Plan creation from Run history.
Why: Restores prior file moves through reviewed Plans instead of direct mutation.
"""

from __future__ import annotations

from dataclasses import dataclass, replace
from datetime import timedelta
from pathlib import PurePath
from typing import TYPE_CHECKING

from omym2.config import (
    OPERATION_RESULT_RETENTION_HOURS,
    OPERATION_TOMBSTONE_RETENTION_DAYS,
    PLAN_ACTION_SORT_ORDER_START,
    PLAN_ACTION_SORT_ORDER_STEP,
)
from omym2.domain.models.file_event import FileEventStatus
from omym2.domain.models.operation import Operation, OperationKind, OperationStatus, PlanCreatedResult
from omym2.domain.models.plan import Plan, PlanStatus, PlanType
from omym2.domain.models.plan_action import ActionStatus, ActionType, PlanAction, PlanActionReason
from omym2.domain.models.run import RunStatus
from omym2.domain.models.track import TrackStatus

if TYPE_CHECKING:
    from datetime import datetime

    from omym2.domain.models.file_event import FileEvent
    from omym2.domain.models.file_snapshot import FileSnapshot
    from omym2.domain.models.library import Library
    from omym2.domain.models.run import Run
    from omym2.features.common_ports import FileSystemPath, PathResolver, UnitOfWork
    from omym2.features.undo.dto import CreateUndoPlanRequest
    from omym2.features.undo.ports import CreateUndoPlanPorts
    from omym2.shared.ids import ActionId, EventId, LibraryId, OperationId, PlanId, RunId, TrackId

ALREADY_UNDONE_OR_IN_PROGRESS_MESSAGE = "Undo has already been applied or is in progress for this Run."
NOTHING_TO_UNDO_MESSAGE = "Run has no confirmed file mutation left to undo."
PENDING_FILE_EVENT_REQUIRES_REVIEW_MESSAGE = (
    "Undo cannot be planned while a related FileEvent is pending; run check and review it first."
)
RUN_LIBRARY_NOT_FOUND_MESSAGE = "Run Library was not found."
RUN_NOT_FOUND_MESSAGE = "Run was not found."
RUN_NOT_TERMINAL_MESSAGE = "Undo can only be planned after the Run has finished."
RUN_PLAN_NOT_FOUND_MESSAGE = "Run Plan was not found."
RUN_REFRESH_METADATA_UNSUPPORTED_MESSAGE = (
    "Undo is not supported for Runs that include refresh_metadata actions because metadata-only refresh history is not "
    "reversible yet."
)
RUNNING_OPERATION_REQUIRED_MESSAGE = "Undo completion requires its corresponding running Operation."
SUMMARY_ACTION_COUNT_KEY = "action_count"
SUMMARY_BLOCKED_ACTIONS_KEY = "blocked_actions"
SUMMARY_MOVE_ACTIONS_KEY = "move_actions"


@dataclass(frozen=True, slots=True)
class CreateUndoPlanUseCase:
    """Create reviewed undo Plans from succeeded FileEvents."""

    ports: CreateUndoPlanPorts

    def validate(self, request: CreateUndoPlanRequest) -> None:
        """Validate durable Undo eligibility without filesystem reads or writes."""
        with self.ports.uow as uow:
            source = _load_source_history(uow, request.run_id)
            _ = _validate_source_history(source)

    def execute(self, request: CreateUndoPlanRequest) -> Plan:
        """Create an undo Plan from succeeded FileEvents in one Run."""
        timestamp = self.ports.clock.now()

        with self.ports.uow as uow:
            operation = _running_operation(uow, request.operation_id, request.run_id)
            source = _load_source_history(uow, request.run_id)
            decision = _validate_source_history(source)
            if decision.ready_plan is not None:
                ready_plan = replace(
                    decision.ready_plan,
                    actions=tuple(uow.plan_actions.list_by_plan(decision.ready_plan.plan_id)),
                )
                if operation is not None:
                    _save_succeeded_operation(uow, operation, ready_plan, self.ports.clock.now())
                    uow.commit()
                return ready_plan

            undo_plan_id = self.ports.id_generator.new_plan_id()
            lookup = _UndoLookup(
                source_actions_by_id=source.actions_by_id,
                verified_external_event_ids=frozenset(
                    event.event_id
                    for event in decision.events
                    if _is_verified_external_import(source.plan, event, source.actions_by_id)
                ),
            )
            actions = self._actions(uow, source.library, undo_plan_id, decision.events, lookup)
            plan = Plan(
                plan_id=undo_plan_id,
                library_id=source.run.library_id,
                plan_type=PlanType.UNDO,
                status=PlanStatus.READY,
                created_at=timestamp,
                config_hash=source.plan.config_hash,
                library_root_at_plan=source.library.root_path,
                source_run_id=source.run.run_id,
                summary=_summary(actions),
                actions=actions,
            )

            uow.plans.save(plan)
            for action in actions:
                uow.plan_actions.save(action)
            if operation is not None:
                _save_succeeded_operation(uow, operation, plan, self.ports.clock.now())

            uow.commit()
            return plan

    def _actions(
        self,
        uow: UnitOfWork,
        library: Library,
        undo_plan_id: PlanId,
        events: tuple[FileEvent, ...],
        lookup: _UndoLookup,
    ) -> tuple[PlanAction, ...]:
        actions: list[PlanAction] = []
        sort_order = PLAN_ACTION_SORT_ORDER_START

        for event in events:
            candidate = self._candidate(uow, library, event, lookup)
            actions.append(
                PlanAction(
                    action_id=self.ports.id_generator.new_action_id(),
                    plan_id=undo_plan_id,
                    library_id=library.library_id,
                    track_id=candidate.track_id,
                    action_type=ActionType.MOVE,
                    source_path=candidate.source_path,
                    target_path=event.source_path,
                    content_hash_at_plan=None if candidate.snapshot is None else candidate.snapshot.content_hash,
                    metadata_hash_at_plan=None if candidate.snapshot is None else candidate.snapshot.metadata_hash,
                    status=ActionStatus.PLANNED if candidate.reason is None else ActionStatus.BLOCKED,
                    reason=candidate.reason,
                    sort_order=sort_order,
                    reverses_event_id=event.event_id,
                )
            )
            sort_order += PLAN_ACTION_SORT_ORDER_STEP

        return tuple(actions)

    def _candidate(
        self,
        uow: UnitOfWork,
        library: Library,
        event: FileEvent,
        lookup: _UndoLookup,
    ) -> _UndoCandidate:
        source_action = lookup.source_actions_by_id.get(event.plan_action_id)
        track_id = None if source_action is None else source_action.track_id
        track = None if track_id is None else uow.tracks.get(track_id)
        source_path = event.target_path if track is None else track.current_path
        snapshot = None
        reason = PlanActionReason.SOURCE_CHANGED if track_id is None else None

        if reason is None and (track is None or track.status != TrackStatus.ACTIVE):
            reason = PlanActionReason.SOURCE_CHANGED
        elif reason is None:
            try:
                source_filesystem_path = _resolve_path(self.ports.path_resolver, library, source_path)
            except ValueError:
                reason = PlanActionReason.INVALID_PATH
            else:
                try:
                    snapshot = self.ports.file_snapshot_reader.capture(source_filesystem_path)
                except FileNotFoundError:
                    reason = PlanActionReason.SOURCE_MISSING
                except OSError, ValueError:
                    reason = PlanActionReason.SOURCE_CHANGED

        if (
            reason is None
            and track is not None
            and (
                snapshot is None
                or snapshot.content_hash != track.content_hash
                or snapshot.metadata_hash != track.metadata_hash
            )
        ):
            reason = PlanActionReason.SOURCE_CHANGED

        if (
            reason is None
            and PurePath(event.source_path).is_absolute()
            and event.event_id not in lookup.verified_external_event_ids
        ):
            reason = PlanActionReason.INVALID_PATH

        target_filesystem_path = _resolve_path(self.ports.path_resolver, library, event.source_path)
        if reason is None and self.ports.file_presence.exists(target_filesystem_path):
            reason = PlanActionReason.TARGET_EXISTS

        return _UndoCandidate(track_id=track_id, source_path=source_path, snapshot=snapshot, reason=reason)


def _is_verified_external_import(
    source_plan: Plan,
    event: FileEvent,
    source_actions_by_id: dict[ActionId, PlanAction],
) -> bool:
    source_action = source_actions_by_id.get(event.plan_action_id)
    return (
        source_plan.plan_type == PlanType.ADD
        and source_action is not None
        and source_action.track_id is not None
        and source_action.source_path == event.source_path
        and source_action.target_path == event.target_path
        and PurePath(source_action.source_path or "").is_absolute()
        and not PurePath(source_action.target_path or "").is_absolute()
    )


class UndoPlanError(ValueError):
    """Raised when undo cannot be planned from durable history."""


@dataclass(frozen=True, slots=True)
class _UndoCandidate:
    """Plan-time judgment for one reverse FileEvent action."""

    track_id: TrackId | None
    source_path: str
    snapshot: FileSnapshot | None
    reason: PlanActionReason | None


@dataclass(slots=True)
class _UndoLookup:
    """Cached source history used while judging undo candidates."""

    source_actions_by_id: dict[ActionId, PlanAction]
    verified_external_event_ids: frozenset[EventId]


@dataclass(frozen=True, slots=True)
class _UndoSourceHistory:
    """Validated source Run plus every prior Undo attempt in its scope."""

    run: Run
    library: Library
    plan: Plan
    actions_by_id: dict[ActionId, PlanAction]
    events: tuple[FileEvent, ...]
    prior_plans: tuple[Plan, ...]
    prior_histories: tuple[_PriorUndoHistory, ...]


@dataclass(frozen=True, slots=True)
class _PriorUndoHistory:
    """One prior Undo Plan's actions and mutation evidence."""

    actions_by_id: dict[ActionId, PlanAction]
    events: tuple[FileEvent, ...]


@dataclass(frozen=True, slots=True)
class _UndoDecision:
    """Validated ready-Plan reuse or ordered source events for regeneration."""

    events: tuple[FileEvent, ...] = ()
    ready_plan: Plan | None = None


def _load_source_history(uow: UnitOfWork, run_id: RunId) -> _UndoSourceHistory:
    run = uow.runs.get(run_id)
    if run is None:
        raise UndoPlanError(RUN_NOT_FOUND_MESSAGE)
    if run.status == RunStatus.RUNNING:
        raise UndoPlanError(RUN_NOT_TERMINAL_MESSAGE)

    library = uow.libraries.get(run.library_id)
    if library is None:
        raise UndoPlanError(RUN_LIBRARY_NOT_FOUND_MESSAGE)

    plan = uow.plans.get(run.plan_id)
    if plan is None:
        raise UndoPlanError(RUN_PLAN_NOT_FOUND_MESSAGE)
    actions = tuple(uow.plan_actions.list_by_plan(run.plan_id))
    if any(action.action_type == ActionType.REFRESH_METADATA for action in actions):
        raise UndoPlanError(RUN_REFRESH_METADATA_UNSUPPORTED_MESSAGE)

    prior_plans = tuple(uow.plans.list_by_source_run(run.run_id))
    return _UndoSourceHistory(
        run=run,
        library=library,
        plan=plan,
        actions_by_id={action.action_id: action for action in actions},
        events=tuple(uow.file_events.list_by_run(run.run_id)),
        prior_plans=prior_plans,
        prior_histories=_prior_undo_histories(uow, prior_plans),
    )


def _validate_source_history(source: _UndoSourceHistory) -> _UndoDecision:
    if any(event.status == FileEventStatus.PENDING for event in source.events) or any(
        event.status == FileEventStatus.PENDING for history in source.prior_histories for event in history.events
    ):
        raise UndoPlanError(PENDING_FILE_EVENT_REQUIRES_REVIEW_MESSAGE)

    reversible_events = tuple(
        event
        for event in source.events
        if _is_reversible_source_event(
            source.run.run_id,
            source.run.library_id,
            event,
            source.actions_by_id,
        )
    )
    if not reversible_events:
        raise UndoPlanError(NOTHING_TO_UNDO_MESSAGE)

    if any(plan.status in {PlanStatus.APPLYING, PlanStatus.APPLIED} for plan in source.prior_plans):
        raise UndoPlanError(ALREADY_UNDONE_OR_IN_PROGRESS_MESSAGE)

    ready_plan = next((plan for plan in source.prior_plans if plan.status == PlanStatus.READY), None)
    if ready_plan is not None:
        return _UndoDecision(ready_plan=ready_plan)

    reversed_event_ids = _durably_reversed_event_ids(source.prior_histories, source.run.library_id)
    events = tuple(reversed(tuple(event for event in reversible_events if event.event_id not in reversed_event_ids)))
    if not events:
        raise UndoPlanError(NOTHING_TO_UNDO_MESSAGE)
    return _UndoDecision(events=events)


def _prior_undo_histories(uow: UnitOfWork, plans: tuple[Plan, ...]) -> tuple[_PriorUndoHistory, ...]:
    histories: list[_PriorUndoHistory] = []
    for plan in plans:
        actions = tuple(uow.plan_actions.list_by_plan(plan.plan_id))
        events = tuple(
            event
            for undo_run in uow.runs.list_by_plan(plan.plan_id)
            for event in uow.file_events.list_by_run(undo_run.run_id)
        )
        histories.append(
            _PriorUndoHistory(
                actions_by_id={action.action_id: action for action in actions},
                events=events,
            )
        )
    return tuple(histories)


def _durably_reversed_event_ids(
    histories: tuple[_PriorUndoHistory, ...],
    library_id: LibraryId,
) -> frozenset[EventId]:
    reversed_event_ids: set[EventId] = set()
    for history in histories:
        for event in history.events:
            action = history.actions_by_id.get(event.plan_action_id)
            if (
                event.status == FileEventStatus.SUCCEEDED
                and event.library_id == library_id
                and action is not None
                and action.library_id == library_id
                and action.reverses_event_id is not None
            ):
                reversed_event_ids.add(action.reverses_event_id)
    return frozenset(reversed_event_ids)


def _is_reversible_source_event(
    run_id: RunId,
    library_id: LibraryId,
    event: FileEvent,
    source_actions_by_id: dict[ActionId, PlanAction],
) -> bool:
    source_action = source_actions_by_id.get(event.plan_action_id)
    return (
        event.status == FileEventStatus.SUCCEEDED
        and event.run_id == run_id
        and event.library_id == library_id
        and source_action is not None
        and source_action.library_id == library_id
        and source_action.action_type == ActionType.MOVE
    )


def _running_operation(
    uow: UnitOfWork,
    operation_id: OperationId | None,
    source_run_id: RunId,
) -> Operation | None:
    if operation_id is None:
        return None
    retained = uow.operations.lookup(operation_id)
    if (
        not isinstance(retained, Operation)
        or retained.kind is not OperationKind.UNDO_PLAN
        or retained.status is not OperationStatus.RUNNING
        or retained.run_id != source_run_id
    ):
        raise RuntimeError(RUNNING_OPERATION_REQUIRED_MESSAGE)
    return retained


def _save_succeeded_operation(
    uow: UnitOfWork,
    operation: Operation,
    plan: Plan,
    completed_at: datetime,
) -> None:
    uow.operations.save(
        replace(operation, library_id=plan.library_id).mark_succeeded(
            result=PlanCreatedResult(plan.plan_id),
            completed_at=completed_at,
            result_expires_at=completed_at + timedelta(hours=OPERATION_RESULT_RETENTION_HOURS),
            tombstone_expires_at=completed_at + timedelta(days=OPERATION_TOMBSTONE_RETENTION_DAYS),
        )
    )


def _resolve_path(path_resolver: PathResolver, library: Library, path: str) -> FileSystemPath:
    if PurePath(path).is_absolute():
        return path
    return path_resolver.resolve_library_path(library.root_path, path)


def _summary(actions: tuple[PlanAction, ...]) -> dict[str, str]:
    blocked_count = sum(action.status == ActionStatus.BLOCKED for action in actions)
    return {
        SUMMARY_ACTION_COUNT_KEY: str(len(actions)),
        SUMMARY_MOVE_ACTIONS_KEY: str(len(actions) - blocked_count),
        SUMMARY_BLOCKED_ACTIONS_KEY: str(blocked_count),
    }
