"""
Summary: Implements read-only Library consistency checks.
Why: Lets users diagnose DB and filesystem drift without mutating state.
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import PurePath
from typing import TYPE_CHECKING

from omym2.domain.models.check_issue import CheckIssue, CheckIssueType
from omym2.domain.models.library import LibraryStatus
from omym2.domain.models.plan import PlanStatus
from omym2.domain.models.plan_action import ActionStatus
from omym2.domain.models.track import TrackStatus
from omym2.domain.services.config_fingerprint import calculate_path_policy_fingerprint

if TYPE_CHECKING:
    from collections.abc import Sequence

    from omym2.domain.models.file_event import FileEvent
    from omym2.domain.models.file_scan_entry import FileScanEntry
    from omym2.domain.models.library import Library
    from omym2.domain.models.plan import Plan
    from omym2.domain.models.track import Track
    from omym2.features.check.dto import CheckLibraryRequest
    from omym2.features.check.ports import CheckLibraryPorts
    from omym2.features.common_ports import FileSystemPath, PathResolver, UnitOfWork
    from omym2.shared.ids import RunId

LIBRARY_NOT_FOUND_MESSAGE = "Library was not found."


@dataclass(frozen=True, slots=True)
class CheckLibraryUseCase:
    """Report consistency issues without changing DB or filesystem state."""

    ports: CheckLibraryPorts

    def execute(self, request: CheckLibraryRequest) -> tuple[CheckIssue, ...]:
        """Report read-only consistency issues for a Library."""
        config = self.ports.config_store.load()
        current_path_policy_hash = calculate_path_policy_fingerprint(config.path_policy, config.artist_ids)

        with self.ports.uow as uow:
            libraries = _selected_libraries(uow, request)
            issues: list[CheckIssue] = []
            for library in libraries:
                active_tracks = tuple(
                    track
                    for track in uow.tracks.list_by_library(library.library_id)
                    if track.status == TrackStatus.ACTIVE
                )
                plans = tuple(uow.plans.list_by_library(library.library_id))

                issues.extend(_library_state_issues(library, current_path_policy_hash))
                issues.extend(self._track_issues(library, active_tracks))
                issues.extend(self._scan_issues(library, active_tracks))
                issues.extend(self._plan_source_issues(uow, library, plans))
                issues.extend(_pending_event_issues(uow, library))

            return tuple(issues)

    def _track_issues(self, library: Library, tracks: Sequence[Track]) -> tuple[CheckIssue, ...]:
        issues: list[CheckIssue] = []
        for track in tracks:
            if track.current_path != track.canonical_path:
                issues.append(
                    CheckIssue(
                        issue_type=CheckIssueType.CURRENT_PATH_DIFFERS_FROM_CANONICAL_PATH,
                        library_id=library.library_id,
                        path=track.current_path,
                        track_id=track.track_id,
                    )
                )

            filesystem_path = self.ports.path_resolver.resolve_library_path(library.root_path, track.current_path)
            try:
                snapshot = self.ports.file_snapshot_reader.capture(filesystem_path)
            except FileNotFoundError:
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

    def _scan_issues(self, library: Library, tracks: Sequence[Track]) -> tuple[CheckIssue, ...]:
        managed_paths = {track.current_path for track in tracks}
        managed_hashes = {track.content_hash for track in tracks}
        issues: list[CheckIssue] = []

        for entry in self.ports.file_scanner.scan(library.root_path):
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
            snapshot = self.ports.file_snapshot_reader.capture(entry.path)
        except FileNotFoundError:
            return False
        return snapshot.content_hash in managed_hashes

    def _plan_source_issues(
        self,
        uow: UnitOfWork,
        library: Library,
        plans: Sequence[Plan],
    ) -> tuple[CheckIssue, ...]:
        issues: list[CheckIssue] = []

        for plan in plans:
            if plan.status != PlanStatus.READY:
                continue
            for action in uow.plan_actions.list_by_plan(plan.plan_id):
                if action.status != ActionStatus.PLANNED or action.source_path is None:
                    continue
                if action.content_hash_at_plan is None and action.metadata_hash_at_plan is None:
                    continue

                source_filesystem_path = _resolve_action_path(self.ports.path_resolver, library, action.source_path)
                try:
                    snapshot = self.ports.file_snapshot_reader.capture(source_filesystem_path)
                except FileNotFoundError:
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


def _selected_libraries(uow: UnitOfWork, request: CheckLibraryRequest) -> tuple[Library, ...]:
    if request.library_id is None:
        return tuple(uow.libraries.list_all())

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
