"""
Summary: Captures metadata-free file state through retained descriptors.
Why: Lets companion and unprocessed planning verify arbitrary regular files safely.
"""

from __future__ import annotations

import errno
import os
import stat
from dataclasses import dataclass, field
from datetime import UTC, datetime
from pathlib import Path
from typing import TYPE_CHECKING

from omym2.adapters.fs.hash_calculator import FileContentHasher
from omym2.adapters.fs.win32_file_handles import (
    WIN32_EXPECTED_FILE_MESSAGE,
    Win32FileIdentity,
    default_win32_file_handle_backend,
    win32_directory_prefixes,
)
from omym2.domain.models.file_snapshot import FileContentSnapshot, FilesystemIdentity
from omym2.features.common_ports import (
    Clock,
    FileObservationChangedError,
    FileObservationInvalidPathError,
    SystemClock,
)

if TYPE_CHECKING:
    from omym2.adapters.fs.win32_file_handles import Win32FileHandle, Win32FileHandleBackend
    from omym2.features.common_ports import FileSystemPath

CONTENT_SNAPSHOT_CHANGED_MESSAGE = "Source path changed during content snapshot capture."
CONTENT_SNAPSHOT_NOT_REGULAR_MESSAGE = "Content snapshot source must be a regular file."
CONTENT_SNAPSHOT_OUTSIDE_ROOT_MESSAGE = "Content snapshot source must be below its root."
CONTENT_SNAPSHOT_SYMLINK_MESSAGE = "Content snapshot source and its parent directories must not be symbolic links."
_OPEN_SUPPORTS_DIR_FD = os.open in os.supports_dir_fd
_STAT_SUPPORTS_DIR_FD = os.stat in os.supports_dir_fd
_STAT_SUPPORTS_NOFOLLOW = os.stat in os.supports_follow_symlinks
_NONBLOCKING_OPEN_FLAG = getattr(os, "O_NONBLOCK", 0)
_BINARY_OPEN_FLAG = getattr(os, "O_BINARY", 0)
_NOINHERIT_OPEN_FLAG = getattr(os, "O_NOINHERIT", 0)


@dataclass(frozen=True, slots=True)
class _OpenedContentFile:
    """Retained descriptors and identities for one root-anchored regular file."""

    path: Path
    root_path: Path
    root_descriptor: int | None
    parent_descriptor: int | None
    file_descriptor: int
    parent_parts: tuple[str, ...]
    parent_identities: tuple[os.stat_result, ...]
    initial_identity: os.stat_result
    fallback_parent_paths: tuple[Path, ...] = ()
    windows_handles: tuple[Win32FileHandle, ...] = ()


@dataclass(frozen=True, slots=True)
class FilesystemFileContentSnapshotReader:
    """Capture content state without tags or symlink-following path reads."""

    clock: Clock = field(default_factory=SystemClock)
    hasher: FileContentHasher = field(default_factory=FileContentHasher)
    windows_backend: Win32FileHandleBackend | None = field(
        default_factory=default_win32_file_handle_backend,
        repr=False,
        compare=False,
    )

    def capture(self, path: FileSystemPath, *, root: FileSystemPath) -> FileContentSnapshot:
        """Capture one regular file while proving it remained below the retained root."""
        source_path = _absolute_path(path)
        root_path = _absolute_path(root)
        opened = _open_content_file(source_path, root_path, windows_backend=self.windows_backend)
        try:
            content_hash = self.hasher.calculate_descriptor(opened.file_descriptor)
            completed_identity = os.fstat(opened.file_descriptor)
            if not _same_file_state(opened.initial_identity, completed_identity):
                raise FileObservationChangedError(CONTENT_SNAPSHOT_CHANGED_MESSAGE)
            _verify_opened_path(opened, completed_identity)
            return FileContentSnapshot(
                path=str(source_path),
                size=completed_identity.st_size,
                mtime=datetime.fromtimestamp(completed_identity.st_mtime, UTC),
                content_hash=content_hash,
                filesystem_identity=_filesystem_identity(completed_identity),
                captured_at=self.clock.now(),
            )
        finally:
            _close_opened_file(opened)


def _absolute_path(path: FileSystemPath) -> Path:
    # Path.resolve() would follow the very symlinks this boundary must reject.
    return Path(os.path.abspath(os.fspath(path)))  # noqa: PTH100  # Require lexical normalization only.


