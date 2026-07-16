"""
Summary: Classifies failed companion moves that can be safely planned again.
Why: Preserves durable provenance while recovering companions left at their source.
"""

from __future__ import annotations

from collections import defaultdict
from dataclasses import dataclass
from pathlib import PurePath, PurePosixPath
from typing import TYPE_CHECKING

from omym2.domain.models.companion_asset import (
    CompanionAssetKind,
    CompanionAssetStatus,
)
from omym2.domain.models.file_event import FileEventStatus, FileEventType
from omym2.domain.models.plan import PlanStatus, PlanType
from omym2.domain.models.plan_action import ActionStatus, ActionType
from omym2.domain.models.run import RunStatus
from omym2.domain.models.track import TrackStatus

if TYPE_CHECKING:
    from collections.abc import Sequence
    from datetime import datetime

    from omym2.domain.models.companion_asset import CompanionAsset
    from omym2.domain.models.file_event import FileEvent
    from omym2.domain.models.plan import Plan
    from omym2.domain.models.plan_action import PlanAction, PlanActionDependency
    from omym2.domain.models.run import Run
    from omym2.domain.models.track import Track
    from omym2.shared.ids import ActionId, CompanionAssetId, LibraryId, PlanId, RunId, TrackId


_FAILED_PLAN_STATUSES = frozenset({PlanStatus.PARTIAL_FAILED, PlanStatus.FAILED})
_FAILED_RUN_STATUSES = frozenset({RunStatus.PARTIAL_FAILED, RunStatus.FAILED})
_COMPANION_ACTION_TYPES = frozenset({ActionType.MOVE_LYRICS, ActionType.MOVE_ARTWORK})
_EVENT_TYPE_BY_ACTION_TYPE = {
    ActionType.MOVE_LYRICS: FileEventType.MOVE_LYRICS_FILE,
    ActionType.MOVE_ARTWORK: FileEventType.MOVE_ARTWORK_FILE,
}


@dataclass(frozen=True, slots=True)
class RecoverableCompanion:
    """One failed companion mutation with complete, unambiguous provenance."""

    source_plan_id: PlanId
    library_id: LibraryId
    source_plan_type: PlanType
    source_root: str | None
    source_path: str
    target_path: str
    content_hash: str
    kind: CompanionAssetKind
    companion_asset_id: CompanionAssetId
    owner_track_id: TrackId
    dependency_track_ids: tuple[TrackId, ...]


@dataclass(frozen=True, slots=True)
class CompanionRecoveryEvidence:
    """Complete Library history required by the recovery classifier."""

    plans: Sequence[Plan]
    actions: Sequence[PlanAction]
    dependencies: Sequence[PlanActionDependency]
    runs: Sequence[Run]
    events: Sequence[FileEvent]
    tracks: Sequence[Track]
    companion_assets: Sequence[CompanionAsset]


@dataclass(frozen=True, slots=True)
class _RecoveryHistory:
    """Indexed durable records needed to judge one failed companion action."""

    plans_by_id: dict[PlanId, Plan]
    actions_by_plan: dict[PlanId, tuple[PlanAction, ...]]
    actions_by_id: dict[ActionId, PlanAction]
    dependencies_by_action: dict[ActionId, tuple[PlanActionDependency, ...]]
    runs_by_plan: dict[PlanId, tuple[Run, ...]]
    runs_by_id: dict[RunId, Run]
    events_by_run: dict[RunId, tuple[FileEvent, ...]]
    events_by_asset: dict[CompanionAssetId, tuple[FileEvent, ...]]
    tracks_by_id: dict[TrackId, Track]
    assets_by_id: dict[CompanionAssetId, CompanionAsset]


def find_recoverable_companions(
    evidence: CompanionRecoveryEvidence,
) -> tuple[RecoverableCompanion, ...]:
    """Return only uniquely mapped companion failures safe to plan again."""
    history = _index_history(evidence)
    candidates = tuple(
        candidate
        for plan in evidence.plans
        for action in history.actions_by_plan.get(plan.plan_id, ())
        if (candidate := _recoverable_companion(plan, action, history)) is not None
    )

    candidates_by_source: dict[tuple[str | None, str, CompanionAssetKind], list[RecoverableCompanion]] = defaultdict(
        list
    )
    candidates_by_asset: dict[CompanionAssetId, list[RecoverableCompanion]] = defaultdict(list)
    for candidate in candidates:
        candidates_by_source[(candidate.source_root, candidate.source_path, candidate.kind)].append(candidate)
        candidates_by_asset[candidate.companion_asset_id].append(candidate)

    return tuple(
        candidate
        for candidate in candidates
        if len(candidates_by_source[(candidate.source_root, candidate.source_path, candidate.kind)]) == 1
        and len(candidates_by_asset[candidate.companion_asset_id]) == 1
        and _asset_failure_chain_is_valid(candidate, history)
    )


