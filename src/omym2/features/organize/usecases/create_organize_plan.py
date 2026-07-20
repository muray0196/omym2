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
from omym2.domain.models.companion_asset import CompanionAsset, CompanionAssetKind, CompanionAssetStatus
from omym2.domain.models.library import Library, LibraryStatus
from omym2.domain.models.operation import (
    OperationKind,
    PlanCreatedResult,
    RegisteredWithoutPlanResult,
)
from omym2.domain.models.plan import Plan, PlanStatus, PlanType
from omym2.domain.models.plan_action import (
    ActionStatus,
    ActionType,
    PlanAction,
    PlanActionDependency,
    PlanActionReason,
)
from omym2.domain.models.track import Track, TrackStatus
from omym2.domain.services.album_year import metadata_with_resolved_album_year
from omym2.domain.services.collision_policy import CollisionDecisionKind, CollisionPolicy, OccupiedPaths
from omym2.domain.services.companion_association import (
    CompanionAssociationResult,
    CompanionAudioCandidate,
    associate_companions,
    companion_action_type,
    companion_dependency_sources,
    companion_issue_reason,
    companion_kind,
)
from omym2.domain.services.companion_recovery import (
    CompanionRecoveryEvidence,
    RecoverableCompanion,
    find_recoverable_companions,
)
from omym2.domain.services.config_fingerprint import calculate_config_fingerprint, calculate_path_policy_fingerprint
from omym2.domain.services.path_policy import (
    PathPolicy,
    has_missing_required_metadata,
    path_generation_failure_reason,
    resolve_canonical_path_batch,
)
from omym2.domain.services.running_operation import running_operation
from omym2.domain.services.snapshot_baseline import snapshot_from_trusted_stat
from omym2.features.common_ports import (
    FileObservationChangedError,
    FileObservationInvalidPathError,
    FileSnapshotCaptureRequest,
    SourceInventoryRequest,
)
from omym2.features.organize.dto import OrganizeLibraryResult
from omym2.shared.paths import normalize_library_relative_path

