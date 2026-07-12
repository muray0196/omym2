"""
Summary: Moves files at the filesystem boundary.
Why: Lets apply mutate Library files without embedding I/O in feature code.
"""

from __future__ import annotations

import os
import shutil
import stat
from contextlib import suppress
from dataclasses import dataclass, field
from pathlib import Path
from typing import TYPE_CHECKING

from omym2.config import PARENT_DIRECTORY_REFERENCE

if TYPE_CHECKING:
    from omym2.features.common_ports import FileSystemPath

SOURCE_SYMLINK_MESSAGE = "Source path must not be a symbolic link."
SOURCE_REPLACED_MESSAGE = "Source path changed during the move."
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
        try:
            source_fd = os.open(source_path, os.O_RDONLY | os.O_NOFOLLOW)
        except OSError as exc:
            if source_path.is_symlink():
                raise ValueError(SOURCE_SYMLINK_MESSAGE) from exc
            raise

        try:
            source_stat = os.fstat(source_fd)
            if not stat.S_ISREG(source_stat.st_mode):
                raise ValueError(SOURCE_REPLACED_MESSAGE)
            if target_root is not None:
                _move_inside_root(source_path, source_fd, source_stat, target_path, Path(target_root))
                return

            target_parent = target_path.parent
            parent_was_ensured = target_parent in self._ensured_parent_directories
            if not parent_was_ensured or not target_parent.is_dir():
                target_parent.mkdir(parents=True, exist_ok=True)
                self._ensured_parent_directories.add(target_parent)

            _claim_target(source_path, source_fd, source_stat, target_path)

            try:
                _unlink_verified_source(source_path, source_stat)
            except BaseException:
                target_path.unlink(missing_ok=True)
                raise
        finally:
            os.close(source_fd)


def _claim_target(source_path: Path, source_fd: int, source_stat: os.stat_result, target_path: Path) -> None:
    try:
        os.link(source_path, target_path, follow_symlinks=False)
    except FileExistsError, FileNotFoundError:
        # Preserve the TARGET_EXISTS and SOURCE_MISSING failure contracts.
        raise
    except OSError:
        # The hardlink claim can fail for reasons other than an occupied
        # target: cross-device moves (EXDEV) and filesystems that refuse
        # hardlinks (EPERM, ENOTSUP, ...). Claiming the target exclusively
        # before copying content stays overwrite-safe in all of them.
        _claim_and_copy(source_fd, source_stat, target_path)
        return

    if not _path_matches_source(target_path, source_stat):
        target_path.unlink(missing_ok=True)
        raise ValueError(SOURCE_REPLACED_MESSAGE)


def _claim_and_copy(source_fd: int, source_stat: os.stat_result, target_path: Path) -> None:
    target_fd = os.open(target_path, os.O_CREAT | os.O_EXCL | os.O_WRONLY)
    try:
        _copy_open_source(source_fd, source_stat, target_fd)
    except BaseException:
        target_path.unlink(missing_ok=True)
        raise
    finally:
        os.close(target_fd)


def _move_inside_root(
    source_path: Path,
    source_fd: int,
    source_stat: os.stat_result,
    target_path: Path,
    target_root: Path,
) -> None:
    relative_target = target_path.relative_to(target_root)
    target_parts = relative_target.parts
    # relative_to is lexical and keeps ".." parts, and O_NOFOLLOW cannot stop
    # dot-dot traversal, so the escape must be rejected here.
    if not target_parts or PARENT_DIRECTORY_REFERENCE in target_parts:
        raise ValueError(TARGET_BELOW_ROOT_MESSAGE)

    root_fd = os.open(target_root, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW)
    try:
        directory_fd = os.dup(root_fd)
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
            _claim_target_at(source_path, source_fd, source_stat, target_name, directory_fd)
            try:
                _verify_claimed_target_below_root(
                    target_name,
                    target_parts[:-1],
                    directory_fd,
                    root_fd,
                    target_root,
                )
            except BaseException:
                with suppress(FileNotFoundError):
                    os.unlink(target_name, dir_fd=directory_fd)
                raise
            try:
                _unlink_verified_source(source_path, source_stat)
            except BaseException:
                with suppress(FileNotFoundError):
                    os.unlink(target_name, dir_fd=directory_fd)
                raise
        finally:
            os.close(directory_fd)
    finally:
        os.close(root_fd)