def _index_history(
    evidence: CompanionRecoveryEvidence,
) -> _RecoveryHistory:
    actions_by_plan: dict[PlanId, list[PlanAction]] = defaultdict(list)
    dependencies_by_action: dict[ActionId, list[PlanActionDependency]] = defaultdict(list)
    runs_by_plan: dict[PlanId, list[Run]] = defaultdict(list)
    events_by_run: dict[RunId, list[FileEvent]] = defaultdict(list)
    events_by_asset: dict[CompanionAssetId, list[FileEvent]] = defaultdict(list)
    for action in evidence.actions:
        actions_by_plan[action.plan_id].append(action)
    for dependency in evidence.dependencies:
        dependencies_by_action[dependency.action_id].append(dependency)
    for run in evidence.runs:
        runs_by_plan[run.plan_id].append(run)
    for event in evidence.events:
        events_by_run[event.run_id].append(event)
        if event.companion_asset_id is not None:
            events_by_asset[event.companion_asset_id].append(event)
    return _RecoveryHistory(
        plans_by_id={plan.plan_id: plan for plan in evidence.plans},
        actions_by_plan={key: tuple(value) for key, value in actions_by_plan.items()},
        actions_by_id={action.action_id: action for action in evidence.actions},
        dependencies_by_action={key: tuple(value) for key, value in dependencies_by_action.items()},
        runs_by_plan={key: tuple(value) for key, value in runs_by_plan.items()},
        runs_by_id={run.run_id: run for run in evidence.runs},
        events_by_run={key: tuple(value) for key, value in events_by_run.items()},
        events_by_asset={key: tuple(value) for key, value in events_by_asset.items()},
        tracks_by_id={track.track_id: track for track in evidence.tracks},
        assets_by_id={asset.companion_asset_id: asset for asset in evidence.companion_assets},
    )


def _recoverable_companion(  # noqa: C901, PLR0911, PLR0912  # Each provenance boundary fails closed.
    plan: Plan,
    action: PlanAction,
    history: _RecoveryHistory,
) -> RecoverableCompanion | None:
    if not _failed_action_header_is_valid(plan, action):
        return None
    runs = history.runs_by_plan.get(plan.plan_id, ())
    if len(runs) != 1:
        return None
    run = runs[0]
    if (
        run.library_id != plan.library_id
        or run.status not in _FAILED_RUN_STATUSES
        or run.completed_at is None
        or run.started_at < plan.created_at
    ):
        return None

    companion_asset_id = action.companion_asset_id
    owner_action_id = action.owner_action_id
    source_path = action.source_path
    content_hash = action.content_hash_at_plan
    if companion_asset_id is None or owner_action_id is None or source_path is None or content_hash is None:
        return None
    action_events = tuple(
        event for event in history.events_by_run.get(run.run_id, ()) if event.plan_action_id == action.action_id
    )
    if len(action_events) != 1 or not _failed_event_is_valid(action, run, action_events[0]):
        return None
    failed_event = action_events[0]
    if not (
        run.started_at <= failed_event.started_at
        and failed_event.completed_at is not None
        and failed_event.completed_at <= run.completed_at
    ):
        return None

    actions = history.actions_by_plan.get(plan.plan_id, ())
    actions_by_id = {candidate.action_id: candidate for candidate in actions}
    dependencies = history.dependencies_by_action.get(action.action_id, ())
    dependency_ids = tuple(dependency.depends_on_action_id for dependency in dependencies)
    if (
        len(dependency_ids) == 0
        or len(set(dependency_ids)) != len(dependency_ids)
        or any(
            dependency.plan_id != plan.plan_id or dependency.action_id != action.action_id
            for dependency in dependencies
        )
        or owner_action_id not in dependency_ids
    ):
        return None

    events_by_action: dict[ActionId, list[FileEvent]] = defaultdict(list)
    for event in history.events_by_run.get(run.run_id, ()):
        events_by_action[event.plan_action_id].append(event)

    dependency_tracks: list[Track] = []
    for dependency_id in dependency_ids:
        dependency_action = actions_by_id.get(dependency_id)
        if dependency_action is None:
            return None
        dependency_events = events_by_action.get(dependency_id, ())
        if len(dependency_events) != 1:
            return None
        track = _succeeded_audio_track(plan, dependency_action, run, dependency_events[0], history)
        if track is None:
            return None
        dependency_tracks.append(track)

    owner_action = actions_by_id.get(owner_action_id)
    if owner_action is None or owner_action.track_id is None:
        return None
    owner_track = history.tracks_by_id.get(owner_action.track_id)
    if (
        owner_track is None
        or owner_track not in dependency_tracks
        or (action.track_id is not None and action.track_id != owner_track.track_id)
    ):
        return None
    if len({track.track_id for track in dependency_tracks}) != len(dependency_tracks):
        return None

    target_path = _current_target_path(action, owner_track, tuple(dependency_tracks))
    if target_path is None:
        return None
    existing_asset = history.assets_by_id.get(companion_asset_id)
    if existing_asset is not None and not _existing_asset_is_valid(action, owner_track, existing_asset):
        return None

    return RecoverableCompanion(
        source_plan_id=plan.plan_id,
        library_id=plan.library_id,
        source_plan_type=plan.plan_type,
        source_root=plan.source_root_at_plan,
        source_path=source_path,
        target_path=target_path,
        content_hash=content_hash,
        kind=_companion_kind(action.action_type),
        companion_asset_id=companion_asset_id,
        owner_track_id=owner_track.track_id,
        dependency_track_ids=tuple(track.track_id for track in dependency_tracks),
    )


