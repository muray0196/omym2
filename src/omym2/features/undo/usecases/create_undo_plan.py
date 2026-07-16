"""
Summary: Implements undo Plan creation from Run history.
Why: Restores prior file moves through reviewed Plans instead of direct mutation.
"""

from __future__ import annotations

import os
from dataclasses import dataclass, replace
from datetime import timedelta
from pathlib import Path, PurePath
from typing import TYPE_CHECKING

from omym2.config import (
    OPERATION_RESULT_RETENTION_HOURS,
    OPERATION_TOMBSTONE_RETENTION_DAYS,
    PLAN_ACTION_SORT_ORDER_START,
    PLAN_ACTION_SORT_ORDER_STEP,
)
from omym2.domain.models.companion_asset import CompanionAssetKind, CompanionAssetStatus
from omym2.domain.models.file_event import FileEventStatus, FileEventType
from omym2.domain.models.operation import Operation, OperationKind, OperationStatus, PlanCreatedResult
from omym2.domain.models.plan import Plan, PlanStatus, PlanType
from omym2.domain.models.plan_action import (
    ActionStatus,
    ActionType,
    PlanAction,
    PlanActionDependency,
    PlanActionReason,
)
from omym2.domain.models.run import RunStatus
from omym2.domain.models.track import TrackStatus
from omym2.domain.services.unprocessed_collection import validate_unprocessed_path_layout
from omym2.features.common_ports import FileObservationChangedError, FileObservationInvalidPathError

if TYPE_CHECKING:
    from datetime import datetime

    from omym2.domain.models.companion_asset import CompanionAsset
    from omym2.domain.models.file_event import FileEvent
    from omym2.domain.models.library import Library
    from omym2.domain.models.run import Run
    from omym2.features.common_ports import FileSystemPath, PathResolver, UnitOfWork
    from omym2.features.undo.dto import CreateUndoPlanRequest
    from omym2.features.undo.ports import CreateUndoPlanPorts
    from omym2.shared.ids import (
        ActionId,
        CompanionAssetId,
        EventId,
        LibraryId,
        OperationId,
        PlanId,
        RunId,
        TrackId,
    )

ALREADY_UNDONE_OR_IN_PROGRESS_MESSAGE = "Undo has already been applied or is in progress for this Run."
NOTHING_TO_UNDO_MESSAGE = "Run has no confirmed file mutation left to undo."
PENDING_FILE_EVENT_REQUIRES_REVIEW_MESSAGE = (
    "Undo cannot be planned while a related FileEvent is pending; run check and review it first."
)
INVALID_COMPANION_PROVENANCE_MESSAGE = "Companion mutation history is inconsistent and cannot be undone."
INVALID_UNPROCESSED_PROVENANCE_MESSAGE = "Unprocessed mutation history is inconsistent and cannot be undone."
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

COMPANION_ACTION_TYPES = frozenset({ActionType.MOVE_LYRICS, ActionType.MOVE_ARTWORK})
COMPANION_EVENT_TYPES = frozenset({FileEventType.MOVE_LYRICS_FILE, FileEventType.MOVE_ARTWORK_FILE})
COMPANION_EVENT_TYPE_BY_ACTION_TYPE = {
    ActionType.MOVE_LYRICS: FileEventType.MOVE_LYRICS_FILE,
    ActionType.MOVE_ARTWORK: FileEventType.MOVE_ARTWORK_FILE,
}
TERMINAL_SOURCE_PLAN_STATUSES = frozenset({PlanStatus.APPLIED, PlanStatus.PARTIAL_FAILED, PlanStatus.FAILED})
TERMINAL_SOURCE_RUN_STATUSES = frozenset({RunStatus.SUCCEEDED, RunStatus.PARTIAL_FAILED, RunStatus.FAILED})


