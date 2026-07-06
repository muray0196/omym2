"""
Summary: Implements reviewed Plan detail lookup with optional action filtering.
Why: Shows the exact recorded PlanActions that apply will later use.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING

from omym2.features.plans.dto import PlanDetail

if TYPE_CHECKING:
    from omym2.features.plans.dto import GetPlanDetailRequest
    from omym2.features.plans.ports import PlanQueryPorts

PLAN_NOT_FOUND_MESSAGE = "Plan was not found."


@dataclass(frozen=True, slots=True)
class GetPlanDetailUseCase:
    """Load one Plan and its recorded actions, optionally filtered by status."""

    ports: PlanQueryPorts

    def execute(self, request: GetPlanDetailRequest) -> PlanDetail:
        """Return one Plan with actions in review order.

        Raises PlanNotFoundError before touching actions. total_action_count
        is computed from the full unfiltered action set before
        request.action_status filtering is applied, if any.
        """
        with self.ports.uow as uow:
            plan = uow.plans.get(request.plan_id)
            if plan is None:
                raise PlanNotFoundError(PLAN_NOT_FOUND_MESSAGE)
            actions = tuple(uow.plan_actions.list_by_plan(request.plan_id))
            total_action_count = len(actions)
            if request.action_status is not None:
                actions = tuple(action for action in actions if action.status == request.action_status)
            return PlanDetail(plan=plan, actions=actions, total_action_count=total_action_count)


class PlanNotFoundError(ValueError):
    """Raised when a requested Plan ID is unknown."""
