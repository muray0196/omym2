"""
Summary: Implements Library consistency checks and persists their findings.
Why: Diagnoses DB/filesystem drift and persists browseable findings.
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
from omym2.domain.models.companion_asset import CompanionAssetStatus
from omym2.domain.models.file_event import FileEventStatus, FileEventType
from omym2.domain.models.library import LibraryStatus
from omym2.domain.models.operation import CheckCompletedResult, Operation, OperationKind, OperationStatus
from omym2.domain.models.plan import PlanStatus, PlanType
from omym2.domain.models.plan_action import ActionStatus, ActionType
from omym2.domain.models.run import RunStatus
from omym2.domain.models.track import TrackStatus
from omym2.domain.services.companion_association import CompanionAudioCandidate, associate_companions
from omym2.domain.services.companion_recovery import (
    CompanionRecoveryEvidence,
    find_recoverable_companions,
)
from omym2.domain.services.config_fingerprint import calculate_path_policy_fingerprint
from omym2.domain.services.snapshot_baseline import snapshot_from_trusted_stat
from omym2.domain.services.unprocessed_collection import validate_unprocessed_path_layout
from omym2.features.check.dto import CheckLibraryResult
from omym2.features.common_ports import FileSnapshotCaptureRequest, SourceInventoryRequest

if TYPE_CHECKING:
    from collections.abc import Sequence
    from datetime import datetime

    from omym2.domain.models.companion_asset import CompanionAsset
    from omym2.domain.models.file_event import FileEvent
    from omym2.domain.models.file_scan_entry import FileScanEntry
    from omym2.domain.models.file_snapshot import FileContentSnapshot, FileSnapshot
    from omym2.domain.models.library import Library
    from omym2.domain.models.plan import Plan
    from omym2.domain.models.plan_action import PlanAction
    from omym2.domain.models.run import Run
    from omym2.domain.models.track import Track
    from omym2.features.check.dto import CheckLibraryRequest
    from omym2.features.check.ports import CheckLibraryPorts
    from omym2.features.common_ports import (
        BatchFileSnapshotReader,
        FileContentSnapshotReader,
        FileSystemPath,
        PathResolver,
        UnitOfWork,
    )
    from omym2.shared.ids import ActionId, CheckRunId, EventId, LibraryId, OperationId, PlanId, RunId

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
        )
        checked_at = self.ports.clock.now()
        snapshot_memo = _SnapshotMemo(self.ports.file_snapshot_reader)
        content_snapshot_memo = _ContentSnapshotMemo(self.ports.file_content_snapshot_reader)

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
                active_companion_assets = tuple(
                    asset
                    for asset in uow.companion_assets.list_by_library(library.library_id)
                    if asset.status == CompanionAssetStatus.ACTIVE
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
                library_issues.extend(
                    self._companion_asset_issues(
                        library,
                        active_tracks,
                        active_companion_assets,
                        content_snapshot_memo,
                    )
                )
                if not request.trust_stat:
                    scan_entries = tuple(self.ports.file_scanner.scan(library.root_path))
                library_issues.extend(self._scan_issues(library, active_tracks, scan_entries))
                if config.companions.enabled:
                    library_issues.extend(
                        self._unmanaged_companion_issues(library, active_tracks, active_companion_assets)
                    )
                library_issues.extend(
                    self._failed_companion_source_issues(
                        uow,
                        library,
                        plans,
                        active_tracks,
                        active_companion_assets,
                        content_snapshot_memo,
                    )
                )
                library_issues.extend(
                    self._plan_source_issues(
                        uow,
                        library,
                        plans,
                        snapshot_memo,
                        content_snapshot_memo,
                    )
                )
                library_issues.extend(
                    self._unprocessed_event_issues(
                        uow,
                        library,
                        plans,
                        content_snapshot_memo,
                    )
                )
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

    def _companion_asset_issues(
        self,
        library: Library,
        tracks: Sequence[Track],
        companion_assets: Sequence[CompanionAsset],
        snapshot_memo: _ContentSnapshotMemo,
    ) -> tuple[CheckIssue, ...]:
        active_track_ids = {track.track_id for track in tracks}
        issues: list[CheckIssue] = []
        for asset in companion_assets:
            if asset.owner_track_id not in active_track_ids:
                issues.append(
                    CheckIssue(
                        issue_type=CheckIssueType.COMPANION_OWNER_MISSING,
                        library_id=library.library_id,
                        path=asset.current_path,
                        companion_asset_id=asset.companion_asset_id,
                    )
                )
            if asset.current_path != asset.canonical_path:
                issues.append(
                    CheckIssue(
                        issue_type=CheckIssueType.COMPANION_CURRENT_PATH_DIFFERS_FROM_CANONICAL_PATH,
                        library_id=library.library_id,
                        path=asset.current_path,
                        companion_asset_id=asset.companion_asset_id,
                    )
                )

            filesystem_path = self.ports.path_resolver.resolve_library_path(
                library.root_path,
                asset.current_path,
            )
            snapshot = snapshot_memo.capture(filesystem_path, root=library.root_path)
            if snapshot is None:
                issues.append(
                    CheckIssue(
                        issue_type=CheckIssueType.COMPANION_FILE_MISSING,
                        library_id=library.library_id,
                        path=asset.current_path,
                        companion_asset_id=asset.companion_asset_id,
                    )
                )
            elif snapshot.content_hash != asset.content_hash:
                issues.append(
                    CheckIssue(
                        issue_type=CheckIssueType.COMPANION_CONTENT_HASH_CHANGED,
                        library_id=library.library_id,
                        path=asset.current_path,
                        companion_asset_id=asset.companion_asset_id,
                    )
                )
        return tuple(issues)

    def _unmanaged_companion_issues(
        self,
        library: Library,
        tracks: Sequence[Track],
        companion_assets: Sequence[CompanionAsset],
    ) -> tuple[CheckIssue, ...]:
        if not tracks:
            return ()
        inventory = self.ports.source_inventory_reader.scan(SourceInventoryRequest(root=library.root_path))
        associations = associate_companions(
            (
                CompanionAudioCandidate(
                    source_path=track.current_path,
                    target_path=track.current_path,
                )
                for track in tracks
            ),
            (entry.relative_path for entry in inventory),
        )
        managed_paths = {asset.current_path for asset in companion_assets}
        return tuple(
            CheckIssue(
                issue_type=CheckIssueType.UNMANAGED_COMPANION_EXISTS,
                library_id=library.library_id,
                path=path,
            )
            for path in sorted(associations.claimed_source_paths - managed_paths)
        )

    def _failed_companion_source_issues(  # noqa: PLR0913  # Durable and filesystem evidence stay explicit.
        self,
        uow: UnitOfWork,
        library: Library,
        plans: Sequence[Plan],
        tracks: Sequence[Track],
        companion_assets: Sequence[CompanionAsset],
        snapshot_memo: _ContentSnapshotMemo,
    ) -> tuple[CheckIssue, ...]:
        actions = tuple(action for plan in plans for action in uow.plan_actions.list_by_plan(plan.plan_id))
        dependencies = tuple(
            dependency
            for action in actions
            for dependency in uow.plan_action_dependencies.list_by_action(action.action_id)
        )
        recoveries = find_recoverable_companions(
            CompanionRecoveryEvidence(
                plans=plans,
                actions=actions,
                dependencies=dependencies,
                runs=tuple(uow.runs.list_by_library(library.library_id)),
                events=tuple(uow.file_events.list_by_library(library.library_id)),
                tracks=tracks,
                companion_assets=companion_assets,
            )
        )
        issues: list[CheckIssue] = []
        for recovery in recoveries:
            if PurePath(recovery.source_path).is_absolute():
                filesystem_path = recovery.source_path
                source_root = recovery.source_root
            else:
                filesystem_path = self.ports.path_resolver.resolve_library_path(
                    library.root_path,
                    recovery.source_path,
                )
                source_root = library.root_path
            snapshot = None if source_root is None else snapshot_memo.capture(filesystem_path, root=source_root)
            if snapshot is None or snapshot.content_hash != recovery.content_hash:
                continue
            issues.append(
                CheckIssue(
                    issue_type=CheckIssueType.FAILED_COMPANION_SOURCE_EXISTS,
                    library_id=library.library_id,
                    path=recovery.source_path,
                    plan_id=recovery.source_plan_id,
                    companion_asset_id=recovery.companion_asset_id,
                    detail=("add" if recovery.source_plan_type is PlanType.ADD else "organize"),
                )
            )
        return tuple(issues)

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
        content_snapshot_memo: _ContentSnapshotMemo,
    ) -> tuple[CheckIssue, ...]:
        source_checks: list[_PlanSourceCheck] = []
        content_source_checks: list[_PlanContentSourceCheck] = []
        for plan in plans:
            if plan.status != PlanStatus.READY:
                continue
            for action in uow.plan_actions.list_by_plan(plan.plan_id):
                if action.status != ActionStatus.PLANNED or action.source_path is None:
                    continue
                if action.content_hash_at_plan is None and action.metadata_hash_at_plan is None:
                    continue

                if action.companion_asset_id is not None or action.action_type is ActionType.MOVE_UNPROCESSED:
                    content_source_checks.append(_content_source_check(self.ports.path_resolver, library, plan, action))
                else:
                    source_filesystem_path = _resolve_action_path(
                        self.ports.path_resolver,
                        library,
                        action.source_path,
                    )
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

        issues.extend(
            _content_plan_source_issues(
                library,
                content_source_checks,
                content_snapshot_memo,
            )
        )
        return tuple(issues)

    def _unprocessed_event_issues(
        self,
        uow: UnitOfWork,
        library: Library,
        plans: Sequence[Plan],
        snapshot_memo: _ContentSnapshotMemo,
    ) -> tuple[CheckIssue, ...]:
        """Check collected files still owned only by durable mutation history."""
        plans_by_id = {plan.plan_id: plan for plan in plans}
        actions = tuple(action for plan in plans for action in uow.plan_actions.list_by_plan(plan.plan_id))
        actions_by_id = {action.action_id: action for action in actions}
        action_ids_with_dependencies = frozenset(
            action.action_id for action in actions if uow.plan_action_dependencies.list_by_action(action.action_id)
        )
        runs = tuple(uow.runs.list_by_library(library.library_id))
        runs_by_id = {run.run_id: run for run in runs}
        library_events = tuple(uow.file_events.list_by_library(library.library_id))
        run_events = tuple(event for run in runs for event in uow.file_events.list_by_run(run.run_id))
        events_by_id = {event.event_id: event for event in run_events}
        event_count_by_action_id = Counter(event.plan_action_id for event in run_events)
        reversed_event_ids = _confirmed_unprocessed_reversal_ids(
            plans_by_id,
            actions_by_id,
            runs_by_id,
            run_events,
            events_by_id,
            action_ids_with_dependencies,
            event_count_by_action_id,
        )

        issues: list[CheckIssue] = []
        for event in library_events:
            if (
                event.event_id in reversed_event_ids
                or event.event_type is not FileEventType.MOVE_UNPROCESSED_FILE
                or event.status is not FileEventStatus.SUCCEEDED
            ):
                continue
            action = actions_by_id.get(event.plan_action_id)
            if action is None:
                continue
            plan = plans_by_id.get(action.plan_id)
            run = runs_by_id.get(event.run_id)
            if (
                plan is None
                or run is None
                or not _unprocessed_source_event_is_valid(
                    plan,
                    action,
                    run,
                    event,
                    action_event_count=event_count_by_action_id[action.action_id],
                    has_dependencies=action.action_id in action_ids_with_dependencies,
                )
            ):
                continue

            source_root = plan.source_root_at_plan
            if source_root is None:
                continue
            snapshot = snapshot_memo.capture(event.target_path, root=source_root)
            if snapshot is None:
                issue_type = CheckIssueType.UNPROCESSED_FILE_MISSING
            elif snapshot.content_hash != action.content_hash_at_plan:
                issue_type = CheckIssueType.UNPROCESSED_CONTENT_HASH_CHANGED
            else:
                continue
            issues.append(
                CheckIssue(
                    issue_type=issue_type,
                    library_id=library.library_id,
                    path=event.target_path,
                    plan_id=plan.plan_id,
                )
            )
        return tuple(issues)


def _unprocessed_source_event_is_valid(  # noqa: PLR0913  # Durable history fields stay explicit.
    plan: Plan,
    action: PlanAction,
    run: Run,
    event: FileEvent,
    *,
    action_event_count: int,
    has_dependencies: bool,
) -> bool:
    """Return whether one collected-file event has exact terminal Add provenance."""
    completed_at = event.completed_at
    run_completed_at = run.completed_at
    return (
        completed_at is not None
        and run_completed_at is not None
        and plan.plan_type is PlanType.ADD
        and plan.source_run_id is None
        and plan.status in {PlanStatus.APPLIED, PlanStatus.PARTIAL_FAILED, PlanStatus.FAILED}
        and plan.source_root_at_plan is not None
        and run.plan_id == plan.plan_id
        and run.library_id == plan.library_id
        and run.status in {RunStatus.SUCCEEDED, RunStatus.PARTIAL_FAILED, RunStatus.FAILED}
        and plan.created_at <= run.started_at <= event.started_at
        and event.started_at <= completed_at <= run_completed_at
        and event.run_id == run.run_id
        and event.library_id == plan.library_id
        and event.plan_action_id == action.action_id
        and event.event_type is FileEventType.MOVE_UNPROCESSED_FILE
        and event.status is FileEventStatus.SUCCEEDED
        and event.source_path == action.source_path
        and event.target_path == action.target_path
        and event.companion_asset_id is None
        and action.plan_id == plan.plan_id
        and action.library_id == plan.library_id
        and action.action_type is ActionType.MOVE_UNPROCESSED
        and action.status is ActionStatus.APPLIED
        and action.reason is None
        and action.track_id is None
        and action.content_hash_at_plan is not None
        and action.metadata_hash_at_plan is None
        and action.reverses_event_id is None
        and action.artist_name_diagnostics is None
        and action.companion_asset_id is None
        and action.owner_action_id is None
        and action_event_count == 1
        and not has_dependencies
        and validate_unprocessed_path_layout(
            plan.source_root_at_plan,
            action.source_path or "",
            action.target_path or "",
            excluded_root=plan.library_root_at_plan,
        )
        is not None
    )


def _confirmed_unprocessed_reversal_ids(  # noqa: PLR0913  # Cross-record provenance is explicit.
    plans_by_id: dict[PlanId, Plan],
    actions_by_id: dict[ActionId, PlanAction],
    runs_by_id: dict[RunId, Run],
    events: Sequence[FileEvent],
    events_by_id: dict[EventId, FileEvent],
    action_ids_with_dependencies: frozenset[ActionId],
    event_count_by_action_id: Counter[ActionId],
) -> frozenset[EventId]:
    """Return source events with one strongly matched successful inverse mutation."""
    reversed_event_ids: set[EventId] = set()
    for reversal_event in events:
        reversal_action = actions_by_id.get(reversal_event.plan_action_id)
        if reversal_action is None or reversal_action.reverses_event_id is None:
            continue
        source_event = events_by_id.get(reversal_action.reverses_event_id)
        if source_event is None:
            continue
        source_action = actions_by_id.get(source_event.plan_action_id)
        reversal_plan = plans_by_id.get(reversal_action.plan_id)
        source_plan = None if source_action is None else plans_by_id.get(source_action.plan_id)
        reversal_run = runs_by_id.get(reversal_event.run_id)
        source_run = runs_by_id.get(source_event.run_id)
        reversal_completed_at = reversal_event.completed_at
        reversal_run_completed_at = None if reversal_run is None else reversal_run.completed_at
        source_run_completed_at = None if source_run is None else source_run.completed_at
        if (
            source_action is not None
            and reversal_plan is not None
            and source_plan is not None
            and reversal_run is not None
            and source_run is not None
            and reversal_completed_at is not None
            and reversal_run_completed_at is not None
            and source_run_completed_at is not None
            and _unprocessed_source_event_is_valid(
                source_plan,
                source_action,
                source_run,
                source_event,
                action_event_count=event_count_by_action_id[source_action.action_id],
                has_dependencies=source_action.action_id in action_ids_with_dependencies,
            )
            and reversal_event.status is FileEventStatus.SUCCEEDED
            and reversal_event.event_type is FileEventType.MOVE_UNPROCESSED_FILE
            and reversal_event.library_id == reversal_plan.library_id
            and reversal_event.companion_asset_id is None
            and reversal_event.source_path == reversal_action.source_path == source_event.target_path
            and reversal_event.target_path == reversal_action.target_path == source_event.source_path
            and reversal_action.action_type is ActionType.MOVE_UNPROCESSED
            and reversal_action.status is ActionStatus.APPLIED
            and reversal_action.reason is None
            and reversal_action.plan_id == reversal_plan.plan_id
            and reversal_action.library_id == reversal_plan.library_id == source_plan.library_id
            and reversal_action.track_id is None
            and reversal_action.content_hash_at_plan == source_action.content_hash_at_plan
            and reversal_action.metadata_hash_at_plan is None
            and reversal_action.artist_name_diagnostics is None
            and reversal_action.companion_asset_id is None
            and reversal_action.owner_action_id is None
            and reversal_action.action_id not in action_ids_with_dependencies
            and event_count_by_action_id[reversal_action.action_id] == 1
            and reversal_plan.plan_type is PlanType.UNDO
            and reversal_plan.status in {PlanStatus.APPLIED, PlanStatus.PARTIAL_FAILED, PlanStatus.FAILED}
            and reversal_plan.source_run_id == source_event.run_id
            and reversal_plan.source_root_at_plan == source_plan.source_root_at_plan
            and reversal_plan.config_hash == source_plan.config_hash
            and reversal_run.plan_id == reversal_plan.plan_id
            and reversal_run.library_id == reversal_plan.library_id
            and reversal_run.status in {RunStatus.SUCCEEDED, RunStatus.PARTIAL_FAILED, RunStatus.FAILED}
            and source_event.completed_at is not None
            and source_event.completed_at <= source_run_completed_at <= reversal_plan.created_at
            and reversal_plan.created_at <= reversal_run.started_at <= reversal_event.started_at
            and reversal_event.started_at <= reversal_completed_at
            and reversal_completed_at <= reversal_run_completed_at
        ):
            reversed_event_ids.add(source_event.event_id)
    return frozenset(reversed_event_ids)


class CheckLibraryError(ValueError):
    """Raised when check cannot select the requested Library."""


@dataclass(frozen=True, slots=True)
class _PlanSourceCheck:
    """One READY Plan source awaiting a full snapshot comparison."""

    plan: Plan
    action: PlanAction
    path: FileSystemPath


@dataclass(frozen=True, slots=True)
class _PlanContentSourceCheck:
    """One READY metadata-free Plan source awaiting a content comparison."""

    plan: Plan
    action: PlanAction
    path: FileSystemPath
    root: FileSystemPath | None


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


@dataclass(slots=True)
class _ContentSnapshotMemo:
    """Reuse safe content observations and disappeared results during one check."""

    reader: FileContentSnapshotReader
    _snapshots_by_path_and_root: dict[tuple[str, str], FileContentSnapshot | None] = field(default_factory=dict)

    def capture(self, path: FileSystemPath, *, root: FileSystemPath) -> FileContentSnapshot | None:
        """Capture once, treating a missing or unsafe regular-file path as absent."""
        key = (fspath(path), fspath(root))
        if key not in self._snapshots_by_path_and_root:
            try:
                snapshot = self.reader.capture(path, root=root)
            except FileNotFoundError, NotADirectoryError, ValueError:
                snapshot = None
            self._snapshots_by_path_and_root[key] = snapshot
        return self._snapshots_by_path_and_root[key]


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


def _content_source_check(
    path_resolver: PathResolver,
    library: Library,
    plan: Plan,
    action: PlanAction,
) -> _PlanContentSourceCheck:
    source_path = action.source_path
    if source_path is None:
        raise AssertionError
    if PurePath(source_path).is_absolute():
        return _PlanContentSourceCheck(
            plan=plan,
            action=action,
            path=source_path,
            root=plan.source_root_at_plan,
        )
    return _PlanContentSourceCheck(
        plan=plan,
        action=action,
        path=path_resolver.resolve_library_path(library.root_path, source_path),
        root=library.root_path,
    )


def _content_plan_source_issues(
    library: Library,
    source_checks: Sequence[_PlanContentSourceCheck],
    snapshot_memo: _ContentSnapshotMemo,
) -> tuple[CheckIssue, ...]:
    issues: list[CheckIssue] = []
    for source_check in source_checks:
        action = source_check.action
        snapshot = (
            None if source_check.root is None else snapshot_memo.capture(source_check.path, root=source_check.root)
        )
        detail: str | None = None
        if snapshot is None:
            detail = "source_missing"
        elif action.content_hash_at_plan is not None and snapshot.content_hash != action.content_hash_at_plan:
            detail = "source_changed"
        if detail is not None:
            issues.append(
                CheckIssue(
                    issue_type=CheckIssueType.PLAN_SOURCE_CHANGED,
                    library_id=library.library_id,
                    path=action.source_path,
                    plan_id=source_check.plan.plan_id,
                    companion_asset_id=action.companion_asset_id,
                    detail=detail,
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
                companion_asset_id=event.companion_asset_id,
            )
            for event in pending_events_by_run.get(run.run_id, ())
        )
    return tuple(issues)


def _resolve_action_path(path_resolver: PathResolver, library: Library, path: str) -> FileSystemPath:
    if PurePath(path).is_absolute():
        return path
    return path_resolver.resolve_library_path(library.root_path, path)
