"""
Summary: Defines metadata-rich and content-only observed file state.
Why: Captures safe hash and identity evidence without making it Track identity.
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
class FilesystemIdentity:
    """Ephemeral operating-system identity for one observed filesystem entry."""

    device_id: int
    inode: int
    size: int
    mtime_ns: int
    ctime_ns: int


@dataclass(frozen=True, slots=True)
class FileContentSnapshot:
    """Metadata-free observed state for one regular file."""

    path: str
    size: int
    mtime: datetime
    content_hash: str
    filesystem_identity: FilesystemIdentity
    captured_at: datetime

    def __post_init__(self) -> None:
        """Validate the file size and normalize observation timestamps."""
        if self.size < 0:
            raise ValueError(NEGATIVE_FILE_SIZE_MESSAGE)
        object.__setattr__(self, "mtime", as_utc(self.mtime))
        object.__setattr__(self, "captured_at", as_utc(self.captured_at))


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
    filesystem_identity: FilesystemIdentity | None
    captured_at: datetime

    def __post_init__(self) -> None:
        """Validate observation timestamps and size."""
        if self.size < 0:
            raise ValueError(NEGATIVE_FILE_SIZE_MESSAGE)
        object.__setattr__(self, "mtime", as_utc(self.mtime))
        object.__setattr__(self, "captured_at", as_utc(self.captured_at))
