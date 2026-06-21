"""
Summary: Defines the Run detail usecase contract.
Why: Gives history screens a stable Run and FileEvent query shape.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from omym2.features.history.dto import GetRunDetailRequest, RunDetail
    from omym2.features.history.ports import HistoryPorts

USECASE_DEFERRED_MESSAGE = "Get run detail behavior is deferred until the history vertical slice phase."


@dataclass(frozen=True, slots=True)
class GetRunDetailUseCase:
    """Contract for loading Run detail."""

    ports: HistoryPorts

    def execute(self, request: GetRunDetailRequest) -> RunDetail:
        """Return a Run and its durable file events."""
        # Phase 3 fixes the call shape only; Phase 11 owns history behavior.
        del request
        raise NotImplementedError(USECASE_DEFERRED_MESSAGE)