if TYPE_CHECKING:
    from collections.abc import Sequence
    from datetime import datetime

    from omym2.domain.models.app_config import AppConfig
    from omym2.domain.models.artist_name_resolution import ArtistNameDiagnostics
    from omym2.domain.models.file_scan_entry import FileScanEntry
    from omym2.domain.models.file_snapshot import FileContentSnapshot, FileSnapshot
    from omym2.features.common_ports import SourceInventoryEntry, UnitOfWork
    from omym2.features.organize.dto import CreateOrganizePlanRequest
    from omym2.features.organize.ports import CreateOrganizePlanPorts
    from omym2.shared.ids import CompanionAssetId, LibraryId, TrackId

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
            _ = running_operation(
                uow.operations.lookup,
                request.operation_id,
                OperationKind.ORGANIZE_PLAN,
                required_message=RUNNING_OPERATION_REQUIRED_MESSAGE,
            )
            library = self._select_library(uow, request.library_root, path_policy_hash, timestamp)
            existing_track_records = tuple(uow.tracks.list_by_library(library.library_id))
            existing_companion_assets = tuple(uow.companion_assets.list_by_library(library.library_id))
            recoverable_companions = _load_recoverable_companions(
                uow,
                library.library_id,
                existing_track_records,
                existing_companion_assets,
            )

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
        inventory_entries = (
            tuple(self.ports.source_inventory_reader.scan(SourceInventoryRequest(root=library.root_path)))
            if config.companions.enabled
            else ()
        )
        companion_candidates = (
            self._companion_candidates(library, candidates, inventory_entries) if config.companions.enabled else ()
        )
        if config.companions.enabled:
            companion_candidates = _merge_organize_companion_candidates(
                companion_candidates,
                self._recovery_companion_candidates(
                    library,
                    candidates,
                    inventory_entries,
                    existing_track_records,
                    recoverable_companions,
                ),
            )

        with self.ports.uow as uow:
            operation = running_operation(
                uow.operations.lookup,
                request.operation_id,
                OperationKind.ORGANIZE_PLAN,
                required_message=RUNNING_OPERATION_REQUIRED_MESSAGE,
            )
            result = self._persist_result(
                uow,
                library,
                candidates,
                companion_candidates,
                _OrganizePersistence(
                    existing_tracks=existing_tracks,
                    existing_companion_assets=existing_companion_assets,
                    inventory_entries=inventory_entries,
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

        if has_missing_required_metadata(snapshot, config):
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
        batch_resolution = resolve_canonical_path_batch(
            self.ports.artist_name_resolver.resolve_many,
            metadata_batch,
            metadata_batch,
            config.path_policy,
            config.metadata.album_year_resolution,
        )
        projections = iter(batch_resolution.projections)
        diagnostics = iter(batch_resolution.diagnostics)
        resolved_years = batch_resolution.resolved_years
        album_disc_totals = batch_resolution.album_disc_totals
        judged_candidates: list[_OrganizeCandidate] = []

        for candidate in candidates:
            snapshot = candidate.snapshot
            if snapshot is None or candidate.block_reason is not None:
                judged_candidates.append(candidate)
                continue

            artist_names = next(projections)
            candidate_diagnostics = next(diagnostics)
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
                    artist_names=artist_names,
                )
            except ValueError as exc:
                judged_candidates.append(
                    replace(
                        candidate,
                        target_path=None,
                        block_reason=path_generation_failure_reason(exc),
                        artist_name_diagnostics=candidate_diagnostics,
                    )
                )
                continue

            judged_candidates.append(
                replace(
                    candidate,
                    target_path=target_path,
                    artist_name_diagnostics=candidate_diagnostics,
                )
            )

        return tuple(judged_candidates)

    def _companion_candidates(
        self,
        library: Library,
        candidates: Sequence[_OrganizeCandidate],
        inventory_entries: Sequence[SourceInventoryEntry],
    ) -> tuple[_OrganizeCompanionCandidate, ...]:
        association_result = associate_companions(
            tuple(CompanionAudioCandidate(candidate.source_path, candidate.target_path) for candidate in candidates),
            tuple(entry.relative_path for entry in inventory_entries),
        )
        return self._claimed_companion_candidates(
            library,
            inventory_entries,
            association_result,
        )

    def _claimed_companion_candidates(
        self,
        library: Library,
        inventory_entries: Sequence[SourceInventoryEntry],
        association_result: CompanionAssociationResult,
    ) -> tuple[_OrganizeCompanionCandidate, ...]:
        inventory_by_relative_path = {entry.relative_path: entry for entry in inventory_entries}
        association_by_source = {
            association.source_path: association for association in association_result.associations
        }
        issue_by_source = {issue.source_path: issue for issue in association_result.issues}
        claimed: list[_OrganizeCompanionCandidate] = []
        for source_path in sorted(association_result.claimed_source_paths):
            entry = inventory_by_relative_path[source_path]
            association = association_by_source.get(source_path)
            issue = issue_by_source.get(source_path)
            snapshot, observation_reason = self._capture_companion_snapshot(entry, library.root_path)
            claimed.append(
                _OrganizeCompanionCandidate(
                    kind=companion_kind(association, issue),
                    source_path=source_path,
                    target_path=None if association is None else association.target_path,
                    owner_audio_source_path=(None if association is None else association.owner_audio_source_path),
                    dependency_audio_source_paths=companion_dependency_sources(association, issue),
                    snapshot=snapshot,
                    reason=observation_reason or companion_issue_reason(issue),
                )
            )
        return tuple(claimed)

    def _capture_companion_snapshot(
        self,
        entry: SourceInventoryEntry,
        library_root: str,
    ) -> tuple[FileContentSnapshot | None, PlanActionReason | None]:
        try:
            return self.ports.file_content_snapshot_reader.capture(entry.path, root=library_root), None
        except FileNotFoundError:
            return None, PlanActionReason.SOURCE_MISSING
        except FileObservationChangedError, OSError:
            return None, PlanActionReason.SOURCE_CHANGED
        except FileObservationInvalidPathError, ValueError:
            return None, PlanActionReason.INVALID_PATH

    def _recovery_companion_candidates(
        self,
        library: Library,
        candidates: Sequence[_OrganizeCandidate],
        inventory_entries: Sequence[SourceInventoryEntry],
        existing_tracks: Sequence[Track],
        recoverable_companions: Sequence[RecoverableCompanion],
    ) -> tuple[_OrganizeCompanionCandidate, ...]:
        inventory_by_path = {entry.relative_path: entry for entry in inventory_entries}
        track_by_id = {track.track_id: track for track in existing_tracks}
        candidates_by_source: dict[str, list[_OrganizeCandidate]] = {}
        for candidate in candidates:
            candidates_by_source.setdefault(candidate.source_path, []).append(candidate)

        recoveries: list[_OrganizeCompanionCandidate] = []
        for recovery in recoverable_companions:
            if recovery.source_plan_type not in {PlanType.ORGANIZE, PlanType.REFRESH}:
                continue
            entry = inventory_by_path.get(recovery.source_path)
            if entry is None or not _recovery_tracks_are_stable(
                recovery,
                track_by_id,
                candidates_by_source,
            ):
                continue
            snapshot, reason = self._capture_companion_snapshot(entry, library.root_path)
            if reason is not None or snapshot is None or snapshot.content_hash != recovery.content_hash:
                continue
            recoveries.append(
                _OrganizeCompanionCandidate(
                    kind=recovery.kind,
                    source_path=recovery.source_path,
                    target_path=recovery.target_path,
                    owner_audio_source_path=None,
                    dependency_audio_source_paths=(),
                    snapshot=snapshot,
                    reason=None,
                    companion_asset_id=recovery.companion_asset_id,
                    owner_track_id=recovery.owner_track_id,
                )
            )
        return tuple(recoveries)

    def _persist_result(  # noqa: C901  # Audio, companion registration, and one-Plan persistence share one transaction.
        self,
        uow: UnitOfWork,
        library: Library,
        candidates: Sequence[_OrganizeCandidate],
        companion_candidates: Sequence[_OrganizeCompanionCandidate],
        persistence: _OrganizePersistence,
    ) -> OrganizeLibraryResult:
        existing_tracks = persistence.existing_tracks
        timestamp = persistence.timestamp
        occupied_paths = OccupiedPaths.from_paths(
            (
                *(candidate.source_path for candidate in candidates if candidate.snapshot is not None),
                *(entry.relative_path for entry in persistence.inventory_entries),
                *(track.current_path for track in existing_tracks.values() if track.status is TrackStatus.ACTIVE),
                *(
                    asset.current_path
                    for asset in persistence.existing_companion_assets
                    if asset.status is CompanionAssetStatus.ACTIVE
                ),
            )
        )
        target_counts = _target_counts(candidates, companion_candidates)
        action_records: list[_ActionRecord] = []
        tracks: list[Track] = []
        track_by_source: dict[str, Track] = {}
        audio_reason_by_source: dict[str, PlanActionReason | None] = {}

        for candidate in candidates:
            action_reason = candidate.block_reason or self._collision_reason(
                library,
                source_path=candidate.source_path,
                target_path=candidate.target_path,
                occupied_paths=occupied_paths,
                target_counts=target_counts,
            )
            audio_reason_by_source[candidate.source_path] = action_reason
            track = None
            if action_reason is None:
                track = self._track_for_candidate(library.library_id, candidate, existing_tracks, timestamp)
                tracks.append(track)
                track_by_source[candidate.source_path] = track

            if action_reason is not None or candidate.target_path != candidate.source_path:
                action_records.append(
                    _ActionRecord(
                        candidate=candidate,
                        track_id=None if track is None else track.track_id,
                        reason=action_reason,
                    )
                )

        track_by_id = {track.track_id: track for track in tracks}
        companion_action_records: list[_CompanionActionRecord] = []
        companion_assets: list[CompanionAsset] = []
        for candidate in companion_candidates:
            reason = _companion_owner_reason(
                candidate,
                audio_reason_by_source,
                track_by_source,
                track_by_id,
            )
            if reason is None:
                reason = self._collision_reason(
                    library,
                    source_path=candidate.source_path,
                    target_path=candidate.target_path,
                    occupied_paths=occupied_paths,
                    target_counts=target_counts,
                )
            owner_track = (
                track_by_id.get(candidate.owner_track_id)
                if candidate.owner_track_id is not None
                else track_by_source.get(candidate.owner_audio_source_path or "")
            )
            existing_asset = _existing_companion_asset(
                persistence.existing_companion_assets,
                candidate,
            )
            companion_asset_id = (
                candidate.companion_asset_id
                or (None if existing_asset is None else existing_asset.companion_asset_id)
                or self.ports.id_generator.new_companion_asset_id()
            )
            if (
                reason is None
                and candidate.target_path == candidate.source_path
                and owner_track is not None
                and candidate.snapshot is not None
            ):
                companion_assets.append(
                    _registered_companion_asset(
                        library,
                        candidate,
                        owner_track,
                        companion_asset_id,
                        existing_asset,
                        timestamp,
                    )
                )
                continue
            companion_action_records.append(
                _CompanionActionRecord(
                    candidate=candidate,
                    track_id=None if owner_track is None else owner_track.track_id,
                    companion_asset_id=companion_asset_id,
                    reason=reason,
                )
            )

        actions, dependencies = self._actions(
            library,
            action_records,
            companion_action_records,
        )
        final_library = _final_library_state(library, actions, timestamp)

        uow.libraries.save(final_library)
        for track in tracks:
            uow.tracks.save(track)
        for companion_asset in companion_assets:
            uow.companion_assets.save(companion_asset)

        plan = self._plan(final_library, actions, persistence.config_hash, timestamp)
        if plan is not None:
            uow.plans.save(plan)
            for action in actions:
                uow.plan_actions.save(action)
            for dependency in dependencies:
                uow.plan_action_dependencies.save(dependency)

        return OrganizeLibraryResult(
            library=final_library,
            plan=plan,
            actions=actions,
            track_count=len(tracks),
        )

    def _collision_reason(
        self,
        library: Library,
        *,
        source_path: str,
        target_path: str | None,
        occupied_paths: OccupiedPaths,
        target_counts: dict[str, int],
    ) -> PlanActionReason | None:
        if target_path is None or target_path == source_path:
            return None
        decision = CollisionPolicy().decide(
            target_path,
            occupied_paths,
            batch_target_count=target_counts[target_path],
        )
        if decision.kind is CollisionDecisionKind.BLOCKED:
            return decision.reason
        target_filesystem_path = self.ports.path_resolver.resolve_library_path(
            library.root_path,
            target_path,
        )
        if self.ports.file_presence.exists(target_filesystem_path):
            return PlanActionReason.TARGET_EXISTS
        return None

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

    def _actions(
        self,
        library: Library,
        records: Sequence[_ActionRecord],
        companion_records: Sequence[_CompanionActionRecord],
    ) -> tuple[tuple[PlanAction, ...], tuple[PlanActionDependency, ...]]:
        if len(records) == 0 and len(companion_records) == 0:
            return (), ()

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
                    artist_name_diagnostics=candidate.artist_name_diagnostics,
                )
            )
            sort_order += PLAN_ACTION_SORT_ORDER_STEP

        audio_action_by_source = {action.source_path: action for action in actions if action.source_path is not None}
        dependencies: list[PlanActionDependency] = []
        for record in companion_records:
            candidate = record.candidate
            action_id = self.ports.id_generator.new_action_id()
            owner_action = (
                None
                if candidate.owner_audio_source_path is None
                else audio_action_by_source.get(candidate.owner_audio_source_path)
            )
            actions.append(
                PlanAction(
                    action_id=action_id,
                    plan_id=plan_id,
                    library_id=library.library_id,
                    track_id=record.track_id,
                    action_type=companion_action_type(candidate.kind),
                    source_path=candidate.source_path,
                    target_path=candidate.target_path,
                    content_hash_at_plan=(None if candidate.snapshot is None else candidate.snapshot.content_hash),
                    metadata_hash_at_plan=None,
                    status=(ActionStatus.PLANNED if record.reason is None else ActionStatus.BLOCKED),
                    reason=record.reason,
                    sort_order=sort_order,
                    companion_asset_id=record.companion_asset_id,
                    owner_action_id=None if owner_action is None else owner_action.action_id,
                )
            )
            dependencies.extend(
                PlanActionDependency(
                    plan_id=plan_id,
                    action_id=action_id,
                    depends_on_action_id=dependency_action.action_id,
                )
                for source_path in candidate.dependency_audio_source_paths
                if (dependency_action := audio_action_by_source.get(source_path)) is not None
            )
            sort_order += PLAN_ACTION_SORT_ORDER_STEP
        return tuple(actions), tuple(dependencies)

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
    artist_name_diagnostics: ArtistNameDiagnostics | None = None


