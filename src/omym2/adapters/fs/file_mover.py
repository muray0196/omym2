"""
Summary: Moves files at the filesystem boundary.
Why: Lets apply mutate Library files without embedding I/O in feature code.
"""

from __future__ import annotations

import errno
import os
from dataclasses import dataclass
from pathlib import Path
from shutil import copy2
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from omym2.features.common_ports import FileSystemPath

SYMLINK_PARENT_MESSAGE = "Refusing to move through symlinked target parent"


@dataclass(frozen=True, slots=True)
class FilesystemFileMover:
    """Move one filesystem file without applying business policy."""

    def move(self, source: FileSystemPath, target: FileSystemPath) -> None:
        """Move source to target while refusing to overwrite an existing path."""
        source_path = Path(source)
        target_path = Path(target)
        target_path.parent.mkdir(parents=True, exist_ok=True)
        _ensure_no_symlink_parent(target_path)

        try:
            os.link(source_path, target_path)
        except OSError as exc:
            if exc.errno == errno.EXDEV:
                _copy_cross_device_without_overwrite(source_path, target_path)
            else:
                raise
        source_path.unlink()


def _ensure_no_symlink_parent(target_path: Path) -> None:
    """Reject target parents that would redirect the reviewed destination."""
    for parent in (target_path.parent, *target_path.parent.parents):
        if parent.is_symlink():
            message = f"{SYMLINK_PARENT_MESSAGE}: {parent}"
            raise OSError(message)


def _copy_cross_device_without_overwrite(source_path: Path, target_path: Path) -> None:
    """Copy across devices while keeping final target creation atomic."""
    temp_path = target_path.with_name(f".{target_path.name}.omym2-tmp-{os.getpid()}")
    try:
        _ = copy2(source_path, temp_path)
        os.link(temp_path, target_path)
    finally:
        temp_path.unlink(missing_ok=True)
