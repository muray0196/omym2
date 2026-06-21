"""
Summary: Defines current managed track state.
Why: Keeps Track identity stable independent of paths and hashes.
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


@dataclass(frozen=True, slots=True)
class Track:
    """Current managed state of one music file known to OMYM2."""

    track_id: TrackId
    library_id: LibraryId
    current_path: str
    canonical_path: str
    content_hash: str
    metadata_hash: str
    metadata: TrackMetadata
    status: TrackStatus
    first_seen_at: datetime
    last_seen_at: datetime
    updated_at: datetime

    def __post_init__(self) -> None:
        """Normalize stored Library paths and timestamps."""
        object.__setattr__(self, "current_path", normalize_library_relative_path(self.current_path))
        object.__setattr__(self, "canonical_path", normalize_library_relative_path(self.canonical_path))
        object.__setattr__(self, "first_seen_at", as_utc(self.first_seen_at))
        object.__setattr__(self, "last_seen_at", as_utc(self.last_seen_at))
        object.__setattr__(self, "updated_at", as_utc(self.updated_at))

    def with_paths(self, current_path: str, canonical_path: str, updated_at: datetime) -> Track:
        """Return updated path state without changing Track identity."""
        return Track(
            track_id=self.track_id,
            library_id=self.library_id,
            current_path=current_path,
            canonical_path=canonical_path,
            content_hash=self.content_hash,
            metadata_hash=self.metadata_hash,
            metadata=self.metadata,
            status=self.status,
            first_seen_at=self.first_seen_at,
            last_seen_at=self.last_seen_at,
            updated_at=updated_at,
        )
