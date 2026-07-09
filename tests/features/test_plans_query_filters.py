"""
Summary: Tests the Plan browsing usecases: paged listing, paged actions, facets, and groups.
Why: Protects the Plan review query pipeline (filters pushed into the query, keyset
     paging, facet totals, target-directory grouping) before CLI and Web render it.
"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from uuid import UUID

import pytest

from omym2.domain.models.library import Library, LibraryStatus
from omym2.domain.models.plan import Plan, PlanStatus, PlanType
from omym2.domain.models.plan_action import ActionStatus, ActionType, PlanAction
from omym2.features.plans.dto import (
    GetPlanHeaderRequest,
    GroupPlanActionsRequest,
    ListPlanActionsRequest,
    ListPlansRequest,
    PlanActionFacetsRequest,
)
from omym2.features.plans.ports import PlanQueryPorts
from omym2.features.plans.usecases.get_plan_action_facets import GetPlanActionFacetsUseCase
from omym2.features.plans.usecases.get_plan_header import (
    PLAN_NOT_FOUND_MESSAGE,
    GetPlanHeaderUseCase,
    PlanNotFoundError,
)
from omym2.features.plans.usecases.group_plan_actions import GroupPlanActionsUseCase
from omym2.features.plans.usecases.list_plan_actions import ListPlanActionsUseCase
from omym2.features.plans.usecases.list_plans import ListPlansUseCase
from omym2.shared.ids import ActionId, LibraryId, PlanId
from omym2.shared.pagination import PageRequest
from tests.fakes.in_memory_repositories import InMemoryUnitOfWork

BASE_TIME = datetime(2026, 1, 1, tzinfo=UTC)
CONFIG_HASH = "config-hash"
LIBRARY_ID = LibraryId(UUID("018f6a4f-3c2d-7b8a-9abc-def012345690"))
LIBRARY_ROOT = "/music/library"

PLAN_ID_1 = PlanId(UUID("018f6a4f-3c2d-7b8a-9abc-def012345691"))
PLAN_ID_2 = PlanId(UUID("018f6a4f-3c2d-7b8a-9abc-def012345692"))
PLAN_ID_3 = PlanId(UUID("018f6a4f-3c2d-7b8a-9abc-def012345693"))
PLAN_ID_4 = PlanId(UUID("018f6a4f-3c2d-7b8a-9abc-def012345694"))
PLAN_ID_5 = PlanId(UUID("018f6a4f-3c2d-7b8a-9abc-def012345695"))

ACTION_ID_1 = ActionId(UUID("018f6a4f-3c2d-7b8a-9abc-def012345696"))
ACTION_ID_2 = ActionId(UUID("018f6a4f-3c2d-7b8a-9abc-def012345697"))
ACTION_ID_3 = ActionId(UUID("018f6a4f-3c2d-7b8a-9abc-def012345698"))
ACTION_ID_4 = ActionId(UUID("018f6a4f-3c2d-7b8a-9abc-def01234569a"))

UNKNOWN_PLAN_ID = PlanId(UUID("018f6a4f-3c2d-7b8a-9abc-def012345699"))

THREE_ACTIONS = 3
TWO_ACTIONS = 2
TWO_ITEM_LIMIT = 2
FIVE_PLAN_TOTAL = 5
THREE_PLAN_TOTAL = 3
TWO_PLAN_TOTAL = 2


def test_list_plans_filters_by_status() -> None:
    """Only Plans matching the requested status are returned, newest first."""
    uow = InMemoryUnitOfWork()
    uow.libraries.save(_library())
    uow.plans.save(_plan(PLAN_ID_1, status=PlanStatus.READY, created_at=BASE_TIME))
    uow.plans.save(_plan(PLAN_ID_2, status=PlanStatus.FAILED, created_at=BASE_TIME + timedelta(days=1)))
    uow.plans.save(_plan(PLAN_ID_3, status=PlanStatus.READY, created_at=BASE_TIME + timedelta(days=2)))

    page = ListPlansUseCase(PlanQueryPorts(uow)).execute(ListPlansRequest(status=PlanStatus.READY))

    assert tuple(plan.plan_id for plan in page.items) == (PLAN_ID_3, PLAN_ID_1)
    assert page.total == TWO_PLAN_TOTAL


def test_list_plans_filters_by_type() -> None:
    """Only Plans matching the requested plan_type are returned, newest first."""
    uow = InMemoryUnitOfWork()
    uow.libraries.save(_library())
    uow.plans.save(_plan(PLAN_ID_1, plan_type=PlanType.ADD, created_at=BASE_TIME))
    uow.plans.save(_plan(PLAN_ID_2, plan_type=PlanType.ORGANIZE, created_at=BASE_TIME + timedelta(days=1)))
    uow.plans.save(_plan(PLAN_ID_3, plan_type=PlanType.ADD, created_at=BASE_TIME + timedelta(days=2)))

    page = ListPlansUseCase(PlanQueryPorts(uow)).execute(ListPlansRequest(plan_type=PlanType.ADD))

    assert tuple(plan.plan_id for plan in page.items) == (PLAN_ID_3, PLAN_ID_1)


def test_list_plans_orders_newest_first_by_default() -> None:
    """Unfiltered listing sorts by (created_at, plan_id) descending in both scopes."""
    uow = InMemoryUnitOfWork()
    uow.libraries.save(_library())
    uow.plans.save(_plan(PLAN_ID_2, created_at=BASE_TIME + timedelta(days=1)))
    uow.plans.save(_plan(PLAN_ID_1, created_at=BASE_TIME))
    uow.plans.save(_plan(PLAN_ID_3, created_at=BASE_TIME + timedelta(days=2)))

    page_all = ListPlansUseCase(PlanQueryPorts(uow)).execute(ListPlansRequest())
    page_scoped = ListPlansUseCase(PlanQueryPorts(uow)).execute(ListPlansRequest(library_id=LIBRARY_ID))

    expected = (PLAN_ID_3, PLAN_ID_2, PLAN_ID_1)
    assert tuple(plan.plan_id for plan in page_all.items) == expected
    assert tuple(plan.plan_id for plan in page_scoped.items) == expected


def test_list_plans_limit_applies_after_filtering() -> None:
    """The page limit narrows the filtered set, not the pre-filter fetch.

    Seeded so a naive limit-then-filter pipeline (sort desc, take 2, then
    filter to READY) would see only the two newest Plans -- both FAILED --
    and return an empty result. The filter-then-page order must return the
    two newest READY Plans instead.
    """
    uow = InMemoryUnitOfWork()
    uow.libraries.save(_library())
    uow.plans.save(_plan(PLAN_ID_1, status=PlanStatus.READY, created_at=BASE_TIME))
    uow.plans.save(_plan(PLAN_ID_2, status=PlanStatus.READY, created_at=BASE_TIME + timedelta(days=1)))
    uow.plans.save(_plan(PLAN_ID_3, status=PlanStatus.READY, created_at=BASE_TIME + timedelta(days=2)))
    uow.plans.save(_plan(PLAN_ID_4, status=PlanStatus.FAILED, created_at=BASE_TIME + timedelta(days=3)))
    uow.plans.save(_plan(PLAN_ID_5, status=PlanStatus.FAILED, created_at=BASE_TIME + timedelta(days=4)))

    page = ListPlansUseCase(PlanQueryPorts(uow)).execute(
        ListPlansRequest(status=PlanStatus.READY, page=PageRequest(limit=TWO_ITEM_LIMIT)),
    )

    assert tuple(plan.plan_id for plan in page.items) == (PLAN_ID_3, PLAN_ID_2)
    assert page.total == THREE_PLAN_TOTAL


def test_list_plans_paginates_forward_with_keyset_cursor() -> None:
    """A limit=2 keyset walk over 5 Plans visits every Plan once, newest first, then terminates."""
    uow = InMemoryUnitOfWork()
    uow.libraries.save(_library())
    plan_ids = (PLAN_ID_1, PLAN_ID_2, PLAN_ID_3, PLAN_ID_4, PLAN_ID_5)
    for index, plan_id in enumerate(plan_ids):
        uow.plans.save(_plan(plan_id, created_at=BASE_TIME + timedelta(days=index)))

    usecase = ListPlansUseCase(PlanQueryPorts(uow))
    visited: list[PlanId] = []
    cursor: tuple[str, ...] | None = None
    for _ in range(len(plan_ids)):
        page = usecase.execute(ListPlansRequest(page=PageRequest(limit=TWO_ITEM_LIMIT, cursor_key=cursor)))
        visited.extend(plan.plan_id for plan in page.items)
        assert page.total == FIVE_PLAN_TOTAL
        if page.next_cursor_key is None:
            break
        cursor = page.next_cursor_key

    assert visited == list(reversed(plan_ids))
    assert len(visited) == len(set(visited))


def test_list_plans_does_not_commit() -> None:
    """Listing Plans never commits the UnitOfWork."""
    uow = InMemoryUnitOfWork()
    uow.libraries.save(_library())
    uow.plans.save(_plan(PLAN_ID_1, created_at=BASE_TIME))

    _ = ListPlansUseCase(PlanQueryPorts(uow)).execute(ListPlansRequest())

    assert uow.commit_count == 0


def test_get_plan_header_returns_plan_without_actions() -> None:
    """The header usecase returns the stored Plan by ID."""
    uow = InMemoryUnitOfWork()
    plan = _plan(PLAN_ID_1, created_at=BASE_TIME)
    uow.plans.save(plan)
    uow.plan_actions.save(_action(ACTION_ID_1, status=ActionStatus.PLANNED, sort_order=0))

    loaded = GetPlanHeaderUseCase(PlanQueryPorts(uow)).execute(GetPlanHeaderRequest(PLAN_ID_1))

    assert loaded == plan


def test_get_plan_header_raises_for_unknown_plan() -> None:
    """An unknown Plan ID raises PlanNotFoundError."""
    uow = InMemoryUnitOfWork()

    with pytest.raises(PlanNotFoundError, match=PLAN_NOT_FOUND_MESSAGE):
        _ = GetPlanHeaderUseCase(PlanQueryPorts(uow)).execute(GetPlanHeaderRequest(UNKNOWN_PLAN_ID))


def test_list_plan_actions_filters_by_status_and_reports_filtered_total() -> None:
    """The status filter is pushed into the query; total counts the filtered rows."""
    uow = InMemoryUnitOfWork()
    uow.plans.save(_plan(PLAN_ID_1, created_at=BASE_TIME))
    uow.plan_actions.save(_action(ACTION_ID_1, status=ActionStatus.PLANNED, sort_order=0))
    uow.plan_actions.save(_action(ACTION_ID_2, status=ActionStatus.BLOCKED, sort_order=1))
    uow.plan_actions.save(_action(ACTION_ID_3, status=ActionStatus.APPLIED, sort_order=2))

    page = ListPlanActionsUseCase(PlanQueryPorts(uow)).execute(
        ListPlanActionsRequest(plan_id=PLAN_ID_1, status=ActionStatus.BLOCKED),
    )

    assert tuple(action.action_id for action in page.items) == (ACTION_ID_2,)
    assert page.total == 1


def test_list_plan_actions_paginates_in_sort_order_with_keyset_cursor() -> None:
    """A limit=2 keyset walk over 3 actions visits every action once in (sort_order, action_id) order."""
    uow = InMemoryUnitOfWork()
    uow.plans.save(_plan(PLAN_ID_1, created_at=BASE_TIME))
    uow.plan_actions.save(_action(ACTION_ID_3, status=ActionStatus.PLANNED, sort_order=2))
    uow.plan_actions.save(_action(ACTION_ID_1, status=ActionStatus.PLANNED, sort_order=0))
    uow.plan_actions.save(_action(ACTION_ID_2, status=ActionStatus.PLANNED, sort_order=1))

    usecase = ListPlanActionsUseCase(PlanQueryPorts(uow))
    visited: list[ActionId] = []
    cursor: tuple[str, ...] | None = None
    for _ in range(THREE_ACTIONS):
        page = usecase.execute(
            ListPlanActionsRequest(plan_id=PLAN_ID_1, page=PageRequest(limit=TWO_ITEM_LIMIT, cursor_key=cursor)),
        )
        visited.extend(action.action_id for action in page.items)
        assert page.total == THREE_ACTIONS
        if page.next_cursor_key is None:
            break
        cursor = page.next_cursor_key

    assert visited == [ACTION_ID_1, ACTION_ID_2, ACTION_ID_3]


def test_list_plan_actions_raises_for_unknown_plan() -> None:
    """An unknown Plan ID raises PlanNotFoundError before querying actions."""
    uow = InMemoryUnitOfWork()

    with pytest.raises(PlanNotFoundError, match=PLAN_NOT_FOUND_MESSAGE):
        _ = ListPlanActionsUseCase(PlanQueryPorts(uow)).execute(ListPlanActionsRequest(plan_id=UNKNOWN_PLAN_ID))


def test_get_plan_action_facets_returns_both_breakdowns_and_unfiltered_total() -> None:
    """Facets carry status and action_type breakdowns ordered count DESC then value ASC."""
    uow = InMemoryUnitOfWork()
    uow.plans.save(_plan(PLAN_ID_1, created_at=BASE_TIME))
    uow.plan_actions.save(_action(ACTION_ID_1, status=ActionStatus.PLANNED, sort_order=0))
    uow.plan_actions.save(_action(ACTION_ID_2, status=ActionStatus.PLANNED, sort_order=1))
    uow.plan_actions.save(
        _action(ACTION_ID_3, status=ActionStatus.BLOCKED, sort_order=2, action_type=ActionType.SKIP),
    )

    result = GetPlanActionFacetsUseCase(PlanQueryPorts(uow)).execute(PlanActionFacetsRequest(PLAN_ID_1))

    assert [(facet.value, facet.count) for facet in result.status_facets] == [
        (ActionStatus.PLANNED.value, 2),
        (ActionStatus.BLOCKED.value, 1),
    ]
    assert [(facet.value, facet.count) for facet in result.action_type_facets] == [
        (ActionType.MOVE.value, 2),
        (ActionType.SKIP.value, 1),
    ]
    assert result.total == THREE_ACTIONS


def test_get_plan_action_facets_raises_for_unknown_plan() -> None:
    """An unknown Plan ID raises PlanNotFoundError before querying facets."""
    uow = InMemoryUnitOfWork()

    with pytest.raises(PlanNotFoundError, match=PLAN_NOT_FOUND_MESSAGE):
        _ = GetPlanActionFacetsUseCase(PlanQueryPorts(uow)).execute(PlanActionFacetsRequest(UNKNOWN_PLAN_ID))


def test_group_plan_actions_groups_by_posix_parent_with_root_label_and_skips_null_targets() -> None:
    """Groups use the POSIX dirname; root-level paths map to '(root)'; null targets are skipped."""
    uow = InMemoryUnitOfWork()
    uow.plans.save(_plan(PLAN_ID_1, created_at=BASE_TIME))
    uow.plan_actions.save(
        _action(ACTION_ID_1, status=ActionStatus.PLANNED, sort_order=0, target_path="Artist/Album/1.flac"),
    )
    uow.plan_actions.save(
        _action(ACTION_ID_2, status=ActionStatus.PLANNED, sort_order=1, target_path="Artist/Album/2.flac"),
    )
    uow.plan_actions.save(
        _action(ACTION_ID_3, status=ActionStatus.PLANNED, sort_order=2, target_path="Loose.flac"),
    )
    uow.plan_actions.save(
        _action(
            ACTION_ID_4,
            status=ActionStatus.PLANNED,
            sort_order=3,
            action_type=ActionType.SKIP,
            target_path=None,
        ),
    )

    page = GroupPlanActionsUseCase(PlanQueryPorts(uow)).execute(GroupPlanActionsRequest(plan_id=PLAN_ID_1))

    assert [(group.key, group.label, group.count) for group in page.items] == [
        ("Artist/Album", "Artist/Album", 2),
        ("(root)", "(root)", 1),
    ]
    assert page.total == TWO_ACTIONS


def test_group_plan_actions_paginates_with_count_then_key_keyset() -> None:
    """A limit=1 keyset walk over target-directory groups visits every group exactly once."""
    uow = InMemoryUnitOfWork()
    uow.plans.save(_plan(PLAN_ID_1, created_at=BASE_TIME))
    uow.plan_actions.save(
        _action(ACTION_ID_1, status=ActionStatus.PLANNED, sort_order=0, target_path="B/1.flac"),
    )
    uow.plan_actions.save(
        _action(ACTION_ID_2, status=ActionStatus.PLANNED, sort_order=1, target_path="B/2.flac"),
    )
    uow.plan_actions.save(
        _action(ACTION_ID_3, status=ActionStatus.PLANNED, sort_order=2, target_path="A/1.flac"),
    )

    usecase = GroupPlanActionsUseCase(PlanQueryPorts(uow))
    visited: list[str] = []
    cursor: tuple[str, ...] | None = None
    for _ in range(THREE_ACTIONS):
        page = usecase.execute(
            GroupPlanActionsRequest(plan_id=PLAN_ID_1, page=PageRequest(limit=1, cursor_key=cursor)),
        )
        visited.extend(group.key for group in page.items)
        assert page.total == TWO_ACTIONS
        if page.next_cursor_key is None:
            break
        cursor = page.next_cursor_key

    assert visited == ["B", "A"]


def test_group_plan_actions_raises_for_unknown_plan() -> None:
    """An unknown Plan ID raises PlanNotFoundError before listing target paths."""
    uow = InMemoryUnitOfWork()

    with pytest.raises(PlanNotFoundError, match=PLAN_NOT_FOUND_MESSAGE):
        _ = GroupPlanActionsUseCase(PlanQueryPorts(uow)).execute(GroupPlanActionsRequest(plan_id=UNKNOWN_PLAN_ID))


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


def _plan(
    plan_id: PlanId,
    *,
    created_at: datetime,
    status: PlanStatus = PlanStatus.READY,
    plan_type: PlanType = PlanType.ADD,
) -> Plan:
    return Plan(
        plan_id=plan_id,
        library_id=LIBRARY_ID,
        plan_type=plan_type,
        status=status,
        created_at=created_at,
        config_hash=CONFIG_HASH,
        library_root_at_plan=LIBRARY_ROOT,
    )


def _action(
    action_id: ActionId,
    *,
    status: ActionStatus,
    sort_order: int,
    action_type: ActionType = ActionType.MOVE,
    target_path: str | None = "Target/Track.flac",
) -> PlanAction:
    return PlanAction(
        action_id=action_id,
        plan_id=PLAN_ID_1,
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
