"""
Summary: Tests core domain model invariants.
Why: Protects identity, path storage, and execution status semantics.
"""

from __future__ import annotations

from dataclasses import replace
from datetime import UTC, datetime, timedelta, timezone

import pytest

from omym2.domain.models.artist_name_resolution import (
    ArtistNameDiagnostics,
    ArtistNameResolutionDiagnostic,
    ArtistNameResolutionIssue,
    ArtistNameResolutionProvenance,
)
from omym2.domain.models.companion_asset import CompanionAsset, CompanionAssetKind, CompanionAssetStatus
from omym2.domain.models.file_event import FileEvent, FileEventStatus, FileEventType
from omym2.domain.models.library import Library, LibraryStatus
from omym2.domain.models.plan import Plan, PlanStatus, PlanType
from omym2.domain.models.plan_action import (
    ActionStatus,
    ActionType,
    PlanAction,
    PlanActionDependency,
    PlanActionReason,
)
from omym2.domain.models.run import Run, RunStatus
from omym2.domain.models.track import Track, TrackStatus
from omym2.domain.models.track_metadata import TrackMetadata
from omym2.shared.ids import (
    new_action_id,
    new_companion_asset_id,
    new_event_id,
    new_library_id,
    new_plan_id,
    new_run_id,
    new_track_id,
)
from omym2.shared.paths import ROOTED_LIBRARY_PATH_MESSAGE

BASE_TIME = datetime(2026, 1, 1, tzinfo=UTC)
FINISHED_TIME = BASE_TIME + timedelta(minutes=5)
CONFIG_HASH = "config-hash"
CONTENT_HASH = "content-hash"
COMPANION_PATH = "Artist/Album/01_Title.lrc"
ERROR_CODE = "move_failed"
ERROR_MESSAGE = "move failed"
LIBRARY_ROOT = "/music/library"
METADATA_HASH = "metadata-hash"
NORMALIZED_PATH = "Artist/Album/01_Title.flac"
RELATIVE_PATH_WITH_CURRENT_DIR = "./Artist//Album/01_Title.flac"
TARGET_PATH = "Artist/Album/02_Title.flac"
UPDATED_LIBRARY_ROOT = "/music/moved-library"
UPDATED_PATH = "Artist/Album/03_Title.flac"
SORT_ORDER = 1
SEQUENCE_NO = 1
TRACK_SIZE = 1024


def test_library_identity_is_not_derived_from_root_path() -> None:
    """Relinking a Library preserves the original Library ID."""
    library_id = new_library_id()
    library = Library(
        library_id=library_id,
        root_path=LIBRARY_ROOT,
        path_policy_hash=CONFIG_HASH,
        registered_at=BASE_TIME,
        status=LibraryStatus.REGISTERED,
        created_at=BASE_TIME,
        updated_at=BASE_TIME,
    )

    relinked_library = library.with_root_path(UPDATED_LIBRARY_ROOT, FINISHED_TIME)

    assert relinked_library.library_id == library_id
    assert relinked_library.root_path == UPDATED_LIBRARY_ROOT


def test_track_paths_are_stored_relative_to_library_root() -> None:
    """Track construction normalizes Library-managed path fields."""
    track = _track(current_path=RELATIVE_PATH_WITH_CURRENT_DIR, canonical_path=RELATIVE_PATH_WITH_CURRENT_DIR)

    assert track.current_path == NORMALIZED_PATH
    assert track.canonical_path == NORMALIZED_PATH


def test_track_rejects_absolute_library_managed_path() -> None:
    """Track paths must not be absolute filesystem paths."""
    with pytest.raises(ValueError, match=ROOTED_LIBRARY_PATH_MESSAGE):
        _ = _track(current_path=f"/{NORMALIZED_PATH}", canonical_path=NORMALIZED_PATH)


