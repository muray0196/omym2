"""
Summary: Defines managed Track state and browse grouping keys.
Why: Keeps Track identity stable while giving inspection a shared hierarchy vocabulary.
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum
from typing import TYPE_CHECKING

from omym2.shared.paths import normalize_library_relative_path
from omym2.shared.time import as_utc

if TYPE_CHECKING:
    from datetime import datetime

    from omym2.domain.models.track_metadata import TrackMetadata
    from omym2.shared.ids import LibraryId, TrackId


class TrackStatus(StrEnum):
    """Known managed Track states."""

    ACTIVE = "active"
    REMOVED = "removed"


class TrackGrouping(StrEnum):
    """Known Track group-by query groupings."""

    ARTIST = "artist"
    ALBUM = "album"
    DISC = "disc"


TRACK_GROUP_UNKNOWN_KEY = "(unknown)"
TRACK_GROUP_LABEL_SEPARATOR = " — "
TRACK_GROUP_DISC_LABEL_PREFIX = "Disc "
TRACK_GROUP_UNNUMBERED_DISC_LABEL = "Unnumbered disc"
TRACK_GROUP_METADATA_WHITESPACE = " \t\r\n\v\f"  # shared ASCII blank characters for hierarchy metadata values
NEGATIVE_TRACK_SIZE_MESSAGE = "Track file size must not be negative."


@dataclass(frozen=True, slots=True)
class Track:
    """Current managed state of one music file known to OMYM2."""

    track_id: TrackId
    library_id: LibraryId
    current_path: str
    canonical_path: str
    content_hash: str
    metadata_hash: str
    size: int | None
    mtime: datetime | None
    metadata: TrackMetadata
    status: TrackStatus
    first_seen_at: datetime
    last_seen_at: datetime
    updated_at: datetime

    def __post_init__(self) -> None:
        """Normalize stored Library paths and timestamps."""
        if self.size is not None and self.size < 0:
            raise ValueError(NEGATIVE_TRACK_SIZE_MESSAGE)
        object.__setattr__(self, "current_path", normalize_library_relative_path(self.current_path))
        object.__setattr__(self, "canonical_path", normalize_library_relative_path(self.canonical_path))
        if self.mtime is not None:
            object.__setattr__(self, "mtime", as_utc(self.mtime))
        object.__setattr__(self, "first_seen_at", as_utc(self.first_seen_at))
        object.__setattr__(self, "last_seen_at", as_utc(self.last_seen_at))
        object.__setattr__(self, "updated_at", as_utc(self.updated_at))