@dataclass(frozen=True, slots=True)
class CreateUndoPlanUseCase:
    """Create reviewed undo Plans from succeeded FileEvents."""

    ports: CreateUndoPlanPorts

    def validate(self, request: CreateUndoPlanRequest) -> None:
        """Validate durable Undo eligibility without filesystem reads or writes."""
        with self.ports.uow as uow:
            source = _load_source_history(uow, request.run_id)
            _ = _validate_source_history(source, self.ports.clock.now())

    def execute(self, request: CreateUndoPlanRequest) -> Plan:
        """Create an undo Plan from succeeded FileEvents in one Run."""
        timestamp = self.ports.clock.now()

        with self.ports.uow as uow:
            operation = _running_operation(uow, request.operation_id, request.run_id)
            source = _load_source_history(uow, request.run_id)
            decision = _validate_source_history(source, timestamp)
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
                companion_assets_by_id=source.companion_assets_by_id,
                source_root_at_plan=source.plan.source_root_at_plan,
                inverse_action_ids_by_source_action_id={
                    event.plan_action_id: self.ports.id_generator.new_action_id() for event in decision.events
                },
                verified_external_event_ids=frozenset(
                    event.event_id
                    for event in decision.events
                    if _is_verified_external_import(source.plan, event, source.actions_by_id)
                ),
            )
            actions = self._actions(uow, source.library, undo_plan_id, decision.events, lookup)
            dependencies = _inverse_dependencies(
                undo_plan_id,
                actions,
                source.dependencies_by_action_id,
                lookup.inverse_action_ids_by_source_action_id,
            )
            plan = Plan(
                plan_id=undo_plan_id,
                library_id=source.run.library_id,
                plan_type=PlanType.UNDO,
                status=PlanStatus.READY,
                created_at=timestamp,
                config_hash=source.plan.config_hash,
                library_root_at_plan=source.library.root_path,
                source_root_at_plan=source.plan.source_root_at_plan,
                source_run_id=source.run.run_id,
                summary=_summary(actions),
                actions=actions,
            )

            uow.plans.save(plan)
            for action in _owner_safe_persistence_order(actions):
                uow.plan_actions.save(action)
            for dependency in dependencies:
                uow.plan_action_dependencies.save(dependency)
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
                    action_id=lookup.inverse_action_ids_by_source_action_id[event.plan_action_id],
                    plan_id=undo_plan_id,
                    library_id=library.library_id,
                    track_id=candidate.track_id,
                    action_type=candidate.action_type,
                    source_path=candidate.source_path,
                    target_path=event.source_path,
                    content_hash_at_plan=candidate.content_hash,
                    metadata_hash_at_plan=candidate.metadata_hash,
                    status=ActionStatus.PLANNED if candidate.reason is None else ActionStatus.BLOCKED,
                    reason=candidate.reason,
                    sort_order=sort_order,
                    reverses_event_id=event.event_id,
                    companion_asset_id=candidate.companion_asset_id,
                    owner_action_id=candidate.owner_action_id,
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
        if source_action is not None and source_action.action_type is ActionType.MOVE_UNPROCESSED:
            return self._unprocessed_candidate(event, lookup)
        if source_action is not None and source_action.action_type in COMPANION_ACTION_TYPES:
            return self._companion_candidate(library, event, source_action, lookup)
        return self._audio_candidate(uow, library, event, source_action, lookup)

    def _unprocessed_candidate(
        self,
        event: FileEvent,
        lookup: _UndoLookup,
    ) -> _UndoCandidate:
        """Capture the current collected bytes under the retained external root."""
        source_root = lookup.source_root_at_plan
        source_path = event.target_path
        source_action = lookup.source_actions_by_id.get(event.plan_action_id)
        snapshot = None
        reason = None
        if source_root is None or source_action is None or source_action.content_hash_at_plan is None:
            reason = PlanActionReason.INVALID_PATH
        else:
            try:
                snapshot = self.ports.file_content_snapshot_reader.capture(
                    source_path,
                    root=source_root,
                )
            except FileNotFoundError:
                reason = PlanActionReason.SOURCE_MISSING
            except FileObservationChangedError, OSError:
                reason = PlanActionReason.SOURCE_CHANGED
            except FileObservationInvalidPathError, ValueError:
                reason = PlanActionReason.INVALID_PATH

        if (
            reason is None
            and snapshot is not None
            and source_action is not None
            and snapshot.content_hash != source_action.content_hash_at_plan
        ):
            reason = PlanActionReason.SOURCE_CHANGED

        if reason is None and self.ports.file_presence.exists(event.source_path):
            reason = PlanActionReason.TARGET_EXISTS

        return _UndoCandidate(
            track_id=None,
            source_path=source_path,
            action_type=ActionType.MOVE_UNPROCESSED,
            content_hash=None if snapshot is None else snapshot.content_hash,
            metadata_hash=None,
            reason=reason,
        )

    def _audio_candidate(  # noqa: C901  # Audio Undo retains independent snapshot and path failure reasons.
        self,
        uow: UnitOfWork,
        library: Library,
        event: FileEvent,
        source_action: PlanAction | None,
        lookup: _UndoLookup,
    ) -> _UndoCandidate:
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

        try:
            target_filesystem_path = _resolve_path(self.ports.path_resolver, library, event.source_path)
        except ValueError:
            reason = PlanActionReason.INVALID_PATH
        else:
            if reason is None and self.ports.file_presence.exists(target_filesystem_path):
                reason = PlanActionReason.TARGET_EXISTS

        return _UndoCandidate(
            track_id=track_id,
            source_path=source_path,
            action_type=ActionType.MOVE,
            content_hash=None if snapshot is None else snapshot.content_hash,
            metadata_hash=None if snapshot is None else snapshot.metadata_hash,
            reason=reason,
        )

    def _companion_candidate(
        self,
        library: Library,
        event: FileEvent,
        source_action: PlanAction,
        lookup: _UndoLookup,
    ) -> _UndoCandidate:
        companion_asset_id = source_action.companion_asset_id
        asset = None if companion_asset_id is None else lookup.companion_assets_by_id.get(companion_asset_id)
        if asset is None:
            raise UndoPlanError(INVALID_COMPANION_PROVENANCE_MESSAGE)

        source_path = asset.current_path
        snapshot = None
        reason = None
        try:
            source_filesystem_path = _resolve_path(self.ports.path_resolver, library, source_path)
        except ValueError:
            reason = PlanActionReason.INVALID_PATH
        else:
            try:
                snapshot = self.ports.file_content_snapshot_reader.capture(
                    source_filesystem_path,
                    root=library.root_path,
                )
            except FileNotFoundError:
                reason = PlanActionReason.SOURCE_MISSING
            except OSError, ValueError:
                reason = PlanActionReason.SOURCE_CHANGED

        if reason is None and (snapshot is None or snapshot.content_hash != asset.content_hash):
            reason = PlanActionReason.SOURCE_CHANGED

        try:
            target_filesystem_path = _resolve_path(self.ports.path_resolver, library, event.source_path)
        except ValueError:
            reason = PlanActionReason.INVALID_PATH
        else:
            if reason is None and self.ports.file_presence.exists(target_filesystem_path):
                reason = PlanActionReason.TARGET_EXISTS

        source_owner_action_id = source_action.owner_action_id
        return _UndoCandidate(
            track_id=asset.owner_track_id,
            source_path=source_path,
            action_type=source_action.action_type,
            content_hash=None if snapshot is None else snapshot.content_hash,
            metadata_hash=None,
            reason=reason,
            companion_asset_id=asset.companion_asset_id,
            owner_action_id=(
                None
                if source_owner_action_id is None
                else lookup.inverse_action_ids_by_source_action_id.get(source_owner_action_id)
            ),
        )


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
    action_type: ActionType
    content_hash: str | None
    metadata_hash: str | None
    reason: PlanActionReason | None
    companion_asset_id: CompanionAssetId | None = None
    owner_action_id: ActionId | None = None


