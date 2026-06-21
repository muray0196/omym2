"""
Summary: Defines the organize plan creation usecase contract.
Why: Allows tests and adapters to depend on the Phase 3 boundary.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from omym2.domain.models.plan import Plan
    from omym2.features.organize.dto import CreateOrganizePlanRequest
    from omym2.features.organize.ports import CreateOrganizePlanPorts

USECASE_DEFERRED_MESSAGE = "Create organize plan behavior is deferred until the organize vertical slice phase."


@dataclass(frozen=True, slots=True)
class CreateOrganizePlanUseCase:
    """Contract for creating organize Plans."""

    ports: CreateOrganizePlanPorts

    def execute(self, request: CreateOrganizePlanRequest) -> Plan | None:
        """Create an organize Plan, or register a clean Library without a Plan."""
        # Phase 3 fixes the call shape only; Phase 7 owns organize behavior.
        del request
        raise NotImplementedError(USECASE_DEFERRED_MESSAGE)
