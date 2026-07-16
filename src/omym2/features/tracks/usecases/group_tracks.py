"""
Summary: Implements persisted Track hierarchy grouping.
Why: Lets read-only browsing traverse artist, album, and disc groups.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING

from omym2.domain.models.track import TrackGrouping

if TYPE_CHECKING:
    from omym2.features.tracks.dto import GroupTracksRequest
    from omym2.features.tracks.ports import TracksPorts
    from omym2.shared.pagination import GroupCount, Page


GROUP_FILTER_PAIRING_MESSAGE = "grouping and group_key must be provided together."
ARTIST_PARENT_KEY_MESSAGE = "artist grouping does not accept parent_key."
ALBUM_PARENT_KEY_MESSAGE = "album grouping requires parent_key."
DISC_PARENT_KEY_MESSAGE = "disc grouping requires parent_key."


def validate_track_group_filter(grouping: TrackGrouping | None, group_key: str | None) -> None:
    """Require the optional Track group membership filter as an exact pair."""
    if (grouping is None) != (group_key is None):
        raise ValueError(GROUP_FILTER_PAIRING_MESSAGE)


def validate_track_group_parent(grouping: TrackGrouping, parent_key: str | None) -> None:
    """Enforce the parent scope required by each Track hierarchy level."""
    if grouping is TrackGrouping.ARTIST:
        if parent_key is not None:
            raise ValueError(ARTIST_PARENT_KEY_MESSAGE)
        return
    if grouping is TrackGrouping.ALBUM:
        if parent_key is None:
            raise ValueError(ALBUM_PARENT_KEY_MESSAGE)
        return
    if parent_key is None:
        raise ValueError(DISC_PARENT_KEY_MESSAGE)


@dataclass(frozen=True, slots=True)
class GroupTracksUseCase:
    """List Track hierarchy groups as one keyset page."""

    ports: TracksPorts

    def execute(self, request: GroupTracksRequest) -> Page[GroupCount]:
        """Return one page of Track groups for the requested grouping and scope."""
        validate_track_group_parent(request.grouping, request.parent_key)
        with self.ports.uow as uow:
            return uow.tracks.group_page(
                request.library_id,
                request.grouping,
                request.parent_key,
                request.page,
                search=request.search,
                status=request.status,
            )