@dataclass(frozen=True, slots=True)
class _OrganizeCaptureInput:
    """One valid Library source awaiting full snapshot capture."""

    entry: FileScanEntry
    source_path: str


@dataclass(frozen=True, slots=True)
class _OrganizeCompanionCandidate:
    """One claimed Library companion and its reviewed planning evidence."""

    kind: CompanionAssetKind
    source_path: str
    target_path: str | None
    owner_audio_source_path: str | None
    dependency_audio_source_paths: tuple[str, ...]
    snapshot: FileContentSnapshot | None
    reason: PlanActionReason | None
    companion_asset_id: CompanionAssetId | None = None
    owner_track_id: TrackId | None = None


@dataclass(frozen=True, slots=True)
class _ActionRecord:
    """Intermediate action data before the shared Plan ID is generated."""

    candidate: _OrganizeCandidate
    track_id: TrackId | None
    reason: PlanActionReason | None


@dataclass(frozen=True, slots=True)
class _CompanionActionRecord:
    """Companion action inputs after owner Track and collision judgment."""

    candidate: _OrganizeCompanionCandidate
    track_id: TrackId | None
    companion_asset_id: CompanionAssetId
    reason: PlanActionReason | None


@dataclass(frozen=True, slots=True)
class _OrganizePersistence:
    """Inputs shared across organize Track and Plan persistence."""

    existing_tracks: dict[str, Track]
    existing_companion_assets: tuple[CompanionAsset, ...]
    inventory_entries: tuple[SourceInventoryEntry, ...]
    config_hash: str
    timestamp: datetime


