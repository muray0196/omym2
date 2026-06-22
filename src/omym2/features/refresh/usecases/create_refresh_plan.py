"""
Summary: Defines the refresh plan creation usecase contract.
Why: Allows later refresh planning to share the Plan execution model.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from omym2.domain.models.plan import Plan
    from omym2.features.refresh.dto import CreateRefreshPlanRequest
    from omym2.features.refresh.ports import CreateRefreshPlanPorts

USECASE_DEFERRED_MESSAGE = "Create refresh plan behavior is deferred until the refresh vertical slice phase."


@dataclass(frozen=True, slots=True)
class CreateRefreshPlanUseCase:
    """Contract for creating refresh Plans."""

    ports: CreateRefreshPlanPorts

    def execute(self, request: CreateRefreshPlanRequest) -> Plan:
        """Create a refresh Plan for selected managed Tracks."""
        # Phase 3 fixes the call shape only; Phase 10 owns refresh behavior.
        del request
        raise NotImplementedError(USECASE_DEFERRED_MESSAGE)
