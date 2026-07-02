"""
Summary: Moves files at the filesystem boundary.
Why: Lets apply mutate Library files without embedding I/O in feature code.
"""

from __future__ import annotations

import os
import shutil
from dataclasses import dataclass
from pathlib import Path
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from omym2.features.common_ports import FileSystemPath


@dataclass(frozen=True, slots=True)
class FilesystemFileMover:
    """Move one filesystem file without applying business policy."""

    def move(self, source: FileSystemPath, target: FileSystemPath) -> None:
        """Move source to target while atomically refusing to overwrite an existing path.

        A plain exists()-then-move sequence leaves a race window in which a target
        created between the check and the move gets silently replaced by
        os.rename on same-filesystem moves. Claiming the target path atomically
        (hardlink, or an exclusive create for cross-device moves and filesystems
        that refuse hardlinks) closes that window: an existing or concurrently
        created target always raises FileExistsError instead of being overwritten.
        """
        source_path = Path(source)
        target_path = Path(target)
        target_path.parent.mkdir(parents=True, exist_ok=True)

        try:
            os.link(source_path, target_path)
        except FileExistsError, FileNotFoundError:
            # Preserve the TARGET_EXISTS and SOURCE_MISSING failure contracts.
            raise
        except OSError:
            # The hardlink claim can fail for reasons other than an occupied
            # target: cross-device moves (EXDEV) and filesystems that refuse
            # hardlinks (EPERM, ENOTSUP, ...). Claiming the target exclusively
            # before copying content stays overwrite-safe in all of them.
            _claim_and_copy(source_path, target_path)

        source_path.unlink()


def _claim_and_copy(source_path: Path, target_path: Path) -> None:
    fd = os.open(target_path, os.O_CREAT | os.O_EXCL | os.O_WRONLY)
    os.close(fd)
    try:
        _ = shutil.copy2(source_path, target_path)
    except BaseException:
        target_path.unlink(missing_ok=True)
        raise
