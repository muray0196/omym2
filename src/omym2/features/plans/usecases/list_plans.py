"""
Summary: Implements reviewed Plan listing.
Why: Lets users inspect created Plans before apply exists.
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
    """List reviewed Plan headers."""

    ports: PlanQueryPorts

    def execute(self, request: ListPlansRequest) -> tuple[Plan, ...]:
        """Return Plans in repository order for the selected scope."""
        with self.ports.uow as uow:
            if request.library_id is not None:
                return tuple(uow.plans.list_by_library(request.library_id))

            plans: list[Plan] = []
            for library in uow.libraries.list_all():
                plans.extend(uow.plans.list_by_library(library.library_id))
            return tuple(sorted(plans, key=lambda plan: (plan.created_at, str(plan.plan_id))))
