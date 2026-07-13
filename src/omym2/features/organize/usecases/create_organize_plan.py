"""
Summary: Implements organize Library registration planning.
Why: Registers clean Libraries and records review Plans without moving files.
"""

from __future__ import annotations

from dataclasses import dataclass, replace
from datetime import timedelta
from pathlib import Path
from typing import TYPE_CHECKING

from omym2.config import (
    OPERATION_RESULT_RETENTION_HOURS,
    OPERATION_TOMBSTONE_RETENTION_DAYS,
    PLAN_ACTION_SORT_ORDER_START,
    PLAN_ACTION_SORT_ORDER_STEP,
)
from omym2.domain.models.library import Library, LibraryStatus
from omym2.domain.models.operation import (
    Operation,
    OperationKind,
    OperationStatus,
    PlanCreatedResult,
    RegisteredWithoutPlanResult,
)
from omym2.domain.models.plan import Plan, PlanStatus, PlanType
from omym2.domain.models.plan_action import ActionStatus, ActionType, PlanAction, PlanActionReason
from omym2.domain.models.track import Track, TrackStatus
from omym2.domain.services.album_disc import infer_album_disc_totals
from omym2.domain.services.album_year import metadata_with_resolved_album_year, resolve_album_years
from omym2.domain.services.collision_policy import CollisionDecisionKind, CollisionPolicy, OccupiedPaths
from omym2.domain.services.config_fingerprint import calculate_config_fingerprint, calculate_path_policy_fingerprint
from omym2.domain.services.path_policy import MISSING_TITLE_MESSAGE, PathPolicy
from omym2.domain.services.snapshot_baseline import snapshot_from_trusted_stat
from omym2.features.common_ports import FileSnapshotCaptureRequest
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
    from omym2.shared.ids import LibraryId, OperationId, TrackId

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
RUNNING_OPERATION_REQUIRED_MESSAGE = "Organize completion requires its corresponding running Operation."


