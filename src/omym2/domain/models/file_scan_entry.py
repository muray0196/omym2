"""
Summary: Defines cheap filesystem scan results.
Why: Keeps discovery data separate from metadata and hash snapshots.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING

from omym2.shared.time import as_utc

if TYPE_CHECKING:
    from datetime import datetime

NEGATIVE_FILE_SIZE_MESSAGE = "File size must not be negative."


@dataclass(frozen=True, slots=True)
class FileScanEntry:
    """Cheap filesystem discovery result for one candidate file."""

    path: str
    size: int
    mtime: datetime
    file_extension: str

    def __post_init__(self) -> None:
        """Validate observation fields without reading the file again."""
        if self.size < 0:
            raise ValueError(NEGATIVE_FILE_SIZE_MESSAGE)
        object.__setattr__(self, "mtime", as_utc(self.mtime))
