"""
Summary: Tests core domain model invariants.
Why: Protects identity, path storage, and execution status semantics.
"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta

import pytest

from omym2.domain.models.file_event import FileEvent, FileEventStatus, FileEventType
from omym2.domain.models.library import Library, LibraryStatus
from omym2.domain.models.plan import Plan, PlanStatus, PlanType
from omym2.domain.models.plan_action import ActionStatus, ActionType, PlanAction, PlanActionReason
from omym2.domain.models.run import Run, RunStatus
from omym2.domain.models.track import Track, TrackStatus
from omym2.domain.models.track_metadata import TrackMetadata
from omym2.shared.ids import (
    new_action_id,
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
        _track(current_path=f"/{NORMALIZED_PATH}", canonical_path=NORMALIZED_PATH)


def test_track_id_is_not_derived_from_path_hash_or_metadata() -> None:
    """Updating track path state preserves the original Track ID."""
    track = _track(current_path=NORMALIZED_PATH, canonical_path=NORMALIZED_PATH)

    updated_track = track.with_paths(UPDATED_PATH, UPDATED_PATH, FINISHED_TIME)

    assert updated_track.track_id == track.track_id
    assert updated_track.current_path == UPDATED_PATH


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


def _track(current_path: str, canonical_path: str) -> Track:
    return Track(
        track_id=new_track_id(),
        library_id=new_library_id(),
        current_path=current_path,
        canonical_path=canonical_path,
        content_hash=CONTENT_HASH,
        metadata_hash=METADATA_HASH,
        metadata=TrackMetadata(title="Title", artist="Artist"),
        status=TrackStatus.ACTIVE,
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
