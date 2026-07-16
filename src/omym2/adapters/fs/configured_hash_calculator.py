"""
Summary: Calculates file hashes with the latest persisted chunk-size control.
Why: Lets eagerly composed read-only commands honor settings without eager Config I/O.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING

from omym2.adapters.fs.hash_calculator import FileContentHasher

if TYPE_CHECKING:
    from omym2.features.common_ports import ConfigReader, FileSystemPath


@dataclass(frozen=True, slots=True)
class ConfiguredFileContentHasher:
    """Load the current operational hash control for each standalone capture."""

    config_reader: ConfigReader

    @property
    def chunk_size_bytes(self) -> int:
        """Return the current persisted streaming chunk size."""
        return self.config_reader.load().hashing.read_chunk_size_bytes

    def calculate(self, path: FileSystemPath) -> str:
        """Hash one file with the chunk size from the current persisted Config."""
        return FileContentHasher(self.chunk_size_bytes).calculate(path)
