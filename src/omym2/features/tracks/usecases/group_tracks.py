"""
Summary: Implements Track group-by listing.
Why: Lets Web browsing show grouped Track counts (e.g. artist/album) with pagination.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from omym2.features.tracks.dto import GroupTracksRequest
    from omym2.features.tracks.ports import TracksPorts
    from omym2.shared.pagination import GroupCount, Page


@dataclass(frozen=True, slots=True)
class GroupTracksUseCase:
    """List Track groups as one keyset page, ordered count DESC then key ASC."""

    ports: TracksPorts

    def execute(self, request: GroupTracksRequest) -> Page[GroupCount]:
        """Return one page of Track groups for the requested grouping and scope."""
        with self.ports.uow as uow:
            return uow.tracks.group_page(request.library_id, request.grouping, request.page)
