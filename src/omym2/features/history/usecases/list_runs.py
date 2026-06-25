"""
Summary: Implements Run listing for history views.
Why: Lets CLI and Web inspect apply attempts through one query boundary.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from omym2.domain.models.run import Run
    from omym2.features.history.dto import ListRunsRequest
    from omym2.features.history.ports import HistoryPorts


@dataclass(frozen=True, slots=True)
class ListRunsUseCase:
    """List apply Runs in newest-first order."""

    ports: HistoryPorts

    def execute(self, request: ListRunsRequest) -> tuple[Run, ...]:
        """List Runs for the selected Library scope."""
        with self.ports.uow as uow:
            if request.library_id is not None:
                runs = tuple(uow.runs.list_by_library(request.library_id))
            else:
                runs = tuple(
                    run for library in uow.libraries.list_all() for run in uow.runs.list_by_library(library.library_id)
                )

        return tuple(sorted(runs, key=lambda run: (run.started_at, str(run.run_id)), reverse=True))
