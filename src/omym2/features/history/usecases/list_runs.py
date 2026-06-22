"""
Summary: Defines the Run listing usecase contract.
Why: Allows CLI and Web history views to share the same query boundary.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from omym2.domain.models.run import Run
    from omym2.features.history.dto import ListRunsRequest
    from omym2.features.history.ports import HistoryPorts

USECASE_DEFERRED_MESSAGE = "List runs behavior is deferred until the history vertical slice phase."


@dataclass(frozen=True, slots=True)
class ListRunsUseCase:
    """Contract for listing apply Runs."""

    ports: HistoryPorts

    def execute(self, request: ListRunsRequest) -> tuple[Run, ...]:
        """List Runs for the selected Library scope."""
        # Phase 3 fixes the call shape only; Phase 11 owns history behavior.
        del request
        raise NotImplementedError(USECASE_DEFERRED_MESSAGE)
