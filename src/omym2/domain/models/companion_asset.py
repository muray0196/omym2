"""
Summary: Defines managed companion lyrics and artwork state.
Why: Keeps companion identity stable across reviewed file moves and Undo.
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum
from typing import TYPE_CHECKING

from omym2.shared.paths import normalize_library_relative_path
from omym2.shared.time import as_utc

if TYPE_CHECKING:
    from datetime import datetime

    from omym2.shared.ids import CompanionAssetId, LibraryId, TrackId

NEGATIVE_COMPANION_ASSET_SIZE_MESSAGE = "Companion asset file size must not be negative."


class CompanionAssetKind(StrEnum):
    """Known companion asset kinds."""

    LYRICS = "lyrics"
    ARTWORK = "artwork"


class CompanionAssetStatus(StrEnum):
    """Known managed companion asset states."""

    ACTIVE = "active"
    REMOVED = "removed"


@dataclass(frozen=True, slots=True)
class CompanionAsset:
    """Current managed state of one companion file known to OMYM2."""

    companion_asset_id: CompanionAssetId
    library_id: LibraryId
    kind: CompanionAssetKind
    owner_track_id: TrackId
    current_path: str
    canonical_path: str
    content_hash: str
    size: int | None
    mtime: datetime | None
    status: CompanionAssetStatus
    first_seen_at: datetime
    last_seen_at: datetime
    updated_at: datetime

    def __post_init__(self) -> None:
        """Normalize managed paths and observation timestamps."""
        if self.size is not None and self.size < 0:
            raise ValueError(NEGATIVE_COMPANION_ASSET_SIZE_MESSAGE)
        object.__setattr__(self, "current_path", normalize_library_relative_path(self.current_path))
        object.__setattr__(self, "canonical_path", normalize_library_relative_path(self.canonical_path))
        if self.mtime is not None:
            object.__setattr__(self, "mtime", as_utc(self.mtime))
        object.__setattr__(self, "first_seen_at", as_utc(self.first_seen_at))
        object.__setattr__(self, "last_seen_at", as_utc(self.last_seen_at))
        object.__setattr__(self, "updated_at", as_utc(self.updated_at))