def test_track_id_is_not_derived_from_path_hash_or_metadata() -> None:
    """Updating track path state preserves the original Track ID."""
    track = _track(current_path=NORMALIZED_PATH, canonical_path=NORMALIZED_PATH)

    updated_track = track.with_paths(UPDATED_PATH, UPDATED_PATH, FINISHED_TIME)

    assert updated_track.track_id == track.track_id
    assert updated_track.current_path == UPDATED_PATH


def test_track_normalizes_and_preserves_stat_baseline() -> None:
    """Track keeps a verified stat baseline while normalizing its mtime to UTC."""
    observed_mtime = datetime(2026, 1, 1, 9, tzinfo=timezone(timedelta(hours=9)))
    track = _track(
        current_path=NORMALIZED_PATH,
        canonical_path=NORMALIZED_PATH,
        size=TRACK_SIZE,
        mtime=observed_mtime,
    )

    updated_track = track.with_paths(UPDATED_PATH, UPDATED_PATH, FINISHED_TIME)

    assert track.size == TRACK_SIZE
    assert track.mtime == BASE_TIME
    assert updated_track.size == TRACK_SIZE
    assert updated_track.mtime == BASE_TIME


def test_track_rejects_negative_stat_baseline_size() -> None:
    """A persisted Track stat baseline cannot contain a negative size."""
    with pytest.raises(ValueError, match="must not be negative"):
        _ = _track(
            current_path=NORMALIZED_PATH,
            canonical_path=NORMALIZED_PATH,
            size=-1,
            mtime=BASE_TIME,
        )


def test_companion_asset_normalizes_library_paths_without_changing_identity() -> None:
    """CompanionAsset identity remains stable while managed paths normalize."""
    companion_asset = _companion_asset(current_path="./Artist//Album/01_Title.lrc")

    relocated = replace(companion_asset, current_path="Artist/Album 2/01_Title.lrc")

    assert companion_asset.current_path == COMPANION_PATH
    assert companion_asset.canonical_path == COMPANION_PATH
    assert relocated.companion_asset_id == companion_asset.companion_asset_id


def test_companion_asset_rejects_absolute_managed_path_and_negative_size() -> None:
    """Companion assets enforce relative Library paths and valid stat baselines."""
    with pytest.raises(ValueError, match=ROOTED_LIBRARY_PATH_MESSAGE):
        _ = _companion_asset(current_path=f"/{COMPANION_PATH}")

    with pytest.raises(ValueError, match="must not be negative"):
        _ = _companion_asset(current_path=COMPANION_PATH, size=-1)


def test_companion_asset_normalizes_observation_timestamps_to_utc() -> None:
    """Companion asset stat and lifecycle timestamps use the shared UTC contract."""
    observed_time = datetime(2026, 1, 1, 9, tzinfo=timezone(timedelta(hours=9)))

    companion_asset = _companion_asset(current_path=COMPANION_PATH, mtime=observed_time)

    assert companion_asset.mtime == BASE_TIME
    assert companion_asset.first_seen_at == BASE_TIME


def test_plan_terminal_status_blocks_reapply_by_state() -> None:
    """Applied Plans are terminal according to the single-use policy."""
    plan = Plan(
        plan_id=new_plan_id(),
        library_id=new_library_id(),
        plan_type=PlanType.ADD,
        status=PlanStatus.READY,
        created_at=BASE_TIME,
        config_hash=CONFIG_HASH,
        library_root_at_plan=LIBRARY_ROOT,
    )

    applied_plan = plan.mark_applying().mark_applied()

    assert applied_plan.status == PlanStatus.APPLIED
    assert applied_plan.is_terminal


def test_plan_action_uses_blocked_for_plan_time_issue_and_failed_for_apply_time_issue() -> None:
    """Blocked and failed are separate status outcomes with explicit reasons."""
    action = _plan_action(ActionStatus.PLANNED, None)

    blocked_action = action.mark_blocked(PlanActionReason.TARGET_EXISTS)
    failed_action = action.mark_failed(PlanActionReason.SOURCE_CHANGED)

    assert blocked_action.status == ActionStatus.BLOCKED
    assert blocked_action.reason == PlanActionReason.TARGET_EXISTS
    assert failed_action.status == ActionStatus.FAILED
    assert failed_action.reason == PlanActionReason.SOURCE_CHANGED