def _load_recoverable_companions(
    uow: UnitOfWork,
    library_id: LibraryId,
    tracks: Sequence[Track],
    companion_assets: Sequence[CompanionAsset],
) -> tuple[RecoverableCompanion, ...]:
    plans = tuple(uow.plans.list_by_library(library_id))
    actions = tuple(action for plan in plans for action in uow.plan_actions.list_by_plan(plan.plan_id))
    dependencies = tuple(
        dependency for action in actions for dependency in uow.plan_action_dependencies.list_by_action(action.action_id)
    )
    return find_recoverable_companions(
        CompanionRecoveryEvidence(
            plans=plans,
            actions=actions,
            dependencies=dependencies,
            runs=tuple(uow.runs.list_by_library(library_id)),
            events=tuple(uow.file_events.list_by_library(library_id)),
            tracks=tracks,
            companion_assets=companion_assets,
        )
    )


def _merge_organize_companion_candidates(
    claimed: Sequence[_OrganizeCompanionCandidate],
    recoveries: Sequence[_OrganizeCompanionCandidate],
) -> tuple[_OrganizeCompanionCandidate, ...]:
    claimed_paths = {candidate.source_path for candidate in claimed}
    return (*claimed, *(candidate for candidate in recoveries if candidate.source_path not in claimed_paths))


