"""
Summary: Implements Library consistency checks and persists their findings.
Why: Lets users diagnose DB and filesystem drift, then browse the latest findings as a cheap
DB read instead of recomputing them on every request.
"""

from __future__ import annotations

from collections import Counter
from dataclasses import dataclass, field
from datetime import timedelta
from os import fspath
from pathlib import PurePath
from typing import TYPE_CHECKING

from omym2.config import OPERATION_RESULT_RETENTION_HOURS, OPERATION_TOMBSTONE_RETENTION_DAYS
from omym2.domain.models.check_issue import CheckIssue, CheckIssueType
from omym2.domain.models.check_run import CheckRun
from omym2.domain.models.library import LibraryStatus
from omym2.domain.models.operation import CheckCompletedResult, Operation, OperationKind, OperationStatus
from omym2.domain.models.plan import PlanStatus
from omym2.domain.models.plan_action import ActionStatus
from omym2.domain.models.track import TrackStatus
from omym2.domain.services.config_fingerprint import calculate_path_policy_fingerprint
from omym2.domain.services.snapshot_baseline import snapshot_from_trusted_stat
from omym2.features.check.dto import CheckLibraryResult
from omym2.features.common_ports import FileSnapshotCaptureRequest

if TYPE_CHECKING:
    from collections.abc import Sequence
    from datetime import datetime

    from omym2.domain.models.file_event import FileEvent
    from omym2.domain.models.file_scan_entry import FileScanEntry
    from omym2.domain.models.file_snapshot import FileSnapshot
    from omym2.domain.models.library import Library
    from omym2.domain.models.plan import Plan
    from omym2.domain.models.plan_action import PlanAction
    from omym2.domain.models.track import Track
    from omym2.features.check.dto import CheckLibraryRequest
    from omym2.features.check.ports import CheckLibraryPorts
    from omym2.features.common_ports import BatchFileSnapshotReader, FileSystemPath, PathResolver, UnitOfWork
    from omym2.shared.ids import CheckRunId, LibraryId, OperationId, RunId

LIBRARY_NOT_FOUND_MESSAGE = "Library was not found."
RUNNING_OPERATION_REQUIRED_MESSAGE = "Check completion requires its corresponding running Operation."


