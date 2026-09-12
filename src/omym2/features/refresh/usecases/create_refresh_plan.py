"""
Summary: Implements refresh Plan creation for managed Library Tracks.
Why: Relocates files after tag correction without direct file mutation.
"""

from __future__ import annotations

from collections import Counter
from dataclasses import dataclass, replace
from datetime import timedelta
from os import fspath
from pathlib import PurePath, PurePosixPath
from typing import TYPE_CHECKING

from omym2.config import (
    OPERATION_RESULT_RETENTION_HOURS,
    OPERATION_TOMBSTONE_RETENTION_DAYS,
    PLAN_ACTION_SORT_ORDER_START,
    PLAN_ACTION_SORT_ORDER_STEP,
)
from omym2.domain.models.companion_asset import CompanionAsset, CompanionAssetKind, CompanionAssetStatus
from omym2.domain.models.library import LibraryStatus
from omym2.domain.models.operation import OperationKind, PlanCreatedResult
from omym2.domain.models.plan import Plan, PlanStatus, PlanType
from omym2.domain.models.plan_action import (
    ActionStatus,
    ActionType,
    PlanAction,
    PlanActionDependency,
    PlanActionReason,
)
from omym2.domain.models.track import TrackStatus
from omym2.domain.services.album_year import metadata_with_resolved_album_year
from omym2.domain.services.artist_name_reconciliation import artist_name_reconciliation_required
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
from omym2.domain.services.config_fingerprint import (
    STALE_LIBRARY_MESSAGE as _STALE_LIBRARY_MESSAGE,
)
from omym2.domain.services.config_fingerprint import (
    calculate_config_fingerprint,
    calculate_path_policy_fingerprint,
    is_path_policy_stale,
)
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
from omym2.features.refresh.dto import RefreshTargetKind
from omym2.shared.paths import normalize_library_relative_path

if TYPE_CHECKING:
    from collections.abc import Sequence
    from datetime import datetime

    from omym2.domain.models.app_config import AppConfig
    from omym2.domain.models.artist_name_resolution import ArtistNameDiagnostics, ArtistNameResolution
    from omym2.domain.models.file_snapshot import FileContentSnapshot, FileSnapshot
    from omym2.domain.models.library import Library
    from omym2.domain.models.track import Track
    from omym2.domain.models.track_metadata import TrackMetadata
    from omym2.features.common_ports import FileSystemPath, SourceInventoryEntry, UnitOfWork
    from omym2.features.refresh.dto import CreateRefreshPlanRequest
    from omym2.features.refresh.ports import CreateRefreshPlanPorts
    from omym2.shared.ids import CompanionAssetId, PlanId, TrackId

AMBIGUOUS_REGISTERED_LIBRARY_MESSAGE = (
    "Multiple registered Libraries exist. Library selection is not supported for refresh yet."
)
ARTIST_NAME_RECONCILIATION_REQUIRED_MESSAGE = (
    "Artist naming for Library tracks outside this refresh Plan changed. Run organize before refresh."
)
NO_REGISTERED_LIBRARY_MESSAGE = "No registered Library can be selected. Run organize --library PATH."
REFRESH_TARGET_NOT_FOUND_MESSAGE = "Refresh target does not match any managed active Track."
SELECTED_LIBRARY_NOT_FOUND_MESSAGE = "Selected Library was not found."
SELECTED_LIBRARY_NOT_REGISTERED_MESSAGE = "Selected Library is not registered. Run organize --library PATH."
TARGET_OUTSIDE_LIBRARY_MESSAGE = "Refresh target must be inside the selected Library."
TARGET_SELECTOR_COUNT_MESSAGE = "Refresh requires exactly one target: track_id, target_path, or include_all."
SUMMARY_ACTION_COUNT_KEY = "action_count"
SUMMARY_BLOCKED_ACTIONS_KEY = "blocked_actions"
SUMMARY_METADATA_ACTIONS_KEY = "metadata_actions"
SUMMARY_MOVE_ACTIONS_KEY = "move_actions"
RUNNING_OPERATION_REQUIRED_MESSAGE = "Refresh completion requires its corresponding running Operation."