def _failed_action_header_is_valid(plan: Plan, action: PlanAction) -> bool:
    if (
        plan.status not in _FAILED_PLAN_STATUSES
        or plan.plan_type not in {PlanType.ADD, PlanType.ORGANIZE, PlanType.REFRESH}
        or action.plan_id != plan.plan_id
        or action.library_id != plan.library_id
        or action.action_type not in _COMPANION_ACTION_TYPES
        or action.status is not ActionStatus.FAILED
        or action.owner_action_id is None
        or action.source_path is None
        or action.target_path is None
        or action.content_hash_at_plan is None
        or action.metadata_hash_at_plan is not None
        or action.companion_asset_id is None
        or PurePath(action.target_path).is_absolute()
    ):
        return False
    source_is_absolute = PurePath(action.source_path).is_absolute()
    if plan.plan_type is PlanType.ADD:
        return (
            source_is_absolute
            and plan.source_root_at_plan is not None
            and PurePath(plan.source_root_at_plan).is_absolute()
            and _path_is_within_root(action.source_path, plan.source_root_at_plan)
        )
    return not source_is_absolute and plan.source_root_at_plan is None


def _failed_event_is_valid(action: PlanAction, run: Run, event: FileEvent) -> bool:
    return (
        event.run_id == run.run_id
        and event.library_id == action.library_id
        and event.plan_action_id == action.action_id
        and event.event_type is _EVENT_TYPE_BY_ACTION_TYPE[action.action_type]
        and event.source_path == action.source_path
        and event.target_path == action.target_path
        and event.status is FileEventStatus.FAILED
        and event.completed_at is not None
        and event.companion_asset_id == action.companion_asset_id
    )


