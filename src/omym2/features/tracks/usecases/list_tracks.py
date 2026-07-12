"""
Summary: Implements read-only Track listing and exact group membership browsing.
Why: Lets Web inspection read managed Track state through a usecase boundary.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING

from omym2.features.tracks.usecases.group_tracks import validate_track_group_filter

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
        validate_track_group_filter(request.grouping, request.group_key)
        with self.ports.uow as uow:
            return uow.tracks.query_page(
                request.library_id,
                track_id=request.track_id,
                search=request.search,
                status=request.status,
                grouping=request.grouping,
                group_key=request.group_key,
                page=request.page,
            )
