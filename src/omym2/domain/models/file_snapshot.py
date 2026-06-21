"""
Summary: Defines complete observed file state.
Why: Captures metadata and hashes without making them track identity.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING

from omym2.shared.time import as_utc

if TYPE_CHECKING:
    from datetime import datetime

    from omym2.domain.models.track_metadata import TrackMetadata

NEGATIVE_FILE_SIZE_MESSAGE = "File size must not be negative."


@dataclass(frozen=True, slots=True)
class FileSnapshot:
    """Complete observed state of one file at a point in time."""

    path: str
    size: int
    mtime: datetime
    file_extension: str
    content_hash: str
    metadata_hash: str
    metadata: TrackMetadata
    captured_at: datetime

    def __post_init__(self) -> None:
        """Validate observation timestamps and size."""
        if self.size < 0:
            raise ValueError(NEGATIVE_FILE_SIZE_MESSAGE)
        object.__setattr__(self, "mtime", as_utc(self.mtime))
        object.__setattr__(self, "captured_at", as_utc(self.captured_at))