def _asset_failure_chain_is_valid(  # noqa: C901, PLR0911, PLR0912  # Every retry boundary fails closed.
    recovery: RecoverableCompanion,
    history: _RecoveryHistory,
) -> bool:
    asset_events = history.events_by_asset.get(recovery.companion_asset_id, ())
    all_asset_actions = tuple(
        action for action in history.actions_by_id.values() if action.companion_asset_id == recovery.companion_asset_id
    )
    anchor_action = next(
        (
            action
            for action in all_asset_actions
            if action.plan_id == recovery.source_plan_id and action.owner_action_id is not None
        ),
        None,
    )
    anchor_event = next(
        (
            event
            for event in asset_events
            if anchor_action is not None and event.plan_action_id == anchor_action.action_id
        ),
        None,
    )
    anchor_plan = history.plans_by_id.get(recovery.source_plan_id)
    if (
        anchor_action is None
        or anchor_event is None
        or anchor_event.completed_at is None
        or anchor_plan is None
        or any(event.status is FileEventStatus.PENDING for event in asset_events)
    ):
        return False

    prior_actions: list[PlanAction] = []
    retry_actions: list[PlanAction] = []
    for action in all_asset_actions:
        plan = history.plans_by_id.get(action.plan_id)
        if plan is None:
            return False
        if plan.status in {PlanStatus.READY, PlanStatus.APPLYING}:
            return False
        if plan.status in {PlanStatus.CANCELLED, PlanStatus.EXPIRED}:
            continue
        if plan.is_terminal and action.status is ActionStatus.BLOCKED:
            continue
        if (
            action.action_id != anchor_action.action_id
            and plan.plan_id != anchor_plan.plan_id
            and plan.created_at < anchor_event.completed_at
        ):
            prior_actions.append(action)
            continue
        retry_actions.append(action)

    prior_action_ids = {action.action_id for action in prior_actions}
    retry_action_ids = {action.action_id for action in retry_actions}
    retry_events = tuple(event for event in asset_events if event.plan_action_id in retry_action_ids)
    prior_events = tuple(event for event in asset_events if event.plan_action_id not in retry_action_ids)
    if (
        len(retry_events) == 0
        or len({event.plan_action_id for event in retry_events}) != len(retry_events)
        or {event.plan_action_id for event in retry_events} != retry_action_ids
        or any(event.status is not FileEventStatus.FAILED for event in retry_events)
        or len({event.plan_action_id for event in prior_events}) != len(prior_events)
        or {event.plan_action_id for event in prior_events} != prior_action_ids
        or any(
            not _prior_asset_event_is_valid(
                history.actions_by_id[event.plan_action_id],
                event,
                anchor_plan.created_at,
                history,
            )
            for event in prior_events
        )
    ):
        return False

    for event in retry_events:
        action = history.actions_by_id.get(event.plan_action_id)
        run = history.runs_by_id.get(event.run_id)
        if action is None or run is None:
            return False
        plan = history.plans_by_id.get(action.plan_id)
        if plan is None or len(history.runs_by_plan.get(plan.plan_id, ())) != 1:
            return False
        if event.plan_action_id == anchor_action.action_id:
            continue
        if not _retry_failure_is_valid(
            recovery,
            plan,
            action,
            run,
            event,
            anchor_event.completed_at,
            history,
        ):
            return False
    return True


def _prior_asset_event_is_valid(
    action: PlanAction,
    event: FileEvent,
    anchor_created_at: datetime,
    history: _RecoveryHistory,
) -> bool:
    plan = history.plans_by_id.get(action.plan_id)
    run = history.runs_by_id.get(event.run_id)
    completed_at = event.completed_at
    if (
        plan is None
        or run is None
        or completed_at is None
        or run.completed_at is None
        or len(history.runs_by_plan.get(plan.plan_id, ())) != 1
        or action.action_type not in _COMPANION_ACTION_TYPES
    ):
        return False
    expected_status = (
        FileEventStatus.SUCCEEDED
        if action.status is ActionStatus.APPLIED
        else FileEventStatus.FAILED
        if action.status is ActionStatus.FAILED
        else None
    )
    return (
        expected_status is not None
        and plan.is_terminal
        and run.status is not RunStatus.RUNNING
        and run.plan_id == plan.plan_id
        and run.library_id == plan.library_id == action.library_id == event.library_id
        and plan.created_at <= run.started_at <= event.started_at <= completed_at
        and completed_at <= run.completed_at <= anchor_created_at
        and event.plan_action_id == action.action_id
        and event.event_type is _EVENT_TYPE_BY_ACTION_TYPE[action.action_type]
        and event.source_path == action.source_path
        and event.target_path == action.target_path
        and event.status is expected_status
        and event.companion_asset_id == action.companion_asset_id
    )


