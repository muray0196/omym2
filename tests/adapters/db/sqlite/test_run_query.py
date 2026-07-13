"""
Summary: Tests SQLiteRunRepository/SQLiteFileEventRepository keyset paging, filters, and facets.
Why: Protects the history browsing SQL contract (DESC run keyset math, ASC event keyset math, filter pushdown).
"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from typing import TYPE_CHECKING
from uuid import UUID

from omym2.adapters.config.application_paths import default_application_paths
from omym2.adapters.db.sqlite.unit_of_work import SQLiteUnitOfWork
from omym2.domain.models.file_event import FileEvent, FileEventStatus, FileEventType
from omym2.domain.models.library import Library, LibraryStatus
from omym2.domain.models.plan import Plan, PlanStatus, PlanType
from omym2.domain.models.plan_action import ActionStatus, ActionType, PlanAction
from omym2.domain.models.run import Run, RunStatus
from omym2.shared.ids import ActionId, EventId, LibraryId, PlanId, RunId
from omym2.shared.pagination import PageRequest

if TYPE_CHECKING:
    from pathlib import Path

ACTION_ID = ActionId(UUID("018f6a4f-3c2d-7b8a-9abc-def0123456e1"))
BASE_TIME = datetime(2026, 1, 1, tzinfo=UTC)
CONFIG_HASH = "config-hash"
LIBRARY_ID = LibraryId(UUID("018f6a4f-3c2d-7b8a-9abc-def0123456c0"))
SECOND_LIBRARY_ID = LibraryId(UUID("018f6a4f-3c2d-7b8a-9abc-def0123456c1"))
LIBRARY_ROOT = "/music/library"
PLAN_ID = PlanId(UUID("018f6a4f-3c2d-7b8a-9abc-def0123456d0"))
SECOND_PLAN_ID = PlanId(UUID("018f6a4f-3c2d-7b8a-9abc-def0123456d1"))
THIRD_PLAN_ID = PlanId(UUID("018f6a4f-3c2d-7b8a-9abc-def0123456d2"))
FOURTH_PLAN_ID = PlanId(UUID("018f6a4f-3c2d-7b8a-9abc-def0123456d3"))
FIFTH_PLAN_ID = PlanId(UUID("018f6a4f-3c2d-7b8a-9abc-def0123456d4"))

RUN_ID_1 = RunId(UUID("018f6a4f-3c2d-7b8a-9abc-def0123456f1"))
RUN_ID_2 = RunId(UUID("018f6a4f-3c2d-7b8a-9abc-def0123456f2"))
RUN_ID_3 = RunId(UUID("018f6a4f-3c2d-7b8a-9abc-def0123456f3"))
RUN_ID_4 = RunId(UUID("018f6a4f-3c2d-7b8a-9abc-def0123456f4"))
RUN_ID_5 = RunId(UUID("018f6a4f-3c2d-7b8a-9abc-def0123456f5"))

EVENT_ID_1 = EventId(UUID("018f6a4f-3c2d-7b8a-9abc-def0123456a1"))
EVENT_ID_2 = EventId(UUID("018f6a4f-3c2d-7b8a-9abc-def0123456a2"))
EVENT_ID_3 = EventId(UUID("018f6a4f-3c2d-7b8a-9abc-def0123456a3"))

TWO_ITEM_LIMIT = 2
FIVE_RUN_TOTAL = 5
THREE_EVENT_TOTAL = 3


def test_run_query_page_walks_every_run_newest_first_with_desc_keyset_cursor(tmp_path: Path) -> None:
    """A limit=2 keyset walk over 5 Runs visits every Run once in (started_at DESC, run_id DESC) order."""
    database_file = default_application_paths(tmp_path).database_file
    run_ids = (RUN_ID_1, RUN_ID_2, RUN_ID_3, RUN_ID_4, RUN_ID_5)
    plan_ids = (PLAN_ID, SECOND_PLAN_ID, THIRD_PLAN_ID, FOURTH_PLAN_ID, FIFTH_PLAN_ID)
    with SQLiteUnitOfWork(database_file) as uow:
        uow.libraries.save(_library(LIBRARY_ID))
        for plan_id in plan_ids:
            uow.plans.save(_plan(plan_id=plan_id))
        for index, (run_id, plan_id) in enumerate(zip(run_ids, plan_ids, strict=True)):
            uow.runs.save(_run(run_id, started_at=BASE_TIME + timedelta(days=index), plan_id=plan_id))
        uow.commit()

    visited: list[RunId] = []
    cursor: tuple[str, ...] | None = None
    with SQLiteUnitOfWork(database_file) as uow:
        for _ in range(len(run_ids)):
            page = uow.runs.query_page(
                None,
                plan_id=None,
                status=None,
                page=PageRequest(limit=TWO_ITEM_LIMIT, cursor_key=cursor),
            )
            visited.extend(run.run_id for run in page.items)
            assert page.total == FIVE_RUN_TOTAL
            if page.next_cursor_key is None:
                break
            cursor = page.next_cursor_key

    assert visited == list(reversed(run_ids))
    assert len(visited) == len(set(visited))


def test_run_query_page_breaks_started_at_ties_by_run_id_desc(tmp_path: Path) -> None:
    """Runs sharing one started_at are ordered and keyset-walked by run_id DESC."""
    database_file = default_application_paths(tmp_path).database_file
    run_ids = (RUN_ID_1, RUN_ID_2, RUN_ID_3)
    plan_ids = (PLAN_ID, SECOND_PLAN_ID, THIRD_PLAN_ID)
    with SQLiteUnitOfWork(database_file) as uow:
        uow.libraries.save(_library(LIBRARY_ID))
        for plan_id in plan_ids:
            uow.plans.save(_plan(plan_id=plan_id))
        for run_id, plan_id in zip(run_ids, plan_ids, strict=True):
            uow.runs.save(_run(run_id, started_at=BASE_TIME, plan_id=plan_id))
        uow.commit()

    visited: list[RunId] = []
    cursor: tuple[str, ...] | None = None
    with SQLiteUnitOfWork(database_file) as uow:
        for _ in range(len(run_ids)):
            page = uow.runs.query_page(
                None,
                plan_id=None,
                status=None,
                page=PageRequest(limit=1, cursor_key=cursor),
            )
            visited.extend(run.run_id for run in page.items)
            if page.next_cursor_key is None:
                break
            cursor = page.next_cursor_key

    assert visited == [RUN_ID_3, RUN_ID_2, RUN_ID_1]


def test_run_query_page_pushes_status_and_library_filters_into_sql(tmp_path: Path) -> None:
    """Status/library filters narrow both the rows and the total, before the limit applies."""
    database_file = default_application_paths(tmp_path).database_file
    with SQLiteUnitOfWork(database_file) as uow:
        uow.libraries.save(_library(LIBRARY_ID))
        uow.libraries.save(_library(SECOND_LIBRARY_ID))
        uow.plans.save(_plan())
        uow.plans.save(_plan(plan_id=SECOND_PLAN_ID))
        uow.plans.save(_plan(plan_id=THIRD_PLAN_ID, library_id=SECOND_LIBRARY_ID))
        uow.runs.save(_run(RUN_ID_1, started_at=BASE_TIME, status=RunStatus.SUCCEEDED))
        uow.runs.save(
            _run(
                RUN_ID_2,
                started_at=BASE_TIME + timedelta(days=1),
                status=RunStatus.FAILED,
                plan_id=SECOND_PLAN_ID,
            )
        )
        uow.runs.save(
            _run(
                RUN_ID_3,
                started_at=BASE_TIME + timedelta(days=2),
                status=RunStatus.SUCCEEDED,
                library_id=SECOND_LIBRARY_ID,
                plan_id=THIRD_PLAN_ID,
            )
        )
        uow.commit()

    with SQLiteUnitOfWork(database_file) as uow:
        page = uow.runs.query_page(LIBRARY_ID, plan_id=None, status=RunStatus.SUCCEEDED, page=PageRequest())

    assert tuple(run.run_id for run in page.items) == (RUN_ID_1,)
    assert page.total == 1


def test_run_query_page_filters_by_plan_id(tmp_path: Path) -> None:
    """plan_id narrows Run browsing to one Plan without scanning pages client-side."""
    database_file = default_application_paths(tmp_path).database_file
    with SQLiteUnitOfWork(database_file) as uow:
        uow.libraries.save(_library(LIBRARY_ID))
        uow.plans.save(_plan())
        uow.plans.save(_plan(plan_id=SECOND_PLAN_ID))
        uow.runs.save(_run(RUN_ID_1, started_at=BASE_TIME))
        uow.runs.save(_run(RUN_ID_2, started_at=BASE_TIME + timedelta(days=1), plan_id=SECOND_PLAN_ID))
        uow.commit()

    with SQLiteUnitOfWork(database_file) as uow:
        page = uow.runs.query_page(None, plan_id=PLAN_ID, status=None, page=PageRequest())

    assert tuple(run.run_id for run in page.items) == (RUN_ID_1,)
    assert page.total == 1


def test_run_status_facets_order_count_desc_then_value_asc(tmp_path: Path) -> None:
    """status_facets is ordered count DESC, then value ASC."""
    database_file = default_application_paths(tmp_path).database_file
    with SQLiteUnitOfWork(database_file) as uow:
        uow.libraries.save(_library(LIBRARY_ID))
        uow.plans.save(_plan())
        uow.plans.save(_plan(plan_id=SECOND_PLAN_ID))
        uow.plans.save(_plan(plan_id=THIRD_PLAN_ID))
        uow.runs.save(_run(RUN_ID_1, started_at=BASE_TIME, status=RunStatus.SUCCEEDED))
        uow.runs.save(
            _run(
                RUN_ID_2,
                started_at=BASE_TIME + timedelta(days=1),
                status=RunStatus.SUCCEEDED,
                plan_id=SECOND_PLAN_ID,
            )
        )
        uow.runs.save(
            _run(
                RUN_ID_3,
                started_at=BASE_TIME + timedelta(days=2),
                status=RunStatus.FAILED,
                plan_id=THIRD_PLAN_ID,
            )
        )
        uow.commit()

    with SQLiteUnitOfWork(database_file) as uow:
        status_facets = uow.runs.status_facets(LIBRARY_ID)

    assert [(facet.value, facet.count) for facet in status_facets] == [
        (RunStatus.SUCCEEDED.value, 2),
        (RunStatus.FAILED.value, 1),
    ]


def test_file_event_query_page_walks_events_in_sequence_order_with_keyset_cursor(tmp_path: Path) -> None:
    """A limit=2 keyset walk over 3 events visits every event once in (sequence_no, event_id) order."""
    database_file = default_application_paths(tmp_path).database_file
    with SQLiteUnitOfWork(database_file) as uow:
        uow.libraries.save(_library(LIBRARY_ID))
        uow.plans.save(_plan())
        uow.plan_actions.save(_action())
        uow.runs.save(_run(RUN_ID_1, started_at=BASE_TIME))
        uow.file_events.save(_event(EVENT_ID_2, sequence_no=2))
        uow.file_events.save(_event(EVENT_ID_1, sequence_no=1))
        uow.file_events.save(_event(EVENT_ID_3, sequence_no=3))
        uow.commit()

    visited: list[EventId] = []
    cursor: tuple[str, ...] | None = None
    with SQLiteUnitOfWork(database_file) as uow:
        for _ in range(THREE_EVENT_TOTAL):
            page = uow.file_events.query_page(
                RUN_ID_1,
                status=None,
                page=PageRequest(limit=TWO_ITEM_LIMIT, cursor_key=cursor),
            )
            visited.extend(event.event_id for event in page.items)
            assert page.total == THREE_EVENT_TOTAL
            if page.next_cursor_key is None:
                break
            cursor = page.next_cursor_key

    assert visited == [EVENT_ID_1, EVENT_ID_2, EVENT_ID_3]


def test_file_event_query_page_filters_by_status_in_sql(tmp_path: Path) -> None:
    """The optional status filter narrows both the rows and the total."""
    database_file = default_application_paths(tmp_path).database_file
    with SQLiteUnitOfWork(database_file) as uow:
        uow.libraries.save(_library(LIBRARY_ID))
        uow.plans.save(_plan())
        uow.plan_actions.save(_action())
        uow.runs.save(_run(RUN_ID_1, started_at=BASE_TIME))
        uow.file_events.save(_event(EVENT_ID_1, sequence_no=1, status=FileEventStatus.SUCCEEDED))
        uow.file_events.save(_event(EVENT_ID_2, sequence_no=2, status=FileEventStatus.FAILED))
        uow.commit()

    with SQLiteUnitOfWork(database_file) as uow:
        page = uow.file_events.query_page(RUN_ID_1, status=FileEventStatus.FAILED, page=PageRequest())

    assert tuple(event.event_id for event in page.items) == (EVENT_ID_2,)
    assert page.total == 1


def test_file_event_status_facets_order_count_desc_then_value_asc(tmp_path: Path) -> None:
    """status_facets returns the FileEvent status breakdown for one Run."""
    database_file = default_application_paths(tmp_path).database_file
    with SQLiteUnitOfWork(database_file) as uow:
        uow.libraries.save(_library(LIBRARY_ID))
        uow.plans.save(_plan())
        uow.plan_actions.save(_action())
        uow.runs.save(_run(RUN_ID_1, started_at=BASE_TIME))
        uow.file_events.save(_event(EVENT_ID_1, sequence_no=1, status=FileEventStatus.SUCCEEDED))
        uow.file_events.save(_event(EVENT_ID_2, sequence_no=2, status=FileEventStatus.SUCCEEDED))
        uow.file_events.save(_event(EVENT_ID_3, sequence_no=3, status=FileEventStatus.FAILED))
        uow.commit()

    with SQLiteUnitOfWork(database_file) as uow:
        status_facets = uow.file_events.status_facets(RUN_ID_1)

    assert [(facet.value, facet.count) for facet in status_facets] == [
        (FileEventStatus.SUCCEEDED.value, 2),
        (FileEventStatus.FAILED.value, 1),
    ]


def test_file_event_list_target_paths_returns_recorded_paths_in_sequence_order(tmp_path: Path) -> None:
    """list_target_paths exposes recorded FileEvent target paths without deriving directories in SQL."""
    database_file = default_application_paths(tmp_path).database_file
    with SQLiteUnitOfWork(database_file) as uow:
        uow.libraries.save(_library(LIBRARY_ID))
        uow.plans.save(_plan())
        uow.plan_actions.save(_action())
        uow.runs.save(_run(RUN_ID_1, started_at=BASE_TIME))
        uow.file_events.save(_event(EVENT_ID_2, sequence_no=2, target_path="Artist/Album/2.flac"))
        uow.file_events.save(_event(EVENT_ID_1, sequence_no=1, target_path="Artist/Album/1.flac"))
        uow.commit()

    with SQLiteUnitOfWork(database_file) as uow:
        target_paths = uow.file_events.list_target_paths(RUN_ID_1)

    assert target_paths == ("Artist/Album/1.flac", "Artist/Album/2.flac")


def _library(library_id: LibraryId) -> Library:
    return Library(
        library_id=library_id,
        root_path=f"/music/{library_id}",
        path_policy_hash="config",
        registered_at=BASE_TIME,
        status=LibraryStatus.REGISTERED,
        created_at=BASE_TIME,
        updated_at=BASE_TIME,
    )


def _plan(*, plan_id: PlanId = PLAN_ID, library_id: LibraryId = LIBRARY_ID) -> Plan:
    return Plan(
        plan_id=plan_id,
        library_id=library_id,
        plan_type=PlanType.ADD,
        status=PlanStatus.APPLIED,
        created_at=BASE_TIME,
        config_hash=CONFIG_HASH,
        library_root_at_plan=LIBRARY_ROOT,
    )


def _action() -> PlanAction:
    return PlanAction(
        action_id=ACTION_ID,
        plan_id=PLAN_ID,
        library_id=LIBRARY_ID,
        track_id=None,
        action_type=ActionType.MOVE,
        source_path="Source/Track.flac",
        target_path="Target/Track.flac",
        content_hash_at_plan=None,
        metadata_hash_at_plan=None,
        status=ActionStatus.APPLIED,
        reason=None,
        sort_order=1,
    )


def _run(
    run_id: RunId,
    *,
    started_at: datetime,
    status: RunStatus = RunStatus.SUCCEEDED,
    library_id: LibraryId = LIBRARY_ID,
    plan_id: PlanId = PLAN_ID,
) -> Run:
    return Run(
        run_id=run_id,
        plan_id=plan_id,
        library_id=library_id,
        status=status,
        started_at=started_at,
        completed_at=started_at,
    )


def _event(
    event_id: EventId,
    *,
    sequence_no: int,
    status: FileEventStatus = FileEventStatus.SUCCEEDED,
    target_path: str = "Target/Track.flac",
) -> FileEvent:
    return FileEvent(
        event_id=event_id,
        library_id=LIBRARY_ID,
        run_id=RUN_ID_1,
        plan_action_id=ACTION_ID,
        event_type=FileEventType.MOVE_FILE,
        source_path="Source/Track.flac",
        target_path=target_path,
        status=status,
        started_at=BASE_TIME,
        completed_at=BASE_TIME,
        error_code=None,
        error_message=None,
        sequence_no=sequence_no,
    )