@dataclass(frozen=True, slots=True)
class CreateRefreshPlanUseCase:
    """Create refresh relocation Plans without moving Library music files."""

    ports: CreateRefreshPlanPorts

    def execute(self, request: CreateRefreshPlanRequest) -> Plan:
        """Create a refresh Plan for selected managed Tracks."""
        _require_one_target_selector(request)
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
                OperationKind.REFRESH_PLAN,
                required_message=RUNNING_OPERATION_REQUIRED_MESSAGE,
            )
            library = _select_registered_library(uow, request, path_policy_hash)
            active_tracks = tuple(
                track for track in uow.tracks.list_by_library(library.library_id) if track.status == TrackStatus.ACTIVE
            )
            active_companion_assets = tuple(
                asset
                for asset in uow.companion_assets.list_by_library(library.library_id)
                if asset.status is CompanionAssetStatus.ACTIVE
            )
            selected_tracks = self._selected_tracks(request, library, active_tracks)

        trust_eligible_paths = {
            path for path, count in Counter(track.current_path for track in active_tracks).items() if count == 1
        }
        source_paths = tuple(
            self.ports.path_resolver.resolve_library_path(library.root_path, track.current_path)
            for track in selected_tracks
        )
        snapshots = self._capture_snapshots(
            selected_tracks,
            source_paths,
            trust_eligible_paths,
            timestamp,
            trust_stat=request.trust_stat,
        )
        candidates = tuple(
            self._candidate(track, snapshot, config) for track, snapshot in zip(selected_tracks, snapshots, strict=True)
        )
        candidates = self._with_target_paths(candidates, active_tracks, config, path_policy)
        inventory_entries = (
            tuple(self.ports.source_inventory_reader.scan(SourceInventoryRequest(root=library.root_path)))
            if config.companions.enabled
            else ()
        )
        companion_candidates = (
            self._companion_candidates(
                library,
                candidates,
                active_tracks,
                active_companion_assets,
                inventory_entries,
            )
            if config.companions.enabled
            else ()
        )
        companion_candidates = _with_companion_owner_blocks(candidates, companion_candidates)
        candidates, companion_candidates = self._with_target_conflicts(
            library,
            candidates,
            active_tracks,
            active_companion_assets,
            companion_candidates,
        )
        companion_candidates = _with_companion_owner_blocks(candidates, companion_candidates)
        if _artist_name_reconciliation_required(
            active_tracks=active_tracks,
            candidates=candidates,
            config=config,
            path_policy=path_policy,
        ):
            raise RefreshLibraryReconciliationRequiredError(ARTIST_NAME_RECONCILIATION_REQUIRED_MESSAGE)
        plan_id = self.ports.id_generator.new_plan_id()
        actions, dependencies = self._actions(
            plan_id,
            library,
            candidates,
            companion_candidates,
        )
        plan = _plan(plan_id, library, actions, config_hash, timestamp)

        with self.ports.uow as uow:
            operation = running_operation(
                uow.operations.lookup,
                request.operation_id,
                OperationKind.REFRESH_PLAN,
                required_message=RUNNING_OPERATION_REQUIRED_MESSAGE,
            )
            uow.plans.save(plan)
            for action in actions:
                uow.plan_actions.save(action)
            for dependency in dependencies:
                uow.plan_action_dependencies.save(dependency)
            if operation is not None:
                completed_at = self.ports.clock.now()
                uow.operations.save(
                    replace(operation, library_id=library.library_id).mark_succeeded(
                        result=PlanCreatedResult(plan.plan_id),
                        completed_at=completed_at,
                        result_expires_at=completed_at + timedelta(hours=OPERATION_RESULT_RETENTION_HOURS),
                        tombstone_expires_at=completed_at + timedelta(days=OPERATION_TOMBSTONE_RETENTION_DAYS),
                    )
                )

            uow.commit()
            return plan

    def _capture_snapshots(
        self,
        tracks: Sequence[Track],
        source_paths: Sequence[FileSystemPath],
        trust_eligible_paths: set[str],
        timestamp: datetime,
        *,
        trust_stat: bool,
    ) -> tuple[FileSnapshot | None, ...]:
        snapshots: list[FileSnapshot | None] = [None] * len(tracks)
        uncached_indexes: list[int] = []
        uncached_requests: list[FileSnapshotCaptureRequest] = []

        for index, (track, source_path) in enumerate(zip(tracks, source_paths, strict=True)):
            if trust_stat and track.current_path in trust_eligible_paths:
                try:
                    observation = self.ports.file_stat_reader.observe(source_path)
                except FileNotFoundError:
                    continue
                trusted_snapshot = snapshot_from_trusted_stat(
                    track,
                    track.current_path,
                    fspath(source_path),
                    observation,
                    timestamp,
                )
                if trusted_snapshot is not None:
                    snapshots[index] = trusted_snapshot
                    continue

            uncached_indexes.append(index)
            uncached_requests.append(FileSnapshotCaptureRequest(source_path))

        if len(uncached_requests) > 0:
            captured = self.ports.file_snapshot_reader.capture_many(tuple(uncached_requests))
            for index, snapshot in zip(uncached_indexes, captured, strict=True):
                snapshots[index] = snapshot

        return tuple(snapshots)

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
        if request.target_kind is RefreshTargetKind.FILE:
            return _require_matches(exact_matches)
        if request.target_kind is None and len(exact_matches) > 0:
            return exact_matches

        prefix = f"{relative_target}/"
        return _require_matches(tuple(track for track in active_tracks if track.current_path.startswith(prefix)))

    def _candidate(
        self,
        track: Track,
        snapshot: FileSnapshot | None,
        config: AppConfig,
    ) -> _RefreshCandidate:
        if snapshot is None:
            return _blocked_candidate(track, PlanActionReason.SOURCE_MISSING)

        if has_missing_required_metadata(snapshot, config):
            return _blocked_candidate(track, PlanActionReason.MISSING_REQUIRED_METADATA, snapshot=snapshot)

        return _RefreshCandidate(
            track=track,
            snapshot=snapshot,
            target_path=None,
            reason=None,
            needs_action=False,
        )

    def _with_target_paths(
        self,
        candidates: Sequence[_RefreshCandidate],
        active_tracks: Sequence[Track],
        config: AppConfig,
        path_policy: PathPolicy,
    ) -> tuple[_RefreshCandidate, ...]:
        candidate_metadata = _candidate_metadata(candidates)
        metadata_batch = _effective_metadata_batch(candidates, active_tracks)
        batch_resolution = resolve_canonical_path_batch(
            self.ports.artist_name_resolver.resolve_many,
            candidate_metadata,
            metadata_batch,
            config.path_policy,
            config.metadata.album_year_resolution,
        )
        resolution_pairs = iter(batch_resolution.resolution_pairs)
        projections = iter(batch_resolution.projections)
        diagnostics = iter(batch_resolution.diagnostics)
        resolved_years = batch_resolution.resolved_years
        album_disc_totals = batch_resolution.album_disc_totals
        judged_candidates: list[_RefreshCandidate] = []

        for candidate in candidates:
            snapshot = candidate.snapshot
            if snapshot is None or candidate.reason is not None:
                judged_candidates.append(candidate)
                continue

            artist_names = next(projections)
            candidate_diagnostics = next(diagnostics)
            candidate_resolutions = next(resolution_pairs)
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
                        reason=path_generation_failure_reason(exc),
                        needs_action=True,
                        artist_name_resolutions=candidate_resolutions,
                        artist_name_diagnostics=candidate_diagnostics,
                    )
                )
                continue

            judged_candidates.append(
                replace(
                    candidate,
                    target_path=target_path,
                    needs_action=(
                        target_path != candidate.track.current_path
                        or snapshot.content_hash != candidate.track.content_hash
                        or snapshot.metadata_hash != candidate.track.metadata_hash
                    ),
                    artist_name_resolutions=candidate_resolutions,
                    artist_name_diagnostics=candidate_diagnostics,
                )
            )

        return tuple(judged_candidates)

    def _companion_candidates(
        self,
        library: Library,
        candidates: Sequence[_RefreshCandidate],
        active_tracks: Sequence[Track],
        active_companion_assets: Sequence[CompanionAsset],
        inventory_entries: Sequence[SourceInventoryEntry],
    ) -> tuple[_RefreshCompanionCandidate, ...]:
        selected_relocation_sources = {
            candidate.track.current_path for candidate in candidates if _is_relocation_candidate(candidate)
        }
        if len(selected_relocation_sources) == 0:
            return ()

        candidate_by_track_id = {candidate.track.track_id: candidate for candidate in candidates}
        audio_candidates = tuple(
            CompanionAudioCandidate(
                source_path=track.current_path,
                target_path=(
                    selected_candidate.target_path
                    if (selected_candidate := candidate_by_track_id.get(track.track_id)) is not None
                    else track.current_path
                ),
            )
            for track in active_tracks
        )
        inventory_paths = {
            *(entry.relative_path for entry in inventory_entries),
            *(asset.current_path for asset in active_companion_assets),
        }
        association_result = associate_companions(audio_candidates, inventory_paths)
        claimed = list(
            self._claimed_refresh_companions(
                library,
                active_tracks,
                active_companion_assets,
                inventory_entries,
                association_result,
                selected_relocation_sources,
            )
        )
        claimed_keys = {(candidate.source_path, candidate.kind) for candidate in claimed}
        track_by_id = {track.track_id: track for track in active_tracks}
        for asset in active_companion_assets:
            owner_track = track_by_id.get(asset.owner_track_id)
            if (
                owner_track is None
                or owner_track.current_path not in selected_relocation_sources
                or (asset.current_path, asset.kind) in claimed_keys
            ):
                continue
            owner_candidate = candidate_by_track_id.get(owner_track.track_id)
            target_path = _managed_companion_target(asset, owner_candidate)
            snapshot, observation_reason = self._capture_companion_snapshot(
                self.ports.path_resolver.resolve_library_path(
                    library.root_path,
                    asset.current_path,
                ),
                library.root_path,
            )
            reason = observation_reason
            if reason is None and target_path is None:
                reason = PlanActionReason.COMPANION_OWNER_BLOCKED
            if reason is None and target_path == asset.current_path:
                continue
            claimed.append(
                _RefreshCompanionCandidate(
                    kind=asset.kind,
                    source_path=asset.current_path,
                    target_path=target_path,
                    owner_audio_source_path=owner_track.current_path,
                    dependency_audio_source_paths=(owner_track.current_path,),
                    snapshot=snapshot,
                    reason=reason,
                    companion_asset_id=asset.companion_asset_id,
                    owner_track_id=owner_track.track_id,
                )
            )

        return tuple(sorted(claimed, key=lambda candidate: (candidate.source_path, candidate.kind)))

    def _claimed_refresh_companions(  # noqa: PLR0913  # Policy output needs exact path, owner, and asset mappings.
        self,
        library: Library,
        active_tracks: Sequence[Track],
        active_companion_assets: Sequence[CompanionAsset],
        inventory_entries: Sequence[SourceInventoryEntry],
        association_result: CompanionAssociationResult,
        selected_relocation_sources: set[str],
    ) -> tuple[_RefreshCompanionCandidate, ...]:
        inventory_by_relative_path = {entry.relative_path: entry for entry in inventory_entries}
        association_by_source = {
            association.source_path: association for association in association_result.associations
        }
        issue_by_source = {issue.source_path: issue for issue in association_result.issues}
        track_by_source: dict[str, Track] = {}
        for track in active_tracks:
            _ = track_by_source.setdefault(track.current_path, track)
        claimed: list[_RefreshCompanionCandidate] = []
        for source_path in sorted(association_result.claimed_source_paths):
            association = association_by_source.get(source_path)
            issue = issue_by_source.get(source_path)
            dependency_sources = companion_dependency_sources(association, issue)
            if selected_relocation_sources.isdisjoint(dependency_sources):
                continue
            kind = companion_kind(association, issue)
            owner_source = None if association is None else association.owner_audio_source_path
            owner_track = None if owner_source is None else track_by_source.get(owner_source)
            existing_asset = _existing_companion_asset(
                active_companion_assets,
                source_path,
                kind,
            )
            source_filesystem_path = (
                inventory_by_relative_path[source_path].path
                if source_path in inventory_by_relative_path
                else self.ports.path_resolver.resolve_library_path(library.root_path, source_path)
            )
            snapshot, observation_reason = self._capture_companion_snapshot(
                source_filesystem_path,
                library.root_path,
            )
            target_path = None if association is None else association.target_path
            reason = observation_reason or companion_issue_reason(issue)
            if reason is None and target_path == source_path:
                continue
            claimed.append(
                _RefreshCompanionCandidate(
                    kind=kind,
                    source_path=source_path,
                    target_path=target_path,
                    owner_audio_source_path=owner_source,
                    dependency_audio_source_paths=dependency_sources,
                    snapshot=snapshot,
                    reason=reason,
                    companion_asset_id=(None if existing_asset is None else existing_asset.companion_asset_id),
                    owner_track_id=None if owner_track is None else owner_track.track_id,
                )
            )
        return tuple(claimed)

    def _capture_companion_snapshot(
        self,
        source_path: FileSystemPath,
        library_root: str,
    ) -> tuple[FileContentSnapshot | None, PlanActionReason | None]:
        try:
            return self.ports.file_content_snapshot_reader.capture(source_path, root=library_root), None
        except FileNotFoundError:
            return None, PlanActionReason.SOURCE_MISSING
        except FileObservationChangedError, OSError:
            return None, PlanActionReason.SOURCE_CHANGED
        except FileObservationInvalidPathError, ValueError:
            return None, PlanActionReason.INVALID_PATH

    def _with_target_conflicts(
        self,
        library: Library,
        candidates: Sequence[_RefreshCandidate],
        active_tracks: Sequence[Track],
        active_companion_assets: Sequence[CompanionAsset],
        companion_candidates: Sequence[_RefreshCompanionCandidate],
    ) -> tuple[tuple[_RefreshCandidate, ...], tuple[_RefreshCompanionCandidate, ...]]:
        occupied_paths = OccupiedPaths.from_paths(
            (
                *(track.current_path for track in active_tracks),
                *(asset.current_path for asset in active_companion_assets),
            )
        )
        target_counts = _batch_target_counts(candidates, companion_candidates)
        judged_candidates: list[_RefreshCandidate] = []

        for candidate in candidates:
            if self._has_target_conflict(
                library,
                source_path=candidate.track.current_path,
                target_path=candidate.target_path,
                occupied_paths=occupied_paths,
                target_counts=target_counts,
                eligible=(
                    candidate.needs_action
                    and candidate.reason is None
                    and candidate.target_path != candidate.track.current_path
                ),
            ):
                judged_candidates.append(replace(candidate, reason=PlanActionReason.TARGET_EXISTS))
            else:
                judged_candidates.append(candidate)

        judged_companions = tuple(
            replace(companion, reason=PlanActionReason.TARGET_EXISTS)
            if self._has_target_conflict(
                library,
                source_path=companion.source_path,
                target_path=companion.target_path,
                occupied_paths=occupied_paths,
                target_counts=target_counts,
                eligible=companion.reason is None,
            )
            else companion
            for companion in companion_candidates
        )
        return tuple(judged_candidates), judged_companions

    def _has_target_conflict(  # noqa: PLR0913  # Stored source and target are checked against both collision sources.
        self,
        library: Library,
        *,
        source_path: str,
        target_path: str | None,
        occupied_paths: OccupiedPaths,
        target_counts: dict[str, int],
        eligible: bool,
    ) -> bool:
        if not eligible or target_path is None or target_path == source_path:
            return False

        decision = CollisionPolicy().decide(
            target_path,
            occupied_paths,
            batch_target_count=target_counts[target_path],
        )
        if decision.kind is CollisionDecisionKind.BLOCKED:
            return True

        target_filesystem_path = self.ports.path_resolver.resolve_library_path(library.root_path, target_path)
        return self.ports.file_presence.exists(target_filesystem_path)

    def _actions(
        self,
        plan_id: PlanId,
        library: Library,
        candidates: Sequence[_RefreshCandidate],
        companion_candidates: Sequence[_RefreshCompanionCandidate],
    ) -> tuple[tuple[PlanAction, ...], tuple[PlanActionDependency, ...]]:
        actions: list[PlanAction] = []
        sort_order = PLAN_ACTION_SORT_ORDER_START

        for candidate in candidates:
            if not candidate.needs_action:
                continue

            snapshot = candidate.snapshot
            action_type = _action_type(candidate)
            actions.append(
                PlanAction(
                    action_id=self.ports.id_generator.new_action_id(),
                    plan_id=plan_id,
                    library_id=library.library_id,
                    track_id=candidate.track.track_id,
                    action_type=action_type,
                    source_path=candidate.track.current_path,
                    target_path=candidate.target_path,
                    content_hash_at_plan=None if snapshot is None else snapshot.content_hash,
                    metadata_hash_at_plan=None if snapshot is None else snapshot.metadata_hash,
                    status=ActionStatus.PLANNED if candidate.reason is None else ActionStatus.BLOCKED,
                    reason=candidate.reason,
                    sort_order=sort_order,
                    artist_name_diagnostics=candidate.artist_name_diagnostics,
                )
            )
            sort_order += PLAN_ACTION_SORT_ORDER_STEP

        audio_action_by_source = {action.source_path: action for action in actions if action.source_path is not None}
        dependencies: list[PlanActionDependency] = []
        for companion in companion_candidates:
            action_id = self.ports.id_generator.new_action_id()
            owner_action = (
                None
                if companion.owner_audio_source_path is None
                else audio_action_by_source.get(companion.owner_audio_source_path)
            )
            actions.append(
                PlanAction(
                    action_id=action_id,
                    plan_id=plan_id,
                    library_id=library.library_id,
                    track_id=companion.owner_track_id,
                    action_type=companion_action_type(companion.kind),
                    source_path=companion.source_path,
                    target_path=companion.target_path,
                    content_hash_at_plan=(None if companion.snapshot is None else companion.snapshot.content_hash),
                    metadata_hash_at_plan=None,
                    status=(ActionStatus.PLANNED if companion.reason is None else ActionStatus.BLOCKED),
                    reason=companion.reason,
                    sort_order=sort_order,
                    companion_asset_id=(
                        companion.companion_asset_id
                        if companion.companion_asset_id is not None
                        else self.ports.id_generator.new_companion_asset_id()
                    ),
                    owner_action_id=None if owner_action is None else owner_action.action_id,
                )
            )
            dependencies.extend(
                PlanActionDependency(
                    plan_id=plan_id,
                    action_id=action_id,
                    depends_on_action_id=dependency_action.action_id,
                )
                for source_path in companion.dependency_audio_source_paths
                if (dependency_action := audio_action_by_source.get(source_path)) is not None
            )
            sort_order += PLAN_ACTION_SORT_ORDER_STEP

        return tuple(actions), tuple(dependencies)