@dataclass(slots=True)
class _UndoLookup:
    """Cached source history used while judging undo candidates."""

    source_actions_by_id: dict[ActionId, PlanAction]
    companion_assets_by_id: dict[CompanionAssetId, CompanionAsset]
    source_root_at_plan: str | None
    inverse_action_ids_by_source_action_id: dict[ActionId, ActionId]
    verified_external_event_ids: frozenset[EventId]


@dataclass(frozen=True, slots=True)
class _UndoSourceHistory:
    """Validated source Run plus every prior Undo attempt in its scope."""

    run: Run
    library: Library
    plan: Plan
    actions_by_id: dict[ActionId, PlanAction]
    dependencies_by_action_id: dict[ActionId, tuple[PlanActionDependency, ...]]
    companion_assets_by_id: dict[CompanionAssetId, CompanionAsset]
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
    companion_assets = tuple(uow.companion_assets.list_by_library(run.library_id))
    return _UndoSourceHistory(
        run=run,
        library=library,
        plan=plan,
        actions_by_id={action.action_id: action for action in actions},
        dependencies_by_action_id={
            action.action_id: tuple(uow.plan_action_dependencies.list_by_action(action.action_id)) for action in actions
        },
        companion_assets_by_id={asset.companion_asset_id: asset for asset in companion_assets},
        events=tuple(uow.file_events.list_by_run(run.run_id)),
        prior_plans=prior_plans,
        prior_histories=_prior_undo_histories(uow, prior_plans),
    )


