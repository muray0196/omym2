"""
Summary: Checks filesystem path presence without reading file contents.
Why: Lets planning block every occupied target, including broken symlinks, without content I/O.
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
        """Return whether a filesystem directory entry exists at path."""
        try:
            _ = Path(path).lstat()
        except FileNotFoundError:
            return False
        except OSError:
            return True
        return True
