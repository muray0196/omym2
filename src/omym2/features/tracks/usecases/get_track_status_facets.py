"""
Summary: Implements Track status facet counts.
Why: Lets Web browsing show status value/count breakdowns without pagination.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING

from omym2.features.tracks.dto import TrackStatusFacetsResult

if TYPE_CHECKING:
    from omym2.features.tracks.dto import TrackStatusFacetsRequest
    from omym2.features.tracks.ports import TracksPorts


@dataclass(frozen=True, slots=True)
class GetTrackStatusFacetsUseCase:
    """Return Track status facet counts for the requested Library scope."""

    ports: TracksPorts

    def execute(self, request: TrackStatusFacetsRequest) -> TrackStatusFacetsResult:
        """Return status facets plus the total Track count in scope.

        `total` is the sum of facet counts: every Track has exactly one
        status, so the facet breakdown always partitions the full scope.
        """
        with self.ports.uow as uow:
            facets = uow.tracks.status_facets(request.library_id, search=request.search)
        return TrackStatusFacetsResult(facets=facets, total=sum(facet.count for facet in facets))
