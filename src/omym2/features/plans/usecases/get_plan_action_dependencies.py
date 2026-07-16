"""
Summary: Reads durable dependency IDs for reviewed PlanActions.
Why: Lets inspection surfaces expose execution ordering without deriving it.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from omym2.features.plans.dto import GetPlanActionDependenciesRequest
    from omym2.features.plans.ports import PlanQueryPorts
    from omym2.shared.ids import ActionId


@dataclass(frozen=True, slots=True)
class GetPlanActionDependenciesUseCase:
    """Read recorded action dependency IDs in stable repository order."""

    ports: PlanQueryPorts

    def execute(
        self,
        request: GetPlanActionDependenciesRequest,
    ) -> dict[ActionId, tuple[ActionId, ...]]:
        """Return every requested action's durable dependency IDs."""
        if not request.action_ids:
            return {}
        with self.ports.uow as uow:
            return {
                action_id: tuple(
                    dependency.depends_on_action_id
                    for dependency in uow.plan_action_dependencies.list_by_action(action_id)
                )
                for action_id in request.action_ids
            }
