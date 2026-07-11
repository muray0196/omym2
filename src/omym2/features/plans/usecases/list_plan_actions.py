"""
Summary: Implements paged listing of one Plan's recorded actions, with group drill-down.
Why: Lets Web and CLI inspection browse a Plan's actions at scale, separately from its header.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING

from omym2.features.plans.usecases.get_plan_header import PLAN_NOT_FOUND_MESSAGE, PlanNotFoundError
from omym2.features.plans.usecases.group_plan_actions import derive_plan_action_group_key
from omym2.shared.pagination import INVALID_CURSOR_MESSAGE, CursorDecodeError, Page

if TYPE_CHECKING:
    from omym2.domain.models.plan_action import PlanAction
    from omym2.features.common_ports import PlanActionGroupRow, UnitOfWork
    from omym2.features.plans.dto import ListPlanActionsRequest, PlanActionGrouping
    from omym2.features.plans.ports import PlanQueryPorts

GROUP_FILTER_PAIRING_MESSAGE = "grouping and group_key must be provided together."
ACTION_CURSOR_KEY_LENGTH = 2  # a plan-action cursor key is a (sort_order, action_id) 2-tuple


@dataclass(frozen=True, slots=True)
class ListPlanActionsUseCase:
    """List one Plan's recorded actions as one keyset page, ordered (sort_order, action_id).

    Without a group filter the page comes straight from the repository's SQL
    keyset query. With `grouping`/`group_key` set, membership is derived in
    Python via `derive_plan_action_group_key` (a business rule), the cursor
    and limit apply to the member (sort_order, action_id) pairs, and only the
    page's full rows are fetched by ID.
    """

    ports: PlanQueryPorts

    def execute(self, request: ListPlanActionsRequest) -> Page[PlanAction]:
        """Return one page of actions for the Plan, optionally filtered by status and group.

        Raises PlanNotFoundError for an unknown Plan ID before querying
        actions, and ValueError when only one of `grouping`/`group_key` is
        provided.
        """
        if (request.grouping is None) != (request.group_key is None):
            raise ValueError(GROUP_FILTER_PAIRING_MESSAGE)
        with self.ports.uow as uow:
            if uow.plans.get(request.plan_id) is None:
                raise PlanNotFoundError(PLAN_NOT_FOUND_MESSAGE)
            if request.grouping is None or request.group_key is None:
                return uow.plan_actions.query_page(request.plan_id, status=request.status, page=request.page)
            return _group_member_page(uow, request, request.grouping, request.group_key)


def _group_member_page(
    uow: UnitOfWork,
    request: ListPlanActionsRequest,
    grouping: PlanActionGrouping,
    group_key: str,
) -> Page[PlanAction]:
    """Return one keyset page of the group's member actions under the status filter."""
    rows = uow.plan_actions.list_group_rows(request.plan_id)
    members = sorted(
        (
            row
            for row in rows
            if (request.status is None or row.status is request.status) and _is_group_member(row, grouping, group_key)
        ),
        key=lambda row: (row.sort_order, str(row.action_id)),
    )
    total = len(members)

    if request.page.cursor_key is not None:
        cursor_sort_order, cursor_action_id = _decode_action_cursor(request.page.cursor_key)
        members = [
            row for row in members if (row.sort_order, str(row.action_id)) > (cursor_sort_order, cursor_action_id)
        ]

    page_rows = members[: request.page.limit]
    has_more = len(members) > request.page.limit
    actions = tuple(uow.plan_actions.list_by_ids(tuple(row.action_id for row in page_rows)))
    next_cursor_key = (str(page_rows[-1].sort_order), str(page_rows[-1].action_id)) if has_more else None
    return Page(items=actions, next_cursor_key=next_cursor_key, total=total)


def _is_group_member(row: PlanActionGroupRow, grouping: PlanActionGrouping, group_key: str) -> bool:
    """Return whether the action's derived group key matches the requested key."""
    derived = derive_plan_action_group_key(row, grouping)
    return derived is not None and derived.key == group_key


def _decode_action_cursor(cursor_key: tuple[str, ...]) -> tuple[int, str]:
    """Decode a (sort_order, action_id) cursor key, mirroring the SQL keyset path."""
    if len(cursor_key) != ACTION_CURSOR_KEY_LENGTH:
        raise CursorDecodeError(INVALID_CURSOR_MESSAGE)
    sort_order_text, action_id_text = cursor_key
    try:
        return int(sort_order_text), action_id_text
    except ValueError as error:
        raise CursorDecodeError(INVALID_CURSOR_MESSAGE) from error