def _validate_source_history(source: _UndoSourceHistory, planned_at: datetime) -> _UndoDecision:
    if any(event.status == FileEventStatus.PENDING for event in source.events) or any(
        event.status == FileEventStatus.PENDING for history in source.prior_histories for event in history.events
    ):
        raise UndoPlanError(PENDING_FILE_EVENT_REQUIRES_REVIEW_MESSAGE)

    reversed_event_ids = _durably_reversed_event_ids(source.prior_histories, source.run.library_id)
    succeeded_companion_events = tuple(
        event
        for event in source.events
        if event.status is FileEventStatus.SUCCEEDED
        and event.event_id not in reversed_event_ids
        and _is_companionish(source, event)
    )
    if any(not _companion_provenance_is_valid(source, event, planned_at) for event in succeeded_companion_events):
        raise UndoPlanError(INVALID_COMPANION_PROVENANCE_MESSAGE)

    succeeded_unprocessed_events = tuple(
        event
        for event in source.events
        if event.status is FileEventStatus.SUCCEEDED
        and event.event_id not in reversed_event_ids
        and _is_unprocessedish(source, event)
    )
    if any(not _unprocessed_provenance_is_valid(source, event, planned_at) for event in succeeded_unprocessed_events):
        raise UndoPlanError(INVALID_UNPROCESSED_PROVENANCE_MESSAGE)

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
    if len({event.plan_action_id for event in reversible_events}) != len(reversible_events):
        raise UndoPlanError(INVALID_COMPANION_PROVENANCE_MESSAGE)

    if any(plan.status in {PlanStatus.APPLYING, PlanStatus.APPLIED} for plan in source.prior_plans):
        raise UndoPlanError(ALREADY_UNDONE_OR_IN_PROGRESS_MESSAGE)

    ready_plan = next((plan for plan in source.prior_plans if plan.status == PlanStatus.READY), None)
    if ready_plan is not None:
        return _UndoDecision(ready_plan=ready_plan)

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
    expected_event_type = (
        None if source_action is None else _event_type_for_reversible_action(source_action.action_type)
    )
    return (
        event.status == FileEventStatus.SUCCEEDED
        and event.run_id == run_id
        and event.library_id == library_id
        and source_action is not None
        and source_action.library_id == library_id
        and expected_event_type is not None
        and event.event_type is expected_event_type
    )


def _is_companionish(source: _UndoSourceHistory, event: FileEvent) -> bool:
    source_action = source.actions_by_id.get(event.plan_action_id)
    return (
        event.event_type in COMPANION_EVENT_TYPES
        or event.companion_asset_id is not None
        or (
            source_action is not None
            and (
                source_action.action_type in COMPANION_ACTION_TYPES
                or source_action.companion_asset_id is not None
                or source_action.owner_action_id is not None
            )
        )
    )


def _is_unprocessedish(source: _UndoSourceHistory, event: FileEvent) -> bool:
    source_action = source.actions_by_id.get(event.plan_action_id)
    return event.event_type is FileEventType.MOVE_UNPROCESSED_FILE or (
        source_action is not None and source_action.action_type is ActionType.MOVE_UNPROCESSED
    )


def _unprocessed_provenance_is_valid(
    source: _UndoSourceHistory,
    event: FileEvent,
    planned_at: datetime,
) -> bool:
    """Require one exact successful Add collection event before planning its inverse."""
    source_action = source.actions_by_id.get(event.plan_action_id)
    source_root = source.plan.source_root_at_plan
    completed_at = event.completed_at
    run_completed_at = source.run.completed_at
    if (
        source_action is None
        or source_root is None
        or completed_at is None
        or run_completed_at is None
        or source_action.source_path is None
        or source_action.target_path is None
    ):
        return False
    return (
        source.plan.plan_type is PlanType.ADD
        and source.plan.source_run_id is None
        and source.plan.status in TERMINAL_SOURCE_PLAN_STATUSES
        and source.run.status in TERMINAL_SOURCE_RUN_STATUSES
        and source.run.plan_id == source.plan.plan_id
        and source.run.library_id == source.plan.library_id == source.library.library_id
        and source.plan.created_at <= source.run.started_at <= event.started_at
        and event.started_at <= completed_at <= run_completed_at <= planned_at
        and event.run_id == source.run.run_id
        and event.library_id == source.library.library_id
        and event.plan_action_id == source_action.action_id
        and event.event_type is FileEventType.MOVE_UNPROCESSED_FILE
        and event.status is FileEventStatus.SUCCEEDED
        and event.source_path == source_action.source_path
        and event.target_path == source_action.target_path
        and event.companion_asset_id is None
        and source_action.plan_id == source.plan.plan_id
        and source_action.library_id == source.library.library_id
        and source_action.action_type is ActionType.MOVE_UNPROCESSED
        and source_action.status is ActionStatus.APPLIED
        and source_action.reason is None
        and source_action.track_id is None
        and source_action.content_hash_at_plan is not None
        and source_action.metadata_hash_at_plan is None
        and source_action.reverses_event_id is None
        and source_action.artist_name_diagnostics is None
        and source_action.companion_asset_id is None
        and source_action.owner_action_id is None
        and not source.dependencies_by_action_id.get(source_action.action_id, ())
        and sum(candidate.plan_action_id == source_action.action_id for candidate in source.events) == 1
        and validate_unprocessed_path_layout(
            source_root,
            source_action.source_path,
            source_action.target_path,
            excluded_root=source.plan.library_root_at_plan,
        )
        is not None
    )


