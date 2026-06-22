"""
Summary: Calculates content hashes from filesystem files.
Why: Lets adapters stream bytes while preserving the configured hash policy.
"""

from __future__ import annotations

from dataclasses import dataclass
from hashlib import new
from pathlib import Path
from typing import TYPE_CHECKING

from omym2.config import CONTENT_FINGERPRINT_ALGORITHM, CONTENT_HASH_READ_CHUNK_SIZE_BYTES

if TYPE_CHECKING:
    from omym2.features.common_ports import FileSystemPath

INVALID_CHUNK_SIZE_MESSAGE = "Content hash chunk size must be positive."


@dataclass(frozen=True, slots=True)
class FileContentHasher:
    """Calculate configured content fingerprints for files."""

    chunk_size_bytes: int = CONTENT_HASH_READ_CHUNK_SIZE_BYTES

    def __post_init__(self) -> None:
        """Validate the read chunk size before file I/O starts."""
        if self.chunk_size_bytes <= 0:
            raise ValueError(INVALID_CHUNK_SIZE_MESSAGE)

    def calculate(self, path: FileSystemPath) -> str:
        """Return the configured content hash for one file."""
        digest = new(CONTENT_FINGERPRINT_ALGORITHM)
        with Path(path).open("rb") as file:
            while chunk := file.read(self.chunk_size_bytes):
                digest.update(chunk)
        return digest.hexdigest()