@dataclass(frozen=True, slots=True)
class CheckLibraryUseCase:
    """Report consistency issues, then persist them as each Library's latest check run."""

    ports: CheckLibraryPorts

    def execute(self, request: CheckLibraryRequest) -> CheckLibraryResult:
        """Report consistency issues for a Library and persist them as its latest check run.

        Never mutates Library music files, Tracks, Plans, or Runs. Only writes to the
        check_runs / check_issues tables that hold this diagnostic's own findings.
        """
        config = self.ports.config_store.load()
        current_path_policy_hash = calculate_path_policy_fingerprint(
            config.path_policy,
            config.artist_ids,
            config.metadata.album_year_resolution,
            config.artist_names,
        )
        checked_at = self.ports.clock.now()
        snapshot_memo = _SnapshotMemo(self.ports.file_snapshot_reader)

        with self.ports.uow as uow:
            operation = _running_operation(uow, request.operation_id)
            libraries = _selected_libraries(uow, request)
            issues: list[CheckIssue] = []
            check_run_ids: list[CheckRunId] = []
            for library in libraries:
                active_tracks = tuple(
                    track
                    for track in uow.tracks.list_by_library(library.library_id)
                    if track.status == TrackStatus.ACTIVE
                )
                plans = tuple(uow.plans.list_by_library(library.library_id))
                scan_entries = tuple(self.ports.file_scanner.scan(library.root_path)) if request.trust_stat else ()

                library_issues: list[CheckIssue] = []
                library_issues.extend(_library_state_issues(library, current_path_policy_hash))
                if request.trust_stat:
                    for path, snapshot in self._trusted_track_snapshots(
                        library,
                        active_tracks,
                        scan_entries,
                        checked_at,
                    ):
                        snapshot_memo.remember(path, snapshot)
                library_issues.extend(self._track_issues(library, active_tracks, snapshot_memo))
                if not request.trust_stat:
                    scan_entries = tuple(self.ports.file_scanner.scan(library.root_path))
                library_issues.extend(self._scan_issues(library, active_tracks, scan_entries))
                library_issues.extend(self._plan_source_issues(uow, library, plans, snapshot_memo))
                library_issues.extend(_pending_event_issues(uow, library))

                check_run_ids.append(self._persist_check_run(uow, library.library_id, library_issues, checked_at))
                issues.extend(library_issues)

            if operation is not None:
                completed_at = self.ports.clock.now()
                uow.operations.save(
                    operation.mark_succeeded(
                        result=CheckCompletedResult(tuple(check_run_ids), len(issues)),
                        completed_at=completed_at,
                        result_expires_at=completed_at + timedelta(hours=OPERATION_RESULT_RETENTION_HOURS),
                        tombstone_expires_at=completed_at + timedelta(days=OPERATION_TOMBSTONE_RETENTION_DAYS),
                    )
                )
            uow.commit()
            return CheckLibraryResult(
                issues=tuple(issues),
                checked_at=checked_at,
                check_run_ids=tuple(check_run_ids),
            )

    def _persist_check_run(
        self,
        uow: UnitOfWork,
        library_id: LibraryId,
        issues: Sequence[CheckIssue],
        checked_at: datetime,
    ) -> CheckRunId:
        """Replace one Library's prior check run with its freshly computed findings."""
        uow.check_issues.delete_for_library(library_id)
        uow.check_runs.delete_for_library(library_id)
        check_run = CheckRun(
            check_run_id=self.ports.id_generator.new_check_run_id(),
            library_id=library_id,
            checked_at=checked_at,
            total_count=len(issues),
        )
        uow.check_runs.save(check_run)
        uow.check_issues.save_many(check_run.check_run_id, issues)
        return check_run.check_run_id

    def _track_issues(
        self,
        library: Library,
        tracks: Sequence[Track],
        snapshot_memo: _SnapshotMemo,
    ) -> tuple[CheckIssue, ...]:
        filesystem_paths = tuple(
            self.ports.path_resolver.resolve_library_path(library.root_path, track.current_path) for track in tracks
        )
        snapshots = snapshot_memo.capture_many(filesystem_paths)
        issues: list[CheckIssue] = []
        for track, snapshot in zip(tracks, snapshots, strict=True):
            if track.current_path != track.canonical_path:
                issues.append(
                    CheckIssue(
                        issue_type=CheckIssueType.CURRENT_PATH_DIFFERS_FROM_CANONICAL_PATH,
                        library_id=library.library_id,
                        path=track.current_path,
                        track_id=track.track_id,
                    )
                )

            if snapshot is None:
                issues.append(
                    CheckIssue(
                        issue_type=CheckIssueType.DB_FILE_MISSING,
                        library_id=library.library_id,
                        path=track.current_path,
                        track_id=track.track_id,
                    )
                )
                continue

            if snapshot.content_hash != track.content_hash:
                issues.append(
                    CheckIssue(
                        issue_type=CheckIssueType.CONTENT_HASH_CHANGED,
                        library_id=library.library_id,
                        path=track.current_path,
                        track_id=track.track_id,
                    )
                )
            if snapshot.metadata_hash != track.metadata_hash:
                issues.append(
                    CheckIssue(
                        issue_type=CheckIssueType.METADATA_HASH_CHANGED,
                        library_id=library.library_id,
                        path=track.current_path,
                        track_id=track.track_id,
                    )
                )

        issues.extend(_duplicate_track_issues(library, tracks))
        return tuple(issues)

    def _trusted_track_snapshots(
        self,
        library: Library,
        tracks: Sequence[Track],
        scan_entries: Sequence[FileScanEntry],
        checked_at: datetime,
    ) -> tuple[tuple[FileSystemPath, FileSnapshot], ...]:
        trust_eligible_paths = {
            path for path, count in Counter(track.current_path for track in tracks).items() if count == 1
        }
        entries_by_path = {
            self.ports.path_resolver.relative_to_library(library.root_path, entry.path): entry for entry in scan_entries
        }
        trusted: list[tuple[FileSystemPath, FileSnapshot]] = []
        for track in tracks:
            if track.current_path not in trust_eligible_paths:
                continue
            observation = entries_by_path.get(track.current_path)
            if observation is None:
                continue
            filesystem_path = self.ports.path_resolver.resolve_library_path(
                library.root_path,
                track.current_path,
            )
            snapshot = snapshot_from_trusted_stat(
                track,
                track.current_path,
                fspath(filesystem_path),
                observation,
                checked_at,
            )
            if snapshot is not None:
                trusted.append((filesystem_path, snapshot))
        return tuple(trusted)

    def _scan_issues(
        self,
        library: Library,
        tracks: Sequence[Track],
        scan_entries: Sequence[FileScanEntry],
    ) -> tuple[CheckIssue, ...]:
        managed_paths = {track.current_path for track in tracks}
        managed_hashes = {track.content_hash for track in tracks}
        issues: list[CheckIssue] = []

        for entry in scan_entries:
            relative_path = self.ports.path_resolver.relative_to_library(library.root_path, entry.path)
            if relative_path in managed_paths:
                continue

            issues.append(
                CheckIssue(
                    issue_type=CheckIssueType.UNMANAGED_FILE_EXISTS,
                    library_id=library.library_id,
                    path=relative_path,
                )
            )
            if self._is_duplicate_candidate(entry, managed_hashes):
                issues.append(
                    CheckIssue(
                        issue_type=CheckIssueType.DUPLICATE_CANDIDATE,
                        library_id=library.library_id,
                        path=relative_path,
                    )
                )

        return tuple(issues)

    def _is_duplicate_candidate(self, entry: FileScanEntry, managed_hashes: set[str]) -> bool:
        try:
            content_hash = self.ports.file_content_hasher.calculate(entry.path)
        except FileNotFoundError:
            return False
        return content_hash in managed_hashes

    def _plan_source_issues(
        self,
        uow: UnitOfWork,
        library: Library,
        plans: Sequence[Plan],
        snapshot_memo: _SnapshotMemo,
    ) -> tuple[CheckIssue, ...]:
        source_checks: list[_PlanSourceCheck] = []
        for plan in plans:
            if plan.status != PlanStatus.READY:
                continue
            for action in uow.plan_actions.list_by_plan(plan.plan_id):
                if action.status != ActionStatus.PLANNED or action.source_path is None:
                    continue
                if action.content_hash_at_plan is None and action.metadata_hash_at_plan is None:
                    continue

                source_filesystem_path = _resolve_action_path(self.ports.path_resolver, library, action.source_path)
                source_checks.append(_PlanSourceCheck(plan=plan, action=action, path=source_filesystem_path))

        snapshots = snapshot_memo.capture_many(tuple(source_check.path for source_check in source_checks))
        issues: list[CheckIssue] = []
        for source_check, snapshot in zip(source_checks, snapshots, strict=True):
            plan = source_check.plan
            action = source_check.action
            if snapshot is None:
                issues.append(
                    CheckIssue(
                        issue_type=CheckIssueType.PLAN_SOURCE_CHANGED,
                        library_id=library.library_id,
                        path=action.source_path,
                        plan_id=plan.plan_id,
                        detail="source_missing",
                    )
                )
                continue

            content_changed = (
                action.content_hash_at_plan is not None and snapshot.content_hash != action.content_hash_at_plan
            )
            metadata_changed = (
                action.metadata_hash_at_plan is not None and snapshot.metadata_hash != action.metadata_hash_at_plan
            )
            if content_changed or metadata_changed:
                issues.append(
                    CheckIssue(
                        issue_type=CheckIssueType.PLAN_SOURCE_CHANGED,
                        library_id=library.library_id,
                        path=action.source_path,
                        plan_id=plan.plan_id,
                        detail="source_changed",
                    )
                )

        return tuple(issues)


