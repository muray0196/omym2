"""
Summary: Implements refresh Plan creation for managed Library Tracks.
Why: Relocates files after tag correction without direct file mutation.
"""

from __future__ import annotations

from dataclasses import dataclass, replace
from pathlib import PurePath
from typing import TYPE_CHECKING

from omym2.config import PLAN_ACTION_SORT_ORDER_START, PLAN_ACTION_SORT_ORDER_STEP
from omym2.domain.models.library import LibraryStatus
from omym2.domain.models.plan import Plan, PlanStatus, PlanType
from omym2.domain.models.plan_action import ActionStatus, ActionType, PlanAction, PlanActionReason
from omym2.domain.models.track import TrackStatus
from omym2.domain.services.config_fingerprint import calculate_config_fingerprint, calculate_path_policy_fingerprint
from omym2.domain.services.path_policy import MISSING_TITLE_MESSAGE, PathPolicy
from omym2.shared.paths import normalize_library_relative_path

if TYPE_CHECKING:
    from collections.abc import Sequence
    from datetime import datetime

    from omym2.domain.models.app_config import AppConfig
    from omym2.domain.models.file_snapshot import FileSnapshot
    from omym2.domain.models.library import Library
    from omym2.domain.models.track import Track
    from omym2.features.common_ports import UnitOfWork
    from omym2.features.refresh.dto import CreateRefreshPlanRequest
    from omym2.features.refresh.ports import CreateRefreshPlanPorts
    from omym2.shared.ids import PlanId

AMBIGUOUS_REGISTERED_LIBRARY_MESSAGE = (
    "Multiple registered Libraries exist. Library selection is not supported for refresh yet."
)
NO_REGISTERED_LIBRARY_MESSAGE = "No registered Library can be selected. Run organize --library PATH."
REFRESH_TARGET_NOT_FOUND_MESSAGE = "Refresh target does not match any managed active Track."
SELECTED_LIBRARY_NOT_FOUND_MESSAGE = "Selected Library was not found."
SELECTED_LIBRARY_NOT_REGISTERED_MESSAGE = "Selected Library is not registered. Run organize --library PATH."
STALE_LIBRARY_MESSAGE = "Registered Library uses a stale PathPolicy. Run organize --library PATH."
TARGET_OUTSIDE_LIBRARY_MESSAGE = "Refresh target must be inside the selected Library."
TARGET_SELECTOR_COUNT_MESSAGE = "Refresh requires exactly one target: track_id, target_path, or include_all."
SUMMARY_ACTION_COUNT_KEY = "action_count"
SUMMARY_BLOCKED_ACTIONS_KEY = "blocked_actions"
SUMMARY_MOVE_ACTIONS_KEY = "move_actions"