def _descriptor_relative_support_available() -> bool:
    return (
        _OPEN_SUPPORTS_DIR_FD
        and _STAT_SUPPORTS_DIR_FD
        and _STAT_SUPPORTS_NOFOLLOW
        and hasattr(os, "O_DIRECTORY")
        and hasattr(os, "O_NOFOLLOW")
    )


def _open_content_file(
    source_path: Path,
    root_path: Path,
    *,
    windows_backend: Win32FileHandleBackend | None,
) -> _OpenedContentFile:
    source_parts = _relative_source_parts(source_path, root_path)
    if windows_backend is not None:
        return _open_content_file_by_windows_handles(
            source_path,
            root_path,
            source_parts,
            windows_backend,
        )
    if not _descriptor_relative_support_available():
        return _open_content_file_by_path(source_path, root_path, source_parts)
    return _open_content_file_by_descriptor(source_path, root_path, source_parts)


def _open_content_file_by_windows_handles(
    source_path: Path,
    root_path: Path,
    source_parts: tuple[str, ...],
    backend: Win32FileHandleBackend,
) -> _OpenedContentFile:
    handles: list[Win32FileHandle] = []
    file_descriptor: int | None = None
    try:
        handles.extend(_open_windows_directory(backend, Path(prefix)) for prefix in win32_directory_prefixes(root_path))
        current_path = root_path
        for part in source_parts[:-1]:
            current_path /= part
            handles.append(_open_windows_directory(backend, current_path))
        try:
            file_handle = backend.open_file(source_path)
        except ValueError as exc:
            message = (
                CONTENT_SNAPSHOT_NOT_REGULAR_MESSAGE
                if str(exc) == WIN32_EXPECTED_FILE_MESSAGE
                else CONTENT_SNAPSHOT_SYMLINK_MESSAGE
            )
            raise FileObservationInvalidPathError(message) from exc
        handles.append(file_handle)
        file_descriptor = file_handle.duplicate_binary_fd()
        opened_identity = os.fstat(file_descriptor)
        _require_opened_regular_file(opened_identity)
        _require_win32_identity_matches_stat(file_handle.identity, opened_identity)
        return _OpenedContentFile(
            path=source_path,
            root_path=root_path,
            root_descriptor=None,
            parent_descriptor=None,
            file_descriptor=file_descriptor,
            parent_parts=source_parts[:-1],
            parent_identities=(),
            initial_identity=opened_identity,
            windows_handles=tuple(handles),
        )
    except BaseException as exc:
        if file_descriptor is not None:
            try:
                os.close(file_descriptor)
            except BaseException as close_error:  # noqa: BLE001  # Preserve the open failure.
                exc.add_note(f"Content descriptor close also failed: {close_error!r}")
        for handle in reversed(handles):
            try:
                handle.close()
            except BaseException as close_error:  # noqa: BLE001  # Every retained prefix still needs closing.
                exc.add_note(f"Retained Win32 handle close also failed: {close_error!r}")
        raise


def _open_windows_directory(backend: Win32FileHandleBackend, path: Path) -> Win32FileHandle:
    try:
        return backend.open_directory(path)
    except (NotADirectoryError, ValueError) as exc:
        raise FileObservationInvalidPathError(CONTENT_SNAPSHOT_SYMLINK_MESSAGE) from exc


def _relative_source_parts(source_path: Path, root_path: Path) -> tuple[str, ...]:
    try:
        relative_source = source_path.relative_to(root_path)
    except ValueError as exc:
        raise FileObservationInvalidPathError(CONTENT_SNAPSHOT_OUTSIDE_ROOT_MESSAGE) from exc
    source_parts = relative_source.parts
    if not source_parts or os.pardir in source_parts:
        raise FileObservationInvalidPathError(CONTENT_SNAPSHOT_OUTSIDE_ROOT_MESSAGE)
    return source_parts


def _open_content_file_by_descriptor(
    source_path: Path,
    root_path: Path,
    source_parts: tuple[str, ...],
) -> _OpenedContentFile:
    root_descriptor = _open_directory(root_path)
    directory_descriptor: int | None = None
    file_descriptor: int | None = None
    try:
        directory_descriptor, parent_identities = _open_parent_chain(root_descriptor, source_parts[:-1])
        file_descriptor, opened_identity = _open_regular_file(source_parts[-1], directory_descriptor)
        return _OpenedContentFile(
            path=source_path,
            root_path=root_path,
            root_descriptor=root_descriptor,
            parent_descriptor=directory_descriptor,
            file_descriptor=file_descriptor,
            parent_parts=source_parts[:-1],
            parent_identities=tuple(parent_identities),
            initial_identity=opened_identity,
        )
    except BaseException:
        if file_descriptor is not None:
            os.close(file_descriptor)
        if directory_descriptor is not None:
            os.close(directory_descriptor)
        os.close(root_descriptor)
        raise