@dataclass(frozen=True, slots=True)
class CreateOrganizePlanUseCase:
    """Create organize Plans or register a clean Library."""

    ports: CreateOrganizePlanPorts

    def execute(self, request: CreateOrganizePlanRequest) -> OrganizeLibraryResult:
        """Create an organize Plan, or register a clean Library without a Plan."""
        config = self.ports.config_store.load()
        config_hash = calculate_config_fingerprint(config)
        path_policy_hash = calculate_path_policy_fingerprint(
            config.path_policy,
            config.artist_ids,
            config.metadata.album_year_resolution,
        )
        path_policy = PathPolicy.from_app_config(config)
        timestamp = self.ports.clock.now()

        with self.ports.uow as uow:
            operation = _running_operation(uow, request.operation_id)
            library = self._select_library(uow, request.library_root, path_policy_hash, timestamp)
            existing_track_records = tuple(uow.tracks.list_by_library(library.library_id))
            trust_eligible_tracks = _unique_tracks_by_current_path(existing_track_records)
            existing_tracks = {track.current_path: track for track in existing_track_records}
            existing_tracks.update(trust_eligible_tracks)
            scan_entries = tuple(self.ports.file_scanner.scan(library.root_path))
            capture_inputs = tuple(self._capture_input(library.root_path, entry) for entry in scan_entries)
            valid_capture_inputs = tuple(
                capture_input for capture_input in capture_inputs if isinstance(capture_input, _OrganizeCaptureInput)
            )
            snapshots = self._capture_snapshots(
                valid_capture_inputs,
                trust_eligible_tracks,
                timestamp,
                trust_stat=request.trust_stat,
            )
            captured_candidates = iter(
                tuple(
                    self._candidate(capture_input.source_path, snapshot, config)
                    for capture_input, snapshot in zip(valid_capture_inputs, snapshots, strict=True)
                )
            )
            candidates = tuple(
                capture_input if isinstance(capture_input, _OrganizeCandidate) else next(captured_candidates)
                for capture_input in capture_inputs
            )
            candidates = self._with_target_paths(candidates, config, path_policy)
            result = self._persist_result(
                uow,
                library,
                candidates,
                _OrganizePersistence(
                    existing_tracks=existing_tracks,
                    config_hash=config_hash,
                    timestamp=timestamp,
                ),
            )
            if operation is not None:
                operation_result = (
                    PlanCreatedResult(result.plan.plan_id)
                    if result.plan is not None
                    else RegisteredWithoutPlanResult(result.library.library_id, result.track_count)
                )
                completed_at = self.ports.clock.now()
                uow.operations.save(
                    replace(operation, library_id=result.library.library_id).mark_succeeded(
                        result=operation_result,
                        completed_at=completed_at,
                        result_expires_at=completed_at + timedelta(hours=OPERATION_RESULT_RETENTION_HOURS),
                        tombstone_expires_at=completed_at + timedelta(days=OPERATION_TOMBSTONE_RETENTION_DAYS),
                    )
                )
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

    def _capture_input(
        self,
        library_root: str,
        entry: FileScanEntry,
    ) -> _OrganizeCaptureInput | _OrganizeCandidate:
        try:
            source_path = self.ports.path_resolver.relative_to_library(library_root, entry.path)
        except ValueError:
            return _blocked_candidate(
                source_path=_scanner_relative_path(library_root, entry.path),
                snapshot=None,
                block_reason=PlanActionReason.INVALID_PATH,
            )
        return _OrganizeCaptureInput(entry=entry, source_path=source_path)

    def _capture_snapshots(
        self,
        capture_inputs: Sequence[_OrganizeCaptureInput],
        trust_eligible_tracks: dict[str, Track],
        timestamp: datetime,
        *,
        trust_stat: bool,
    ) -> tuple[FileSnapshot | None, ...]:
        snapshots: list[FileSnapshot | None] = [None] * len(capture_inputs)
        uncached_indexes: list[int] = []
        uncached_requests: list[FileSnapshotCaptureRequest] = []

        for index, capture_input in enumerate(capture_inputs):
            trusted_snapshot = None
            eligible_track = trust_eligible_tracks.get(capture_input.source_path)
            if trust_stat and eligible_track is not None:
                trusted_snapshot = snapshot_from_trusted_stat(
                    eligible_track,
                    capture_input.source_path,
                    capture_input.entry.path,
                    capture_input.entry,
                    timestamp,
                )
            if trusted_snapshot is not None:
                snapshots[index] = trusted_snapshot
                continue

            uncached_indexes.append(index)
            uncached_requests.append(FileSnapshotCaptureRequest(capture_input.entry.path))

        if len(uncached_requests) > 0:
            captured = self.ports.file_snapshot_reader.capture_many(tuple(uncached_requests))
            for index, snapshot in zip(uncached_indexes, captured, strict=True):
                snapshots[index] = snapshot

        return tuple(snapshots)

    def _candidate(
        self,
        source_path: str,
        snapshot: FileSnapshot | None,
        config: AppConfig,
    ) -> _OrganizeCandidate:
        if snapshot is None:
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

        return _OrganizeCandidate(
            source_path=source_path,
            snapshot=snapshot,
            target_path=None,
            block_reason=None,
        )

    def _with_target_paths(
        self,
        candidates: Sequence[_OrganizeCandidate],
        config: AppConfig,
        path_policy: PathPolicy,
    ) -> tuple[_OrganizeCandidate, ...]:
        metadata_batch = tuple(
            candidate.snapshot.metadata
            for candidate in candidates
            if candidate.snapshot is not None and candidate.block_reason is None
        )
        resolved_years = resolve_album_years(
            metadata_batch,
            config.path_policy,
            config.metadata.album_year_resolution,
        )
        resolved_metadata_batch = tuple(
            metadata_with_resolved_album_year(metadata, config.path_policy, resolved_years)
            for metadata in metadata_batch
        )
        album_disc_totals = infer_album_disc_totals(
            resolved_metadata_batch,
            unknown_artist=config.path_policy.unknown_artist,
            unknown_album=config.path_policy.unknown_album,
        )
        judged_candidates: list[_OrganizeCandidate] = []

        for candidate in candidates:
            snapshot = candidate.snapshot
            if snapshot is None or candidate.block_reason is not None:
                judged_candidates.append(candidate)
                continue

            try:
                resolved_metadata = metadata_with_resolved_album_year(
                    snapshot.metadata,
                    config.path_policy,
                    resolved_years,
                )
                target_path = path_policy.canonical_path(
                    resolved_metadata,
                    snapshot.file_extension,
                    album_disc_total=album_disc_totals.for_metadata(resolved_metadata),
                )
            except ValueError as exc:
                judged_candidates.append(
                    replace(candidate, target_path=None, block_reason=_path_generation_failure_reason(exc))
                )
                continue

            judged_candidates.append(replace(candidate, target_path=target_path))

        return tuple(judged_candidates)

    def _persist_result(
        self,
        uow: UnitOfWork,
        library: Library,
        candidates: Sequence[_OrganizeCandidate],
        persistence: _OrganizePersistence,
    ) -> OrganizeLibraryResult:
        existing_tracks = persistence.existing_tracks
        timestamp = persistence.timestamp
        occupied_paths = OccupiedPaths.from_paths(
            candidate.source_path for candidate in candidates if candidate.snapshot is not None
        )
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

        plan = self._plan(final_library, actions, persistence.config_hash, timestamp)
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
            size=snapshot.size,
            mtime=snapshot.mtime,
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
class _OrganizeCaptureInput:
    """One valid Library source awaiting full snapshot capture."""

    entry: FileScanEntry
    source_path: str


