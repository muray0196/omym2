"""
Summary: Implements undo Plan creation from Run history.
Why: Restores prior file moves through reviewed Plans instead of direct mutation.
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import PurePath
from typing import TYPE_CHECKING

from omym2.config import PLAN_ACTION_SORT_ORDER_START, PLAN_ACTION_SORT_ORDER_STEP
from omym2.domain.models.file_event import FileEventStatus
from omym2.domain.models.plan import Plan, PlanStatus, PlanType
from omym2.domain.models.plan_action import ActionStatus, ActionType, PlanAction, PlanActionReason
from omym2.domain.models.run import RunStatus
from omym2.domain.models.track import TrackStatus

if TYPE_CHECKING:
    from omym2.domain.models.file_event import FileEvent
    from omym2.domain.models.file_snapshot import FileSnapshot
    from omym2.domain.models.library import Library
    from omym2.domain.models.track import Track
    from omym2.features.common_ports import FileSystemPath, PathResolver, UnitOfWork
    from omym2.features.undo.dto import CreateUndoPlanRequest
    from omym2.features.undo.ports import CreateUndoPlanPorts
    from omym2.shared.ids import ActionId, EventId, LibraryId, PlanId, TrackId

RUN_LIBRARY_NOT_FOUND_MESSAGE = "Run Library was not found."
RUN_NOT_FOUND_MESSAGE = "Run was not found."
RUN_NOT_TERMINAL_MESSAGE = "Undo can only be planned after the Run has finished."
RUN_PLAN_NOT_FOUND_MESSAGE = "Run Plan was not found."
RUN_REFRESH_METADATA_UNSUPPORTED_MESSAGE = (
    "Undo is not supported for Runs that include refresh_metadata actions because metadata-only refresh history is not "
    "reversible yet."
)
SUMMARY_ACTION_COUNT_KEY = "action_count"
SUMMARY_BLOCKED_ACTIONS_KEY = "blocked_actions"
SUMMARY_MOVE_ACTIONS_KEY = "move_actions"


@dataclass(frozen=True, slots=True)
class CreateUndoPlanUseCase:
    """Create reviewed undo Plans from succeeded FileEvents."""

    ports: CreateUndoPlanPorts

    def execute(self, request: CreateUndoPlanRequest) -> Plan:
        """Create an undo Plan from succeeded FileEvents in one Run."""
        timestamp = self.ports.clock.now()

        with self.ports.uow as uow:
            run = uow.runs.get(request.run_id)
            if run is None:
                raise UndoPlanError(RUN_NOT_FOUND_MESSAGE)
            if run.status == RunStatus.RUNNING:
                raise UndoPlanError(RUN_NOT_TERMINAL_MESSAGE)

            library = uow.libraries.get(run.library_id)
            if library is None:
                raise UndoPlanError(RUN_LIBRARY_NOT_FOUND_MESSAGE)

            source_plan = uow.plans.get(run.plan_id)
            if source_plan is None:
                raise UndoPlanError(RUN_PLAN_NOT_FOUND_MESSAGE)
            source_actions = tuple(uow.plan_actions.list_by_plan(run.plan_id))
            if any(action.action_type == ActionType.REFRESH_METADATA for action in source_actions):
                # Undo currently replays FileEvents only; refresh_metadata updates Track state without a reversible log.
                raise UndoPlanError(RUN_REFRESH_METADATA_UNSUPPORTED_MESSAGE)
            source_actions_by_id = {action.action_id: action for action in source_actions}

            undo_plan_id = self.ports.id_generator.new_plan_id()
            events = tuple(
                reversed(
                    tuple(
                        event
                        for event in uow.file_events.list_by_run(run.run_id)
                        if event.status == FileEventStatus.SUCCEEDED
                    )
                )
            )
            lookup = _UndoLookup(
                source_actions_by_id=source_actions_by_id,
                tracks_by_library={},
                verified_external_event_ids=frozenset(
                    event.event_id
                    for event in events
                    if _is_verified_external_import(source_plan, event, source_actions_by_id)
                ),
            )
            actions = self._actions(uow, library, undo_plan_id, events, lookup)
            plan = Plan(
                plan_id=undo_plan_id,
                library_id=run.library_id,
                plan_type=PlanType.UNDO,
                status=PlanStatus.READY,
                created_at=timestamp,
                config_hash=source_plan.config_hash,
                library_root_at_plan=library.root_path,
                summary=_summary(actions),
                actions=actions,
            )

            uow.plans.save(plan)
            for action in actions:
                uow.plan_actions.save(action)

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
        track_id = _track_id_for_event(uow, event, lookup.source_actions_by_id, lookup.tracks_by_library)
        track = None if track_id is None else uow.tracks.get(track_id)
        source_path = event.target_path if track is None else track.current_path
        snapshot = None
        reason = None

        if track_id is not None and (track is None or track.status != TrackStatus.ACTIVE):
            reason = PlanActionReason.SOURCE_CHANGED
        else:
            source_filesystem_path = _resolve_path(self.ports.path_resolver, library, source_path)
            try:
                snapshot = self.ports.file_snapshot_reader.capture(source_filesystem_path)
            except FileNotFoundError:
                reason = PlanActionReason.SOURCE_MISSING

        if reason is None and track_id is None:
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
    tracks_by_library: dict[LibraryId, tuple[Track, ...]]
    verified_external_event_ids: frozenset[EventId]


def _track_id_for_event(
    uow: UnitOfWork,
    event: FileEvent,
    source_actions_by_id: dict[ActionId, PlanAction],
    tracks_by_library: dict[LibraryId, tuple[Track, ...]],
) -> TrackId | None:
    source_action = source_actions_by_id.get(event.plan_action_id)
    if source_action is not None and source_action.track_id is not None:
        return source_action.track_id

    if PurePath(event.target_path).is_absolute():
        return None

    library_tracks = tracks_by_library.get(event.library_id)
    if library_tracks is None:
        library_tracks = tuple(uow.tracks.list_by_library(event.library_id))
        tracks_by_library[event.library_id] = library_tracks

    matches = tuple(
        track
        for track in library_tracks
        if track.status == TrackStatus.ACTIVE and track.current_path == event.target_path
    )
    if len(matches) != 1:
        return None
    return matches[0].track_id


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