def _open_content_file_by_path(
    source_path: Path,
    root_path: Path,
    source_parts: tuple[str, ...],
) -> _OpenedContentFile:
    fallback_parent_paths, parent_identities = _read_parent_path_identities(root_path, source_parts[:-1])
    listed_identity = source_path.stat(follow_symlinks=False)
    _require_unlinked_regular_file(source_path, listed_identity)
    try:
        file_descriptor = os.open(
            source_path,
            os.O_RDONLY | _NONBLOCKING_OPEN_FLAG | _BINARY_OPEN_FLAG | _NOINHERIT_OPEN_FLAG,
        )
    except OSError as exc:
        if exc.errno in {errno.ELOOP, errno.ENOTDIR}:
            raise FileObservationInvalidPathError(CONTENT_SNAPSHOT_SYMLINK_MESSAGE) from exc
        raise
    try:
        opened_identity = os.fstat(file_descriptor)
        _require_opened_regular_file(opened_identity)
        _require_same_file_state(listed_identity, opened_identity)
    except BaseException:
        os.close(file_descriptor)
        raise
    return _OpenedContentFile(
        path=source_path,
        root_path=root_path,
        root_descriptor=None,
        parent_descriptor=None,
        file_descriptor=file_descriptor,
        parent_parts=source_parts[:-1],
        parent_identities=parent_identities,
        initial_identity=opened_identity,
        fallback_parent_paths=fallback_parent_paths,
    )


def _read_parent_path_identities(
    root_path: Path,
    parent_parts: tuple[str, ...],
) -> tuple[tuple[Path, ...], tuple[os.stat_result, ...]]:
    parent_paths = [root_path]
    parent_paths.extend(root_path.joinpath(*parent_parts[:index]) for index in range(1, len(parent_parts) + 1))
    parent_identities: list[os.stat_result] = []
    for parent_path in parent_paths:
        identity = parent_path.stat(follow_symlinks=False)
        _require_unlinked_directory(parent_path, identity)
        parent_identities.append(identity)
    return tuple(parent_paths), tuple(parent_identities)


def _open_parent_chain(
    root_descriptor: int,
    parent_parts: tuple[str, ...],
) -> tuple[int, tuple[os.stat_result, ...]]:
    directory_descriptor = os.dup(root_descriptor)
    parent_identities: list[os.stat_result] = []
    try:
        for part in parent_parts:
            next_descriptor = _open_directory(part, dir_fd=directory_descriptor)
            os.close(directory_descriptor)
            directory_descriptor = next_descriptor
            parent_identities.append(os.fstat(directory_descriptor))
        return directory_descriptor, tuple(parent_identities)
    except BaseException:
        os.close(directory_descriptor)
        raise


def _open_regular_file(source_name: str, parent_descriptor: int) -> tuple[int, os.stat_result]:
    listed_identity = os.stat(source_name, dir_fd=parent_descriptor, follow_symlinks=False)
    _require_listed_regular_file(listed_identity)
    try:
        file_descriptor = os.open(
            source_name,
            os.O_RDONLY | os.O_NOFOLLOW | _NONBLOCKING_OPEN_FLAG,
            dir_fd=parent_descriptor,
        )
    except OSError as exc:
        if exc.errno in {errno.ELOOP, errno.ENOTDIR}:
            raise FileObservationInvalidPathError(CONTENT_SNAPSHOT_SYMLINK_MESSAGE) from exc
        raise
    try:
        opened_identity = os.fstat(file_descriptor)
    except BaseException:
        os.close(file_descriptor)
        raise
    try:
        _require_opened_regular_file(opened_identity)
        _require_same_file_state(listed_identity, opened_identity)
    except BaseException:
        os.close(file_descriptor)
        raise
    return file_descriptor, opened_identity


def _require_listed_regular_file(identity: os.stat_result) -> None:
    if stat.S_ISLNK(identity.st_mode):
        raise FileObservationInvalidPathError(CONTENT_SNAPSHOT_SYMLINK_MESSAGE)
    _require_opened_regular_file(identity)


