"""
Summary: Implements add Plan creation for registered Libraries.
Why: Lets users review incoming imports before any Library file mutation.
"""

from __future__ import annotations

import os
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
from omym2.domain.models.companion_asset import CompanionAssetKind, CompanionAssetStatus
from omym2.domain.models.library import Library, LibraryStatus
from omym2.domain.models.operation import Operation, OperationKind, OperationStatus, PlanCreatedResult
from omym2.domain.models.plan import Plan, PlanStatus, PlanType
from omym2.domain.models.plan_action import (
    ActionStatus,
    ActionType,
    PlanAction,
    PlanActionDependency,
    PlanActionReason,
)
from omym2.domain.models.track import TrackStatus
from omym2.domain.services.album_disc import infer_album_disc_totals
from omym2.domain.services.album_year import metadata_with_resolved_album_year, resolve_album_years
from omym2.domain.services.artist_name import (
    artist_name_diagnostics,
    artist_name_projections,
    artist_name_sources,
)
from omym2.domain.services.artist_name_reconciliation import artist_name_reconciliation_required
from omym2.domain.services.collision_policy import CollisionDecisionKind, CollisionPolicy, OccupiedPaths
from omym2.domain.services.companion_association import (
    CompanionAssociation,
    CompanionAssociationResult,
    CompanionAudioCandidate,
    CompanionIssue,
    CompanionIssueCode,
    associate_companions,
)
from omym2.domain.services.companion_recovery import (
    CompanionRecoveryEvidence,
    RecoverableCompanion,
    find_recoverable_companions,
)
from omym2.domain.services.config_fingerprint import (
    STALE_LIBRARY_MESSAGE as _STALE_LIBRARY_MESSAGE,
)
from omym2.domain.services.config_fingerprint import (
    calculate_config_fingerprint,
    calculate_path_policy_fingerprint,
    is_path_policy_stale,
)
from omym2.domain.services.path_policy import MISSING_TITLE_MESSAGE, PathPolicy
from omym2.features.common_ports import (
    FileObservationChangedError,
    FileObservationInvalidPathError,
    FileSnapshotCaptureRequest,
    SourceInventoryRequest,
)

if TYPE_CHECKING:
    from collections.abc import Sequence
    from datetime import datetime

    from omym2.domain.models.app_config import AppConfig
    from omym2.domain.models.artist_name_resolution import ArtistNameDiagnostics, ArtistNameResolution
    from omym2.domain.models.companion_asset import CompanionAsset
    from omym2.domain.models.file_scan_entry import FileScanEntry
    from omym2.domain.models.file_snapshot import FileContentSnapshot, FileSnapshot
    from omym2.domain.models.track import Track
    from omym2.features.add.dto import CreateAddPlanRequest
    from omym2.features.add.ports import CreateAddPlanPorts
    from omym2.features.common_ports import FileSystemPath, SourceInventoryEntry, UnitOfWork
    from omym2.shared.ids import CompanionAssetId, LibraryId, OperationId, PlanId, TrackId

AMBIGUOUS_REGISTERED_LIBRARY_MESSAGE = (
    "Multiple registered Libraries exist. Library selection is not supported for add yet."
)
ARTIST_NAME_RECONCILIATION_REQUIRED_MESSAGE = (
    "Artist naming for existing Library tracks changed. Run organize before add."
)
NO_INCOMING_SOURCE_MESSAGE = "No Incoming path is configured. Use add SOURCE_DIR."
NO_REGISTERED_LIBRARY_MESSAGE = "No registered Library can be selected. Run organize --library PATH."
SELECTED_LIBRARY_NOT_FOUND_MESSAGE = "The selected Library was not found."
SELECTED_LIBRARY_NOT_REGISTERED_MESSAGE = "The selected Library is not registered."
SOURCE_INSIDE_LIBRARY_MESSAGE = "The add source cannot be inside the Library."
SUMMARY_ACTION_COUNT_KEY = "action_count"
SUMMARY_BLOCKED_ACTIONS_KEY = "blocked_actions"
SUMMARY_MOVE_ACTIONS_KEY = "move_actions"
SUMMARY_SKIP_ACTIONS_KEY = "skip_actions"
SUMMARY_UNPROCESSED_ACTIONS_KEY = "unprocessed_actions"
SUMMARY_UNPROCESSED_PREVIEW_LIMIT_KEY = "unprocessed_preview_limit"
RUNNING_OPERATION_REQUIRED_MESSAGE = "Add completion requires its corresponding running Operation."
CLAIMED_COMPANION_DECISION_MISSING_MESSAGE = "Claimed companion must have an association or issue."


