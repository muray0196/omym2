"""
Summary: Implements organize Library registration planning.
Why: Registers clean Libraries and records review Plans without moving files.
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import TYPE_CHECKING

from omym2.config import PLAN_ACTION_SORT_ORDER_START, PLAN_ACTION_SORT_ORDER_STEP
from omym2.domain.models.library import Library, LibraryStatus
from omym2.domain.models.plan import Plan, PlanStatus, PlanType
from omym2.domain.models.plan_action import ActionStatus, ActionType, PlanAction, PlanActionReason
from omym2.domain.models.track import Track, TrackStatus
from omym2.domain.services.config_fingerprint import calculate_config_fingerprint, calculate_path_policy_fingerprint
from omym2.domain.services.path_policy import MISSING_TITLE_MESSAGE, PathPolicy
from omym2.features.organize.dto import OrganizeLibraryResult
from omym2.shared.paths import normalize_library_relative_path

if TYPE_CHECKING:
    from collections.abc import Sequence
    from datetime import datetime

    from omym2.domain.models.app_config import AppConfig
    from omym2.domain.models.file_scan_entry import FileScanEntry
    from omym2.domain.models.file_snapshot import FileSnapshot
    from omym2.features.common_ports import UnitOfWork
    from omym2.features.organize.dto import CreateOrganizePlanRequest
    from omym2.features.organize.ports import CreateOrganizePlanPorts
    from omym2.shared.ids import LibraryId, TrackId

AMBIGUOUS_LIBRARY_SELECTION_MESSAGE = "Multiple known Libraries exist. Use organize --library PATH."
NO_LIBRARY_SELECTION_MESSAGE = "No known Library can be selected. Use organize --library PATH."
UNREGISTERED_PATH_MESSAGE = (
    "Refusing to organize an unregistered path while another Library exists; "
    "the path may be a moved Library or a second Library."
)
SUMMARY_ACTION_COUNT_KEY = "action_count"
SUMMARY_BLOCKED_ACTIONS_KEY = "blocked_actions"
SUMMARY_PLANNED_ACTIONS_KEY = "planned_actions"
SUMMARY_TRACK_COUNT_KEY = "track_count"
INCOMPLETE_CANDIDATE_MESSAGE = "Cannot record a Track for an incomplete organize candidate."


@dataclass(frozen=True, slots=True)
class CreateOrganizePlanUseCase:
    """Create organize Plans or register a clean Library."""

    ports: CreateOrganizePlanPorts

    def execute(self, request: CreateOrganizePlanRequest) -> OrganizeLibraryResult:
        """Create an organize Plan, or register a clean Library without a Plan."""
        config = self.ports.config_store.load()
        config_hash = calculate_config_fingerprint(config)
        path_policy_hash = calculate_path_policy_fingerprint(config.path_policy)
        timestamp = self.ports.clock.now()

        with self.ports.uow as uow:
            library = self._select_library(uow, request.library_root, path_policy_hash, timestamp)
            scan_entries = self.ports.file_scanner.scan(library.root_path)
            candidates = tuple(self._candidate(library.root_path, entry, config) for entry in scan_entries)
            result = self._persist_result(uow, library, candidates, config_hash, timestamp)
            uow.commit()
            return result

    def _select_library(
        self,
        uow: UnitOfWork,
        requested_root: str | None,
        path_policy_hash: str,
        timestamp: datetime,
    ) -> Library:
        if requested_root is not None:
            existing_library = uow.libraries.find_by_root_path(requested_root)
            if existing_library is not None:
                return _with_path_policy_hash(existing_library, path_policy_hash, timestamp)

            if len(uow.libraries.list_all()) > 0:
                raise OrganizeLibrarySelectionError(UNREGISTERED_PATH_MESSAGE)

            return Library(
                library_id=self.ports.id_generator.new_library_id(),
                root_path=requested_root,
                path_policy_hash=path_policy_hash,
                registered_at=None,
                status=LibraryStatus.UNREGISTERED,
                created_at=timestamp,
                updated_at=timestamp,
            )

        libraries = tuple(uow.libraries.list_all())
        if len(libraries) == 0:
            raise OrganizeLibrarySelectionError(NO_LIBRARY_SELECTION_MESSAGE)
        if len(libraries) > 1:
            raise OrganizeLibrarySelectionError(AMBIGUOUS_LIBRARY_SELECTION_MESSAGE)
        return _with_path_policy_hash(libraries[0], path_policy_hash, timestamp)

    def _candidate(self, library_root: str, entry: FileScanEntry, config: AppConfig) -> _OrganizeCandidate:
        try:
            source_path = self.ports.path_resolver.relative_to_library(library_root, entry.path)
        except ValueError:
            return _blocked_candidate(
                source_path=_scanner_relative_path(library_root, entry.path),
                snapshot=None,
                block_reason=PlanActionReason.INVALID_PATH,
            )

        try:
            snapshot = self.ports.file_snapshot_reader.capture(entry.path)
        except FileNotFoundError:
            return _blocked_candidate(
                source_path=source_path,
                snapshot=None,
                block_reason=PlanActionReason.SOURCE_MISSING,
            )

        if _has_missing_required_metadata(snapshot, config):
            return _blocked_candidate(
                source_path=source_path,
                snapshot=snapshot,
                block_reason=PlanActionReason.MISSING_REQUIRED_METADATA,
            )

        try:
            target_path = PathPolicy(config.path_policy).canonical_path(snapshot.metadata, snapshot.file_extension)
        except ValueError as exc:
            return _blocked_candidate(
                source_path=source_path,
                snapshot=snapshot,
                block_reason=_path_generation_failure_reason(exc),
            )

        return _OrganizeCandidate(
            source_path=source_path,
            snapshot=snapshot,
            target_path=target_path,
            block_reason=None,
        )

    def _persist_result(
        self,
        uow: UnitOfWork,
        library: Library,
        candidates: Sequence[_OrganizeCandidate],
        config_hash: str,
        timestamp: datetime,
    ) -> OrganizeLibraryResult:
        existing_tracks = {track.current_path: track for track in uow.tracks.list_by_library(library.library_id)}
        occupied_paths = {candidate.source_path for candidate in candidates if candidate.snapshot is not None}
        target_sources = _target_sources(candidates)
        action_records: list[_ActionRecord] = []
        tracks: list[Track] = []

        for candidate in candidates:
            action_reason = candidate.block_reason or _collision_reason(candidate, occupied_paths, target_sources)
            track = None
            if action_reason is None:
                track = self._track_for_candidate(library.library_id, candidate, existing_tracks, timestamp)
                tracks.append(track)

            if action_reason is not None or candidate.target_path != candidate.source_path:
                action_records.append(
                    _ActionRecord(
                        candidate=candidate,
                        track_id=None if track is None else track.track_id,
                        reason=action_reason,
                    )
                )

        actions = self._actions(library, action_records)
        final_library = _final_library_state(library, actions, timestamp)

        uow.libraries.save(final_library)
        for track in tracks:
            uow.tracks.save(track)

        plan = self._plan(final_library, actions, config_hash, timestamp)
        if plan is not None:
            uow.plans.save(plan)
            for action in actions:
                uow.plan_actions.save(action)

        return OrganizeLibraryResult(
            library=final_library,
            plan=plan,
            actions=actions,
            track_count=len(tracks),
        )

    def _track_for_candidate(
        self,
        library_id: LibraryId,
        candidate: _OrganizeCandidate,
        existing_tracks: dict[str, Track],
        timestamp: datetime,
    ) -> Track:
        snapshot = candidate.snapshot
        target_path = candidate.target_path
        if snapshot is None or target_path is None:
            raise AssertionError(INCOMPLETE_CANDIDATE_MESSAGE)

        existing_track = existing_tracks.get(candidate.source_path)
        return Track(
            track_id=self.ports.id_generator.new_track_id() if existing_track is None else existing_track.track_id,
            library_id=library_id,
            current_path=candidate.source_path,
            canonical_path=target_path,
            content_hash=snapshot.content_hash,
            metadata_hash=snapshot.metadata_hash,
            metadata=snapshot.metadata,
            status=TrackStatus.ACTIVE,
            first_seen_at=timestamp if existing_track is None else existing_track.first_seen_at,
            last_seen_at=timestamp,
            updated_at=timestamp,
        )

    def _actions(self, library: Library, records: Sequence[_ActionRecord]) -> tuple[PlanAction, ...]:
        if len(records) == 0:
            return ()

        plan_id = self.ports.id_generator.new_plan_id()
        actions: list[PlanAction] = []
        sort_order = PLAN_ACTION_SORT_ORDER_START
        for record in records:
            candidate = record.candidate
            snapshot = candidate.snapshot
            action_status = ActionStatus.PLANNED if record.reason is None else ActionStatus.BLOCKED
            actions.append(
                PlanAction(
                    action_id=self.ports.id_generator.new_action_id(),
                    plan_id=plan_id,
                    library_id=library.library_id,
                    track_id=record.track_id,
                    action_type=ActionType.MOVE,
                    source_path=candidate.source_path,
                    target_path=candidate.target_path,
                    content_hash_at_plan=None if snapshot is None else snapshot.content_hash,
                    metadata_hash_at_plan=None if snapshot is None else snapshot.metadata_hash,
                    status=action_status,
                    reason=record.reason,
                    sort_order=sort_order,
                )
            )
            sort_order += PLAN_ACTION_SORT_ORDER_STEP
        return tuple(actions)

    def _plan(
        self,
        library: Library,
        actions: Sequence[PlanAction],
        config_hash: str,
        timestamp: datetime,
    ) -> Plan | None:
        if len(actions) == 0:
            return None

        planned_count = sum(action.status == ActionStatus.PLANNED for action in actions)
        blocked_count = sum(action.status == ActionStatus.BLOCKED for action in actions)
        return Plan(
            plan_id=actions[0].plan_id,
            library_id=library.library_id,
            plan_type=PlanType.ORGANIZE,
            status=PlanStatus.READY,
            created_at=timestamp,
            config_hash=config_hash,
            library_root_at_plan=library.root_path,
            summary={
                SUMMARY_ACTION_COUNT_KEY: str(len(actions)),
                SUMMARY_PLANNED_ACTIONS_KEY: str(planned_count),
                SUMMARY_BLOCKED_ACTIONS_KEY: str(blocked_count),
                SUMMARY_TRACK_COUNT_KEY: str(sum(action.track_id is not None for action in actions)),
            },
            actions=tuple(actions),
        )


class OrganizeLibrarySelectionError(ValueError):
    """Raised when organize cannot select a Library without guessing."""


@dataclass(frozen=True, slots=True)
class _OrganizeCandidate:
    """One scanned source and its plan-time organize judgment."""

    source_path: str
    snapshot: FileSnapshot | None
    target_path: str | None
    block_reason: PlanActionReason | None


@dataclass(frozen=True, slots=True)
class _ActionRecord:
    """Intermediate action data before the shared Plan ID is generated."""

    candidate: _OrganizeCandidate
    track_id: TrackId | None
    reason: PlanActionReason | None


def _blocked_candidate(
    *,
    source_path: str,
    snapshot: FileSnapshot | None,
    block_reason: PlanActionReason,
) -> _OrganizeCandidate:
    return _OrganizeCandidate(
        source_path=source_path,
        snapshot=snapshot,
        target_path=None,
        block_reason=block_reason,
    )


def _with_path_policy_hash(library: Library, path_policy_hash: str, timestamp: datetime) -> Library:
    return Library(
        library_id=library.library_id,
        root_path=library.root_path,
        path_policy_hash=path_policy_hash,
        registered_at=library.registered_at,
        status=library.status,
        created_at=library.created_at,
        updated_at=timestamp,
    )


def _final_library_state(library: Library, actions: Sequence[PlanAction], timestamp: datetime) -> Library:
    if len(actions) == 0:
        return _with_status(library, LibraryStatus.REGISTERED, registered_at=timestamp, timestamp=timestamp)

    if any(action.status == ActionStatus.BLOCKED for action in actions):
        return _with_status(library, LibraryStatus.BLOCKED, registered_at=None, timestamp=timestamp)

    return _with_status(library, LibraryStatus.UNREGISTERED, registered_at=None, timestamp=timestamp)


def _with_status(
    library: Library,
    status: LibraryStatus,
    *,
    registered_at: datetime | None,
    timestamp: datetime,
) -> Library:
    return Library(
        library_id=library.library_id,
        root_path=library.root_path,
        path_policy_hash=library.path_policy_hash,
        registered_at=registered_at,
        status=status,
        created_at=library.created_at,
        updated_at=timestamp,
    )


def _has_missing_required_metadata(snapshot: FileSnapshot, config: AppConfig) -> bool:
    metadata = snapshot.metadata
    if config.metadata.require_title and _missing_text(metadata.title):
        return True
    # Artist identity can come from either track artist or album artist in the
    # initial path model, so either value satisfies the required artist gate.
    if config.metadata.require_artist and _missing_text(metadata.artist) and _missing_text(metadata.album_artist):
        return True
    return config.metadata.require_album and _missing_text(metadata.album)


def _missing_text(value: str | None) -> bool:
    return value is None or value.strip() == ""


def _scanner_relative_path(library_root: str, path: str) -> str:
    """Return the lexical Library-relative scanner path for invalid sources."""
    try:
        relative_path = Path(path).expanduser().relative_to(Path(library_root).expanduser())
    except ValueError:
        return normalize_library_relative_path(Path(path).name)
    return normalize_library_relative_path(relative_path.as_posix())


def _path_generation_failure_reason(exc: ValueError) -> PlanActionReason:
    if str(exc) == MISSING_TITLE_MESSAGE:
        return PlanActionReason.MISSING_REQUIRED_METADATA
    return PlanActionReason.INVALID_PATH


def _target_sources(candidates: Sequence[_OrganizeCandidate]) -> dict[str, tuple[str, ...]]:
    grouped: dict[str, list[str]] = {}
    for candidate in candidates:
        if candidate.target_path is None:
            continue
        grouped.setdefault(candidate.target_path, []).append(candidate.source_path)
    return {target_path: tuple(source_paths) for target_path, source_paths in grouped.items()}


def _collision_reason(
    candidate: _OrganizeCandidate,
    occupied_paths: set[str],
    target_sources: dict[str, tuple[str, ...]],
) -> PlanActionReason | None:
    target_path = candidate.target_path
    if target_path is None:
        return None

    if target_path in occupied_paths and target_path != candidate.source_path:
        return PlanActionReason.TARGET_EXISTS

    if len(target_sources[target_path]) > 1 and target_path not in occupied_paths:
        return PlanActionReason.TARGET_EXISTS

    return None