class RefreshLibrarySelectionError(ValueError):
    """Raised when refresh cannot select a registered Library."""


class RefreshTargetSelectionError(ValueError):
    """Raised when refresh cannot select managed active Tracks."""


class RefreshLibraryReconciliationRequiredError(RefreshLibrarySelectionError):
    """Raised when a partial refresh would leave related Tracks unreconciled."""


@dataclass(frozen=True, slots=True)
class _RefreshCandidate:
    """One managed Track and its plan-time refresh judgment."""

    track: Track
    snapshot: FileSnapshot | None
    target_path: str | None
    reason: PlanActionReason | None
    needs_action: bool
    artist_name_resolutions: tuple[ArtistNameResolution, ...] = ()
    artist_name_diagnostics: ArtistNameDiagnostics | None = None


@dataclass(frozen=True, slots=True)
class _RefreshCompanionCandidate:
    """One managed or discovered companion associated with selected relocation."""

    kind: CompanionAssetKind
    source_path: str
    target_path: str | None
    owner_audio_source_path: str | None
    dependency_audio_source_paths: tuple[str, ...]
    snapshot: FileContentSnapshot | None
    reason: PlanActionReason | None
    companion_asset_id: CompanionAssetId | None
    owner_track_id: TrackId | None


def _artist_name_reconciliation_required(
    *,
    active_tracks: Sequence[Track],
    candidates: Sequence[_RefreshCandidate],
    config: AppConfig,
    path_policy: PathPolicy,
) -> bool:
    executable_candidates = tuple(candidate for candidate in candidates if _is_executable_candidate(candidate))
    executable_track_ids = {candidate.track.track_id for candidate in executable_candidates}
    unreconciled_tracks = tuple(track for track in active_tracks if track.track_id not in executable_track_ids)
    planned_resolutions = tuple(
        resolution for candidate in executable_candidates for resolution in candidate.artist_name_resolutions
    )
    executable_metadata = tuple(
        candidate.snapshot.metadata for candidate in executable_candidates if candidate.snapshot is not None
    )
    return artist_name_reconciliation_required(
        unreconciled_tracks=unreconciled_tracks,
        planned_resolutions=planned_resolutions,
        effective_metadata_batch=executable_metadata + tuple(track.metadata for track in unreconciled_tracks),
        config=config,
        path_policy=path_policy,
    )