def _retry_failure_is_valid(  # noqa: PLR0913  # Retry provenance fields remain explicit.
    recovery: RecoverableCompanion,
    plan: Plan,
    action: PlanAction,
    run: Run,
    event: FileEvent,
    anchor_completed_at: datetime,
    history: _RecoveryHistory,
) -> bool:
    completed_at = event.completed_at
    if completed_at is None:
        return False
    source_scope_is_valid = (
        plan.plan_type is PlanType.ADD
        and recovery.source_root is not None
        and plan.source_root_at_plan == recovery.source_root
        and PurePath(action.source_path or "").is_absolute()
    ) or (
        plan.plan_type in {PlanType.ORGANIZE, PlanType.REFRESH}
        and recovery.source_root is None
        and plan.source_root_at_plan is None
        and not PurePath(action.source_path or "").is_absolute()
    )
    return (
        source_scope_is_valid
        and plan.library_id == recovery.library_id
        and plan.status in _FAILED_PLAN_STATUSES
        and plan.created_at >= anchor_completed_at
        and action.plan_id == plan.plan_id
        and action.library_id == recovery.library_id
        and action.action_type is _action_type(recovery.kind)
        and action.status is ActionStatus.FAILED
        and action.source_path == recovery.source_path
        and action.target_path is not None
        and not PurePath(action.target_path).is_absolute()
        and action.content_hash_at_plan == recovery.content_hash
        and action.metadata_hash_at_plan is None
        and action.companion_asset_id == recovery.companion_asset_id
        and action.track_id == recovery.owner_track_id
        and action.owner_action_id is None
        and len(history.dependencies_by_action.get(action.action_id, ())) == 0
        and run.plan_id == plan.plan_id
        and run.library_id == recovery.library_id
        and run.status in _FAILED_RUN_STATUSES
        and run.completed_at is not None
        and plan.created_at <= run.started_at <= event.started_at
        and _failed_event_is_valid(action, run, event)
        and completed_at <= run.completed_at
        and completed_at >= anchor_completed_at
    )


def _succeeded_audio_track(
    plan: Plan,
    action: PlanAction,
    run: Run,
    event: FileEvent,
    history: _RecoveryHistory,
) -> Track | None:
    if action.track_id is None:
        return None
    track = history.tracks_by_id.get(action.track_id)
    if (
        action.plan_id != plan.plan_id
        or action.library_id != plan.library_id
        or action.action_type is not ActionType.MOVE
        or action.status is not ActionStatus.APPLIED
        or action.source_path is None
        or action.target_path is None
        or PurePath(action.target_path).is_absolute()
        or event.run_id != run.run_id
        or event.library_id != plan.library_id
        or event.plan_action_id != action.action_id
        or event.event_type is not FileEventType.MOVE_FILE
        or event.source_path != action.source_path
        or event.target_path != action.target_path
        or event.status is not FileEventStatus.SUCCEEDED
        or event.completed_at is None
        or run.completed_at is None
        or not (run.started_at <= event.started_at <= event.completed_at <= run.completed_at)
        or event.companion_asset_id is not None
        or track is None
        or track.library_id != plan.library_id
        or track.status is not TrackStatus.ACTIVE
    ):
        return None
    return track


def _current_target_path(
    action: PlanAction,
    owner_track: Track,
    dependency_tracks: tuple[Track, ...],
) -> str | None:
    if action.action_type is ActionType.MOVE_LYRICS:
        return PurePosixPath(owner_track.current_path).with_suffix(".lrc").as_posix()
    target_parents = {PurePosixPath(track.current_path).parent for track in dependency_tracks}
    if len(target_parents) != 1:
        return None
    source_name = PurePosixPath(action.source_path or "").name
    if source_name == "":
        return None
    return (target_parents.pop() / source_name).as_posix()


def _existing_asset_is_valid(
    action: PlanAction,
    owner_track: Track,
    asset: CompanionAsset,
) -> bool:
    return (
        asset.library_id == action.library_id
        and asset.kind is _companion_kind(action.action_type)
        and asset.owner_track_id == owner_track.track_id
        and asset.current_path == action.source_path
        and asset.content_hash == action.content_hash_at_plan
        and asset.status is CompanionAssetStatus.ACTIVE
    )


def _companion_kind(action_type: ActionType) -> CompanionAssetKind:
    if action_type is ActionType.MOVE_LYRICS:
        return CompanionAssetKind.LYRICS
    return CompanionAssetKind.ARTWORK


def _action_type(kind: CompanionAssetKind) -> ActionType:
    if kind is CompanionAssetKind.LYRICS:
        return ActionType.MOVE_LYRICS
    return ActionType.MOVE_ARTWORK


def _path_is_within_root(path: str, root: str) -> bool:
    try:
        _ = PurePath(path).relative_to(PurePath(root))
    except ValueError:
        return False
    return True
