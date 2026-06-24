"""
Summary: Checks filesystem path presence without reading file contents.
Why: Lets planning block occupied targets without metadata or hash I/O.
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from omym2.features.common_ports import FileSystemPath


@dataclass(frozen=True, slots=True)
class FilesystemFilePresence:
    """Check whether a filesystem path currently exists."""

    def exists(self, path: FileSystemPath) -> bool:
        """Return whether a file or directory exists at path."""
        return Path(path).exists()
