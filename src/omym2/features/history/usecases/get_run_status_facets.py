"""
Summary: Implements Run status facet counts.
Why: Lets Web browsing show status value/count breakdowns without pagination.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING

from omym2.features.history.dto import RunStatusFacetsResult

if TYPE_CHECKING:
    from omym2.features.history.dto import RunStatusFacetsRequest
    from omym2.features.history.ports import HistoryPorts


@dataclass(frozen=True, slots=True)
class GetRunStatusFacetsUseCase:
    """Return Run status facet counts for the requested Library scope."""

    ports: HistoryPorts

    def execute(self, request: RunStatusFacetsRequest) -> RunStatusFacetsResult:
        """Return status facets plus the total Run count in scope.

        `total` is the sum of facet counts: every Run has exactly one
        status, so the facet breakdown always partitions the full scope.
        """
        with self.ports.uow as uow:
            facets = uow.runs.status_facets(request.library_id)
        return RunStatusFacetsResult(facets=facets, total=sum(facet.count for facet in facets))
