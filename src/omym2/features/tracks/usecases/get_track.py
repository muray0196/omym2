"""
Summary: Implements exact persisted Track lookup.
Why: Gives Track detail routes a read-only feature boundary.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from omym2.domain.models.track import Track
    from omym2.features.tracks.dto import GetTrackRequest
    from omym2.features.tracks.ports import TracksPorts

TRACK_NOT_FOUND_MESSAGE = "Track was not found."


@dataclass(frozen=True, slots=True)
class GetTrackUseCase:
    """Load one persisted Track without filesystem access."""

    ports: TracksPorts

    def execute(self, request: GetTrackRequest) -> Track:
        """Return one Track or raise TrackNotFoundError for an unknown ID."""
        with self.ports.uow as uow:
            track = uow.tracks.get(request.track_id)
            if track is None:
                raise TrackNotFoundError(TRACK_NOT_FOUND_MESSAGE)
            return track


class TrackNotFoundError(ValueError):
    """Raised when a requested Track ID is unknown."""