@dataclass(frozen=True, slots=True)
class CreateRefreshPlanUseCase:
    """Create refresh relocation Plans without moving Library music files."""

    ports: CreateRefreshPlanPorts

    def execute(self, request: CreateRefreshPlanRequest) -> Plan:
        """Create a refresh Plan for selected managed Tracks."""
        _require_one_target_selector(request)
        config = self.ports.config_store.load()
        config_hash = calculate_config_fingerprint(config)
        path_policy_hash = calculate_path_policy_fingerprint(config.path_policy)
        timestamp = self.ports.clock.now()

        with self.ports.uow as uow:
            library = _select_registered_library(uow, request, path_policy_hash)
            active_tracks = tuple(
                track for track in uow.tracks.list_by_library(library.library_id) if track.status == TrackStatus.ACTIVE
            )
            selected_tracks = self._selected_tracks(request, library, active_tracks)
            candidates = tuple(self._candidate(library, track, config) for track in selected_tracks)
            candidates = self._with_target_conflicts(library, candidates, active_tracks)
            plan_id = self.ports.id_generator.new_plan_id()
            actions = self._actions(plan_id, library, candidates)
            plan = _plan(plan_id, library, actions, config_hash, timestamp)

            uow.plans.save(plan)
            for action in actions:
                uow.plan_actions.save(action)

            uow.commit()
            return plan

    def _selected_tracks(
        self,
        request: CreateRefreshPlanRequest,
        library: Library,
        active_tracks: Sequence[Track],
    ) -> tuple[Track, ...]:
        if request.include_all:
            return _require_matches(tuple(active_tracks))

        if request.track_id is not None:
            return _require_matches(tuple(track for track in active_tracks if track.track_id == request.track_id))

        target_path = request.target_path
        if target_path is None:
            raise RefreshTargetSelectionError(TARGET_SELECTOR_COUNT_MESSAGE)

        relative_target = _target_relative_path(self.ports, library, target_path)
        exact_matches = tuple(track for track in active_tracks if track.current_path == relative_target)
        if len(exact_matches) > 0:
            return exact_matches

        prefix = f"{relative_target}/"
        return _require_matches(tuple(track for track in active_tracks if track.current_path.startswith(prefix)))

    def _candidate(self, library: Library, track: Track, config: AppConfig) -> _RefreshCandidate:
        source_filesystem_path = self.ports.path_resolver.resolve_library_path(library.root_path, track.current_path)

        try:
            snapshot = self.ports.file_snapshot_reader.capture(source_filesystem_path)
        except FileNotFoundError:
            return _blocked_candidate(track, PlanActionReason.SOURCE_MISSING)

        if _has_missing_required_metadata(snapshot, config):
            return _blocked_candidate(track, PlanActionReason.MISSING_REQUIRED_METADATA, snapshot=snapshot)

        try:
            target_path = PathPolicy(config.path_policy).canonical_path(snapshot.metadata, snapshot.file_extension)
        except ValueError as exc:
            return _blocked_candidate(track, _path_generation_failure_reason(exc), snapshot=snapshot)

        return _RefreshCandidate(
            track=track,
            snapshot=snapshot,
            target_path=target_path,
            reason=None,
            needs_action=target_path != track.current_path,
        )

    def _with_target_conflicts(
        self,
        library: Library,
        candidates: Sequence[_RefreshCandidate],
        active_tracks: Sequence[Track],
    ) -> tuple[_RefreshCandidate, ...]:
        occupied_paths = {track.current_path for track in active_tracks}
        target_sources = _move_target_sources(candidates)
        judged_candidates: list[_RefreshCandidate] = []

        for candidate in candidates:
            if self._has_target_conflict(library, candidate, occupied_paths, target_sources):
                judged_candidates.append(replace(candidate, reason=PlanActionReason.TARGET_EXISTS))
            else:
                judged_candidates.append(candidate)

        return tuple(judged_candidates)

    def _has_target_conflict(
        self,
        library: Library,
        candidate: _RefreshCandidate,
        occupied_paths: set[str],
        target_sources: dict[str, tuple[str, ...]],
    ) -> bool:
        target_path = candidate.target_path
        if not candidate.needs_action or candidate.reason is not None or target_path is None:
            return False
        if target_path in occupied_paths and target_path != candidate.track.current_path:
            return True
        if len(target_sources[target_path]) > 1:
            return True

        target_filesystem_path = self.ports.path_resolver.resolve_library_path(library.root_path, target_path)
        return self.ports.file_presence.exists(target_filesystem_path)

    def _actions(
        self,
        plan_id: PlanId,
        library: Library,
        candidates: Sequence[_RefreshCandidate],
    ) -> tuple[PlanAction, ...]:
        actions: list[PlanAction] = []
        sort_order = PLAN_ACTION_SORT_ORDER_START

        for candidate in candidates:
            if not candidate.needs_action:
                continue

            snapshot = candidate.snapshot
            actions.append(
                PlanAction(
                    action_id=self.ports.id_generator.new_action_id(),
                    plan_id=plan_id,
                    library_id=library.library_id,
                    track_id=candidate.track.track_id,
                    action_type=ActionType.MOVE,
                    source_path=candidate.track.current_path,
                    target_path=candidate.target_path,
                    content_hash_at_plan=None if snapshot is None else snapshot.content_hash,
                    metadata_hash_at_plan=None if snapshot is None else snapshot.metadata_hash,
                    status=ActionStatus.PLANNED if candidate.reason is None else ActionStatus.BLOCKED,
                    reason=candidate.reason,
                    sort_order=sort_order,
                )
            )
            sort_order += PLAN_ACTION_SORT_ORDER_STEP

        return tuple(actions)


class RefreshLibrarySelectionError(ValueError):
    """Raised when refresh cannot select a registered Library."""


class RefreshTargetSelectionError(ValueError):
    """Raised when refresh cannot select managed active Tracks."""


@dataclass(frozen=True, slots=True)
class _RefreshCandidate:
    """One managed Track and its plan-time refresh judgment."""

    track: Track
    snapshot: FileSnapshot | None
    target_path: str | None
    reason: PlanActionReason | None
    needs_action: bool


def _require_one_target_selector(request: CreateRefreshPlanRequest) -> None:
    selector_count = sum(
        (
            request.track_id is not None,
            request.target_path is not None,
            request.include_all,
        )
    )
    if selector_count != 1:
        raise RefreshTargetSelectionError(TARGET_SELECTOR_COUNT_MESSAGE)