@pytest.mark.parametrize(
    "reason",
    [
        PlanActionReason.COMPANION_OWNER_BLOCKED,
        PlanActionReason.COMPANION_ASSOCIATION_AMBIGUOUS,
    ],
)
def test_plan_action_preserves_companion_planning_block_reasons(reason: PlanActionReason) -> None:
    """Companion owner and association failures remain distinct review-time reasons."""
    blocked_action = _plan_action(ActionStatus.PLANNED, None).mark_blocked(reason)

    assert blocked_action.status is ActionStatus.BLOCKED
    assert blocked_action.reason is reason


def test_plan_action_stores_final_target_path_with_extension() -> None:
    """PlanAction records the reviewed final target path, including extension."""
    action = _plan_action(ActionStatus.PLANNED, None)

    assert action.target_path == TARGET_PATH
    assert action.target_path.endswith(".flac")


def test_plan_action_status_transitions_preserve_artist_name_diagnostics() -> None:
    """Apply-time status updates cannot erase the naming evidence reviewed with an action."""
    diagnostics = _artist_name_diagnostics()
    companion_asset_id = new_companion_asset_id()
    owner_action_id = new_action_id()
    action = PlanAction(
        action_id=new_action_id(),
        plan_id=new_plan_id(),
        library_id=new_library_id(),
        track_id=None,
        action_type=ActionType.MOVE,
        source_path=NORMALIZED_PATH,
        target_path=TARGET_PATH,
        content_hash_at_plan=CONTENT_HASH,
        metadata_hash_at_plan=METADATA_HASH,
        status=ActionStatus.PLANNED,
        reason=None,
        sort_order=SORT_ORDER,
        artist_name_diagnostics=diagnostics,
        companion_asset_id=companion_asset_id,
        owner_action_id=owner_action_id,
    )

    transitioned = (
        action.mark_applied(),
        action.mark_blocked(PlanActionReason.TARGET_EXISTS),
        action.mark_failed(PlanActionReason.SOURCE_CHANGED),
    )

    assert all(item.artist_name_diagnostics == diagnostics for item in transitioned)
    assert all(item.companion_asset_id == companion_asset_id for item in transitioned)
    assert all(item.owner_action_id == owner_action_id for item in transitioned)


def test_plan_action_dependency_rejects_self_dependency() -> None:
    """A recorded PlanAction dependency cannot name the same action on both sides."""
    action_id = new_action_id()

    with pytest.raises(ValueError, match="cannot depend on itself"):
        _ = PlanActionDependency(
            plan_id=new_plan_id(),
            action_id=action_id,
            depends_on_action_id=action_id,
        )


def test_run_completion_records_failed_state() -> None:
    """Run completion preserves the run ID and records failure details."""
    run = Run(
        run_id=new_run_id(),
        plan_id=new_plan_id(),
        library_id=new_library_id(),
        status=RunStatus.RUNNING,
        started_at=BASE_TIME,
    )

    failed_run = run.mark_failed(FINISHED_TIME, ERROR_MESSAGE)

    assert failed_run.run_id == run.run_id
    assert failed_run.status == RunStatus.FAILED
    assert failed_run.error_summary == ERROR_MESSAGE


def test_file_event_records_pending_before_result() -> None:
    """FileEvent result transitions preserve the original event identity."""
    event = FileEvent(
        event_id=new_event_id(),
        library_id=new_library_id(),
        run_id=new_run_id(),
        plan_action_id=new_action_id(),
        event_type=FileEventType.MOVE_FILE,
        source_path=NORMALIZED_PATH,
        target_path=TARGET_PATH,
        status=FileEventStatus.PENDING,
        started_at=BASE_TIME,
        completed_at=None,
        error_code=None,
        error_message=None,
        sequence_no=SEQUENCE_NO,
    )

    failed_event = event.mark_failed(FINISHED_TIME, ERROR_CODE, ERROR_MESSAGE)

    assert failed_event.event_id == event.event_id
    assert failed_event.status == FileEventStatus.FAILED
    assert failed_event.error_code == ERROR_CODE


