"""
Summary: Moves files at the filesystem boundary.
Why: Lets apply mutate Library files without embedding I/O in feature code.
"""

from __future__ import annotations

import os
import shutil
from contextlib import suppress
from dataclasses import dataclass, field
from pathlib import Path
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from omym2.features.common_ports import FileSystemPath

TARGET_BELOW_ROOT_MESSAGE = "Target path must name a file below its root."


@dataclass(frozen=True, slots=True)
class FilesystemFileMover:
    """Move one filesystem file without applying business policy."""

    _ensured_parent_directories: set[Path] = field(default_factory=set, init=False, repr=False, compare=False)

    def move(
        self,
        source: FileSystemPath,
        target: FileSystemPath,
        *,
        target_root: FileSystemPath | None = None,
    ) -> None:
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
        if target_root is not None:
            _move_inside_root(source_path, target_path, Path(target_root))
            return

        target_parent = target_path.parent
        parent_was_ensured = target_parent in self._ensured_parent_directories
        if not parent_was_ensured or not target_parent.is_dir():
            target_parent.mkdir(parents=True, exist_ok=True)
            self._ensured_parent_directories.add(target_parent)

        _claim_target(source_path, target_path)

        try:
            source_path.unlink()
        except BaseException:
            target_path.unlink(missing_ok=True)
            raise


def _claim_target(source_path: Path, target_path: Path) -> None:
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


def _claim_and_copy(source_path: Path, target_path: Path) -> None:
    fd = os.open(target_path, os.O_CREAT | os.O_EXCL | os.O_WRONLY)
    os.close(fd)
    try:
        _ = shutil.copy2(source_path, target_path)
    except BaseException:
        target_path.unlink(missing_ok=True)
        raise


def _move_inside_root(source_path: Path, target_path: Path, target_root: Path) -> None:
    relative_target = target_path.relative_to(target_root)
    target_parts = relative_target.parts
    if not target_parts:
        raise ValueError(TARGET_BELOW_ROOT_MESSAGE)

    directory_fd = os.open(target_root, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW)
    try:
        for part in target_parts[:-1]:
            with suppress(FileExistsError):
                os.mkdir(part, dir_fd=directory_fd)
            next_directory_fd = os.open(
                part,
                os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW,
                dir_fd=directory_fd,
            )
            os.close(directory_fd)
            directory_fd = next_directory_fd

        target_name = target_parts[-1]
        _claim_target_at(source_path, target_name, directory_fd)
        try:
            source_path.unlink()
        except BaseException:
            os.unlink(target_name, dir_fd=directory_fd)
            raise
    finally:
        os.close(directory_fd)


def _claim_target_at(source_path: Path, target_name: str, target_directory_fd: int) -> None:
    try:
        os.link(source_path, target_name, dst_dir_fd=target_directory_fd, follow_symlinks=False)
    except FileExistsError, FileNotFoundError:
        raise
    except OSError:
        _claim_and_copy_at(source_path, target_name, target_directory_fd)


def _claim_and_copy_at(source_path: Path, target_name: str, target_directory_fd: int) -> None:
    target_fd = os.open(
        target_name,
        os.O_CREAT | os.O_EXCL | os.O_WRONLY,
        dir_fd=target_directory_fd,
    )
    try:
        with source_path.open("rb") as source_file, os.fdopen(target_fd, "wb", closefd=False) as target_file:
            _ = shutil.copyfileobj(source_file, target_file)
        source_stat = source_path.stat()
        os.fchmod(target_fd, source_stat.st_mode)
        os.utime(target_fd, ns=(source_stat.st_atime_ns, source_stat.st_mtime_ns))
    except BaseException:
        os.unlink(target_name, dir_fd=target_directory_fd)
        raise
    finally:
        os.close(target_fd)
