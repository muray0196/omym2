"""
Summary: Cancels one ready Plan through a compare-and-set transition.
Why: Makes Apply-versus-Cancel races single-winner without creating an Operation.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING

from omym2.domain.models.plan import PlanStatus
from omym2.features.plans.usecases.get_plan_header import PLAN_NOT_FOUND_MESSAGE, PlanNotFoundError

if TYPE_CHECKING:
    from omym2.domain.models.plan import Plan
    from omym2.features.plans.dto import CancelPlanRequest
    from omym2.features.plans.ports import PlanQueryPorts

PLAN_NOT_READY_MESSAGE = "Plan is not ready and cannot be cancelled."


@dataclass(frozen=True, slots=True)
class CancelPlanUseCase:
    """Persist the sole ready-to-cancelled Plan transition."""

    ports: PlanQueryPorts

    def execute(self, request: CancelPlanRequest) -> Plan:
        """Return the cancelled Plan or reject a stale/non-ready request."""
        with self.ports.uow as uow:
            plan = uow.plans.get(request.plan_id)
            if plan is None:
                raise PlanNotFoundError(PLAN_NOT_FOUND_MESSAGE)
            if not uow.plans.compare_and_set_status(
                plan.plan_id,
                PlanStatus.READY,
                PlanStatus.CANCELLED,
            ):
                raise PlanCannotBeCancelledError(PLAN_NOT_READY_MESSAGE)
            cancelled = plan.mark_cancelled()
            uow.commit()
            return cancelled


class PlanCannotBeCancelledError(ValueError):
    """Raised when cancellation loses the ready-Plan compare-and-set."""
