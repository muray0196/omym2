"""
Summary: Moves files at the filesystem boundary.
Why: Lets apply mutate Library files without embedding I/O in feature code.
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from omym2.features.common_ports import FileSystemPath


@dataclass(frozen=True, slots=True)
class FilesystemFileMover:
    """Move one filesystem file without applying business policy."""

    def move(self, source: FileSystemPath, target: FileSystemPath) -> None:
        """Move source to target while refusing to overwrite an existing path."""
        source_path = Path(source)
        target_path = Path(target)
        if target_path.exists():
            raise FileExistsError(str(target_path))

        target_path.parent.mkdir(parents=True, exist_ok=True)
        _ = source_path.rename(target_path)