def _recovery_tracks_are_stable(
    recovery: RecoverableCompanion,
    tracks_by_id: dict[TrackId, Track],
    candidates_by_source: dict[str, list[_OrganizeCandidate]],
) -> bool:
    for track_id in recovery.dependency_track_ids:
        track = tracks_by_id.get(track_id)
        if track is None:
            return False
        candidates = candidates_by_source.get(track.current_path, ())
        if len(candidates) != 1:
            return False
        candidate = candidates[0]
        if (
            candidate.snapshot is None
            or candidate.block_reason is not None
            or candidate.target_path != candidate.source_path
        ):
            return False
    return True


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


def _scanner_relative_path(library_root: str, path: str) -> str:
    """Return the lexical Library-relative scanner path for invalid sources."""
    try:
        relative_path = Path(path).expanduser().relative_to(Path(library_root).expanduser())
    except ValueError:
        return normalize_library_relative_path(Path(path).name)
    return normalize_library_relative_path(relative_path.as_posix())


def _target_counts(
    candidates: Sequence[_OrganizeCandidate],
    companion_candidates: Sequence[_OrganizeCompanionCandidate],
) -> dict[str, int]:
    target_counts: dict[str, int] = {}
    for candidate in candidates:
        if candidate.target_path is None:
            continue
        target_counts[candidate.target_path] = target_counts.get(candidate.target_path, 0) + 1
    for candidate in companion_candidates:
        if candidate.reason is not None or candidate.target_path is None:
            continue
        target_counts[candidate.target_path] = target_counts.get(candidate.target_path, 0) + 1
    return target_counts


