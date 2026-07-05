"""
Summary: Implements add Plan creation for registered Libraries.
Why: Lets users review incoming imports before any Library file mutation.
"""

from __future__ import annotations

from dataclasses import dataclass, replace
from pathlib import Path
from typing import TYPE_CHECKING

from omym2.config import PLAN_ACTION_SORT_ORDER_START, PLAN_ACTION_SORT_ORDER_STEP
from omym2.domain.models.library import Library, LibraryStatus
from omym2.domain.models.plan import Plan, PlanStatus, PlanType
from omym2.domain.models.plan_action import ActionStatus, ActionType, PlanAction, PlanActionReason
from omym2.domain.models.track import TrackStatus
from omym2.domain.services.album_disc import infer_album_disc_totals
from omym2.domain.services.collision_policy import CollisionDecisionKind, CollisionPolicy, OccupiedPaths
from omym2.domain.services.config_fingerprint import (
    STALE_LIBRARY_MESSAGE as STALE_LIBRARY_MESSAGE,  # noqa: PLC0414 - re-exported for existing test imports.
)
from omym2.domain.services.config_fingerprint import (
    calculate_config_fingerprint,
    calculate_path_policy_fingerprint,
    is_path_policy_stale,
)
from omym2.domain.services.path_policy import MISSING_TITLE_MESSAGE, PathPolicy

if TYPE_CHECKING:
    from collections.abc import Sequence
    from datetime import datetime

    from omym2.domain.models.app_config import AppConfig
    from omym2.domain.models.file_scan_entry import FileScanEntry
    from omym2.domain.models.file_snapshot import FileSnapshot
    from omym2.domain.models.track import Track
    from omym2.domain.services.album_disc import AlbumDiscTotals
    from omym2.features.add.dto import CreateAddPlanRequest
    from omym2.features.add.ports import CreateAddPlanPorts
    from omym2.features.common_ports import UnitOfWork
    from omym2.shared.ids import PlanId, TrackId

AMBIGUOUS_REGISTERED_LIBRARY_MESSAGE = (
    "Multiple registered Libraries exist. Library selection is not supported for add yet."
)
NO_INCOMING_SOURCE_MESSAGE = "No Incoming path is configured. Use add SOURCE_DIR."
NO_REGISTERED_LIBRARY_MESSAGE = "No registered Library can be selected. Run organize --library PATH."
SUMMARY_ACTION_COUNT_KEY = "action_count"
SUMMARY_BLOCKED_ACTIONS_KEY = "blocked_actions"
SUMMARY_MOVE_ACTIONS_KEY = "move_actions"
SUMMARY_SKIP_ACTIONS_KEY = "skip_actions"


