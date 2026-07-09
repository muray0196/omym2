"""
Summary: Implements paged listing of one Plan's recorded actions.
Why: Lets Web and CLI inspection browse a Plan's actions at scale, separately from its header.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING

from omym2.features.plans.usecases.get_plan_header import PLAN_NOT_FOUND_MESSAGE, PlanNotFoundError

if TYPE_CHECKING:
    from omym2.domain.models.plan_action import PlanAction
    from omym2.features.plans.dto import ListPlanActionsRequest
    from omym2.features.plans.ports import PlanQueryPorts
    from omym2.shared.pagination import Page


@dataclass(frozen=True, slots=True)
class ListPlanActionsUseCase:
    """List one Plan's recorded actions as one keyset page, ordered (sort_order, action_id)."""

    ports: PlanQueryPorts

    def execute(self, request: ListPlanActionsRequest) -> Page[PlanAction]:
        """Return one page of actions for the Plan, optionally filtered by status.

        Raises PlanNotFoundError for an unknown Plan ID before querying actions.
        """
        with self.ports.uow as uow:
            if uow.plans.get(request.plan_id) is None:
                raise PlanNotFoundError(PLAN_NOT_FOUND_MESSAGE)
            return uow.plan_actions.query_page(request.plan_id, status=request.status, page=request.page)