def _companion_owner_reason(
    candidate: _OrganizeCompanionCandidate,
    audio_reason_by_source: dict[str, PlanActionReason | None],
    track_by_source: dict[str, Track],
    track_by_id: dict[TrackId, Track],
) -> PlanActionReason | None:
    if candidate.reason is not None:
        return candidate.reason
    if candidate.owner_track_id is not None:
        if candidate.target_path is None or candidate.owner_track_id not in track_by_id:
            return PlanActionReason.COMPANION_OWNER_BLOCKED
        return None
    owner_source = candidate.owner_audio_source_path
    if (
        candidate.target_path is None
        or owner_source is None
        or owner_source not in track_by_source
        or any(
            source_path not in audio_reason_by_source or audio_reason_by_source[source_path] is not None
            for source_path in candidate.dependency_audio_source_paths
        )
    ):
        return PlanActionReason.COMPANION_OWNER_BLOCKED
    return None


def _existing_companion_asset(
    companion_assets: Sequence[CompanionAsset],
    candidate: _OrganizeCompanionCandidate,
) -> CompanionAsset | None:
    if candidate.companion_asset_id is not None:
        return next(
            (asset for asset in companion_assets if asset.companion_asset_id == candidate.companion_asset_id),
            None,
        )
    return next(
        (
            asset
            for asset in companion_assets
            if asset.current_path == candidate.source_path and asset.kind is candidate.kind
        ),
        None,
    )


def _registered_companion_asset(  # noqa: PLR0913  # Stable asset identity and owner state remain explicit inputs.
    library: Library,
    candidate: _OrganizeCompanionCandidate,
    owner_track: Track,
    companion_asset_id: CompanionAssetId,
    existing_asset: CompanionAsset | None,
    timestamp: datetime,
) -> CompanionAsset:
    snapshot = candidate.snapshot
    target_path = candidate.target_path
    if snapshot is None or target_path is None:
        raise AssertionError(INCOMPLETE_CANDIDATE_MESSAGE)
    return CompanionAsset(
        companion_asset_id=companion_asset_id,
        library_id=library.library_id,
        kind=candidate.kind,
        owner_track_id=owner_track.track_id,
        current_path=candidate.source_path,
        canonical_path=target_path,
        content_hash=snapshot.content_hash,
        size=snapshot.size,
        mtime=snapshot.mtime,
        status=CompanionAssetStatus.ACTIVE,
        first_seen_at=timestamp if existing_asset is None else existing_asset.first_seen_at,
        last_seen_at=timestamp,
        updated_at=timestamp,
    )
