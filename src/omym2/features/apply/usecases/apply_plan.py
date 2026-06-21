"""
Summary: Defines the apply usecase contract.
Why: Fixes the boundary for Plan execution before file mutation logic exists.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from omym2.domain.models.run import Run
    from omym2.features.apply.dto import ApplyPlanRequest
    from omym2.features.apply.ports import ApplyPlanPorts

USECASE_DEFERRED_MESSAGE = "Apply plan behavior is deferred until the apply vertical slice phase."


@dataclass(frozen=True, slots=True)
class ApplyPlanUseCase:
    """Contract for applying reviewed Plans."""

    ports: ApplyPlanPorts

    def execute(self, request: ApplyPlanRequest) -> Run | None:
        """Apply a reviewed Plan and return its Run when one is created."""
        # Phase 3 fixes the call shape only; Phase 9 owns file mutation behavior.
        del request
        raise NotImplementedError(USECASE_DEFERRED_MESSAGE)
