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


@dataclass(frozen=True, slots=True)
class ListTracksUseCase:
    """List managed Tracks in deterministic display order."""

    ports: TracksPorts

    def execute(self, request: ListTracksRequest) -> tuple[Track, ...]:
        """Return Tracks for the requested Library scope."""
        with self.ports.uow as uow:
            if request.library_id is not None:
                tracks = tuple(uow.tracks.list_by_library(request.library_id))
            else:
                tracks = tuple(
                    track
                    for library in uow.libraries.list_all()
                    for track in uow.tracks.list_by_library(library.library_id)
                )

        return tuple(sorted(tracks, key=lambda track: (str(track.library_id), track.current_path, str(track.track_id))))