@dataclass(frozen=True, slots=True)
class CreateAddPlanUseCase:
    """Create reviewed add Plans without moving Library music files."""

    ports: CreateAddPlanPorts

    def execute(self, request: CreateAddPlanRequest) -> Plan:
        """Create an add Plan from Incoming or an explicit source."""
        config = self.ports.config_store.load()
        source_root = _source_root(request, config)
        config_hash = calculate_config_fingerprint(config)
        path_policy_hash = calculate_path_policy_fingerprint(config.path_policy, config.artist_ids)
        path_policy = PathPolicy.from_app_config(config)
        timestamp = self.ports.clock.now()

        with self.ports.uow as uow:
            library = _select_registered_library(uow, path_policy_hash)
            library_tracks = tuple(uow.tracks.list_by_library(library.library_id))
            duplicate_track_by_hash = _duplicate_track_by_hash(library_tracks)
            scan_entries = self.ports.file_scanner.scan(source_root)
            captured_candidates = tuple(self._candidate(entry, config) for entry in scan_entries)
            active_library_metadata = tuple(
                track.metadata for track in library_tracks if track.status == TrackStatus.ACTIVE
            )
            album_disc_totals = infer_album_disc_totals(
                (
                    *(
                        candidate.snapshot.metadata
                        for candidate in captured_candidates
                        if candidate.snapshot is not None
                    ),
                    *active_library_metadata,
                ),
                unknown_artist=config.path_policy.unknown_artist,
                unknown_album=config.path_policy.unknown_album,
            )
            candidates = tuple(
                self._with_target_path(candidate, path_policy, duplicate_track_by_hash, album_disc_totals)
                for candidate in captured_candidates
            )
            candidates = self._with_target_conflicts(library, candidates, library_tracks)
            plan_id = self.ports.id_generator.new_plan_id()
            actions = self._actions(plan_id, library, candidates)
            plan = _plan(plan_id, library, actions, config_hash, timestamp)

            uow.plans.save(plan)
            for action in actions:
                uow.plan_actions.save(action)

            uow.commit()
            return plan

    def _with_target_conflicts(
        self,
        library: Library,
        candidates: Sequence[_AddCandidate],
        tracks: Sequence[Track],
    ) -> tuple[_AddCandidate, ...]:
        occupied_paths = OccupiedPaths.from_paths(track.current_path for track in tracks)
        target_sources = _move_target_sources(candidates)
        judged_candidates: list[_AddCandidate] = []

        for candidate in candidates:
            if self._has_target_conflict(library, candidate, occupied_paths, target_sources):
                judged_candidates.append(replace(candidate, reason=PlanActionReason.TARGET_EXISTS))
            else:
                judged_candidates.append(candidate)

        return tuple(judged_candidates)

    def _has_target_conflict(
        self,
        library: Library,
        candidate: _AddCandidate,
        occupied_paths: OccupiedPaths,
        target_sources: dict[str, tuple[str, ...]],
    ) -> bool:
        target_path = candidate.target_path
        if candidate.action_type != ActionType.MOVE or candidate.reason is not None or target_path is None:
            return False

        decision = CollisionPolicy().decide(
            target_path,
            occupied_paths,
            batch_target_count=len(target_sources[target_path]),
        )
        if decision.kind is CollisionDecisionKind.BLOCKED:
            return True

        target_filesystem_path = self.ports.path_resolver.resolve_library_path(library.root_path, target_path)
        return self.ports.file_presence.exists(target_filesystem_path)

    def _candidate(
        self,
        entry: FileScanEntry,
        config: AppConfig,
    ) -> _AddCandidate:
        source_path = _normalize_external_source_path(entry.path)
        try:
            snapshot = self.ports.file_snapshot_reader.capture(entry.path)
        except FileNotFoundError:
            return _blocked_candidate(source_path, PlanActionReason.SOURCE_MISSING)

        if _source_changed(entry, snapshot):
            return _blocked_candidate(source_path, PlanActionReason.SOURCE_CHANGED, snapshot=snapshot)

        if _has_missing_required_metadata(snapshot, config):
            return _blocked_candidate(source_path, PlanActionReason.MISSING_REQUIRED_METADATA, snapshot=snapshot)

        return _AddCandidate(
            source_path=source_path,
            snapshot=snapshot,
            target_path=None,
            action_type=ActionType.MOVE,
            reason=None,
            track_id=None,
        )

    def _with_target_path(
        self,
        candidate: _AddCandidate,
        path_policy: PathPolicy,
        duplicate_track_by_hash: dict[str, Track],
        album_disc_totals: AlbumDiscTotals,
    ) -> _AddCandidate:
        snapshot = candidate.snapshot
        if candidate.reason is not None or snapshot is None:
            return candidate

        try:
            target_path = path_policy.canonical_path(
                snapshot.metadata,
                snapshot.file_extension,
                album_disc_total=album_disc_totals.for_metadata(snapshot.metadata),
            )
        except ValueError as exc:
            return _blocked_candidate(candidate.source_path, _path_generation_failure_reason(exc), snapshot=snapshot)

        duplicate_track = duplicate_track_by_hash.get(snapshot.content_hash)
        if duplicate_track is not None:
            return _AddCandidate(
                source_path=candidate.source_path,
                snapshot=snapshot,
                target_path=target_path,
                action_type=ActionType.SKIP,
                reason=PlanActionReason.DUPLICATE_HASH,
                track_id=duplicate_track.track_id,
            )

        return _AddCandidate(
            source_path=candidate.source_path,
            snapshot=snapshot,
            target_path=target_path,
            action_type=ActionType.MOVE,
            reason=None,
            track_id=None,
        )

    def _actions(
        self,
        plan_id: PlanId,
        library: Library,
        candidates: Sequence[_AddCandidate],
    ) -> tuple[PlanAction, ...]:
        actions: list[PlanAction] = []
        sort_order = PLAN_ACTION_SORT_ORDER_START

        for candidate in candidates:
            snapshot = candidate.snapshot
            actions.append(
                PlanAction(
                    action_id=self.ports.id_generator.new_action_id(),
                    plan_id=plan_id,
                    library_id=library.library_id,
                    track_id=candidate.track_id,
                    action_type=candidate.action_type,
                    source_path=candidate.source_path,
                    target_path=candidate.target_path,
                    content_hash_at_plan=None if snapshot is None else snapshot.content_hash,
                    metadata_hash_at_plan=None if snapshot is None else snapshot.metadata_hash,
                    status=_action_status(candidate),
                    reason=candidate.reason,
                    sort_order=sort_order,
                )
            )
            sort_order += PLAN_ACTION_SORT_ORDER_STEP

        return tuple(actions)