class CheckLibraryError(ValueError):
    """Raised when check cannot select the requested Library."""


@dataclass(frozen=True, slots=True)
class _PlanSourceCheck:
    """One READY Plan source awaiting a full snapshot comparison."""

    plan: Plan
    action: PlanAction
    path: FileSystemPath


@dataclass(slots=True)
class _SnapshotMemo:
    """Reuse each full file observation for one check invocation."""

    reader: BatchFileSnapshotReader
    _snapshots_by_path: dict[str, FileSnapshot | None] = field(default_factory=dict)

    def remember(self, path: FileSystemPath, snapshot: FileSnapshot | None) -> None:
        """Cache a trusted point-in-time observation for later check phases."""
        _ = self._snapshots_by_path.setdefault(fspath(path), snapshot)

    def capture_many(self, paths: Sequence[FileSystemPath]) -> tuple[FileSnapshot | None, ...]:
        path_keys = tuple(fspath(path) for path in paths)
        queued_keys: set[str] = set()
        uncached: list[tuple[str, FileSystemPath]] = []
        for path, path_key in zip(paths, path_keys, strict=True):
            if path_key in self._snapshots_by_path or path_key in queued_keys:
                continue
            queued_keys.add(path_key)
            uncached.append((path_key, path))

        if len(uncached) > 0:
            snapshots = self.reader.capture_many(tuple(FileSnapshotCaptureRequest(path) for _, path in uncached))
            for (path_key, _), snapshot in zip(uncached, snapshots, strict=True):
                self._snapshots_by_path[path_key] = snapshot

        return tuple(self._snapshots_by_path[path_key] for path_key in path_keys)


