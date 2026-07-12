"""
Summary: Tests the history browsing usecases: paged Run listing, Run header, paged events, and facets.
Why: Protects the history query pipeline (filters pushed into the query, keyset paging, facet totals)
     before CLI and Web render it.
"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from uuid import UUID

import pytest

from omym2.domain.models.file_event import FileEvent, FileEventStatus, FileEventType
from omym2.domain.models.library import Library, LibraryStatus
from omym2.domain.models.plan import Plan, PlanStatus, PlanType
from omym2.domain.models.run import Run, RunStatus
from omym2.features.history.dto import (
    FileEventStatusFacetsRequest,
    GetRunHeaderRequest,
    GroupRunEventsRequest,
    ListRunEventsRequest,
    ListRunsRequest,
    RunStatusFacetsRequest,
)
from omym2.features.history.ports import HistoryPorts
from omym2.features.history.usecases.get_file_event_status_facets import GetFileEventStatusFacetsUseCase
from omym2.features.history.usecases.get_run_header import (
    RUN_NOT_FOUND_MESSAGE,
    GetRunHeaderUseCase,
    RunNotFoundError,
)
from omym2.features.history.usecases.get_run_status_facets import GetRunStatusFacetsUseCase
from omym2.features.history.usecases.group_run_events import GroupRunEventsUseCase
from omym2.features.history.usecases.list_run_events import ListRunEventsUseCase
from omym2.features.history.usecases.list_runs import ListRunsUseCase
from omym2.shared.ids import ActionId, EventId, LibraryId, PlanId, RunId
from omym2.shared.pagination import PageRequest
from tests.fakes.in_memory_repositories import InMemoryUnitOfWork

BASE_TIME = datetime(2026, 1, 1, tzinfo=UTC)
CONFIG_HASH = "config-hash"
LIBRARY_ID = LibraryId(UUID("018f6a4f-3c2d-7b8a-9abc-def012345690"))
LIBRARY_ROOT = "/music/library"
PLAN_ID = PlanId(UUID("018f6a4f-3c2d-7b8a-9abc-def012345691"))
ACTION_ID = ActionId(UUID("018f6a4f-3c2d-7b8a-9abc-def012345692"))

RUN_ID_1 = RunId(UUID("018f6a4f-3c2d-7b8a-9abc-def012345693"))
RUN_ID_2 = RunId(UUID("018f6a4f-3c2d-7b8a-9abc-def012345694"))
RUN_ID_3 = RunId(UUID("018f6a4f-3c2d-7b8a-9abc-def012345695"))
RUN_ID_4 = RunId(UUID("018f6a4f-3c2d-7b8a-9abc-def012345696"))
RUN_ID_5 = RunId(UUID("018f6a4f-3c2d-7b8a-9abc-def012345697"))
UNKNOWN_RUN_ID = RunId(UUID("018f6a4f-3c2d-7b8a-9abc-def012345699"))

EVENT_ID_1 = EventId(UUID("018f6a4f-3c2d-7b8a-9abc-def01234569a"))
EVENT_ID_2 = EventId(UUID("018f6a4f-3c2d-7b8a-9abc-def01234569b"))
EVENT_ID_3 = EventId(UUID("018f6a4f-3c2d-7b8a-9abc-def01234569c"))

TWO_ITEM_LIMIT = 2
THREE_EVENTS = 3
THREE_RUN_TOTAL = 3
TWO_RUN_TOTAL = 2
TWO_GROUP_TOTAL = 2
FIVE_RUN_TOTAL = 5


def test_list_runs_filters_by_status() -> None:
    """Only Runs matching the requested status are returned, newest first."""
    uow = InMemoryUnitOfWork()
    uow.libraries.save(_library())
    uow.plans.save(_plan())
    uow.runs.save(_run(RUN_ID_1, status=RunStatus.SUCCEEDED, started_at=BASE_TIME))
    uow.runs.save(_run(RUN_ID_2, status=RunStatus.FAILED, started_at=BASE_TIME + timedelta(minutes=1)))
    uow.runs.save(_run(RUN_ID_3, status=RunStatus.SUCCEEDED, started_at=BASE_TIME + timedelta(minutes=2)))

    page = ListRunsUseCase(HistoryPorts(uow)).execute(ListRunsRequest(status=RunStatus.SUCCEEDED))

    assert tuple(run.run_id for run in page.items) == (RUN_ID_3, RUN_ID_1)
    assert page.total == TWO_RUN_TOTAL


def test_list_runs_filters_by_plan_id() -> None:
    """Run browsing can locate the Run for one Plan without walking history pages."""
    other_plan_id = PlanId(UUID("018f6a4f-3c2d-7b8a-9abc-def0123456a0"))
    uow = InMemoryUnitOfWork()
    uow.plans.save(_plan())
    uow.plans.save(_plan(plan_id=other_plan_id))
    uow.runs.save(_run(RUN_ID_1, started_at=BASE_TIME))
    uow.runs.save(_run(RUN_ID_2, started_at=BASE_TIME + timedelta(minutes=1), plan_id=other_plan_id))

    page = ListRunsUseCase(HistoryPorts(uow)).execute(ListRunsRequest(plan_id=PLAN_ID))

    assert tuple(run.run_id for run in page.items) == (RUN_ID_1,)
    assert page.total == 1


def test_list_runs_searches_identity_and_status_fields_case_insensitively() -> None:
    """Global Run search matches summary values before paging."""
    uow = InMemoryUnitOfWork()
    uow.plans.save(_plan())
    uow.runs.save(_run(RUN_ID_1, status=RunStatus.SUCCEEDED, started_at=BASE_TIME))
    uow.runs.save(_run(RUN_ID_2, status=RunStatus.FAILED, started_at=BASE_TIME + timedelta(minutes=1)))

    page = ListRunsUseCase(HistoryPorts(uow)).execute(ListRunsRequest(search="FAILED"))

    assert tuple(run.run_id for run in page.items) == (RUN_ID_2,)
    assert page.total == 1


def test_list_runs_orders_newest_first_by_default() -> None:
    """Unfiltered listing sorts by (started_at, run_id) descending in both scopes."""
    uow = InMemoryUnitOfWork()
    uow.libraries.save(_library())
    uow.plans.save(_plan())
    uow.runs.save(_run(RUN_ID_2, started_at=BASE_TIME + timedelta(minutes=1)))
    uow.runs.save(_run(RUN_ID_1, started_at=BASE_TIME))
    uow.runs.save(_run(RUN_ID_3, started_at=BASE_TIME + timedelta(minutes=2)))

    page_all = ListRunsUseCase(HistoryPorts(uow)).execute(ListRunsRequest())
    page_scoped = ListRunsUseCase(HistoryPorts(uow)).execute(ListRunsRequest(library_id=LIBRARY_ID))

    expected = (RUN_ID_3, RUN_ID_2, RUN_ID_1)
    assert tuple(run.run_id for run in page_all.items) == expected
    assert tuple(run.run_id for run in page_scoped.items) == expected


def test_list_runs_limit_applies_after_filtering() -> None:
    """The page limit narrows the filtered set, not the pre-filter fetch."""
    uow = InMemoryUnitOfWork()
    uow.libraries.save(_library())
    uow.plans.save(_plan())
    uow.runs.save(_run(RUN_ID_1, status=RunStatus.SUCCEEDED, started_at=BASE_TIME))
    uow.runs.save(_run(RUN_ID_2, status=RunStatus.SUCCEEDED, started_at=BASE_TIME + timedelta(minutes=1)))
    uow.runs.save(_run(RUN_ID_3, status=RunStatus.SUCCEEDED, started_at=BASE_TIME + timedelta(minutes=2)))
    uow.runs.save(_run(RUN_ID_4, status=RunStatus.FAILED, started_at=BASE_TIME + timedelta(minutes=3)))
    uow.runs.save(_run(RUN_ID_5, status=RunStatus.FAILED, started_at=BASE_TIME + timedelta(minutes=4)))

    page = ListRunsUseCase(HistoryPorts(uow)).execute(
        ListRunsRequest(status=RunStatus.SUCCEEDED, page=PageRequest(limit=TWO_ITEM_LIMIT)),
    )

    assert tuple(run.run_id for run in page.items) == (RUN_ID_3, RUN_ID_2)
    assert page.total == THREE_RUN_TOTAL


def test_list_runs_paginates_forward_with_keyset_cursor() -> None:
    """A limit=2 keyset walk over 5 Runs visits every Run once, newest first, then terminates."""
    uow = InMemoryUnitOfWork()
    uow.libraries.save(_library())
    uow.plans.save(_plan())
    run_ids = (RUN_ID_1, RUN_ID_2, RUN_ID_3, RUN_ID_4, RUN_ID_5)
    for index, run_id in enumerate(run_ids):
        uow.runs.save(_run(run_id, started_at=BASE_TIME + timedelta(minutes=index)))

    usecase = ListRunsUseCase(HistoryPorts(uow))
    visited: list[RunId] = []
    cursor: tuple[str, ...] | None = None
    for _ in range(len(run_ids)):
        page = usecase.execute(ListRunsRequest(page=PageRequest(limit=TWO_ITEM_LIMIT, cursor_key=cursor)))
        visited.extend(run.run_id for run in page.items)
        assert page.total == FIVE_RUN_TOTAL
        if page.next_cursor_key is None:
            break
        cursor = page.next_cursor_key

    assert visited == list(reversed(run_ids))
    assert len(visited) == len(set(visited))


def test_list_runs_does_not_commit() -> None:
    """Listing Runs never commits the UnitOfWork."""
    uow = InMemoryUnitOfWork()
    uow.libraries.save(_library())
    uow.plans.save(_plan())
    uow.runs.save(_run(RUN_ID_1, started_at=BASE_TIME))

    _ = ListRunsUseCase(HistoryPorts(uow)).execute(ListRunsRequest())

    assert uow.commit_count == 0


def test_get_run_header_returns_run() -> None:
    """The header usecase returns the stored Run by ID."""
    uow = InMemoryUnitOfWork()
    run = _run(RUN_ID_1, started_at=BASE_TIME)
    uow.runs.save(run)

    loaded = GetRunHeaderUseCase(HistoryPorts(uow)).execute(GetRunHeaderRequest(RUN_ID_1))

    assert loaded == run


def test_get_run_header_raises_for_unknown_run() -> None:
    """An unknown Run ID raises RunNotFoundError."""
    uow = InMemoryUnitOfWork()

    with pytest.raises(RunNotFoundError, match=RUN_NOT_FOUND_MESSAGE):
        _ = GetRunHeaderUseCase(HistoryPorts(uow)).execute(GetRunHeaderRequest(UNKNOWN_RUN_ID))


def test_list_run_events_filters_by_status_and_reports_filtered_total() -> None:
    """The status filter is pushed into the query; total counts the filtered rows."""
    uow = InMemoryUnitOfWork()
    uow.runs.save(_run(RUN_ID_1, started_at=BASE_TIME))
    uow.file_events.save(_event(EVENT_ID_1, sequence_no=1, status=FileEventStatus.SUCCEEDED))
    uow.file_events.save(_event(EVENT_ID_2, sequence_no=2, status=FileEventStatus.FAILED))
    uow.file_events.save(_event(EVENT_ID_3, sequence_no=3, status=FileEventStatus.SUCCEEDED))

    page = ListRunEventsUseCase(HistoryPorts(uow)).execute(
        ListRunEventsRequest(run_id=RUN_ID_1, status=FileEventStatus.FAILED),
    )

    assert tuple(event.event_id for event in page.items) == (EVENT_ID_2,)
    assert page.total == 1


def test_list_run_events_paginates_in_sequence_order_with_keyset_cursor() -> None:
    """A limit=2 keyset walk over 3 events visits every event once in (sequence_no, event_id) order."""
    uow = InMemoryUnitOfWork()
    uow.runs.save(_run(RUN_ID_1, started_at=BASE_TIME))
    uow.file_events.save(_event(EVENT_ID_3, sequence_no=3))
    uow.file_events.save(_event(EVENT_ID_1, sequence_no=1))
    uow.file_events.save(_event(EVENT_ID_2, sequence_no=2))

    usecase = ListRunEventsUseCase(HistoryPorts(uow))
    visited: list[EventId] = []
    cursor: tuple[str, ...] | None = None
    for _ in range(THREE_EVENTS):
        page = usecase.execute(
            ListRunEventsRequest(run_id=RUN_ID_1, page=PageRequest(limit=TWO_ITEM_LIMIT, cursor_key=cursor)),
        )
        visited.extend(event.event_id for event in page.items)
        assert page.total == THREE_EVENTS
        if page.next_cursor_key is None:
            break
        cursor = page.next_cursor_key

    assert visited == [EVENT_ID_1, EVENT_ID_2, EVENT_ID_3]


def test_list_run_events_raises_for_unknown_run() -> None:
    """An unknown Run ID raises RunNotFoundError before querying events."""
    uow = InMemoryUnitOfWork()

    with pytest.raises(RunNotFoundError, match=RUN_NOT_FOUND_MESSAGE):
        _ = ListRunEventsUseCase(HistoryPorts(uow)).execute(ListRunEventsRequest(run_id=UNKNOWN_RUN_ID))


def test_get_run_status_facets_returns_breakdown_and_total() -> None:
    """Facets carry the status breakdown ordered count DESC then value ASC, plus the unfiltered total."""
    uow = InMemoryUnitOfWork()
    uow.libraries.save(_library())
    uow.plans.save(_plan())
    uow.runs.save(_run(RUN_ID_1, status=RunStatus.SUCCEEDED, started_at=BASE_TIME))
    uow.runs.save(_run(RUN_ID_2, status=RunStatus.SUCCEEDED, started_at=BASE_TIME + timedelta(minutes=1)))
    uow.runs.save(_run(RUN_ID_3, status=RunStatus.FAILED, started_at=BASE_TIME + timedelta(minutes=2)))

    result = GetRunStatusFacetsUseCase(HistoryPorts(uow)).execute(RunStatusFacetsRequest(library_id=LIBRARY_ID))

    assert [(facet.value, facet.count) for facet in result.facets] == [
        (RunStatus.SUCCEEDED.value, 2),
        (RunStatus.FAILED.value, 1),
    ]
    assert result.total == THREE_RUN_TOTAL


def test_get_file_event_status_facets_returns_breakdown_and_total() -> None:
    """FileEvent facets carry the status breakdown for one Run without loading event pages."""
    uow = InMemoryUnitOfWork()
    uow.runs.save(_run(RUN_ID_1, started_at=BASE_TIME))
    uow.file_events.save(_event(EVENT_ID_1, sequence_no=1, status=FileEventStatus.SUCCEEDED))
    uow.file_events.save(_event(EVENT_ID_2, sequence_no=2, status=FileEventStatus.FAILED))
    uow.file_events.save(_event(EVENT_ID_3, sequence_no=3, status=FileEventStatus.SUCCEEDED))

    result = GetFileEventStatusFacetsUseCase(HistoryPorts(uow)).execute(FileEventStatusFacetsRequest(run_id=RUN_ID_1))

    assert [(facet.value, facet.count) for facet in result.facets] == [
        (FileEventStatus.SUCCEEDED.value, 2),
        (FileEventStatus.FAILED.value, 1),
    ]
    assert result.total == THREE_EVENTS


def test_group_run_events_groups_by_target_directory() -> None:
    """FileEvent grouping derives target-directory counts from recorded target_path values."""
    uow = InMemoryUnitOfWork()
    uow.runs.save(_run(RUN_ID_1, started_at=BASE_TIME))
    uow.file_events.save(_event(EVENT_ID_1, sequence_no=1, target_path="Artist/Album/1.flac"))
    uow.file_events.save(_event(EVENT_ID_2, sequence_no=2, target_path="Artist/Album/2.flac"))
    uow.file_events.save(_event(EVENT_ID_3, sequence_no=3, target_path="Root.flac"))

    page = GroupRunEventsUseCase(HistoryPorts(uow)).execute(
        GroupRunEventsRequest(run_id=RUN_ID_1, page=PageRequest(limit=1))
    )

    assert [(group.key, group.count) for group in page.items] == [("Artist/Album", 2)]
    assert page.next_cursor_key == ("2", "Artist/Album")
    assert page.total == TWO_GROUP_TOTAL


def test_file_event_summaries_raise_for_unknown_run() -> None:
    """Facet and group summaries reject an unknown Run before querying events."""
    uow = InMemoryUnitOfWork()

    with pytest.raises(RunNotFoundError, match=RUN_NOT_FOUND_MESSAGE):
        _ = GetFileEventStatusFacetsUseCase(HistoryPorts(uow)).execute(
            FileEventStatusFacetsRequest(run_id=UNKNOWN_RUN_ID)
        )
    with pytest.raises(RunNotFoundError, match=RUN_NOT_FOUND_MESSAGE):
        _ = GroupRunEventsUseCase(HistoryPorts(uow)).execute(GroupRunEventsRequest(run_id=UNKNOWN_RUN_ID))


def _library() -> Library:
    return Library(
        library_id=LIBRARY_ID,
        root_path=LIBRARY_ROOT,
        path_policy_hash="path-policy",
        registered_at=BASE_TIME,
        status=LibraryStatus.REGISTERED,
        created_at=BASE_TIME,
        updated_at=BASE_TIME,
    )


def _plan(*, plan_id: PlanId = PLAN_ID) -> Plan:
    return Plan(
        plan_id=plan_id,
        library_id=LIBRARY_ID,
        plan_type=PlanType.ADD,
        status=PlanStatus.APPLIED,
        created_at=BASE_TIME,
        config_hash=CONFIG_HASH,
        library_root_at_plan=LIBRARY_ROOT,
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
