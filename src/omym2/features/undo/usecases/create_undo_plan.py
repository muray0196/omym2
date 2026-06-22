"""
Summary: Defines the undo plan creation usecase contract.
Why: Allows undo to reuse Plan apply semantics in a later phase.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from omym2.domain.models.plan import Plan
    from omym2.features.undo.dto import CreateUndoPlanRequest
    from omym2.features.undo.ports import CreateUndoPlanPorts

USECASE_DEFERRED_MESSAGE = "Create undo plan behavior is deferred until the undo vertical slice phase."


@dataclass(frozen=True, slots=True)
class CreateUndoPlanUseCase:
    """Contract for creating undo Plans from Runs."""

    ports: CreateUndoPlanPorts

    def execute(self, request: CreateUndoPlanRequest) -> Plan:
        """Create an undo Plan from succeeded FileEvents in one Run."""
        # Phase 3 fixes the call shape only; Phase 11 owns undo behavior.
        del request
        raise NotImplementedError(USECASE_DEFERRED_MESSAGE)