class AddLibrarySelectionError(ValueError):
    """Raised when add cannot select exactly one current registered Library."""


class AddSourceSelectionError(ValueError):
    """Raised when add cannot determine the incoming source directory."""


@dataclass(frozen=True, slots=True)
class _AddCandidate:
    """One scanned incoming file and its plan-time add judgment."""

    source_path: str
    snapshot: FileSnapshot | None
    target_path: str | None
    action_type: ActionType
    reason: PlanActionReason | None
    track_id: TrackId | None


def _source_root(request: CreateAddPlanRequest, config: AppConfig) -> str:
    if request.source_path is not None:
        return _normalize_external_source_path(request.source_path)
    if config.paths.incoming is not None:
        return _normalize_external_source_path(config.paths.incoming)
    raise AddSourceSelectionError(NO_INCOMING_SOURCE_MESSAGE)


def _normalize_external_source_path(raw_path: str) -> str:
    return str(Path(raw_path).expanduser().resolve(strict=False))


def _select_registered_library(uow: UnitOfWork, path_policy_hash: str) -> Library:
    registered_libraries = tuple(
        library for library in uow.libraries.list_all() if library.status == LibraryStatus.REGISTERED
    )
    if len(registered_libraries) == 0:
        raise AddLibrarySelectionError(NO_REGISTERED_LIBRARY_MESSAGE)
    if len(registered_libraries) > 1:
        raise AddLibrarySelectionError(AMBIGUOUS_REGISTERED_LIBRARY_MESSAGE)

    library = registered_libraries[0]
    if is_path_policy_stale(library.path_policy_hash, path_policy_hash):
        raise AddLibrarySelectionError(STALE_LIBRARY_MESSAGE)
    return library


def _blocked_candidate(
    source_path: str,
    reason: PlanActionReason,
    *,
    snapshot: FileSnapshot | None = None,
) -> _AddCandidate:
    return _AddCandidate(
        source_path=source_path,
        snapshot=snapshot,
        target_path=None,
        action_type=ActionType.MOVE,
        reason=reason,
        track_id=None,
    )


def _duplicate_track_by_hash(tracks: Sequence[Track]) -> dict[str, Track]:
    """Map each content hash to its first Track in repository list order."""
    duplicate_track_by_hash: dict[str, Track] = {}
    for track in tracks:
        _ = duplicate_track_by_hash.setdefault(track.content_hash, track)
    return duplicate_track_by_hash


def _move_target_sources(candidates: Sequence[_AddCandidate]) -> dict[str, tuple[str, ...]]:
    grouped: dict[str, list[str]] = {}
    for candidate in candidates:
        if candidate.action_type != ActionType.MOVE or candidate.reason is not None or candidate.target_path is None:
            continue
        grouped.setdefault(candidate.target_path, []).append(candidate.source_path)
    return {target_path: tuple(source_paths) for target_path, source_paths in grouped.items()}


def _action_status(candidate: _AddCandidate) -> ActionStatus:
    if candidate.action_type == ActionType.SKIP or candidate.reason is None:
        return ActionStatus.PLANNED
    return ActionStatus.BLOCKED


def _plan(
    plan_id: PlanId,
    library: Library,
    actions: Sequence[PlanAction],
    config_hash: str,
    timestamp: datetime,
) -> Plan:
    move_count = sum(
        action.action_type == ActionType.MOVE and action.status == ActionStatus.PLANNED for action in actions
    )
    skip_count = sum(action.action_type == ActionType.SKIP for action in actions)
    blocked_count = sum(action.status == ActionStatus.BLOCKED for action in actions)
    return Plan(
        plan_id=plan_id,
        library_id=library.library_id,
        plan_type=PlanType.ADD,
        status=PlanStatus.READY,
        created_at=timestamp,
        config_hash=config_hash,
        library_root_at_plan=library.root_path,
        summary={
            SUMMARY_ACTION_COUNT_KEY: str(len(actions)),
            SUMMARY_MOVE_ACTIONS_KEY: str(move_count),
            SUMMARY_SKIP_ACTIONS_KEY: str(skip_count),
            SUMMARY_BLOCKED_ACTIONS_KEY: str(blocked_count),
        },
        actions=tuple(actions),
    )


def _source_changed(entry: FileScanEntry, snapshot: FileSnapshot) -> bool:
    return entry.size != snapshot.size or entry.mtime != snapshot.mtime


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
