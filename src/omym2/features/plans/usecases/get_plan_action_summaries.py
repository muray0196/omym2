"""
Summary: Implements bulk typed PlanAction summary lookup.
Why: Lets Plan list views expose current review counts without loading actions one by one.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING

from omym2.features.plans.dto import plan_action_summary_from_counts

if TYPE_CHECKING:
    from omym2.features.plans.dto import GetPlanActionSummariesRequest, PlanActionSummary
    from omym2.features.plans.ports import PlanQueryPorts
    from omym2.shared.ids import PlanId


@dataclass(frozen=True, slots=True)
class GetPlanActionSummariesUseCase:
    """Return typed current action summaries for one bounded Plan page."""

    ports: PlanQueryPorts

    def execute(self, request: GetPlanActionSummariesRequest) -> dict[PlanId, PlanActionSummary]:
        """Return one summary per requested Plan ID without loading individual actions."""
        if not request.plan_ids:
            return {}
        with self.ports.uow as uow:
            counts_by_plan = uow.plan_actions.action_counts_by_plan(request.plan_ids)
        return {plan_id: plan_action_summary_from_counts(counts) for plan_id, counts in counts_by_plan.items()}