def _running_operation(uow: UnitOfWork, operation_id: OperationId | None) -> Operation | None:
    if operation_id is None:
        return None
    retained = uow.operations.lookup(operation_id)
    if (
        not isinstance(retained, Operation)
        or retained.kind is not OperationKind.CHECK
        or retained.status is not OperationStatus.RUNNING
    ):
        raise RuntimeError(RUNNING_OPERATION_REQUIRED_MESSAGE)
    return retained


def _selected_libraries(uow: UnitOfWork, request: CheckLibraryRequest) -> tuple[Library, ...]:
    if request.library_id is None:
        libraries = tuple(uow.libraries.list_all())
        if not libraries:
            raise CheckLibraryError(LIBRARY_NOT_FOUND_MESSAGE)
        return libraries

    library = uow.libraries.get(request.library_id)
    if library is None:
        raise CheckLibraryError(LIBRARY_NOT_FOUND_MESSAGE)
    return (library,)


def _library_state_issues(library: Library, current_path_policy_hash: str) -> tuple[CheckIssue, ...]:
    issues: list[CheckIssue] = []

    if library.status == LibraryStatus.UNREGISTERED:
        issues.append(CheckIssue(CheckIssueType.LIBRARY_UNREGISTERED, library.library_id))
    if library.status == LibraryStatus.BLOCKED:
        issues.append(CheckIssue(CheckIssueType.LIBRARY_BLOCKED, library.library_id))
    if library.status == LibraryStatus.STALE or library.path_policy_hash != current_path_policy_hash:
        issues.append(CheckIssue(CheckIssueType.LIBRARY_STALE, library.library_id))

    return tuple(issues)


def _duplicate_track_issues(library: Library, tracks: Sequence[Track]) -> tuple[CheckIssue, ...]:
    first_path_by_hash: dict[str, str] = {}
    issues: list[CheckIssue] = []

    for track in tracks:
        first_path = first_path_by_hash.get(track.content_hash)
        if first_path is None:
            first_path_by_hash[track.content_hash] = track.current_path
            continue
        issues.append(
            CheckIssue(
                issue_type=CheckIssueType.DUPLICATE_CANDIDATE,
                library_id=library.library_id,
                path=track.current_path,
                track_id=track.track_id,
                detail=first_path,
            )
        )

    return tuple(issues)


def _pending_event_issues(uow: UnitOfWork, library: Library) -> tuple[CheckIssue, ...]:
    pending_events_by_run: dict[RunId, list[FileEvent]] = {}
    for event in uow.file_events.list_pending_by_library(library.library_id):
        pending_events_by_run.setdefault(event.run_id, []).append(event)

    issues: list[CheckIssue] = []
    for run in uow.runs.list_by_library(library.library_id):
        issues.extend(
            CheckIssue(
                issue_type=CheckIssueType.PENDING_FILE_EVENT_EXISTS,
                library_id=library.library_id,
                path=event.target_path,
                plan_id=run.plan_id,
            )
            for event in pending_events_by_run.get(run.run_id, ())
        )
    return tuple(issues)


def _resolve_action_path(path_resolver: PathResolver, library: Library, path: str) -> FileSystemPath:
    if PurePath(path).is_absolute():
        return path
    return path_resolver.resolve_library_path(library.root_path, path)
