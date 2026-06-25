"""
Summary: Implements Run detail retrieval.
Why: Exposes durable FileEvents for diagnostics and future Web history views.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING

from omym2.features.history.dto import RunDetail

if TYPE_CHECKING:
    from omym2.features.history.dto import GetRunDetailRequest
    from omym2.features.history.ports import HistoryPorts

RUN_NOT_FOUND_MESSAGE = "Run was not found."


@dataclass(frozen=True, slots=True)
class GetRunDetailUseCase:
    """Load one Run and its durable FileEvents."""

    ports: HistoryPorts

    def execute(self, request: GetRunDetailRequest) -> RunDetail:
        """Return a Run and its durable file events."""
        with self.ports.uow as uow:
            run = uow.runs.get(request.run_id)
            if run is None:
                raise RunNotFoundError(RUN_NOT_FOUND_MESSAGE)
            file_events = tuple(uow.file_events.list_by_run(request.run_id))

        return RunDetail(run=run, file_events=file_events)


class RunNotFoundError(ValueError):
    """Raised when requested Run history does not exist."""
