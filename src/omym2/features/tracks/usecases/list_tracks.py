"""
Summary: Implements read-only Track listing.
Why: Lets Web inspection read managed Track state through a usecase boundary.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from omym2.domain.models.track import Track
    from omym2.features.tracks.dto import ListTracksRequest
    from omym2.features.tracks.ports import TracksPorts
    from omym2.shared.pagination import Page


@dataclass(frozen=True, slots=True)
class ListTracksUseCase:
    """List managed Tracks as one keyset page in deterministic display order."""

    ports: TracksPorts

    def execute(self, request: ListTracksRequest) -> Page[Track]:
        """Return one page of Tracks for the requested scope, search, and status filters."""
        with self.ports.uow as uow:
            return uow.tracks.query_page(
                request.library_id,
                search=request.search,
                status=request.status,
                page=request.page,
            )
