"""
Summary: Tests ListPlansUseCase filter/sort/limit and GetPlanDetailUseCase action filtering.
Why: Protects the Plan review query pipeline (filter -> sort -> limit) and
     total_action_count accounting before the CLI exposes these as flags.
"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from uuid import UUID

import pytest

from omym2.domain.models.library import Library, LibraryStatus
from omym2.domain.models.plan import Plan, PlanStatus, PlanType
from omym2.domain.models.plan_action import ActionStatus, ActionType, PlanAction
from omym2.features.plans.dto import GetPlanDetailRequest, ListPlansRequest
from omym2.features.plans.ports import PlanQueryPorts
from omym2.features.plans.usecases.get_plan_detail import (
    PLAN_NOT_FOUND_MESSAGE,
    GetPlanDetailUseCase,
    PlanNotFoundError,
)
from omym2.features.plans.usecases.list_plans import ListPlansUseCase
from omym2.shared.ids import ActionId, LibraryId, PlanId
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

UNKNOWN_PLAN_ID = PlanId(UUID("018f6a4f-3c2d-7b8a-9abc-def012345699"))

THREE_ACTIONS = 3
TWO_ACTIONS = 2


def test_list_plans_filters_by_status() -> None:
    """Only Plans matching the requested status are returned."""
    uow = InMemoryUnitOfWork()
    uow.libraries.save(_library())
    uow.plans.save(_plan(PLAN_ID_1, status=PlanStatus.READY, created_at=BASE_TIME))
    uow.plans.save(_plan(PLAN_ID_2, status=PlanStatus.FAILED, created_at=BASE_TIME + timedelta(days=1)))
    uow.plans.save(_plan(PLAN_ID_3, status=PlanStatus.READY, created_at=BASE_TIME + timedelta(days=2)))

    plans = ListPlansUseCase(PlanQueryPorts(uow)).execute(ListPlansRequest(status=PlanStatus.READY))

    assert tuple(plan.plan_id for plan in plans) == (PLAN_ID_3, PLAN_ID_1)


def test_list_plans_filters_by_type() -> None:
    """Only Plans matching the requested plan_type are returned."""
    uow = InMemoryUnitOfWork()
    uow.libraries.save(_library())
    uow.plans.save(_plan(PLAN_ID_1, plan_type=PlanType.ADD, created_at=BASE_TIME))
    uow.plans.save(_plan(PLAN_ID_2, plan_type=PlanType.ORGANIZE, created_at=BASE_TIME + timedelta(days=1)))
    uow.plans.save(_plan(PLAN_ID_3, plan_type=PlanType.ADD, created_at=BASE_TIME + timedelta(days=2)))

    plans = ListPlansUseCase(PlanQueryPorts(uow)).execute(ListPlansRequest(plan_type=PlanType.ADD))

    assert tuple(plan.plan_id for plan in plans) == (PLAN_ID_3, PLAN_ID_1)


def test_list_plans_orders_newest_first_by_default() -> None:
    """Unfiltered listing sorts by created_at descending in both scopes."""
    uow = InMemoryUnitOfWork()
    uow.libraries.save(_library())
    uow.plans.save(_plan(PLAN_ID_2, created_at=BASE_TIME + timedelta(days=1)))
    uow.plans.save(_plan(PLAN_ID_1, created_at=BASE_TIME))
    uow.plans.save(_plan(PLAN_ID_3, created_at=BASE_TIME + timedelta(days=2)))

    plans_all = ListPlansUseCase(PlanQueryPorts(uow)).execute(ListPlansRequest())
    plans_scoped = ListPlansUseCase(PlanQueryPorts(uow)).execute(ListPlansRequest(library_id=LIBRARY_ID))

    expected = (PLAN_ID_3, PLAN_ID_2, PLAN_ID_1)
    assert tuple(plan.plan_id for plan in plans_all) == expected
    assert tuple(plan.plan_id for plan in plans_scoped) == expected


def test_list_plans_limit_applies_after_filtering() -> None:
    """Limit narrows the filtered+sorted set, not the pre-filter fetch.

    Seeded so a naive limit-then-filter pipeline (sort desc, take 2, then
    filter to READY) would see only the two newest Plans -- both FAILED --
    and return an empty result. The correct filter -> sort -> limit order
    must return the two newest READY Plans instead.
    """
    uow = InMemoryUnitOfWork()
    uow.libraries.save(_library())
    uow.plans.save(_plan(PLAN_ID_1, status=PlanStatus.READY, created_at=BASE_TIME))
    uow.plans.save(_plan(PLAN_ID_2, status=PlanStatus.READY, created_at=BASE_TIME + timedelta(days=1)))
    uow.plans.save(_plan(PLAN_ID_3, status=PlanStatus.READY, created_at=BASE_TIME + timedelta(days=2)))
    uow.plans.save(_plan(PLAN_ID_4, status=PlanStatus.FAILED, created_at=BASE_TIME + timedelta(days=3)))
    uow.plans.save(_plan(PLAN_ID_5, status=PlanStatus.FAILED, created_at=BASE_TIME + timedelta(days=4)))

    plans = ListPlansUseCase(PlanQueryPorts(uow)).execute(
        ListPlansRequest(status=PlanStatus.READY, limit=2),
    )

    assert tuple(plan.plan_id for plan in plans) == (PLAN_ID_3, PLAN_ID_2)


def test_list_plans_limit_larger_than_result_set_returns_all() -> None:
    """A limit exceeding the filtered result set returns every match."""
    uow = InMemoryUnitOfWork()
    uow.libraries.save(_library())
    uow.plans.save(_plan(PLAN_ID_1, created_at=BASE_TIME))
    uow.plans.save(_plan(PLAN_ID_2, created_at=BASE_TIME + timedelta(days=1)))

    plans = ListPlansUseCase(PlanQueryPorts(uow)).execute(ListPlansRequest(limit=10))

    assert tuple(plan.plan_id for plan in plans) == (PLAN_ID_2, PLAN_ID_1)


def test_list_plans_combined_status_and_type_filter_returns_empty_when_no_match() -> None:
    """Combined filters that individually match different Plans return nothing."""
    uow = InMemoryUnitOfWork()
    uow.libraries.save(_library())
    uow.plans.save(
        _plan(PLAN_ID_1, status=PlanStatus.READY, plan_type=PlanType.ADD, created_at=BASE_TIME),
    )
    uow.plans.save(
        _plan(
            PLAN_ID_2,
            status=PlanStatus.FAILED,
            plan_type=PlanType.ORGANIZE,
            created_at=BASE_TIME + timedelta(days=1),
        ),
    )

    plans = ListPlansUseCase(PlanQueryPorts(uow)).execute(
        ListPlansRequest(status=PlanStatus.READY, plan_type=PlanType.ORGANIZE),
    )

    assert plans == ()


def test_list_plans_does_not_commit() -> None:
    """Listing Plans never commits the UnitOfWork."""
    uow = InMemoryUnitOfWork()
    uow.libraries.save(_library())
    uow.plans.save(_plan(PLAN_ID_1, created_at=BASE_TIME))

    _ = ListPlansUseCase(PlanQueryPorts(uow)).execute(ListPlansRequest())

    assert uow.commit_count == 0


def test_get_plan_detail_filters_actions_by_status() -> None:
    """Only actions matching the requested action_status are returned."""
    uow = InMemoryUnitOfWork()
    uow.plans.save(_plan(PLAN_ID_1, created_at=BASE_TIME))
    uow.plan_actions.save(_action(ACTION_ID_1, status=ActionStatus.PLANNED, sort_order=0))
    uow.plan_actions.save(_action(ACTION_ID_2, status=ActionStatus.BLOCKED, sort_order=1))
    uow.plan_actions.save(_action(ACTION_ID_3, status=ActionStatus.APPLIED, sort_order=2))

    detail = GetPlanDetailUseCase(PlanQueryPorts(uow)).execute(
        GetPlanDetailRequest(plan_id=PLAN_ID_1, action_status=ActionStatus.BLOCKED),
    )

    assert tuple(action.action_id for action in detail.actions) == (ACTION_ID_2,)
    assert detail.total_action_count == THREE_ACTIONS


def test_get_plan_detail_action_filter_empty_result_still_reports_total_action_count() -> None:
    """A filter matching no actions still reports the unfiltered total."""
    uow = InMemoryUnitOfWork()
    uow.plans.save(_plan(PLAN_ID_1, created_at=BASE_TIME))
    uow.plan_actions.save(_action(ACTION_ID_1, status=ActionStatus.PLANNED, sort_order=0))
    uow.plan_actions.save(_action(ACTION_ID_2, status=ActionStatus.PLANNED, sort_order=1))

    detail = GetPlanDetailUseCase(PlanQueryPorts(uow)).execute(
        GetPlanDetailRequest(plan_id=PLAN_ID_1, action_status=ActionStatus.FAILED),
    )

    assert detail.actions == ()
    assert detail.total_action_count == TWO_ACTIONS


def test_get_plan_detail_no_filter_returns_full_actions_and_matching_total_count() -> None:
    """Without a filter, all actions are returned and total_action_count matches."""
    uow = InMemoryUnitOfWork()
    uow.plans.save(_plan(PLAN_ID_1, created_at=BASE_TIME))
    uow.plan_actions.save(_action(ACTION_ID_1, status=ActionStatus.PLANNED, sort_order=0))
    uow.plan_actions.save(_action(ACTION_ID_2, status=ActionStatus.BLOCKED, sort_order=1))

    detail = GetPlanDetailUseCase(PlanQueryPorts(uow)).execute(GetPlanDetailRequest(plan_id=PLAN_ID_1))

    assert tuple(action.action_id for action in detail.actions) == (ACTION_ID_1, ACTION_ID_2)
    assert detail.total_action_count == TWO_ACTIONS


def test_get_plan_detail_raises_plan_not_found_before_touching_action_filter() -> None:
    """An unknown Plan ID raises before any action filtering happens."""
    uow = InMemoryUnitOfWork()

    with pytest.raises(PlanNotFoundError, match=PLAN_NOT_FOUND_MESSAGE):
        _ = GetPlanDetailUseCase(PlanQueryPorts(uow)).execute(
            GetPlanDetailRequest(plan_id=UNKNOWN_PLAN_ID, action_status=ActionStatus.BLOCKED),
        )


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
) -> PlanAction:
    return PlanAction(
        action_id=action_id,
        plan_id=PLAN_ID_1,
        library_id=LIBRARY_ID,
        track_id=None,
        action_type=ActionType.MOVE,
        source_path="Source/Track.flac",
        target_path="Target/Track.flac",
        content_hash_at_plan=None,
        metadata_hash_at_plan=None,
        status=status,
        reason=None,
        sort_order=sort_order,
    )
