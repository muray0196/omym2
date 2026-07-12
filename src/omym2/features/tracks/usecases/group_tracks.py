"""
Summary: Implements Track hierarchy grouping and key derivation.
Why: Lets read-only browsing traverse persisted artist, album, disc, and legacy groups.
"""

from __future__ import annotations

from dataclasses import dataclass
from json import dumps
from typing import TYPE_CHECKING

from omym2.domain.models.track import (
    TRACK_GROUP_ARTIST_ALBUM_SEPARATOR,
    TRACK_GROUP_DISC_LABEL_PREFIX,
    TRACK_GROUP_LABEL_SEPARATOR,
    TRACK_GROUP_METADATA_WHITESPACE,
    TRACK_GROUP_UNKNOWN_KEY,
    TRACK_GROUP_UNNUMBERED_DISC_LABEL,
    TrackGrouping,
)

if TYPE_CHECKING:
    from omym2.domain.models.track import Track
    from omym2.domain.models.track_metadata import TrackMetadata
    from omym2.features.tracks.dto import GroupTracksRequest
    from omym2.features.tracks.ports import TracksPorts
    from omym2.shared.pagination import GroupCount, Page


GROUP_FILTER_PAIRING_MESSAGE = "grouping and group_key must be provided together."
ARTIST_PARENT_KEY_MESSAGE = "artist grouping does not accept parent_key."
ALBUM_PARENT_KEY_MESSAGE = "album grouping requires parent_key."
DISC_PARENT_KEY_MESSAGE = "disc grouping requires parent_key."
ARTIST_ALBUM_PARENT_KEY_MESSAGE = "artist_album grouping does not accept parent_key."


@dataclass(frozen=True, slots=True)
class TrackGroupKey:
    """One server-defined Track grouping key and its display label."""

    key: str
    label: str


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
    if grouping is TrackGrouping.DISC:
        if parent_key is None:
            raise ValueError(DISC_PARENT_KEY_MESSAGE)
        return
    if parent_key is not None:
        raise ValueError(ARTIST_ALBUM_PARENT_KEY_MESSAGE)


def derive_track_group_key(track: Track, grouping: TrackGrouping) -> TrackGroupKey:
    """Return one Track's exact server-defined group key and display label.

    Hierarchy values use persisted metadata only. The legacy artist_album
    grouping intentionally retains its null-only fallback behavior so its
    existing key contract does not change.
    """
    metadata = track.metadata
    if grouping is TrackGrouping.ARTIST_ALBUM:
        return _legacy_artist_album_group(metadata)

    artist = _hierarchy_artist(metadata)
    album = _hierarchy_album(metadata)
    if grouping is TrackGrouping.ARTIST:
        return TrackGroupKey(key=_json_key(artist), label=artist)

    year = metadata.year
    if grouping is TrackGrouping.ALBUM:
        label = album
        if year is not None:
            label = f"{label}{TRACK_GROUP_LABEL_SEPARATOR}{year}"
        return TrackGroupKey(key=_json_key(artist, album, year), label=label)

    disc_key = _hierarchy_disc_key(metadata)
    label = (
        TRACK_GROUP_UNNUMBERED_DISC_LABEL
        if disc_key == TRACK_GROUP_UNKNOWN_KEY
        else f"{TRACK_GROUP_DISC_LABEL_PREFIX}{disc_key}"
    )
    return TrackGroupKey(key=_json_key(artist, album, year, disc_key), label=label)


def track_group_member_sort_key(track: Track) -> tuple[int, int, str, str]:
    """Return the deterministic music-friendly order used inside one Track group."""
    track_number = track.metadata.track_number
    title = track.metadata.title or ""
    if track_number is not None and track_number > 0:
        return (0, track_number, title, str(track.track_id))
    return (1, 0, title, str(track.track_id))


def _legacy_artist_album_group(metadata: TrackMetadata) -> TrackGroupKey:
    """Return the existing null-only artist/album group without changing its wire key."""
    artist = metadata.album_artist if metadata.album_artist is not None else metadata.artist
    group_artist = TRACK_GROUP_UNKNOWN_KEY if artist is None else artist
    group_album = TRACK_GROUP_UNKNOWN_KEY if metadata.album is None else metadata.album
    return TrackGroupKey(
        key=f"{group_artist}{TRACK_GROUP_ARTIST_ALBUM_SEPARATOR}{group_album}",
        label=f"{group_artist}{TRACK_GROUP_LABEL_SEPARATOR}{group_album}",
    )


def _hierarchy_artist(metadata: TrackMetadata) -> str:
    """Return the non-blank album artist, performer fallback, or unknown marker."""
    for candidate in (metadata.album_artist, metadata.artist):
        if candidate is not None and candidate.strip(TRACK_GROUP_METADATA_WHITESPACE) != "":
            return candidate
    return TRACK_GROUP_UNKNOWN_KEY


def _hierarchy_album(metadata: TrackMetadata) -> str:
    """Return the non-blank album or the unknown marker."""
    if metadata.album is None or metadata.album.strip(TRACK_GROUP_METADATA_WHITESPACE) == "":
        return TRACK_GROUP_UNKNOWN_KEY
    return metadata.album


def _hierarchy_disc_key(metadata: TrackMetadata) -> int | str:
    """Return a positive raw disc number or the unnumbered-disc marker."""
    disc_number = metadata.disc_number
    if disc_number is not None and disc_number > 0:
        return disc_number
    return TRACK_GROUP_UNKNOWN_KEY


def _json_key(*values: int | str | None) -> str:
    """Encode an opaque JSON-array Track hierarchy key matching SQLite json_array."""
    return dumps(values, ensure_ascii=False, separators=(",", ":"))


@dataclass(frozen=True, slots=True)
class GroupTracksUseCase:
    """List Track groups as one keyset page, ordered count DESC then key ASC."""

    ports: TracksPorts

    def execute(self, request: GroupTracksRequest) -> Page[GroupCount]:
        """Return one page of Track groups for the requested grouping and scope."""
        validate_track_group_parent(request.grouping, request.parent_key)
        with self.ports.uow as uow:
            return uow.tracks.group_page(request.library_id, request.grouping, request.parent_key, request.page)
