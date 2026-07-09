"""
Summary: Tests SQLitePlanRepository/SQLitePlanActionRepository keyset paging, facets, and target paths.
Why: Protects the plans browsing SQL contract (DESC keyset math, filter pushdown, facet ordering).
"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from typing import TYPE_CHECKING
from uuid import UUID

from omym2.adapters.config.application_paths import default_application_paths
from omym2.adapters.db.sqlite.unit_of_work import SQLiteUnitOfWork
from omym2.domain.models.library import Library, LibraryStatus
from omym2.domain.models.plan import Plan, PlanStatus, PlanType
from omym2.domain.models.plan_action import ActionStatus, ActionType, PlanAction
from omym2.shared.ids import ActionId, LibraryId, PlanId
from omym2.shared.pagination import PageRequest

if TYPE_CHECKING:
    from pathlib import Path

BASE_TIME = datetime(2026, 1, 1, tzinfo=UTC)
CONFIG_HASH = "config-hash"
LIBRARY_ID = LibraryId(UUID("018f6a4f-3c2d-7b8a-9abc-def0123456c0"))
SECOND_LIBRARY_ID = LibraryId(UUID("018f6a4f-3c2d-7b8a-9abc-def0123456c1"))
LIBRARY_ROOT = "/music/library"

PLAN_ID_1 = PlanId(UUID("018f6a4f-3c2d-7b8a-9abc-def0123456d1"))
PLAN_ID_2 = PlanId(UUID("018f6a4f-3c2d-7b8a-9abc-def0123456d2"))
PLAN_ID_3 = PlanId(UUID("018f6a4f-3c2d-7b8a-9abc-def0123456d3"))
PLAN_ID_4 = PlanId(UUID("018f6a4f-3c2d-7b8a-9abc-def0123456d4"))
PLAN_ID_5 = PlanId(UUID("018f6a4f-3c2d-7b8a-9abc-def0123456d5"))

ACTION_ID_1 = ActionId(UUID("018f6a4f-3c2d-7b8a-9abc-def0123456e1"))
ACTION_ID_2 = ActionId(UUID("018f6a4f-3c2d-7b8a-9abc-def0123456e2"))
ACTION_ID_3 = ActionId(UUID("018f6a4f-3c2d-7b8a-9abc-def0123456e3"))
ACTION_ID_4 = ActionId(UUID("018f6a4f-3c2d-7b8a-9abc-def0123456e4"))

TWO_ITEM_LIMIT = 2
FIVE_PLAN_TOTAL = 5
THREE_ACTION_TOTAL = 3


def test_plan_query_page_walks_every_plan_newest_first_with_desc_keyset_cursor(tmp_path: Path) -> None:
    """A limit=2 keyset walk over 5 Plans visits every Plan once in (created_at DESC, plan_id DESC) order."""
    database_file = default_application_paths(tmp_path).database_file
    plan_ids = (PLAN_ID_1, PLAN_ID_2, PLAN_ID_3, PLAN_ID_4, PLAN_ID_5)
    with SQLiteUnitOfWork(database_file) as uow:
        uow.libraries.save(_library(LIBRARY_ID))
        for index, plan_id in enumerate(plan_ids):
            uow.plans.save(_plan(plan_id, created_at=BASE_TIME + timedelta(days=index)))
        uow.commit()

    visited: list[PlanId] = []
    cursor: tuple[str, ...] | None = None
    with SQLiteUnitOfWork(database_file) as uow:
        for _ in range(len(plan_ids)):
            page = uow.plans.query_page(
                None,
                status=None,
                plan_type=None,
                page=PageRequest(limit=TWO_ITEM_LIMIT, cursor_key=cursor),
            )
            visited.extend(plan.plan_id for plan in page.items)
            assert page.total == FIVE_PLAN_TOTAL
            if page.next_cursor_key is None:
                break
            cursor = page.next_cursor_key

    assert visited == list(reversed(plan_ids))
    assert len(visited) == len(set(visited))


def test_plan_query_page_breaks_created_at_ties_by_plan_id_desc(tmp_path: Path) -> None:
    """Plans sharing one created_at are ordered and keyset-walked by plan_id DESC."""
    database_file = default_application_paths(tmp_path).database_file
    plan_ids = (PLAN_ID_1, PLAN_ID_2, PLAN_ID_3)
    with SQLiteUnitOfWork(database_file) as uow:
        uow.libraries.save(_library(LIBRARY_ID))
        for plan_id in plan_ids:
            uow.plans.save(_plan(plan_id, created_at=BASE_TIME))
        uow.commit()

    visited: list[PlanId] = []
    cursor: tuple[str, ...] | None = None
    with SQLiteUnitOfWork(database_file) as uow:
        for _ in range(len(plan_ids)):
            page = uow.plans.query_page(
                None,
                status=None,
                plan_type=None,
                page=PageRequest(limit=1, cursor_key=cursor),
            )
            visited.extend(plan.plan_id for plan in page.items)
            if page.next_cursor_key is None:
                break
            cursor = page.next_cursor_key

    assert visited == [PLAN_ID_3, PLAN_ID_2, PLAN_ID_1]


def test_plan_query_page_pushes_status_and_type_filters_into_sql(tmp_path: Path) -> None:
    """Status/type filters narrow both the rows and the total, before the limit applies."""
    database_file = default_application_paths(tmp_path).database_file
    with SQLiteUnitOfWork(database_file) as uow:
        uow.libraries.save(_library(LIBRARY_ID))
        uow.plans.save(_plan(PLAN_ID_1, created_at=BASE_TIME, status=PlanStatus.READY, plan_type=PlanType.ADD))
        uow.plans.save(
            _plan(
                PLAN_ID_2,
                created_at=BASE_TIME + timedelta(days=1),
                status=PlanStatus.FAILED,
                plan_type=PlanType.ADD,
            )
        )
        uow.plans.save(
            _plan(
                PLAN_ID_3,
                created_at=BASE_TIME + timedelta(days=2),
                status=PlanStatus.READY,
                plan_type=PlanType.ORGANIZE,
            )
        )
        uow.commit()

    with SQLiteUnitOfWork(database_file) as uow:
        page = uow.plans.query_page(
            None,
            status=PlanStatus.READY,
            plan_type=PlanType.ADD,
            page=PageRequest(),
        )

    assert tuple(plan.plan_id for plan in page.items) == (PLAN_ID_1,)
    assert page.total == 1


def test_plan_query_page_scopes_by_library(tmp_path: Path) -> None:
    """query_page(library_id=...) only returns Plans owned by that Library."""
    database_file = default_application_paths(tmp_path).database_file
    with SQLiteUnitOfWork(database_file) as uow:
        uow.libraries.save(_library(LIBRARY_ID))
        uow.libraries.save(_library(SECOND_LIBRARY_ID))
        uow.plans.save(_plan(PLAN_ID_1, created_at=BASE_TIME))
        uow.plans.save(_plan(PLAN_ID_2, created_at=BASE_TIME, library_id=SECOND_LIBRARY_ID))
        uow.commit()

    with SQLiteUnitOfWork(database_file) as uow:
        page = uow.plans.query_page(
            SECOND_LIBRARY_ID,
            status=None,
            plan_type=None,
            page=PageRequest(),
        )

    assert tuple(plan.plan_id for plan in page.items) == (PLAN_ID_2,)
    assert page.total == 1


def test_plan_action_query_page_walks_actions_in_sort_order_with_keyset_cursor(tmp_path: Path) -> None:
    """A limit=2 keyset walk over 3 actions visits every action once in (sort_order, action_id) order."""
    database_file = default_application_paths(tmp_path).database_file
    with SQLiteUnitOfWork(database_file) as uow:
        uow.libraries.save(_library(LIBRARY_ID))
        uow.plans.save(_plan(PLAN_ID_1, created_at=BASE_TIME))
        uow.plan_actions.save(_action(ACTION_ID_2, sort_order=2))
        uow.plan_actions.save(_action(ACTION_ID_1, sort_order=1))
        uow.plan_actions.save(_action(ACTION_ID_3, sort_order=3))
        uow.commit()

    visited: list[ActionId] = []
    cursor: tuple[str, ...] | None = None
    with SQLiteUnitOfWork(database_file) as uow:
        for _ in range(THREE_ACTION_TOTAL):
            page = uow.plan_actions.query_page(
                PLAN_ID_1,
                status=None,
                page=PageRequest(limit=TWO_ITEM_LIMIT, cursor_key=cursor),
            )
            visited.extend(action.action_id for action in page.items)
            assert page.total == THREE_ACTION_TOTAL
            if page.next_cursor_key is None:
                break
            cursor = page.next_cursor_key

    assert visited == [ACTION_ID_1, ACTION_ID_2, ACTION_ID_3]


def test_plan_action_query_page_filters_by_status_in_sql(tmp_path: Path) -> None:
    """The optional status filter narrows both the rows and the total."""
    database_file = default_application_paths(tmp_path).database_file
    with SQLiteUnitOfWork(database_file) as uow:
        uow.libraries.save(_library(LIBRARY_ID))
        uow.plans.save(_plan(PLAN_ID_1, created_at=BASE_TIME))
        uow.plan_actions.save(_action(ACTION_ID_1, sort_order=1, status=ActionStatus.PLANNED))
        uow.plan_actions.save(_action(ACTION_ID_2, sort_order=2, status=ActionStatus.BLOCKED))
        uow.commit()

    with SQLiteUnitOfWork(database_file) as uow:
        page = uow.plan_actions.query_page(
            PLAN_ID_1,
            status=ActionStatus.BLOCKED,
            page=PageRequest(),
        )

    assert tuple(action.action_id for action in page.items) == (ACTION_ID_2,)
    assert page.total == 1


def test_plan_action_facets_order_count_desc_then_value_asc(tmp_path: Path) -> None:
    """status_facets and action_type_facets are ordered count DESC, then value ASC."""
    database_file = default_application_paths(tmp_path).database_file
    with SQLiteUnitOfWork(database_file) as uow:
        uow.libraries.save(_library(LIBRARY_ID))
        uow.plans.save(_plan(PLAN_ID_1, created_at=BASE_TIME))
        uow.plan_actions.save(_action(ACTION_ID_1, sort_order=1, status=ActionStatus.PLANNED))
        uow.plan_actions.save(_action(ACTION_ID_2, sort_order=2, status=ActionStatus.PLANNED))
        uow.plan_actions.save(
            _action(ACTION_ID_3, sort_order=3, status=ActionStatus.BLOCKED, action_type=ActionType.SKIP)
        )
        uow.commit()

    with SQLiteUnitOfWork(database_file) as uow:
        status_facets = uow.plan_actions.status_facets(PLAN_ID_1)
        action_type_facets = uow.plan_actions.action_type_facets(PLAN_ID_1)

    assert [(facet.value, facet.count) for facet in status_facets] == [
        (ActionStatus.PLANNED.value, 2),
        (ActionStatus.BLOCKED.value, 1),
    ]
    assert [(facet.value, facet.count) for facet in action_type_facets] == [
        (ActionType.MOVE.value, 2),
        (ActionType.SKIP.value, 1),
    ]


def test_list_target_paths_returns_only_non_null_targets_for_the_plan(tmp_path: Path) -> None:
    """list_target_paths selects the Plan's non-null target_path values only."""
    database_file = default_application_paths(tmp_path).database_file
    with SQLiteUnitOfWork(database_file) as uow:
        uow.libraries.save(_library(LIBRARY_ID))
        uow.plans.save(_plan(PLAN_ID_1, created_at=BASE_TIME))
        uow.plans.save(_plan(PLAN_ID_2, created_at=BASE_TIME + timedelta(days=1)))
        uow.plan_actions.save(_action(ACTION_ID_1, sort_order=1, target_path="Artist/Album/1.flac"))
        uow.plan_actions.save(_action(ACTION_ID_2, sort_order=2, action_type=ActionType.SKIP, target_path=None))
        uow.plan_actions.save(_action(ACTION_ID_3, sort_order=3, target_path="Loose.flac"))
        uow.plan_actions.save(_action(ACTION_ID_4, sort_order=1, plan_id=PLAN_ID_2, target_path="Other/2.flac"))
        uow.commit()

    with SQLiteUnitOfWork(database_file) as uow:
        target_paths = uow.plan_actions.list_target_paths(PLAN_ID_1)

    assert target_paths == ("Artist/Album/1.flac", "Loose.flac")


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