def _verify_claimed_target_below_root(
    target_name: str,
    target_parent_parts: tuple[str, ...],
    target_directory_fd: int,
    root_fd: int,
    target_root: Path,
) -> None:
    anchored_directory_fd = os.dup(root_fd)
    try:
        if not _path_matches_stat(target_root, os.fstat(root_fd)):
            raise ValueError(TARGET_BELOW_ROOT_MESSAGE)
        for part in target_parent_parts:
            next_directory_fd = os.open(
                part,
                os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW,
                dir_fd=anchored_directory_fd,
            )
            os.close(anchored_directory_fd)
            anchored_directory_fd = next_directory_fd

        if not _stats_match(os.fstat(anchored_directory_fd), os.fstat(target_directory_fd)):
            raise ValueError(TARGET_BELOW_ROOT_MESSAGE)
        claimed_target_stat = os.stat(target_name, dir_fd=target_directory_fd, follow_symlinks=False)
        anchored_target_stat = os.stat(target_name, dir_fd=anchored_directory_fd, follow_symlinks=False)
        if not _stats_match(claimed_target_stat, anchored_target_stat):
            raise ValueError(TARGET_BELOW_ROOT_MESSAGE)
    except OSError as exc:
        raise ValueError(TARGET_BELOW_ROOT_MESSAGE) from exc
    finally:
        os.close(anchored_directory_fd)


def _claim_target_at(
    source_path: Path,
    source_fd: int,
    source_stat: os.stat_result,
    target_name: str,
    target_directory_fd: int,
) -> None:
    try:
        os.link(source_path, target_name, dst_dir_fd=target_directory_fd, follow_symlinks=False)
    except FileExistsError, FileNotFoundError:
        raise
    except OSError:
        _claim_and_copy_at(source_fd, source_stat, target_name, target_directory_fd)
        return

    if not _path_matches_source(target_name, source_stat, dir_fd=target_directory_fd):
        with suppress(FileNotFoundError):
            os.unlink(target_name, dir_fd=target_directory_fd)
        raise ValueError(SOURCE_REPLACED_MESSAGE)


def _claim_and_copy_at(
    source_fd: int,
    source_stat: os.stat_result,
    target_name: str,
    target_directory_fd: int,
) -> None:
    target_fd = os.open(
        target_name,
        os.O_CREAT | os.O_EXCL | os.O_WRONLY,
        dir_fd=target_directory_fd,
    )
    try:
        _copy_open_source(source_fd, source_stat, target_fd)
    except BaseException:
        with suppress(FileNotFoundError):
            os.unlink(target_name, dir_fd=target_directory_fd)
        raise
    finally:
        os.close(target_fd)


def _copy_open_source(source_fd: int, source_stat: os.stat_result, target_fd: int) -> None:
    _ = os.lseek(source_fd, 0, os.SEEK_SET)
    with (
        os.fdopen(source_fd, "rb", closefd=False) as source_file,
        os.fdopen(
            target_fd,
            "wb",
            closefd=False,
        ) as target_file,
    ):
        _ = shutil.copyfileobj(source_file, target_file)
    os.fchmod(target_fd, stat.S_IMODE(source_stat.st_mode))
    os.utime(target_fd, ns=(source_stat.st_atime_ns, source_stat.st_mtime_ns))


def _unlink_verified_source(source_path: Path, source_stat: os.stat_result) -> None:
    if not _path_matches_source(source_path, source_stat):
        raise ValueError(SOURCE_REPLACED_MESSAGE)
    source_path.unlink()


def _path_matches_source(
    path: Path | str,
    source_stat: os.stat_result,
    *,
    dir_fd: int | None = None,
) -> bool:
    try:
        path_stat = os.stat(path, dir_fd=dir_fd, follow_symlinks=False)
    except FileNotFoundError:
        return False
    return _stats_match(path_stat, source_stat)


def _path_matches_stat(path: Path, expected_stat: os.stat_result) -> bool:
    try:
        path_stat = path.stat(follow_symlinks=False)
    except OSError:
        return False
    return _stats_match(path_stat, expected_stat)


def _stats_match(left: os.stat_result, right: os.stat_result) -> bool:
    return left.st_dev == right.st_dev and left.st_ino == right.st_ino