@dataclass(frozen=True, slots=True)
class _ActionRecord:
    """Intermediate action data before the shared Plan ID is generated."""

    candidate: _OrganizeCandidate
    track_id: TrackId | None
    reason: PlanActionReason | None


@dataclass(frozen=True, slots=True)
class _OrganizePersistence:
    """Inputs shared across organize Track and Plan persistence."""

    existing_tracks: dict[str, Track]
    config_hash: str
    timestamp: datetime


def _running_operation(uow: UnitOfWork, operation_id: OperationId | None) -> Operation | None:
    if operation_id is None:
        return None
    retained = uow.operations.lookup(operation_id)
    if (
        not isinstance(retained, Operation)
        or retained.kind is not OperationKind.ORGANIZE_PLAN
        or retained.status is not OperationStatus.RUNNING
    ):
        raise RuntimeError(RUNNING_OPERATION_REQUIRED_MESSAGE)
    return retained


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


def _unique_tracks_by_current_path(tracks: Sequence[Track]) -> dict[str, Track]:
    unique_tracks: dict[str, Track] = {}
    duplicate_paths: set[str] = set()
    for track in tracks:
        if track.status != TrackStatus.ACTIVE:
            continue
        if track.current_path in unique_tracks:
            duplicate_paths.add(track.current_path)
        else:
            unique_tracks[track.current_path] = track
    return {path: track for path, track in unique_tracks.items() if path not in duplicate_paths}


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
    occupied_paths: OccupiedPaths,
    target_sources: dict[str, tuple[str, ...]],
) -> PlanActionReason | None:
    target_path = candidate.target_path
    if target_path is None:
        return None

    decision = CollisionPolicy().decide(
        target_path,
        occupied_paths,
        batch_target_count=len(target_sources[target_path]),
    )
    if decision.kind is CollisionDecisionKind.AVAILABLE:
        return None

    # A no-op rename onto the candidate's own current Library-relative path is
    # never a conflict, even though that path is itself always present in
    # occupied_paths (every candidate's own source_path is a member).
    if target_path == candidate.source_path:
        return None

    return decision.reason
