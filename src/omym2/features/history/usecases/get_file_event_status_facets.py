"""
Summary: Implements FileEvent status facet counts.
Why: Lets Run detail browsing show FileEvent status breakdowns without loading every event.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING

from omym2.features.history.dto import FileEventStatusFacetsResult
from omym2.features.history.usecases.get_run_header import RUN_NOT_FOUND_MESSAGE, RunNotFoundError

if TYPE_CHECKING:
    from omym2.features.history.dto import FileEventStatusFacetsRequest
    from omym2.features.history.ports import HistoryPorts


@dataclass(frozen=True, slots=True)
class GetFileEventStatusFacetsUseCase:
    """Return FileEvent status facet counts for one Run."""

    ports: HistoryPorts

    def execute(self, request: FileEventStatusFacetsRequest) -> FileEventStatusFacetsResult:
        """Return status facets plus the total FileEvent count for the Run.

        Raises RunNotFoundError for an unknown Run ID before querying events.
        """
        with self.ports.uow as uow:
            if uow.runs.get(request.run_id) is None:
                raise RunNotFoundError(RUN_NOT_FOUND_MESSAGE)
            facets = uow.file_events.status_facets(request.run_id)
        return FileEventStatusFacetsResult(facets=facets, total=sum(facet.count for facet in facets))