def _require_unlinked_regular_file(path: Path, identity: os.stat_result) -> None:
    if _path_is_link_or_reparse_point(path, identity):
        raise FileObservationInvalidPathError(CONTENT_SNAPSHOT_SYMLINK_MESSAGE)
    _require_opened_regular_file(identity)


def _require_unlinked_directory(path: Path, identity: os.stat_result) -> None:
    if _path_is_link_or_reparse_point(path, identity) or not stat.S_ISDIR(identity.st_mode):
        raise FileObservationInvalidPathError(CONTENT_SNAPSHOT_SYMLINK_MESSAGE)


def _path_is_link_or_reparse_point(path: Path, identity: os.stat_result) -> bool:
    file_attributes = getattr(identity, "st_file_attributes", 0)
    return (
        stat.S_ISLNK(identity.st_mode)
        or path.is_junction()
        or bool(file_attributes & stat.FILE_ATTRIBUTE_REPARSE_POINT)
    )


def _require_opened_regular_file(identity: os.stat_result) -> None:
    if not stat.S_ISREG(identity.st_mode):
        raise FileObservationInvalidPathError(CONTENT_SNAPSHOT_NOT_REGULAR_MESSAGE)


def _require_same_file_state(left: os.stat_result, right: os.stat_result) -> None:
    if not _same_file_state(left, right):
        raise FileObservationChangedError(CONTENT_SNAPSHOT_CHANGED_MESSAGE)


def _open_directory(path: Path | str, *, dir_fd: int | None = None) -> int:
    try:
        return os.open(
            path,
            os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW,
            dir_fd=dir_fd,
        )
    except OSError as exc:
        if exc.errno in {errno.ELOOP, errno.ENOTDIR}:
            raise FileObservationInvalidPathError(CONTENT_SNAPSHOT_SYMLINK_MESSAGE) from exc
        raise


def _verify_opened_path(opened: _OpenedContentFile, completed_identity: os.stat_result) -> None:
    if opened.windows_handles:
        _verify_opened_windows_path(opened, completed_identity)
        return
    if opened.root_descriptor is None:
        _verify_opened_path_fallback(opened, completed_identity)
        return

    try:
        current_root_identity = opened.root_path.stat(follow_symlinks=False)
    except OSError as exc:
        raise FileObservationChangedError(CONTENT_SNAPSHOT_CHANGED_MESSAGE) from exc
    if not _same_directory_entry(current_root_identity, os.fstat(opened.root_descriptor)):
        raise FileObservationChangedError(CONTENT_SNAPSHOT_CHANGED_MESSAGE)

    verification_descriptor = os.dup(opened.root_descriptor)
    try:
        for part, expected_identity in zip(
            opened.parent_parts,
            opened.parent_identities,
            strict=True,
        ):
            try:
                next_descriptor = _open_directory(part, dir_fd=verification_descriptor)
            except (OSError, ValueError) as exc:
                raise FileObservationChangedError(CONTENT_SNAPSHOT_CHANGED_MESSAGE) from exc
            os.close(verification_descriptor)
            verification_descriptor = next_descriptor
            if not _same_directory_entry(os.fstat(verification_descriptor), expected_identity):
                raise FileObservationChangedError(CONTENT_SNAPSHOT_CHANGED_MESSAGE)

        try:
            current_identity = os.stat(
                opened.path.name,
                dir_fd=verification_descriptor,
                follow_symlinks=False,
            )
        except OSError as exc:
            raise FileObservationChangedError(CONTENT_SNAPSHOT_CHANGED_MESSAGE) from exc
        if not _same_file_state(current_identity, completed_identity):
            raise FileObservationChangedError(CONTENT_SNAPSHOT_CHANGED_MESSAGE)
    finally:
        os.close(verification_descriptor)


def _verify_opened_windows_path(opened: _OpenedContentFile, completed_identity: os.stat_result) -> None:
    *directory_handles, file_handle = opened.windows_handles
    try:
        for handle in directory_handles:
            if not handle.identity.same_object(handle.refresh_identity()):
                raise FileObservationChangedError(CONTENT_SNAPSHOT_CHANGED_MESSAGE)
        current_file_identity = file_handle.refresh_identity()
    except (OSError, ValueError) as exc:
        raise FileObservationChangedError(CONTENT_SNAPSHOT_CHANGED_MESSAGE) from exc
    if not file_handle.identity.same_object(current_file_identity) or not _win32_identity_matches_stat(
        current_file_identity,
        completed_identity,
    ):
        raise FileObservationChangedError(CONTENT_SNAPSHOT_CHANGED_MESSAGE)


