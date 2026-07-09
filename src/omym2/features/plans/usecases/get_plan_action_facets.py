"""
Summary: Implements PlanAction status/action_type facet counts for one Plan.
Why: Lets Web browsing show status and action-type value/count breakdowns without pagination.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING

from omym2.features.plans.dto import PlanActionFacetsResult
from omym2.features.plans.usecases.get_plan_header import PLAN_NOT_FOUND_MESSAGE, PlanNotFoundError

if TYPE_CHECKING:
    from omym2.features.plans.dto import PlanActionFacetsRequest
    from omym2.features.plans.ports import PlanQueryPorts


@dataclass(frozen=True, slots=True)
class GetPlanActionFacetsUseCase:
    """Return PlanAction status and action_type facet counts for one Plan."""

    ports: PlanQueryPorts

    def execute(self, request: PlanActionFacetsRequest) -> PlanActionFacetsResult:
        """Return status/action_type facets plus the unfiltered action total.

        Raises PlanNotFoundError for an unknown Plan ID before querying facets.
        """
        with self.ports.uow as uow:
            if uow.plans.get(request.plan_id) is None:
                raise PlanNotFoundError(PLAN_NOT_FOUND_MESSAGE)
            status_facets = uow.plan_actions.status_facets(request.plan_id)
            action_type_facets = uow.plan_actions.action_type_facets(request.plan_id)
        return PlanActionFacetsResult(
            status_facets=status_facets,
            action_type_facets=action_type_facets,
            total=sum(facet.count for facet in status_facets),
        )