def _select_registered_library(
    uow: UnitOfWork,
    request: CreateRefreshPlanRequest,
    path_policy_hash: str,
) -> Library:
    if request.library_id is not None:
        library = uow.libraries.get(request.library_id)
        if library is None:
            raise RefreshLibrarySelectionError(SELECTED_LIBRARY_NOT_FOUND_MESSAGE)
        return _require_registered_current_library(library, path_policy_hash)

    registered_libraries = tuple(
        library for library in uow.libraries.list_all() if library.status == LibraryStatus.REGISTERED
    )
    if len(registered_libraries) == 0:
        raise RefreshLibrarySelectionError(NO_REGISTERED_LIBRARY_MESSAGE)
    if len(registered_libraries) > 1:
        raise RefreshLibrarySelectionError(AMBIGUOUS_REGISTERED_LIBRARY_MESSAGE)
    return _require_registered_current_library(registered_libraries[0], path_policy_hash)


def _require_registered_current_library(library: Library, path_policy_hash: str) -> Library:
    if library.status != LibraryStatus.REGISTERED:
        raise RefreshLibrarySelectionError(SELECTED_LIBRARY_NOT_REGISTERED_MESSAGE)
    if library.path_policy_hash != path_policy_hash:
        raise RefreshLibrarySelectionError(STALE_LIBRARY_MESSAGE)
    return library


def _target_relative_path(ports: CreateRefreshPlanPorts, library: Library, target_path: str) -> str:
    try:
        if PurePath(target_path).is_absolute():
            return ports.path_resolver.relative_to_library(library.root_path, target_path)
        return normalize_library_relative_path(target_path)
    except ValueError as exc:
        raise RefreshTargetSelectionError(TARGET_OUTSIDE_LIBRARY_MESSAGE) from exc


def _require_matches(tracks: tuple[Track, ...]) -> tuple[Track, ...]:
    if len(tracks) == 0:
        raise RefreshTargetSelectionError(REFRESH_TARGET_NOT_FOUND_MESSAGE)
    return tracks


def _blocked_candidate(
    track: Track,
    reason: PlanActionReason,
    *,
    snapshot: FileSnapshot | None = None,
) -> _RefreshCandidate:
    return _RefreshCandidate(
        track=track,
        snapshot=snapshot,
        target_path=None,
        reason=reason,
        needs_action=True,
    )


def _move_target_sources(candidates: Sequence[_RefreshCandidate]) -> dict[str, tuple[str, ...]]:
    grouped: dict[str, list[str]] = {}
    for candidate in candidates:
        if not candidate.needs_action or candidate.reason is not None or candidate.target_path is None:
            continue
        grouped.setdefault(candidate.target_path, []).append(candidate.track.current_path)
    return {target_path: tuple(source_paths) for target_path, source_paths in grouped.items()}


def _plan(
    plan_id: PlanId,
    library: Library,
    actions: Sequence[PlanAction],
    config_hash: str,
    timestamp: datetime,
) -> Plan:
    move_count = sum(action.status == ActionStatus.PLANNED for action in actions)
    blocked_count = sum(action.status == ActionStatus.BLOCKED for action in actions)
    return Plan(
        plan_id=plan_id,
        library_id=library.library_id,
        plan_type=PlanType.REFRESH,
        status=PlanStatus.READY,
        created_at=timestamp,
        config_hash=config_hash,
        library_root_at_plan=library.root_path,
        summary={
            SUMMARY_ACTION_COUNT_KEY: str(len(actions)),
            SUMMARY_MOVE_ACTIONS_KEY: str(move_count),
            SUMMARY_BLOCKED_ACTIONS_KEY: str(blocked_count),
        },
        actions=tuple(actions),
    )


def _has_missing_required_metadata(snapshot: FileSnapshot, config: AppConfig) -> bool:
    metadata = snapshot.metadata
    if config.metadata.require_title and _missing_text(metadata.title):
        return True
    # Artist identity can come from either track artist or album artist.
    if config.metadata.require_artist and _missing_text(metadata.artist) and _missing_text(metadata.album_artist):
        return True
    return config.metadata.require_album and _missing_text(metadata.album)


def _missing_text(value: str | None) -> bool:
    return value is None or value.strip() == ""


def _path_generation_failure_reason(exc: ValueError) -> PlanActionReason:
    if str(exc) == MISSING_TITLE_MESSAGE:
        return PlanActionReason.MISSING_REQUIRED_METADATA
    return PlanActionReason.INVALID_PATH