def _companion_provenance_is_valid(  # noqa: PLR0911  # Each durable evidence boundary fails closed.
    source: _UndoSourceHistory,
    event: FileEvent,
    planned_at: datetime,
) -> bool:
    source_action = source.actions_by_id.get(event.plan_action_id)
    if source_action is None or source_action.action_type not in COMPANION_ACTION_TYPES:
        return False
    companion_asset_id = source_action.companion_asset_id
    asset = None if companion_asset_id is None else source.companion_assets_by_id.get(companion_asset_id)
    if asset is None:
        return False

    event_completed_at = event.completed_at
    run_completed_at = source.run.completed_at
    if event_completed_at is None or run_completed_at is None:
        return False
    if not (
        source.plan.status in TERMINAL_SOURCE_PLAN_STATUSES
        and source.run.status in TERMINAL_SOURCE_RUN_STATUSES
        and source.run.plan_id == source.plan.plan_id
        and source.run.library_id == source.plan.library_id == source.library.library_id
        and source.plan.created_at <= event.started_at <= event_completed_at <= run_completed_at <= planned_at
        and event.run_id == source.run.run_id
        and event.library_id == source.library.library_id
        and event.event_type is COMPANION_EVENT_TYPE_BY_ACTION_TYPE[source_action.action_type]
        and event.companion_asset_id == companion_asset_id
        and source_action.plan_id == source.plan.plan_id
        and source_action.library_id == source.library.library_id
        and source_action.status is ActionStatus.APPLIED
        and source_action.track_id is not None
        and source_action.source_path == event.source_path
        and source_action.target_path == event.target_path
        and source_action.content_hash_at_plan is not None
        and source_action.metadata_hash_at_plan is None
        and asset.library_id == source.library.library_id
        and asset.kind is _companion_asset_kind(source_action.action_type)
        and asset.owner_track_id == source_action.track_id
        and asset.status is CompanionAssetStatus.ACTIVE
        and not PurePath(asset.current_path).is_absolute()
        and not PurePath(event.target_path).is_absolute()
    ):
        return False

    dependencies = source.dependencies_by_action_id.get(source_action.action_id, ())
    dependency_action_ids = {dependency.depends_on_action_id for dependency in dependencies}
    succeeded_events_by_action_id = {
        source_event.plan_action_id: source_event
        for source_event in source.events
        if source_event.status is FileEventStatus.SUCCEEDED
    }
    if any(
        dependency.plan_id != source.plan.plan_id
        or dependency.action_id != source_action.action_id
        or (dependency_action := source.actions_by_id.get(dependency.depends_on_action_id)) is None
        or (dependency_event := succeeded_events_by_action_id.get(dependency.depends_on_action_id)) is None
        or dependency_action.plan_id != source.plan.plan_id
        or dependency_action.library_id != source.library.library_id
        or dependency_action.action_type is not ActionType.MOVE
        or dependency_action.status is not ActionStatus.APPLIED
        or dependency_event.run_id != source.run.run_id
        or dependency_event.library_id != source.library.library_id
        or dependency_event.event_type is not FileEventType.MOVE_FILE
        or dependency_event.completed_at is None
        or dependency_event.plan_action_id != dependency_action.action_id
        or dependency_event.source_path != dependency_action.source_path
        or dependency_event.target_path != dependency_action.target_path
        or dependency_event.companion_asset_id is not None
        for dependency in dependencies
    ):
        return False

    owner_action_id = source_action.owner_action_id
    if owner_action_id is not None:
        owner_action = source.actions_by_id.get(owner_action_id)
        if (
            owner_action is None
            or owner_action_id not in dependency_action_ids
            or owner_action.plan_id != source.plan.plan_id
            or owner_action.library_id != source.library.library_id
            or owner_action.action_type is not ActionType.MOVE
            or owner_action.status is not ActionStatus.APPLIED
            or owner_action.track_id != source_action.track_id
        ):
            return False

    if PurePath(event.source_path).is_absolute():
        return (
            source.plan.plan_type is PlanType.ADD
            and source.plan.source_root_at_plan is not None
            and PurePath(source.plan.source_root_at_plan).is_absolute()
            and _path_is_within_root(event.source_path, source.plan.source_root_at_plan)
        )
    return not PurePath(source_action.source_path or "").is_absolute()


