"""
Summary: Implements reviewed Plan header lookup.
Why: Lets Web and CLI inspection load a Plan's header without its recorded actions.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from omym2.domain.models.plan import Plan
    from omym2.features.plans.dto import GetPlanHeaderRequest
    from omym2.features.plans.ports import PlanQueryPorts

PLAN_NOT_FOUND_MESSAGE = "Plan was not found."


@dataclass(frozen=True, slots=True)
class GetPlanHeaderUseCase:
    """Load one Plan header by ID, without its recorded actions."""

    ports: PlanQueryPorts

    def execute(self, request: GetPlanHeaderRequest) -> Plan:
        """Return one Plan header. Raises PlanNotFoundError for an unknown Plan ID."""
        with self.ports.uow as uow:
            plan = uow.plans.get(request.plan_id)
            if plan is None:
                raise PlanNotFoundError(PLAN_NOT_FOUND_MESSAGE)
            return plan


class PlanNotFoundError(ValueError):
    """Raised when a requested Plan ID is unknown."""