def _candidate_metadata(candidates: Sequence[_RefreshCandidate]) -> tuple[TrackMetadata, ...]:
    return tuple(
        candidate.snapshot.metadata
        for candidate in candidates
        if candidate.snapshot is not None and candidate.reason is None
    )


def _effective_metadata_batch(
    candidates: Sequence[_RefreshCandidate],
    active_tracks: Sequence[Track],
) -> tuple[TrackMetadata, ...]:
    selected_track_ids = {candidate.track.track_id for candidate in candidates}
    return _candidate_metadata(candidates) + tuple(
        track.metadata for track in active_tracks if track.track_id not in selected_track_ids
    )


def _is_executable_candidate(candidate: _RefreshCandidate) -> bool:
    return candidate.needs_action and candidate.reason is None and candidate.target_path is not None


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
    if is_path_policy_stale(library.path_policy_hash, path_policy_hash):
        raise RefreshLibrarySelectionError(_STALE_LIBRARY_MESSAGE)
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


def _action_type(candidate: _RefreshCandidate) -> ActionType:
    if candidate.reason is None and candidate.target_path == candidate.track.current_path:
        return ActionType.REFRESH_METADATA
    return ActionType.MOVE


def _is_relocation_candidate(candidate: _RefreshCandidate) -> bool:
    return candidate.needs_action and (
        candidate.reason is not None or candidate.target_path != candidate.track.current_path
    )