def _plan(
    plan_id: PlanId,
    *,
    created_at: datetime,
    status: PlanStatus = PlanStatus.READY,
    plan_type: PlanType = PlanType.ADD,
    library_id: LibraryId = LIBRARY_ID,
) -> Plan:
    return Plan(
        plan_id=plan_id,
        library_id=library_id,
        plan_type=plan_type,
        status=status,
        created_at=created_at,
        config_hash=CONFIG_HASH,
        library_root_at_plan=LIBRARY_ROOT,
    )


def _action(  # noqa: PLR0913 - test fixture spans the paging/facet/target-path action variation matrix.
    action_id: ActionId,
    *,
    sort_order: int,
    status: ActionStatus = ActionStatus.PLANNED,
    action_type: ActionType = ActionType.MOVE,
    target_path: str | None = "Target/Track.flac",
    plan_id: PlanId = PLAN_ID_1,
) -> PlanAction:
    return PlanAction(
        action_id=action_id,
        plan_id=plan_id,
        library_id=LIBRARY_ID,
        track_id=None,
        action_type=action_type,
        source_path="Source/Track.flac",
        target_path=target_path,
        content_hash_at_plan=None,
        metadata_hash_at_plan=None,
        status=status,
        reason=None,
        sort_order=sort_order,
    )