def _verify_opened_path_fallback(opened: _OpenedContentFile, completed_identity: os.stat_result) -> None:
    try:
        current_parent_identities = tuple(
            parent_path.stat(follow_symlinks=False) for parent_path in opened.fallback_parent_paths
        )
        current_source_identity = opened.path.stat(follow_symlinks=False)
    except OSError as exc:
        raise FileObservationChangedError(CONTENT_SNAPSHOT_CHANGED_MESSAGE) from exc

    for parent_path, expected_identity, current_identity in zip(
        opened.fallback_parent_paths,
        opened.parent_identities,
        current_parent_identities,
        strict=True,
    ):
        if _path_is_link_or_reparse_point(parent_path, current_identity) or not _same_directory_entry(
            current_identity,
            expected_identity,
        ):
            raise FileObservationChangedError(CONTENT_SNAPSHOT_CHANGED_MESSAGE)
    if _path_is_link_or_reparse_point(opened.path, current_source_identity) or not _same_file_state(
        current_source_identity,
        completed_identity,
    ):
        raise FileObservationChangedError(CONTENT_SNAPSHOT_CHANGED_MESSAGE)


def _same_directory_entry(left: os.stat_result, right: os.stat_result) -> bool:
    return (
        stat.S_ISDIR(left.st_mode)
        and stat.S_ISDIR(right.st_mode)
        and left.st_dev == right.st_dev
        and left.st_ino == right.st_ino
    )


def _same_file_state(left: os.stat_result, right: os.stat_result) -> bool:
    return (
        stat.S_ISREG(left.st_mode)
        and stat.S_ISREG(right.st_mode)
        and left.st_dev == right.st_dev
        and left.st_ino == right.st_ino
        and left.st_size == right.st_size
        and left.st_mtime_ns == right.st_mtime_ns
        and left.st_ctime_ns == right.st_ctime_ns
    )


def _filesystem_identity(stat_result: os.stat_result) -> FilesystemIdentity:
    return FilesystemIdentity(
        device_id=stat_result.st_dev,
        inode=stat_result.st_ino,
        size=stat_result.st_size,
        mtime_ns=stat_result.st_mtime_ns,
        ctime_ns=stat_result.st_ctime_ns,
    )


def _win32_identity_matches_stat(identity: Win32FileIdentity, stat_result: os.stat_result) -> bool:
    return (
        identity.device_id == stat_result.st_dev
        and identity.inode == stat_result.st_ino
        and identity.size == stat_result.st_size
        and identity.mtime_ns == stat_result.st_mtime_ns
        and identity.ctime_ns == stat_result.st_ctime_ns
    )


def _require_win32_identity_matches_stat(identity: Win32FileIdentity, stat_result: os.stat_result) -> None:
    if not _win32_identity_matches_stat(identity, stat_result):
        raise FileObservationChangedError(CONTENT_SNAPSHOT_CHANGED_MESSAGE)


def _close_opened_file(opened: _OpenedContentFile) -> None:
    cleanup_error: BaseException | None = None
    try:
        os.close(opened.file_descriptor)
    except BaseException as close_error:  # noqa: BLE001  # Remaining retained handles still need closing.
        cleanup_error = close_error
    for handle in reversed(opened.windows_handles):
        try:
            handle.close()
        except BaseException as close_error:  # noqa: BLE001  # Every retained prefix still needs closing.
            cleanup_error = _record_cleanup_error(cleanup_error, close_error)
    if opened.parent_descriptor is not None:
        try:
            os.close(opened.parent_descriptor)
        except BaseException as close_error:  # noqa: BLE001  # Root cleanup must still run.
            cleanup_error = _record_cleanup_error(cleanup_error, close_error)
    if opened.root_descriptor is not None:
        try:
            os.close(opened.root_descriptor)
        except BaseException as close_error:  # noqa: BLE001  # Report after all resources are attempted.
            cleanup_error = _record_cleanup_error(cleanup_error, close_error)
    if cleanup_error is not None:
        raise cleanup_error


def _record_cleanup_error(
    primary_error: BaseException | None,
    additional_error: BaseException,
) -> BaseException:
    if primary_error is None:
        return additional_error
    primary_error.add_note(f"Another retained observation resource close also failed: {additional_error!r}")
    return primary_error