@dataclass(frozen=True, slots=True)
class CreateAddPlanUseCase:
    """Create reviewed add Plans without moving Library music files."""

    ports: CreateAddPlanPorts

    def execute(self, request: CreateAddPlanRequest) -> Plan:
        """Create an add Plan from Incoming or an explicit source."""
        config = self.ports.config_store.load()
        source_root = _source_root(request, config)
        config_hash = calculate_config_fingerprint(config)
        path_policy_hash = calculate_path_policy_fingerprint(
            config.path_policy,
            config.artist_ids,
            config.metadata.album_year_resolution,
            config.artist_names,
        )
        path_policy = PathPolicy.from_app_config(config)
        timestamp = self.ports.clock.now()

        with self.ports.uow as uow:
            _ = _running_operation(uow, request.operation_id)
            library = _select_registered_library(uow, path_policy_hash, request.library_id)
            library_tracks = tuple(uow.tracks.list_by_library(library.library_id))
            companion_assets = tuple(uow.companion_assets.list_by_library(library.library_id))
            recoverable_companions = _load_recoverable_companions(
                uow,
                library.library_id,
                library_tracks,
                companion_assets,
            )

        _require_source_outside_library(source_root, library.root_path)
        inventory_excluded_roots = _inventory_excluded_roots(
            source_root,
            library.root_path,
            config.unprocessed.directory,
            self.ports.internal_excluded_paths,
        )
        active_library_tracks = tuple(track for track in library_tracks if track.status == TrackStatus.ACTIVE)
        duplicate_track_by_hash = _duplicate_track_by_hash(active_library_tracks)
        scan_entries = tuple(
            entry
            for entry in self.ports.file_scanner.scan(
                source_root,
                excluded_roots=inventory_excluded_roots,
            )
            if _is_retained_source_path(
                source_root,
                entry.path,
                inventory_excluded_roots,
                self.ports.rotating_log_files,
            )
        )
        source_paths = tuple(_normalize_external_source_path(entry.path) for entry in scan_entries)
        snapshots = self.ports.file_snapshot_reader.capture_many(
            tuple(FileSnapshotCaptureRequest(entry.path) for entry in scan_entries)
        )
        candidates = tuple(
            self._candidate(entry, source_path, snapshot, config)
            for entry, source_path, snapshot in zip(scan_entries, source_paths, snapshots, strict=True)
        )
        candidates = self._with_target_paths(candidates, library_tracks, config, path_policy)
        candidates = self._with_duplicates(candidates, duplicate_track_by_hash)
        inventory_enabled = config.companions.enabled or config.unprocessed.enabled
        inventory_entries = (
            _retained_inventory_entries(
                source_root,
                self.ports.source_inventory_reader.scan(
                    SourceInventoryRequest(root=source_root, excluded_roots=inventory_excluded_roots)
                ),
                inventory_excluded_roots,
                self.ports.rotating_log_files,
            )
            if inventory_enabled
            else ()
        )
        association_result = (
            associate_companions(
                tuple(
                    CompanionAudioCandidate(
                        source_path=_source_relative_path(source_root, candidate.source_path),
                        target_path=candidate.target_path,
                    )
                    for candidate in candidates
                ),
                tuple(entry.relative_path for entry in inventory_entries),
            )
            if inventory_enabled
            else CompanionAssociationResult(claimed_source_paths=frozenset(), associations=(), issues=())
        )
        companion_candidates = (
            self._companion_candidates(source_root, inventory_entries, association_result)
            if config.companions.enabled
            else ()
        )
        if config.companions.enabled:
            companion_candidates = _merge_add_companion_candidates(
                companion_candidates,
                self._recovery_companion_candidates(
                    source_root,
                    inventory_entries,
                    recoverable_companions,
                ),
            )
        companion_candidates = _with_companion_owner_blocks(source_root, candidates, companion_candidates)
        candidates, companion_candidates = self._with_target_conflicts(
            library,
            candidates,
            active_library_tracks,
            companion_assets,
            companion_candidates,
        )
        companion_candidates = _with_companion_owner_blocks(source_root, candidates, companion_candidates)
        if _artist_name_reconciliation_required(
            active_library_tracks=active_library_tracks,
            candidates=candidates,
            config=config,
            path_policy=path_policy,
        ):
            raise AddLibraryReconciliationRequiredError(ARTIST_NAME_RECONCILIATION_REQUIRED_MESSAGE)
        unprocessed_candidates = (
            self._unprocessed_candidates(
                inventory_entries,
                _AddUnprocessedPlanningContext(
                    source_root=source_root,
                    directory=config.unprocessed.directory,
                    claimed_paths=_claimed_source_paths(
                        source_root,
                        source_paths,
                        association_result.claimed_source_paths,
                        companion_candidates,
                    ),
                    protected_paths=(library.root_path, *self.ports.internal_excluded_paths),
                    rotating_log_files=self.ports.rotating_log_files,
                ),
            )
            if config.unprocessed.enabled
            else ()
        )
        plan_id = self.ports.id_generator.new_plan_id()
        actions, dependencies = self._actions(
            plan_id,
            library,
            _AddActionCandidates(
                source_root=source_root,
                audio=candidates,
                companions=companion_candidates,
                unprocessed=unprocessed_candidates,
            ),
        )
        plan = _plan(
            plan_id,
            library,
            source_root,
            actions,
            config.unprocessed.result_preview_limit,
            config_hash,
            timestamp,
        )

        with self.ports.uow as uow:
            operation = _running_operation(uow, request.operation_id)
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

    def _with_target_conflicts(
        self,
        library: Library,
        candidates: Sequence[_AddCandidate],
        tracks: Sequence[Track],
        companion_assets: Sequence[CompanionAsset],
        companion_candidates: Sequence[_AddCompanionCandidate],
    ) -> tuple[tuple[_AddCandidate, ...], tuple[_AddCompanionCandidate, ...]]:
        occupied_paths = OccupiedPaths.from_paths(
            (
                *(track.current_path for track in tracks),
                *(asset.current_path for asset in companion_assets if asset.status is CompanionAssetStatus.ACTIVE),
            )
        )
        target_counts = _batch_target_counts(candidates, companion_candidates)
        judged_candidates: list[_AddCandidate] = []

        for candidate in candidates:
            if self._has_target_conflict(
                library,
                candidate.target_path,
                occupied_paths,
                target_counts,
                eligible=candidate.action_type is ActionType.MOVE and candidate.reason is None,
            ):
                judged_candidates.append(replace(candidate, reason=PlanActionReason.TARGET_EXISTS))
            else:
                judged_candidates.append(candidate)

        judged_companions = tuple(
            replace(companion, reason=PlanActionReason.TARGET_EXISTS)
            if self._has_target_conflict(
                library,
                companion.target_path,
                occupied_paths,
                target_counts,
                eligible=companion.reason is None,
            )
            else companion
            for companion in companion_candidates
        )

        return tuple(judged_candidates), judged_companions

    def _has_target_conflict(
        self,
        library: Library,
        target_path: str | None,
        occupied_paths: OccupiedPaths,
        target_counts: dict[str, int],
        *,
        eligible: bool,
    ) -> bool:
        if not eligible or target_path is None:
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

    def _with_target_paths(
        self,
        candidates: Sequence[_AddCandidate],
        library_tracks: Sequence[Track],
        config: AppConfig,
        path_policy: PathPolicy,
    ) -> tuple[_AddCandidate, ...]:
        active_library_metadata = tuple(
            track.metadata for track in library_tracks if track.status == TrackStatus.ACTIVE
        )
        candidate_metadata = tuple(
            candidate.snapshot.metadata
            for candidate in candidates
            if candidate.snapshot is not None and candidate.reason is None
        )
        metadata_batch = active_library_metadata + candidate_metadata
        resolutions = self.ports.artist_name_resolver.resolve_many(
            artist_name_sources(candidate_metadata),
            preferences=config.artist_names.preferences,
        )
        projections = iter(
            artist_name_projections(candidate_metadata, tuple(resolution.resolved_name for resolution in resolutions))
        )
        diagnostics = iter(artist_name_diagnostics(candidate_metadata, resolutions))
        resolution_pairs = iter(tuple(zip(resolutions[::2], resolutions[1::2], strict=True)))
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
        judged_candidates: list[_AddCandidate] = []

        for candidate in candidates:
            snapshot = candidate.snapshot
            if snapshot is None or candidate.reason is not None:
                judged_candidates.append(candidate)
                continue

            artist_names = next(projections)
            artist_diagnostics = next(diagnostics)
            artist_name_resolutions = next(resolution_pairs)
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
                        reason=_path_generation_failure_reason(exc),
                        target_path=None,
                        artist_name_diagnostics=artist_diagnostics,
                        artist_name_resolutions=artist_name_resolutions,
                    )
                )
                continue

            judged_candidates.append(
                replace(
                    candidate,
                    target_path=target_path,
                    artist_name_diagnostics=artist_diagnostics,
                    artist_name_resolutions=artist_name_resolutions,
                )
            )

        return tuple(judged_candidates)

    def _with_duplicates(
        self,
        candidates: Sequence[_AddCandidate],
        duplicate_track_by_hash: dict[str, Track],
    ) -> tuple[_AddCandidate, ...]:
        judged_candidates: list[_AddCandidate] = []
        for candidate in candidates:
            snapshot = candidate.snapshot
            if snapshot is None or candidate.reason is not None:
                judged_candidates.append(candidate)
                continue

            duplicate_track = duplicate_track_by_hash.get(snapshot.content_hash)
            if duplicate_track is None:
                judged_candidates.append(candidate)
                continue

            judged_candidates.append(
                replace(
                    candidate,
                    action_type=ActionType.SKIP,
                    reason=PlanActionReason.DUPLICATE_HASH,
                    track_id=duplicate_track.track_id,
                )
            )

        return tuple(judged_candidates)

    def _candidate(
        self,
        entry: FileScanEntry,
        source_path: str,
        snapshot: FileSnapshot | None,
        config: AppConfig,
    ) -> _AddCandidate:
        if snapshot is None:
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

    def _companion_candidates(
        self,
        source_root: str,
        inventory_entries: Sequence[SourceInventoryEntry],
        association_result: CompanionAssociationResult,
    ) -> tuple[_AddCompanionCandidate, ...]:
        inventory_by_relative_path = {entry.relative_path: entry for entry in inventory_entries}
        association_by_source = {
            association.source_path: association for association in association_result.associations
        }
        issue_by_source = {issue.source_path: issue for issue in association_result.issues}
        companion_candidates: list[_AddCompanionCandidate] = []

        for relative_source_path in sorted(association_result.claimed_source_paths):
            entry = inventory_by_relative_path[relative_source_path]
            association = association_by_source.get(relative_source_path)
            issue = issue_by_source.get(relative_source_path)
            snapshot, observation_reason = self._capture_content_snapshot(entry, source_root)
            companion_candidates.append(
                _AddCompanionCandidate(
                    kind=_companion_kind(association, issue),
                    source_relative_path=relative_source_path,
                    source_path=entry.path,
                    target_path=None if association is None else association.target_path,
                    owner_audio_source_path=(None if association is None else association.owner_audio_source_path),
                    dependency_audio_source_paths=_companion_dependency_sources(association, issue),
                    snapshot=snapshot,
                    reason=observation_reason or _companion_issue_reason(issue),
                )
            )

        return tuple(companion_candidates)

    def _capture_content_snapshot(
        self,
        entry: SourceInventoryEntry,
        source_root: str,
    ) -> tuple[FileContentSnapshot | None, PlanActionReason | None]:
        try:
            return self.ports.file_content_snapshot_reader.capture(entry.path, root=source_root), None
        except FileNotFoundError:
            return None, PlanActionReason.SOURCE_MISSING
        except FileObservationChangedError, OSError:
            return None, PlanActionReason.SOURCE_CHANGED
        except FileObservationInvalidPathError, ValueError:
            return None, PlanActionReason.INVALID_PATH

    def _unprocessed_candidates(
        self,
        inventory_entries: Sequence[SourceInventoryEntry],
        context: _AddUnprocessedPlanningContext,
    ) -> tuple[_AddUnprocessedCandidate, ...]:
        candidates: list[_AddUnprocessedCandidate] = []
        for entry in inventory_entries:
            source_path = _normalize_external_source_path(entry.path)
            if source_path in context.claimed_paths:
                continue
            relative_source_path = _source_relative_path(context.source_root, source_path)
            target_path = _normalize_external_source_path(
                Path(context.source_root, context.directory, *Path(relative_source_path).parts)
            )
            snapshot, reason = self._capture_content_snapshot(entry, context.source_root)
            if reason is None:
                if _is_protected_unprocessed_target(target_path, context):
                    reason = PlanActionReason.INVALID_PATH
                elif self.ports.file_presence.exists(target_path):
                    reason = PlanActionReason.TARGET_EXISTS
            candidates.append(
                _AddUnprocessedCandidate(
                    source_path=source_path,
                    target_path=target_path,
                    snapshot=snapshot,
                    reason=reason,
                )
            )
        return tuple(candidates)

    def _recovery_companion_candidates(
        self,
        source_root: str,
        inventory_entries: Sequence[SourceInventoryEntry],
        recoverable_companions: Sequence[RecoverableCompanion],
    ) -> tuple[_AddCompanionCandidate, ...]:
        inventory_by_path = {_normalize_external_source_path(entry.path): entry for entry in inventory_entries}
        candidates: list[_AddCompanionCandidate] = []
        for recovery in recoverable_companions:
            if recovery.source_plan_type is not PlanType.ADD or recovery.source_root != source_root:
                continue
            entry = inventory_by_path.get(recovery.source_path)
            if entry is None:
                continue
            snapshot, reason = self._capture_content_snapshot(entry, source_root)
            if reason is not None or snapshot is None or snapshot.content_hash != recovery.content_hash:
                continue
            candidates.append(
                _AddCompanionCandidate(
                    kind=recovery.kind,
                    source_relative_path=entry.relative_path,
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
        return tuple(candidates)

    def _actions(
        self,
        plan_id: PlanId,
        library: Library,
        candidates: _AddActionCandidates,
    ) -> tuple[tuple[PlanAction, ...], tuple[PlanActionDependency, ...]]:
        actions: list[PlanAction] = []
        sort_order = PLAN_ACTION_SORT_ORDER_START

        for candidate in candidates.audio:
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
                    artist_name_diagnostics=candidate.artist_name_diagnostics,
                )
            )
            sort_order += PLAN_ACTION_SORT_ORDER_STEP

        audio_action_by_source = {
            _source_relative_path(candidates.source_root, action.source_path): action
            for action in actions
            if action.source_path is not None
        }
        dependencies: list[PlanActionDependency] = []
        for companion in candidates.companions:
            action_id = self.ports.id_generator.new_action_id()
            owner_action = (
                None
                if companion.owner_audio_source_path is None
                else audio_action_by_source[companion.owner_audio_source_path]
            )
            action = PlanAction(
                action_id=action_id,
                plan_id=plan_id,
                library_id=library.library_id,
                track_id=companion.owner_track_id,
                action_type=_companion_action_type(companion.kind),
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
            actions.append(action)
            dependencies.extend(
                PlanActionDependency(
                    plan_id=plan_id,
                    action_id=action_id,
                    depends_on_action_id=audio_action_by_source[source_path].action_id,
                )
                for source_path in companion.dependency_audio_source_paths
            )
            sort_order += PLAN_ACTION_SORT_ORDER_STEP

        for candidate in candidates.unprocessed:
            actions.append(
                PlanAction(
                    action_id=self.ports.id_generator.new_action_id(),
                    plan_id=plan_id,
                    library_id=library.library_id,
                    track_id=None,
                    action_type=ActionType.MOVE_UNPROCESSED,
                    source_path=candidate.source_path,
                    target_path=candidate.target_path,
                    content_hash_at_plan=(None if candidate.snapshot is None else candidate.snapshot.content_hash),
                    metadata_hash_at_plan=None,
                    status=(ActionStatus.PLANNED if candidate.reason is None else ActionStatus.BLOCKED),
                    reason=candidate.reason,
                    sort_order=sort_order,
                )
            )
            sort_order += PLAN_ACTION_SORT_ORDER_STEP

        return tuple(actions), tuple(dependencies)


class AddLibrarySelectionError(ValueError):
    """Raised when add cannot select exactly one current registered Library."""


class AddLibraryReconciliationRequiredError(AddLibrarySelectionError):
    """Raised when changed artist naming must be reconciled before import."""


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
    artist_name_resolutions: tuple[ArtistNameResolution, ...] = ()
    artist_name_diagnostics: ArtistNameDiagnostics | None = None


@dataclass(frozen=True, slots=True)
class _AddCompanionCandidate:
    """One claimed incoming companion and its reviewed planning evidence."""

    kind: CompanionAssetKind
    source_relative_path: str
    source_path: str
    target_path: str | None
    owner_audio_source_path: str | None
    dependency_audio_source_paths: tuple[str, ...]
    snapshot: FileContentSnapshot | None
    reason: PlanActionReason | None
    companion_asset_id: CompanionAssetId | None = None
    owner_track_id: TrackId | None = None


@dataclass(frozen=True, slots=True)
class _AddUnprocessedCandidate:
    """One unclaimed source file and its content-only planning judgment."""

    source_path: str
    target_path: str
    snapshot: FileContentSnapshot | None
    reason: PlanActionReason | None


@dataclass(frozen=True, slots=True)
class _AddUnprocessedPlanningContext:
    """Path identities needed to classify and protect unprocessed targets."""

    source_root: str
    directory: str
    claimed_paths: frozenset[str]
    protected_paths: tuple[FileSystemPath, ...]
    rotating_log_files: tuple[FileSystemPath, ...]


@dataclass(frozen=True, slots=True)
class _AddActionCandidates:
    """Candidate groups retained in their durable Plan action order."""

    source_root: str
    audio: tuple[_AddCandidate, ...]
    companions: tuple[_AddCompanionCandidate, ...]
    unprocessed: tuple[_AddUnprocessedCandidate, ...]


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


def _merge_add_companion_candidates(
    claimed: Sequence[_AddCompanionCandidate],
    recoveries: Sequence[_AddCompanionCandidate],
) -> tuple[_AddCompanionCandidate, ...]:
    claimed_paths = {candidate.source_relative_path for candidate in claimed}
    return (*claimed, *(candidate for candidate in recoveries if candidate.source_relative_path not in claimed_paths))


def _source_root(request: CreateAddPlanRequest, config: AppConfig) -> str:
    if request.source_path is not None:
        return _normalize_external_source_path(request.source_path)
    if config.paths.incoming is not None:
        return _normalize_external_source_path(config.paths.incoming)
    raise AddSourceSelectionError(NO_INCOMING_SOURCE_MESSAGE)


def _running_operation(uow: UnitOfWork, operation_id: OperationId | None) -> Operation | None:
    if operation_id is None:
        return None
    retained = uow.operations.lookup(operation_id)
    if (
        not isinstance(retained, Operation)
        or retained.kind is not OperationKind.ADD_PLAN
        or retained.status is not OperationStatus.RUNNING
    ):
        raise RuntimeError(RUNNING_OPERATION_REQUIRED_MESSAGE)
    return retained


def _normalize_external_source_path(raw_path: FileSystemPath) -> str:
    expanded_path = Path(raw_path).expanduser()
    # Path.resolve() would follow the selected root before no-follow inventory.
    return os.path.abspath(os.fspath(expanded_path))  # noqa: PTH100


def _require_source_outside_library(source_root: str, library_root: str) -> None:
    """Reject a source rooted at or below the managed Library."""
    if _is_same_or_descendant(source_root, library_root):
        raise AddSourceSelectionError(SOURCE_INSIDE_LIBRARY_MESSAGE)


def _inventory_excluded_roots(
    source_root: str,
    library_root: str,
    unprocessed_directory: str,
    internal_excluded_paths: Sequence[FileSystemPath],
) -> tuple[str, ...]:
    """Build stable lexical exclusions without broadening them to the application root."""
    paths = (
        _normalize_external_source_path(library_root),
        _normalize_external_source_path(Path(source_root, unprocessed_directory)),
        *(_normalize_external_source_path(path) for path in internal_excluded_paths),
    )
    return tuple(dict.fromkeys(paths))


def _retained_inventory_entries(
    source_root: str,
    inventory_entries: Sequence[SourceInventoryEntry],
    excluded_roots: Sequence[FileSystemPath],
    rotating_log_files: Sequence[FileSystemPath],
) -> tuple[SourceInventoryEntry, ...]:
    """Defensively retain only exact, anchored entries outside every excluded path."""
    retained: list[SourceInventoryEntry] = []
    for entry in inventory_entries:
        if not _is_retained_source_path(source_root, entry.path, excluded_roots, rotating_log_files):
            continue
        source_path = _normalize_external_source_path(entry.path)
        if entry.relative_path != _source_relative_path(source_root, source_path):
            continue
        retained.append(entry)
    return tuple(sorted(retained, key=lambda entry: (entry.relative_path, entry.path)))


def _claimed_source_paths(
    source_root: str,
    audio_source_paths: Sequence[str],
    companion_source_paths: frozenset[str],
    companion_candidates: Sequence[_AddCompanionCandidate],
) -> frozenset[str]:
    """Normalize every scanner and companion claim onto one absolute identity."""
    return frozenset(
        (
            *audio_source_paths,
            *(
                _normalize_external_source_path(Path(source_root, *Path(relative_path).parts))
                for relative_path in companion_source_paths
            ),
            *(candidate.source_path for candidate in companion_candidates),
        )
    )


def _is_retained_source_path(
    source_root: str,
    source_path: FileSystemPath,
    excluded_roots: Sequence[FileSystemPath],
    rotating_log_files: Sequence[FileSystemPath],
) -> bool:
    normalized_source = _normalize_external_source_path(source_path)
    if normalized_source == source_root or not _is_same_or_descendant(normalized_source, source_root):
        return False
    if any(_is_same_or_descendant(normalized_source, excluded) for excluded in excluded_roots):
        return False
    return not any(_is_rotated_log_file(normalized_source, base) for base in rotating_log_files)


def _is_same_or_descendant(path: FileSystemPath, root: FileSystemPath) -> bool:
    normalized_path = Path(_normalize_external_source_path(path))
    normalized_root = Path(_normalize_external_source_path(root))
    try:
        _ = normalized_path.relative_to(normalized_root)
    except ValueError:
        return False
    return True


def _is_rotated_log_file(path: FileSystemPath, log_file: FileSystemPath) -> bool:
    candidate = Path(_normalize_external_source_path(path))
    log_base = Path(_normalize_external_source_path(log_file))
    if candidate.parent != log_base.parent:
        return False
    prefix = f"{log_base.name}."
    suffix = candidate.name.removeprefix(prefix)
    return candidate.name.startswith(prefix) and suffix.isascii() and suffix.isdigit()


def _is_protected_unprocessed_target(
    target_path: FileSystemPath,
    context: _AddUnprocessedPlanningContext,
) -> bool:
    if any(_is_same_or_descendant(target_path, protected) for protected in context.protected_paths):
        return True
    return any(_is_rotated_log_file(target_path, log_file) for log_file in context.rotating_log_files)


def _source_relative_path(source_root: str, source_path: str) -> str:
    return Path(source_path).relative_to(Path(source_root)).as_posix()


def _select_registered_library(
    uow: UnitOfWork,
    path_policy_hash: str,
    library_id: LibraryId | None,
) -> Library:
    if library_id is not None:
        selected_library = uow.libraries.get(library_id)
        if selected_library is None:
            raise AddLibrarySelectionError(SELECTED_LIBRARY_NOT_FOUND_MESSAGE)
        if selected_library.status != LibraryStatus.REGISTERED:
            raise AddLibrarySelectionError(SELECTED_LIBRARY_NOT_REGISTERED_MESSAGE)
        if is_path_policy_stale(selected_library.path_policy_hash, path_policy_hash):
            raise AddLibrarySelectionError(_STALE_LIBRARY_MESSAGE)
        return selected_library

    registered_libraries = tuple(
        library for library in uow.libraries.list_all() if library.status == LibraryStatus.REGISTERED
    )
    if len(registered_libraries) == 0:
        raise AddLibrarySelectionError(NO_REGISTERED_LIBRARY_MESSAGE)
    if len(registered_libraries) > 1:
        raise AddLibrarySelectionError(AMBIGUOUS_REGISTERED_LIBRARY_MESSAGE)

    library = registered_libraries[0]
    if is_path_policy_stale(library.path_policy_hash, path_policy_hash):
        raise AddLibrarySelectionError(_STALE_LIBRARY_MESSAGE)
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


def _artist_name_reconciliation_required(
    *,
    active_library_tracks: Sequence[Track],
    candidates: Sequence[_AddCandidate],
    config: AppConfig,
    path_policy: PathPolicy,
) -> bool:
    planned_resolutions = tuple(
        resolution
        for candidate in candidates
        if _is_executable_move(candidate)
        for resolution in candidate.artist_name_resolutions
    )
    candidate_metadata = tuple(
        candidate.snapshot.metadata
        for candidate in candidates
        if candidate.snapshot is not None and _is_executable_move(candidate)
    )
    metadata_batch = tuple(track.metadata for track in active_library_tracks) + candidate_metadata
    return artist_name_reconciliation_required(
        unreconciled_tracks=active_library_tracks,
        planned_resolutions=planned_resolutions,
        effective_metadata_batch=metadata_batch,
        config=config,
        path_policy=path_policy,
    )


def _is_executable_move(candidate: _AddCandidate) -> bool:
    return candidate.action_type is ActionType.MOVE and candidate.reason is None


def _batch_target_counts(
    candidates: Sequence[_AddCandidate],
    companion_candidates: Sequence[_AddCompanionCandidate],
) -> dict[str, int]:
    target_counts: dict[str, int] = {}
    for candidate in candidates:
        if candidate.action_type != ActionType.MOVE or candidate.reason is not None or candidate.target_path is None:
            continue
        target_counts[candidate.target_path] = target_counts.get(candidate.target_path, 0) + 1
    for candidate in companion_candidates:
        if candidate.reason is not None or candidate.target_path is None:
            continue
        target_counts[candidate.target_path] = target_counts.get(candidate.target_path, 0) + 1
    return target_counts


def _with_companion_owner_blocks(
    source_root: str,
    candidates: Sequence[_AddCandidate],
    companion_candidates: Sequence[_AddCompanionCandidate],
) -> tuple[_AddCompanionCandidate, ...]:
    audio_by_source = {_source_relative_path(source_root, candidate.source_path): candidate for candidate in candidates}
    judged: list[_AddCompanionCandidate] = []
    for companion in companion_candidates:
        dependency_candidates = tuple(
            audio_by_source.get(source_path) for source_path in companion.dependency_audio_source_paths
        )
        owner_missing = (
            companion.owner_audio_source_path is not None and companion.owner_audio_source_path not in audio_by_source
        )
        dependency_blocked = any(
            candidate is None or not _is_executable_move(candidate) for candidate in dependency_candidates
        )
        if companion.reason in {None, PlanActionReason.TARGET_EXISTS} and (
            companion.target_path is None or owner_missing or dependency_blocked
        ):
            judged.append(replace(companion, reason=PlanActionReason.COMPANION_OWNER_BLOCKED))
        else:
            judged.append(companion)
    return tuple(judged)


def _companion_kind(
    association: CompanionAssociation | None,
    issue: CompanionIssue | None,
) -> CompanionAssetKind:
    if association is not None:
        return association.kind
    if issue is not None:
        return issue.kind
    raise AssertionError(CLAIMED_COMPANION_DECISION_MISSING_MESSAGE)


def _companion_dependency_sources(
    association: CompanionAssociation | None,
    issue: CompanionIssue | None,
) -> tuple[str, ...]:
    if association is not None:
        return association.dependency_audio_source_paths
    if issue is not None:
        return issue.dependency_audio_source_paths
    return ()


def _companion_issue_reason(issue: CompanionIssue | None) -> PlanActionReason | None:
    if issue is None:
        return None
    if issue.code in {
        CompanionIssueCode.OWNER_AMBIGUOUS,
        CompanionIssueCode.TARGET_PARENT_MISMATCH,
    }:
        return PlanActionReason.COMPANION_ASSOCIATION_AMBIGUOUS
    return PlanActionReason.COMPANION_OWNER_BLOCKED


def _companion_action_type(kind: CompanionAssetKind) -> ActionType:
    if kind is CompanionAssetKind.LYRICS:
        return ActionType.MOVE_LYRICS
    return ActionType.MOVE_ARTWORK


def _action_status(candidate: _AddCandidate) -> ActionStatus:
    if candidate.action_type == ActionType.SKIP or candidate.reason is None:
        return ActionStatus.PLANNED
    return ActionStatus.BLOCKED


def _plan(  # noqa: PLR0913  # Plan identity and both filesystem roots are distinct durable fields.
    plan_id: PlanId,
    library: Library,
    source_root: str,
    actions: Sequence[PlanAction],
    unprocessed_preview_limit: int,
    config_hash: str,
    timestamp: datetime,
) -> Plan:
    move_count = sum(
        action.action_type
        in {
            ActionType.MOVE,
            ActionType.MOVE_LYRICS,
            ActionType.MOVE_ARTWORK,
            ActionType.MOVE_UNPROCESSED,
        }
        and action.status == ActionStatus.PLANNED
        for action in actions
    )
    skip_count = sum(action.action_type == ActionType.SKIP for action in actions)
    blocked_count = sum(action.status == ActionStatus.BLOCKED for action in actions)
    unprocessed_count = sum(action.action_type is ActionType.MOVE_UNPROCESSED for action in actions)
    return Plan(
        plan_id=plan_id,
        library_id=library.library_id,
        plan_type=PlanType.ADD,
        status=PlanStatus.READY,
        created_at=timestamp,
        config_hash=config_hash,
        library_root_at_plan=library.root_path,
        source_root_at_plan=source_root,
        summary={
            SUMMARY_ACTION_COUNT_KEY: str(len(actions)),
            SUMMARY_MOVE_ACTIONS_KEY: str(move_count),
            SUMMARY_SKIP_ACTIONS_KEY: str(skip_count),
            SUMMARY_BLOCKED_ACTIONS_KEY: str(blocked_count),
            SUMMARY_UNPROCESSED_ACTIONS_KEY: str(unprocessed_count),
            SUMMARY_UNPROCESSED_PREVIEW_LIMIT_KEY: str(unprocessed_preview_limit),
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
