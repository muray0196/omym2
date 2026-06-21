"""
Summary: Defines the add plan creation usecase contract.
Why: Allows tests and adapters to depend on the Phase 3 boundary.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from omym2.domain.models.plan import Plan
    from omym2.features.add.dto import CreateAddPlanRequest
    from omym2.features.add.ports import CreateAddPlanPorts

USECASE_DEFERRED_MESSAGE = "Create add plan behavior is deferred until the add vertical slice phase."


@dataclass(frozen=True, slots=True)
class CreateAddPlanUseCase:
    """Contract for creating add Plans."""

    ports: CreateAddPlanPorts

    def execute(self, request: CreateAddPlanRequest) -> Plan:
        """Create an add Plan from Incoming or an explicit source."""
        # Phase 3 fixes the call shape only; Phase 8 owns add planning behavior.
        del request
        raise NotImplementedError(USECASE_DEFERRED_MESSAGE)