def _batch_target_counts(
    candidates: Sequence[_RefreshCandidate],
    companion_candidates: Sequence[_RefreshCompanionCandidate],
) -> dict[str, int]:
    target_counts: dict[str, int] = {}
    for candidate in candidates:
        if not _is_relocation_candidate(candidate) or candidate.reason is not None or candidate.target_path is None:
            continue
        target_counts[candidate.target_path] = target_counts.get(candidate.target_path, 0) + 1
    for candidate in companion_candidates:
        if candidate.reason is not None or candidate.target_path is None:
            continue
        target_counts[candidate.target_path] = target_counts.get(candidate.target_path, 0) + 1
    return target_counts


def _with_companion_owner_blocks(
    candidates: Sequence[_RefreshCandidate],
    companion_candidates: Sequence[_RefreshCompanionCandidate],
) -> tuple[_RefreshCompanionCandidate, ...]:
    selected_by_source = {candidate.track.current_path: candidate for candidate in candidates}
    judged: list[_RefreshCompanionCandidate] = []
    for companion in companion_candidates:
        dependency_candidates = tuple(
            selected_by_source[source_path]
            for source_path in companion.dependency_audio_source_paths
            if source_path in selected_by_source
        )
        dependency_blocked = any(candidate.reason is not None for candidate in dependency_candidates)
        if companion.reason in {None, PlanActionReason.TARGET_EXISTS} and (
            companion.target_path is None
            or companion.owner_track_id is None
            or len(dependency_candidates) == 0
            or dependency_blocked
        ):
            judged.append(replace(companion, reason=PlanActionReason.COMPANION_OWNER_BLOCKED))
        else:
            judged.append(companion)
    return tuple(judged)


