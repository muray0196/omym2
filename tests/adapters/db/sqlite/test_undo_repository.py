"""
Summary: Tests SQLite persistence and lookup for Undo provenance.
Why: Keeps source Run and reversed FileEvent identities exact across retries.
"""

from __future__ import annotations

from datetime import UTC, datetime
from typing import TYPE_CHECKING
from uuid import UUID

from omym2.adapters.db.sqlite.unit_of_work import SQLiteUnitOfWork
from omym2.domain.models.file_event import FileEvent, FileEventStatus, FileEventType
from omym2.domain.models.library import Library, LibraryStatus
from omym2.domain.models.plan import Plan, PlanStatus, PlanType
from omym2.domain.models.plan_action import ActionStatus, ActionType, PlanAction
from omym2.domain.models.run import Run, RunStatus
from omym2.shared.ids import ActionId, EventId, LibraryId, PlanId, RunId

if TYPE_CHECKING:
    from pathlib import Path

NOW = datetime(2026, 7, 13, tzinfo=UTC)
LIBRARY_ID = LibraryId(UUID("018f6a4f-3c2d-7b8a-9abc-def012345701"))
SOURCE_PLAN_ID = PlanId(UUID("018f6a4f-3c2d-7b8a-9abc-def012345702"))
SOURCE_ACTION_ID = ActionId(UUID("018f6a4f-3c2d-7b8a-9abc-def012345703"))
SOURCE_RUN_ID = RunId(UUID("018f6a4f-3c2d-7b8a-9abc-def012345704"))
SOURCE_EVENT_ID = EventId(UUID("018f6a4f-3c2d-7b8a-9abc-def012345705"))
UNDO_PLAN_ID = PlanId(UUID("018f6a4f-3c2d-7b8a-9abc-def012345706"))
UNDO_ACTION_ID = ActionId(UUID("018f6a4f-3c2d-7b8a-9abc-def012345707"))
LIBRARY_ROOT = "/music/library"
SOURCE_PATH = "Original/Track.flac"
TARGET_PATH = "Artist/Album/Track.flac"


def test_sqlite_round_trips_and_looks_up_exact_undo_provenance(tmp_path: Path) -> None:
    """Undo Plan and action provenance survive persistence and drive source lookup."""
    database_file = tmp_path / "state.sqlite3"
    source_plan = _plan(SOURCE_PLAN_ID, PlanType.ADD, PlanStatus.APPLIED)
    source_action = _action(SOURCE_ACTION_ID, SOURCE_PLAN_ID)
    source_run = Run(
        run_id=SOURCE_RUN_ID,
        plan_id=SOURCE_PLAN_ID,
        library_id=LIBRARY_ID,
        status=RunStatus.SUCCEEDED,
        started_at=NOW,
        completed_at=NOW,
    )
    source_event = FileEvent(
        event_id=SOURCE_EVENT_ID,
        library_id=LIBRARY_ID,
        run_id=SOURCE_RUN_ID,
        plan_action_id=SOURCE_ACTION_ID,
        event_type=FileEventType.MOVE_FILE,
        source_path=SOURCE_PATH,
        target_path=TARGET_PATH,
        status=FileEventStatus.SUCCEEDED,
        started_at=NOW,
        completed_at=NOW,
        error_code=None,
        error_message=None,
        sequence_no=1,
    )
    undo_plan = _plan(
        UNDO_PLAN_ID,
        PlanType.UNDO,
        PlanStatus.READY,
        source_run_id=SOURCE_RUN_ID,
    )
    undo_action = _action(
        UNDO_ACTION_ID,
        UNDO_PLAN_ID,
        source_path=TARGET_PATH,
        target_path=SOURCE_PATH,
        reverses_event_id=SOURCE_EVENT_ID,
    )

    with SQLiteUnitOfWork(database_file) as uow:
        uow.libraries.save(_library())
        uow.plans.save(source_plan)
        uow.plan_actions.save(source_action)
        uow.runs.save(source_run)
        uow.file_events.save(source_event)
        uow.plans.save(undo_plan)
        uow.plan_actions.save(undo_action)
        uow.commit()

    with SQLiteUnitOfWork(database_file) as uow:
        restored_plan = uow.plans.get(UNDO_PLAN_ID)
        restored_action = uow.plan_actions.get(UNDO_ACTION_ID)
        by_source = tuple(uow.plans.list_by_source_run(SOURCE_RUN_ID))

    assert restored_plan == undo_plan
    assert restored_action == undo_action
    assert by_source == (undo_plan,)


def _library() -> Library:
    return Library(
        library_id=LIBRARY_ID,
        root_path=LIBRARY_ROOT,
        path_policy_hash="path-policy",
        registered_at=NOW,
        status=LibraryStatus.REGISTERED,
        created_at=NOW,
        updated_at=NOW,
    )


def _plan(
    plan_id: PlanId,
    plan_type: PlanType,
    status: PlanStatus,
    *,
    source_run_id: RunId | None = None,
) -> Plan:
    return Plan(
        plan_id=plan_id,
        library_id=LIBRARY_ID,
        plan_type=plan_type,
        status=status,
        created_at=NOW,
        config_hash="config",
        library_root_at_plan=LIBRARY_ROOT,
        source_run_id=source_run_id,
        summary={"action_count": "1"},
    )


def _action(
    action_id: ActionId,
    plan_id: PlanId,
    *,
    source_path: str = SOURCE_PATH,
    target_path: str = TARGET_PATH,
    reverses_event_id: EventId | None = None,
) -> PlanAction:
    return PlanAction(
        action_id=action_id,
        plan_id=plan_id,
        library_id=LIBRARY_ID,
        track_id=None,
        action_type=ActionType.MOVE,
        source_path=source_path,
        target_path=target_path,
        content_hash_at_plan="content",
        metadata_hash_at_plan="metadata",
        status=ActionStatus.APPLIED if plan_id == SOURCE_PLAN_ID else ActionStatus.PLANNED,
        reason=None,
        sort_order=1,
        reverses_event_id=reverses_event_id,
    )