def test_companion_file_event_result_preserves_asset_identity() -> None:
    """Companion event completion retains its explicit asset and mutation kind."""
    companion_asset_id = new_companion_asset_id()
    event = FileEvent(
        event_id=new_event_id(),
        library_id=new_library_id(),
        run_id=new_run_id(),
        plan_action_id=new_action_id(),
        event_type=FileEventType.MOVE_LYRICS_FILE,
        source_path=COMPANION_PATH,
        target_path="Artist/Album 2/01_Title.lrc",
        status=FileEventStatus.PENDING,
        started_at=BASE_TIME,
        completed_at=None,
        error_code=None,
        error_message=None,
        sequence_no=SEQUENCE_NO,
        companion_asset_id=companion_asset_id,
    )

    succeeded_event = event.mark_succeeded(FINISHED_TIME)

    assert succeeded_event.event_type is FileEventType.MOVE_LYRICS_FILE
    assert succeeded_event.companion_asset_id == companion_asset_id


def _track(
    current_path: str,
    canonical_path: str,
    *,
    size: int | None = None,
    mtime: datetime | None = None,
) -> Track:
    return Track(
        track_id=new_track_id(),
        library_id=new_library_id(),
        current_path=current_path,
        canonical_path=canonical_path,
        content_hash=CONTENT_HASH,
        metadata_hash=METADATA_HASH,
        size=size,
        mtime=mtime,
        metadata=TrackMetadata(title="Title", artist="Artist"),
        status=TrackStatus.ACTIVE,
        first_seen_at=BASE_TIME,
        last_seen_at=BASE_TIME,
        updated_at=BASE_TIME,
    )


def _companion_asset(
    *,
    current_path: str,
    size: int | None = TRACK_SIZE,
    mtime: datetime | None = BASE_TIME,
) -> CompanionAsset:
    return CompanionAsset(
        companion_asset_id=new_companion_asset_id(),
        library_id=new_library_id(),
        kind=CompanionAssetKind.LYRICS,
        owner_track_id=new_track_id(),
        current_path=current_path,
        canonical_path=COMPANION_PATH,
        content_hash=CONTENT_HASH,
        size=size,
        mtime=mtime,
        status=CompanionAssetStatus.ACTIVE,
        first_seen_at=BASE_TIME,
        last_seen_at=BASE_TIME,
        updated_at=BASE_TIME,
    )


def _plan_action(status: ActionStatus, reason: PlanActionReason | None) -> PlanAction:
    return PlanAction(
        action_id=new_action_id(),
        plan_id=new_plan_id(),
        library_id=new_library_id(),
        track_id=None,
        action_type=ActionType.MOVE,
        source_path=NORMALIZED_PATH,
        target_path=TARGET_PATH,
        content_hash_at_plan=CONTENT_HASH,
        metadata_hash_at_plan=METADATA_HASH,
        status=status,
        reason=reason,
        sort_order=SORT_ORDER,
    )


def _artist_name_diagnostics() -> ArtistNameDiagnostics:
    return ArtistNameDiagnostics(
        artist=ArtistNameResolutionDiagnostic(
            source_name="Artist",
            resolved_name="Preferred Artist",
            provenance=ArtistNameResolutionProvenance.ACCEPTED_MUSICBRAINZ,
        ),
        album_artist=ArtistNameResolutionDiagnostic(
            source_name=None,
            resolved_name=None,
            provenance=ArtistNameResolutionProvenance.ORIGINAL,
            issue=ArtistNameResolutionIssue.MISSING_SOURCE,
        ),
    )