def _managed_companion_target(
    asset: CompanionAsset,
    owner_candidate: _RefreshCandidate | None,
) -> str | None:
    if owner_candidate is None or owner_candidate.target_path is None:
        return None
    owner_target = PurePosixPath(owner_candidate.target_path)
    if asset.kind is CompanionAssetKind.LYRICS:
        return str(owner_target.with_suffix(".lrc"))
    return str(owner_target.parent / PurePosixPath(asset.current_path).name)


def _existing_companion_asset(
    assets: Sequence[CompanionAsset],
    source_path: str,
    kind: CompanionAssetKind,
) -> CompanionAsset | None:
    return next(
        (asset for asset in assets if asset.current_path == source_path and asset.kind is kind),
        None,
    )


def _plan(
    plan_id: PlanId,
    library: Library,
    actions: Sequence[PlanAction],
    config_hash: str,
    timestamp: datetime,
) -> Plan:
    move_count = sum(
        action.action_type in {ActionType.MOVE, ActionType.MOVE_LYRICS, ActionType.MOVE_ARTWORK}
        and action.status == ActionStatus.PLANNED
        for action in actions
    )
    metadata_count = sum(
        action.action_type == ActionType.REFRESH_METADATA and action.status == ActionStatus.PLANNED
        for action in actions
    )
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
            SUMMARY_METADATA_ACTIONS_KEY: str(metadata_count),
            SUMMARY_BLOCKED_ACTIONS_KEY: str(blocked_count),
        },
        actions=tuple(actions),
    )
