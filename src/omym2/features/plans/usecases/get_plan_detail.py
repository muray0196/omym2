"""
Summary: Implements reviewed Plan detail lookup.
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
    """Load one Plan and its recorded actions."""

    ports: PlanQueryPorts

    def execute(self, request: GetPlanDetailRequest) -> PlanDetail:
        """Return one Plan with actions in review order."""
        with self.ports.uow as uow:
            plan = uow.plans.get(request.plan_id)
            if plan is None:
                raise PlanNotFoundError(PLAN_NOT_FOUND_MESSAGE)
            actions = tuple(uow.plan_actions.list_by_plan(request.plan_id))
            return PlanDetail(plan=plan, actions=actions)


class PlanNotFoundError(ValueError):
    """Raised when a requested Plan ID is unknown."""
