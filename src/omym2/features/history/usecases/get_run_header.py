"""
Summary: Implements Run header lookup.
Why: Lets Web and CLI inspection load a Run header without its durable FileEvents.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from omym2.domain.models.run import Run
    from omym2.features.history.dto import GetRunHeaderRequest
    from omym2.features.history.ports import HistoryPorts

RUN_NOT_FOUND_MESSAGE = "Run was not found."


@dataclass(frozen=True, slots=True)
class GetRunHeaderUseCase:
    """Load one Run header by ID, without its durable FileEvents."""

    ports: HistoryPorts

    def execute(self, request: GetRunHeaderRequest) -> Run:
        """Return one Run header. Raises RunNotFoundError for an unknown Run ID."""
        with self.ports.uow as uow:
            run = uow.runs.get(request.run_id)
            if run is None:
                raise RunNotFoundError(RUN_NOT_FOUND_MESSAGE)
            return run


class RunNotFoundError(ValueError):
    """Raised when a requested Run ID is unknown."""
