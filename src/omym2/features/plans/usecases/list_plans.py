"""
Summary: Implements reviewed Plan listing with filter, sort, and limit.
Why: Lets users inspect and narrow down created Plans before apply exists.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from omym2.domain.models.plan import Plan
    from omym2.features.plans.dto import ListPlansRequest
    from omym2.features.plans.ports import PlanQueryPorts


@dataclass(frozen=True, slots=True)
class ListPlansUseCase:
    """List reviewed Plan headers, optionally filtered and limited."""

    ports: PlanQueryPorts

    def execute(self, request: ListPlansRequest) -> tuple[Plan, ...]:
        """Return Plans for the selected scope: filter, then sort newest-first, then limit.

        Fetch is per-Library when request.library_id is set, otherwise
        concatenated across all known Libraries. The pipeline order is
        strict: filter by status/plan_type, sort by (created_at,
        plan_id) descending, then apply limit last.
        """
        with self.ports.uow as uow:
            if request.library_id is not None:
                plans: list[Plan] = list(uow.plans.list_by_library(request.library_id))
            else:
                plans = []
                for library in uow.libraries.list_all():
                    plans.extend(uow.plans.list_by_library(library.library_id))

            if request.status is not None:
                plans = [plan for plan in plans if plan.status == request.status]
            if request.plan_type is not None:
                plans = [plan for plan in plans if plan.plan_type == request.plan_type]

            plans.sort(key=lambda plan: (plan.created_at, str(plan.plan_id)), reverse=True)

            if request.limit is not None:
                plans = plans[: request.limit]

            return tuple(plans)