def _event_type_for_reversible_action(action_type: ActionType) -> FileEventType | None:
    if action_type is ActionType.MOVE:
        return FileEventType.MOVE_FILE
    if action_type is ActionType.MOVE_UNPROCESSED:
        return FileEventType.MOVE_UNPROCESSED_FILE
    return COMPANION_EVENT_TYPE_BY_ACTION_TYPE.get(action_type)


def _companion_asset_kind(action_type: ActionType) -> CompanionAssetKind:
    if action_type is ActionType.MOVE_LYRICS:
        return CompanionAssetKind.LYRICS
    if action_type is ActionType.MOVE_ARTWORK:
        return CompanionAssetKind.ARTWORK
    raise AssertionError(action_type)


def _path_is_within_root(path: str, root: str) -> bool:
    normalized_path = Path(os.path.abspath(Path(path).expanduser()))  # noqa: PTH100  # Lexical only; do not follow links.
    normalized_root = Path(os.path.abspath(Path(root).expanduser()))  # noqa: PTH100  # Match Add root normalization.
    try:
        _ = normalized_path.relative_to(normalized_root)
    except ValueError:
        return False
    return True


def _inverse_dependencies(
    undo_plan_id: PlanId,
    actions: tuple[PlanAction, ...],
    source_dependencies_by_action_id: dict[ActionId, tuple[PlanActionDependency, ...]],
    inverse_action_ids_by_source_action_id: dict[ActionId, ActionId],
) -> tuple[PlanActionDependency, ...]:
    dependencies: set[tuple[ActionId, ActionId]] = set()
    for source_action_id, source_dependencies in source_dependencies_by_action_id.items():
        inverse_dependency_id = inverse_action_ids_by_source_action_id.get(source_action_id)
        if inverse_dependency_id is None:
            continue
        for source_dependency in source_dependencies:
            inverse_action_id = inverse_action_ids_by_source_action_id.get(source_dependency.depends_on_action_id)
            if inverse_action_id is not None:
                dependencies.add((inverse_action_id, inverse_dependency_id))

    sort_order_by_id = {action.action_id: action.sort_order for action in actions}
    return tuple(
        PlanActionDependency(
            plan_id=undo_plan_id,
            action_id=action_id,
            depends_on_action_id=depends_on_action_id,
        )
        for action_id, depends_on_action_id in sorted(
            dependencies,
            key=lambda dependency: (
                sort_order_by_id[dependency[0]],
                sort_order_by_id[dependency[1]],
                str(dependency[0]),
                str(dependency[1]),
            ),
        )
    )


def _owner_safe_persistence_order(actions: tuple[PlanAction, ...]) -> tuple[PlanAction, ...]:
    actions_by_id = {action.action_id: action for action in actions}
    pending = list(actions)
    persisted_ids: set[ActionId] = set()
    ordered: list[PlanAction] = []
    while pending:
        ready = tuple(
            action for action in pending if action.owner_action_id is None or action.owner_action_id in persisted_ids
        )
        if not ready:
            raise UndoPlanError(INVALID_COMPANION_PROVENANCE_MESSAGE)
        for action in ready:
            if action.owner_action_id is not None and action.owner_action_id not in actions_by_id:
                raise UndoPlanError(INVALID_COMPANION_PROVENANCE_MESSAGE)
            ordered.append(action)
            persisted_ids.add(action.action_id)
            pending.remove(action)
    return tuple(ordered)


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
