"""
Summary: Moves files at the filesystem boundary.
Why: Lets apply mutate Library files without embedding I/O in feature code.
"""

from __future__ import annotations

import errno
import os
import shutil
import stat
from contextlib import ExitStack, suppress
from dataclasses import dataclass, field
from pathlib import Path
from typing import TYPE_CHECKING

from omym2.adapters.fs.hash_calculator import FileContentHasher
from omym2.adapters.fs.win32_file_handles import (
    Win32FileHandle,
    Win32FileHandleBackend,
    Win32FileIdentity,
    default_win32_file_handle_backend,
    stat_change_marker_ns,
)
from omym2.config import PARENT_DIRECTORY_REFERENCE

if TYPE_CHECKING:
    from omym2.domain.models.file_snapshot import FilesystemIdentity
    from omym2.features.common_ports import FileSystemPath

SOURCE_BELOW_ROOT_MESSAGE = "Source path must name a file below its root."
SOURCE_SYMLINK_MESSAGE = "Source path must not be a symbolic link."
SOURCE_REPLACED_MESSAGE = "Source path changed during the move."
TARGET_BELOW_ROOT_MESSAGE = "Target path must name a file below its root."
TARGET_REPLACED_MESSAGE = "Target path changed during the move."
ANCHORED_FILESYSTEM_UNSUPPORTED_MESSAGE = "Anchored filesystem operations are not supported."
_OPEN_SUPPORTS_DIR_FD = os.open in os.supports_dir_fd
_STAT_SUPPORTS_DIR_FD = os.stat in os.supports_dir_fd
_STAT_SUPPORTS_NOFOLLOW = os.stat in os.supports_follow_symlinks
_UNLINK_SUPPORTS_DIR_FD = os.unlink in os.supports_dir_fd
_MKDIR_SUPPORTS_DIR_FD = os.mkdir in os.supports_dir_fd
_OPEN_FILE_DESCRIPTOR_DIRECTORY = Path("/proc/self/fd")


def _native_windows_file_handle_backend() -> Win32FileHandleBackend | None:
    """Build the retained HANDLE backend only on native Windows."""
    return default_win32_file_handle_backend()


@dataclass(frozen=True, slots=True)
class _OpenedSource:
    """Retained source descriptors and their verified filesystem identity."""

    path: Path
    file_descriptor: int
    stat_result: os.stat_result
    root_path: Path | None = None
    root_descriptor: int | None = None
    parent_descriptor: int | None = None
    parent_parts: tuple[str, ...] = ()
    name: str | None = None


@dataclass(frozen=True, slots=True)
class _ClaimedTarget:
    """Claimed target identity and source state after that claim."""

    stat_result: os.stat_result
    source_stat_after_claim: os.stat_result


@dataclass(frozen=True, slots=True)
class _WindowsPathBoundary:
    """Lexically rooted path pieces for retained Windows traversal."""

    path: Path
    root_path: Path
    parent_parts: tuple[str, ...]
    name: str


def _windows_path_boundary(
    path: Path,
    root: Path | None,
    *,
    message: str,
) -> _WindowsPathBoundary:
    if not path.is_absolute() or PARENT_DIRECTORY_REFERENCE in path.parts:
        raise ValueError(message)
    if root is None:
        if not path.anchor:
            raise ValueError(message)
        root_path = Path(path.anchor)
    else:
        if not root.is_absolute() or PARENT_DIRECTORY_REFERENCE in root.parts:
            raise ValueError(message)
        root_path = root
    try:
        relative_path = path.relative_to(root_path)
    except ValueError as exc:
        raise ValueError(message) from exc
    relative_parts = relative_path.parts
    if not relative_parts or PARENT_DIRECTORY_REFERENCE in relative_parts:
        raise ValueError(message)
    return _WindowsPathBoundary(
        path=path,
        root_path=root_path,
        parent_parts=relative_parts[:-1],
        name=relative_parts[-1],
    )


@dataclass(frozen=True, slots=True)
class FilesystemFileMover:
    """Move one filesystem file without applying business policy."""

    content_hasher: FileContentHasher = field(default_factory=FileContentHasher)
    windows_backend: Win32FileHandleBackend | None = field(
        default_factory=_native_windows_file_handle_backend,
        repr=False,
        compare=False,
    )
    _ensured_parent_directories: set[Path] = field(default_factory=set, init=False, repr=False, compare=False)

    def move(  # noqa: PLR0913  # Source identity and content hash are separate mutation preconditions.
        self,
        source: FileSystemPath,
        target: FileSystemPath,
        *,
        source_root: FileSystemPath | None = None,
        target_root: FileSystemPath | None = None,
        expected_source_identity: FilesystemIdentity | None = None,
        expected_source_content_hash: str | None = None,
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
        if self.windows_backend is not None:
            _move_with_windows_handles(
                backend=self.windows_backend,
                source_path=source_path,
                target_path=target_path,
                source_root=None if source_root is None else Path(source_root),
                target_root=None if target_root is None else Path(target_root),
                expected_source_identity=expected_source_identity,
                expected_source_content_hash=expected_source_content_hash,
                content_hasher=self.content_hasher,
            )
            return

        _require_descriptor_relative_support(
            needs_target_root=target_root is not None,
        )
        opened_source = _open_source(
            source_path,
            None if source_root is None else Path(source_root),
            expected_source_identity,
        )
        try:
            if target_root is not None:
                _move_inside_root(
                    opened_source,
                    target_path,
                    Path(target_root),
                    expected_source_content_hash=expected_source_content_hash,
                    content_hasher=self.content_hasher,
                )
                return

            target_parent = target_path.parent
            parent_was_ensured = target_parent in self._ensured_parent_directories
            if not parent_was_ensured or not target_parent.is_dir():
                target_parent.mkdir(parents=True, exist_ok=True)
                self._ensured_parent_directories.add(target_parent)

            claimed_target = _claim_target(
                opened_source,
                target_path,
                expected_source_content_hash=expected_source_content_hash,
                content_hasher=self.content_hasher,
            )

            try:
                _require_path_match(
                    condition=_path_matches_source(target_path, claimed_target.stat_result),
                    message=TARGET_REPLACED_MESSAGE,
                )
                _unlink_verified_source(
                    opened_source,
                    claimed_target.source_stat_after_claim,
                    expected_source_content_hash=expected_source_content_hash,
                    content_hasher=self.content_hasher,
                )
            except BaseException:
                _unlink_if_matches(target_path, claimed_target.stat_result)
                raise
        finally:
            _close_source(opened_source)


def _move_with_windows_handles(  # noqa: PLR0913  # Mirrors the stable FileMover precondition boundary.
    *,
    backend: Win32FileHandleBackend,
    source_path: Path,
    target_path: Path,
    source_root: Path | None,
    target_root: Path | None,
    expected_source_identity: FilesystemIdentity | None,
    expected_source_content_hash: str | None,
    content_hasher: FileContentHasher,
) -> None:
    """Move through retained Win32 handles when directory descriptors are unavailable."""
    source_boundary = _windows_path_boundary(
        source_path,
        source_root,
        message=SOURCE_BELOW_ROOT_MESSAGE,
    )
    target_boundary = _windows_path_boundary(
        target_path,
        target_root,
        message=TARGET_BELOW_ROOT_MESSAGE,
    )
    with ExitStack() as retained:
        source_directories = _open_windows_parent_chain(
            retained=retained,
            backend=backend,
            boundary=source_boundary,
            create_missing=False,
            message=SOURCE_BELOW_ROOT_MESSAGE,
        )
        try:
            source_handle = backend.open_source(source_boundary.path)
        except ValueError as exc:
            raise ValueError(SOURCE_SYMLINK_MESSAGE) from exc
        _ = retained.callback(source_handle.close)
        _ = _verify_windows_handle(
            source_handle,
            expected_path=source_boundary.path,
            expected_identity=source_handle.identity,
            message=SOURCE_REPLACED_MESSAGE,
        )
        source_descriptor = source_handle.duplicate_binary_fd()
        _ = retained.callback(os.close, source_descriptor)
        source_stat = os.fstat(source_descriptor)
        if not stat.S_ISREG(source_stat.st_mode):
            raise ValueError(SOURCE_REPLACED_MESSAGE)
        if expected_source_identity is not None and not _stat_matches_identity(
            source_stat,
            expected_source_identity,
        ):
            raise ValueError(SOURCE_REPLACED_MESSAGE)

        target_directories = _open_windows_parent_chain(
            retained=retained,
            backend=backend,
            boundary=target_boundary,
            create_missing=True,
            message=TARGET_BELOW_ROOT_MESSAGE,
        )
        try:
            target_handle = backend.create_file_new(target_boundary.path)
        except FileNotFoundError as exc:
            raise ValueError(TARGET_BELOW_ROOT_MESSAGE) from exc
        _ = retained.callback(target_handle.close)
        target_descriptor = target_handle.duplicate_binary_fd(writable=True)
        _ = retained.callback(os.close, target_descriptor)

        try:
            source_stat_after_copy = _copy_open_source_with_windows_handles(
                source_descriptor=source_descriptor,
                source_stat=source_stat,
                target_descriptor=target_descriptor,
                expected_source_content_hash=expected_source_content_hash,
                content_hasher=content_hasher,
            )
            target_identity = _verify_windows_handle(
                target_handle,
                expected_path=target_boundary.path,
                message=TARGET_REPLACED_MESSAGE,
            )
            _verify_windows_path_chain(
                source_directories,
                message=SOURCE_BELOW_ROOT_MESSAGE,
            )
            _verify_windows_path_chain(
                target_directories,
                message=TARGET_BELOW_ROOT_MESSAGE,
            )
            _ = _verify_windows_handle(
                source_handle,
                expected_path=source_boundary.path,
                expected_identity=source_handle.identity,
                message=SOURCE_REPLACED_MESSAGE,
            )
            _ = _verify_windows_handle(
                target_handle,
                expected_path=target_boundary.path,
                expected_identity=target_identity,
                message=TARGET_REPLACED_MESSAGE,
            )
            _require_unchanged_file_state(source_descriptor, source_stat_after_copy)
            _verify_expected_content_hash(
                source_descriptor,
                expected_source_content_hash,
                content_hasher,
            )
            _verify_expected_content_hash(
                target_descriptor,
                expected_source_content_hash,
                content_hasher,
            )
            target_identity = target_handle.set_metadata(
                mode=stat.S_IMODE(source_stat.st_mode),
                atime_ns=source_stat.st_atime_ns,
                mtime_ns=source_stat.st_mtime_ns,
            )
            _ = _verify_windows_handle(
                target_handle,
                expected_path=target_boundary.path,
                expected_identity=target_identity,
                message=TARGET_REPLACED_MESSAGE,
            )
            source_handle.delete_exact(expected_identity=source_handle.identity)
        except BaseException as exc:
            try:
                _cleanup_windows_target(target_handle, source_stat)
            except BaseException as cleanup_error:  # noqa: BLE001  # Preserve the mutation error if cleanup fails.
                exc.add_note(f"Exact claimed-target cleanup also failed: {cleanup_error!r}")
            raise


def _open_windows_parent_chain(
    *,
    retained: ExitStack,
    backend: Win32FileHandleBackend,
    boundary: _WindowsPathBoundary,
    create_missing: bool,
    message: str,
) -> tuple[Win32FileHandle, ...]:
    handles: list[Win32FileHandle] = []
    current_path = Path(boundary.root_path.anchor)
    handles.append(
        _open_windows_directory(
            retained=retained,
            backend=backend,
            path=current_path,
            message=message,
        )
    )
    root_parts = boundary.root_path.relative_to(current_path).parts
    for part in root_parts:
        current_path = current_path / part
        handles.append(
            _open_windows_directory(
                retained=retained,
                backend=backend,
                path=current_path,
                message=message,
            )
        )
    for part in boundary.parent_parts:
        current_path = current_path / part
        if create_missing:
            try:
                current_path.mkdir()
            except FileExistsError:
                pass
            except FileNotFoundError as exc:
                raise ValueError(message) from exc
        handles.append(
            _open_windows_directory(
                retained=retained,
                backend=backend,
                path=current_path,
                message=message,
            )
        )
    return tuple(handles)


def _open_windows_directory(
    *,
    retained: ExitStack,
    backend: Win32FileHandleBackend,
    path: Path,
    message: str,
) -> Win32FileHandle:
    try:
        handle = backend.open_directory(path)
    except (FileNotFoundError, NotADirectoryError, ValueError) as exc:
        raise ValueError(message) from exc
    _ = retained.callback(handle.close)
    _ = _verify_windows_handle(
        handle,
        expected_path=path,
        expected_identity=handle.identity,
        message=message,
    )
    return handle


def _verify_windows_path_chain(
    handles: tuple[Win32FileHandle, ...],
    *,
    message: str,
) -> None:
    for handle in handles:
        _ = _verify_windows_handle(
            handle,
            expected_path=handle.path,
            message=message,
        )


def _verify_windows_handle(
    handle: Win32FileHandle,
    *,
    expected_path: os.PathLike[str] | str,
    message: str,
    expected_identity: Win32FileIdentity | None = None,
) -> Win32FileIdentity:
    try:
        return handle.verify_current(
            expected_path=expected_path,
            expected_identity=expected_identity,
        )
    except (OSError, ValueError) as exc:
        raise ValueError(message) from exc


def _copy_open_source_with_windows_handles(
    *,
    source_descriptor: int,
    source_stat: os.stat_result,
    target_descriptor: int,
    expected_source_content_hash: str | None,
    content_hasher: FileContentHasher,
) -> os.stat_result:
    if not _file_states_match(os.fstat(source_descriptor), source_stat):
        raise ValueError(SOURCE_REPLACED_MESSAGE)
    _ = os.lseek(source_descriptor, 0, os.SEEK_SET)
    with (
        os.fdopen(source_descriptor, "rb", closefd=False) as source_file,
        os.fdopen(target_descriptor, "wb", closefd=False) as target_file,
    ):
        _ = shutil.copyfileobj(source_file, target_file)
    if not _file_states_match(os.fstat(source_descriptor), source_stat):
        raise ValueError(SOURCE_REPLACED_MESSAGE)
    _verify_expected_content_hash(target_descriptor, expected_source_content_hash, content_hasher)
    _verify_expected_content_hash(source_descriptor, expected_source_content_hash, content_hasher)
    source_stat_after_copy = os.fstat(source_descriptor)
    if not _file_states_match(source_stat_after_copy, source_stat):
        raise ValueError(SOURCE_REPLACED_MESSAGE)
    return source_stat_after_copy


def _cleanup_windows_target(target_handle: Win32FileHandle, source_stat: os.stat_result) -> None:
    metadata_error: BaseException | None = None
    try:
        _ = target_handle.set_metadata(
            mode=stat.S_IWRITE,
            atime_ns=source_stat.st_atime_ns,
            mtime_ns=source_stat.st_mtime_ns,
        )
    except BaseException as exc:  # noqa: BLE001  # Still attempt exact deletion after metadata cleanup fails.
        metadata_error = exc
    try:
        target_handle.delete_exact()
    except BaseException as exc:
        if metadata_error is not None:
            exc.add_note(f"Restoring target writability also failed: {metadata_error!r}")
        raise


def _require_unchanged_file_state(file_descriptor: int, expected_stat: os.stat_result) -> None:
    if not _file_states_match(os.fstat(file_descriptor), expected_stat):
        raise ValueError(SOURCE_REPLACED_MESSAGE)


def _open_source(
    source_path: Path,
    source_root: Path | None,
    expected_identity: FilesystemIdentity | None,
) -> _OpenedSource:
    if source_root is not None:
        opened_source = _open_source_below_root(source_path, source_root)
    else:
        source_parent_fd = os.open(source_path.parent, os.O_RDONLY | os.O_DIRECTORY)
        try:
            source_fd = os.open(
                source_path.name,
                os.O_RDONLY | os.O_NOFOLLOW,
                dir_fd=source_parent_fd,
            )
        except OSError as exc:
            os.close(source_parent_fd)
            if exc.errno == errno.ELOOP:
                raise ValueError(SOURCE_SYMLINK_MESSAGE) from exc
            raise
        source_stat = os.fstat(source_fd)
        opened_source = _OpenedSource(
            source_path,
            source_fd,
            source_stat,
            parent_descriptor=source_parent_fd,
            name=source_path.name,
        )

    if not stat.S_ISREG(opened_source.stat_result.st_mode):
        _close_source(opened_source)
        raise ValueError(SOURCE_REPLACED_MESSAGE)
    if expected_identity is not None and not _stat_matches_identity(
        opened_source.stat_result,
        expected_identity,
    ):
        _close_source(opened_source)
        raise ValueError(SOURCE_REPLACED_MESSAGE)
    return opened_source


def _open_source_below_root(source_path: Path, source_root: Path) -> _OpenedSource:
    try:
        relative_source = source_path.relative_to(source_root)
    except ValueError as exc:
        raise ValueError(SOURCE_BELOW_ROOT_MESSAGE) from exc
    source_parts = relative_source.parts
    if not source_parts or PARENT_DIRECTORY_REFERENCE in source_parts:
        raise ValueError(SOURCE_BELOW_ROOT_MESSAGE)

    root_fd = _open_anchored_directory(source_root, message=SOURCE_BELOW_ROOT_MESSAGE)
    directory_fd = os.dup(root_fd)
    source_fd: int | None = None
    try:
        for part in source_parts[:-1]:
            next_directory_fd = _open_anchored_directory(
                part,
                dir_fd=directory_fd,
                message=SOURCE_BELOW_ROOT_MESSAGE,
            )
            os.close(directory_fd)
            directory_fd = next_directory_fd

        source_name = source_parts[-1]
        try:
            source_fd = os.open(
                source_name,
                os.O_RDONLY | os.O_NOFOLLOW,
                dir_fd=directory_fd,
            )
        except OSError as exc:
            if exc.errno == errno.ELOOP:
                raise ValueError(SOURCE_SYMLINK_MESSAGE) from exc
            if exc.errno == errno.ENOTDIR:
                raise ValueError(SOURCE_BELOW_ROOT_MESSAGE) from exc
            raise
        opened_source = _OpenedSource(
            path=source_path,
            file_descriptor=source_fd,
            stat_result=os.fstat(source_fd),
            root_path=source_root,
            root_descriptor=root_fd,
            parent_descriptor=directory_fd,
            parent_parts=source_parts[:-1],
            name=source_name,
        )
        _verify_source_below_root(opened_source)
    except BaseException:
        if source_fd is not None:
            os.close(source_fd)
        os.close(directory_fd)
        os.close(root_fd)
        raise
    else:
        return opened_source


def _open_anchored_directory(
    path: Path | str,
    *,
    message: str,
    dir_fd: int | None = None,
) -> int:
    try:
        return os.open(
            path,
            os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW,
            dir_fd=dir_fd,
        )
    except FileNotFoundError as exc:
        raise ValueError(message) from exc
    except OSError as exc:
        if exc.errno in {errno.ELOOP, errno.ENOTDIR}:
            raise ValueError(message) from exc
        raise
    except (AttributeError, NotImplementedError) as exc:
        raise ValueError(ANCHORED_FILESYSTEM_UNSUPPORTED_MESSAGE) from exc


def _require_descriptor_relative_support(*, needs_target_root: bool) -> None:
    if not (_OPEN_SUPPORTS_DIR_FD and _STAT_SUPPORTS_DIR_FD and _UNLINK_SUPPORTS_DIR_FD):
        raise ValueError(ANCHORED_FILESYSTEM_UNSUPPORTED_MESSAGE)
    if needs_target_root and not _MKDIR_SUPPORTS_DIR_FD:
        raise ValueError(ANCHORED_FILESYSTEM_UNSUPPORTED_MESSAGE)
    if not _STAT_SUPPORTS_NOFOLLOW:
        raise ValueError(ANCHORED_FILESYSTEM_UNSUPPORTED_MESSAGE)
    if not hasattr(os, "O_DIRECTORY") or not hasattr(os, "O_NOFOLLOW"):
        raise ValueError(ANCHORED_FILESYSTEM_UNSUPPORTED_MESSAGE)


def _close_source(opened_source: _OpenedSource) -> None:
    os.close(opened_source.file_descriptor)
    if opened_source.parent_descriptor is not None:
        os.close(opened_source.parent_descriptor)
    if opened_source.root_descriptor is not None:
        os.close(opened_source.root_descriptor)


def _claim_target(
    opened_source: _OpenedSource,
    target_path: Path,
    *,
    expected_source_content_hash: str | None,
    content_hasher: FileContentHasher,
) -> _ClaimedTarget:
    _verify_opened_source(opened_source)
    if opened_source.root_descriptor is None:
        return _claim_and_copy(
            opened_source,
            target_path,
            expected_source_content_hash=expected_source_content_hash,
            content_hasher=content_hasher,
        )
    try:
        _link_source(opened_source, target_path)
    except FileExistsError:
        # Preserve the TARGET_EXISTS failure contract.
        raise
    except OSError, NotImplementedError:
        # The hardlink claim can fail for reasons other than an occupied
        # target: cross-device moves (EXDEV) and filesystems that refuse
        # hardlinks (EPERM, ENOTSUP, ...). Claiming the target exclusively
        # before copying content stays overwrite-safe in all of them.
        return _claim_and_copy(
            opened_source,
            target_path,
            expected_source_content_hash=expected_source_content_hash,
            content_hasher=content_hasher,
        )

    source_stat_after_claim = os.fstat(opened_source.file_descriptor)
    try:
        current_target_stat = target_path.stat(follow_symlinks=False)
    except FileNotFoundError as exc:
        raise ValueError(TARGET_REPLACED_MESSAGE) from exc
    if not (
        _stats_match(current_target_stat, opened_source.stat_result)
        and _file_states_match_except_ctime(source_stat_after_claim, opened_source.stat_result)
    ):
        _unlink_if_matches(target_path, opened_source.stat_result)
        raise ValueError(SOURCE_REPLACED_MESSAGE)
    try:
        _verify_expected_content_hash(
            opened_source.file_descriptor,
            expected_source_content_hash,
            content_hasher,
        )
    except BaseException:
        _unlink_if_matches(target_path, opened_source.stat_result)
        raise
    return _ClaimedTarget(opened_source.stat_result, source_stat_after_claim)


def _link_source(
    opened_source: _OpenedSource,
    target: Path | str,
    *,
    target_directory_fd: int | None = None,
) -> None:
    open_source_path = _OPEN_FILE_DESCRIPTOR_DIRECTORY / str(opened_source.file_descriptor)
    os.link(
        open_source_path,
        target,
        dst_dir_fd=target_directory_fd,
        follow_symlinks=True,
    )


def _claim_and_copy(
    opened_source: _OpenedSource,
    target_path: Path,
    *,
    expected_source_content_hash: str | None,
    content_hasher: FileContentHasher,
) -> _ClaimedTarget:
    try:
        target_fd = os.open(target_path, os.O_CREAT | os.O_EXCL | os.O_RDWR)
    except FileNotFoundError as exc:
        raise ValueError(TARGET_REPLACED_MESSAGE) from exc
    try:
        source_stat_after_copy = _copy_open_source(
            opened_source.file_descriptor,
            opened_source.stat_result,
            target_fd,
            expected_source_content_hash=expected_source_content_hash,
            content_hasher=content_hasher,
        )
        claimed_target_stat = os.fstat(target_fd)
    except BaseException:
        _unlink_if_matches(target_path, os.fstat(target_fd))
        raise
    finally:
        os.close(target_fd)
    return _ClaimedTarget(
        stat_result=claimed_target_stat,
        source_stat_after_claim=source_stat_after_copy,
    )


def _move_inside_root(
    opened_source: _OpenedSource,
    target_path: Path,
    target_root: Path,
    *,
    expected_source_content_hash: str | None,
    content_hasher: FileContentHasher,
) -> None:
    try:
        relative_target = target_path.relative_to(target_root)
    except ValueError as exc:
        raise ValueError(TARGET_BELOW_ROOT_MESSAGE) from exc
    target_parts = relative_target.parts
    # relative_to is lexical and keeps ".." parts, and O_NOFOLLOW cannot stop
    # dot-dot traversal, so the escape must be rejected here.
    if not target_parts or PARENT_DIRECTORY_REFERENCE in target_parts:
        raise ValueError(TARGET_BELOW_ROOT_MESSAGE)

    root_fd = _open_anchored_directory(target_root, message=TARGET_BELOW_ROOT_MESSAGE)
    try:
        directory_fd = os.dup(root_fd)
        try:
            for part in target_parts[:-1]:
                try:
                    with suppress(FileExistsError):
                        os.mkdir(part, dir_fd=directory_fd)
                except FileNotFoundError as exc:
                    raise ValueError(TARGET_BELOW_ROOT_MESSAGE) from exc
                next_directory_fd = _open_anchored_directory(
                    part,
                    dir_fd=directory_fd,
                    message=TARGET_BELOW_ROOT_MESSAGE,
                )
                os.close(directory_fd)
                directory_fd = next_directory_fd

            target_name = target_parts[-1]
            claimed_target = _claim_target_at(
                opened_source,
                target_name,
                directory_fd,
                expected_source_content_hash=expected_source_content_hash,
                content_hasher=content_hasher,
            )
            try:
                _verify_claimed_target_below_root(
                    target_parts,
                    directory_fd,
                    root_fd,
                    target_root,
                    claimed_target.stat_result,
                )
            except BaseException:
                _unlink_if_matches(target_name, claimed_target.stat_result, dir_fd=directory_fd)
                raise
            try:
                _unlink_verified_source(
                    opened_source,
                    claimed_target.source_stat_after_claim,
                    expected_source_content_hash=expected_source_content_hash,
                    content_hasher=content_hasher,
                )
            except BaseException:
                _unlink_if_matches(target_name, claimed_target.stat_result, dir_fd=directory_fd)
                raise
        finally:
            os.close(directory_fd)
    finally:
        os.close(root_fd)


def _verify_claimed_target_below_root(
    target_parts: tuple[str, ...],
    target_directory_fd: int,
    root_fd: int,
    target_root: Path,
    expected_target_stat: os.stat_result,
) -> None:
    target_name = target_parts[-1]
    anchored_directory_fd = os.dup(root_fd)
    try:
        _require_path_match(
            condition=_path_matches_stat(target_root, os.fstat(root_fd)),
            message=TARGET_BELOW_ROOT_MESSAGE,
        )
        for part in target_parts[:-1]:
            next_directory_fd = os.open(
                part,
                os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW,
                dir_fd=anchored_directory_fd,
            )
            os.close(anchored_directory_fd)
            anchored_directory_fd = next_directory_fd

        _require_path_match(
            condition=_stats_match(os.fstat(anchored_directory_fd), os.fstat(target_directory_fd)),
            message=TARGET_BELOW_ROOT_MESSAGE,
        )
        claimed_target_stat = os.stat(target_name, dir_fd=target_directory_fd, follow_symlinks=False)
        anchored_target_stat = os.stat(target_name, dir_fd=anchored_directory_fd, follow_symlinks=False)
        _require_path_match(
            condition=_stats_match(claimed_target_stat, anchored_target_stat)
            and _stats_match(claimed_target_stat, expected_target_stat),
            message=TARGET_BELOW_ROOT_MESSAGE,
        )
    except OSError as exc:
        raise ValueError(TARGET_BELOW_ROOT_MESSAGE) from exc
    finally:
        os.close(anchored_directory_fd)


def _claim_target_at(
    opened_source: _OpenedSource,
    target_name: str,
    target_directory_fd: int,
    *,
    expected_source_content_hash: str | None,
    content_hasher: FileContentHasher,
) -> _ClaimedTarget:
    _verify_opened_source(opened_source)
    if opened_source.root_descriptor is None:
        return _claim_and_copy_at(
            opened_source,
            target_name,
            target_directory_fd,
            expected_source_content_hash=expected_source_content_hash,
            content_hasher=content_hasher,
        )
    try:
        _link_source(opened_source, target_name, target_directory_fd=target_directory_fd)
    except FileExistsError:
        raise
    except OSError, NotImplementedError:
        return _claim_and_copy_at(
            opened_source,
            target_name,
            target_directory_fd,
            expected_source_content_hash=expected_source_content_hash,
            content_hasher=content_hasher,
        )

    source_stat_after_claim = os.fstat(opened_source.file_descriptor)
    try:
        current_target_stat = os.stat(target_name, dir_fd=target_directory_fd, follow_symlinks=False)
    except FileNotFoundError as exc:
        raise ValueError(TARGET_BELOW_ROOT_MESSAGE) from exc
    if not (
        _stats_match(current_target_stat, opened_source.stat_result)
        and _file_states_match_except_ctime(source_stat_after_claim, opened_source.stat_result)
    ):
        _unlink_if_matches(target_name, opened_source.stat_result, dir_fd=target_directory_fd)
        raise ValueError(SOURCE_REPLACED_MESSAGE)
    try:
        _verify_expected_content_hash(
            opened_source.file_descriptor,
            expected_source_content_hash,
            content_hasher,
        )
    except BaseException:
        _unlink_if_matches(target_name, opened_source.stat_result, dir_fd=target_directory_fd)
        raise
    return _ClaimedTarget(opened_source.stat_result, source_stat_after_claim)


def _claim_and_copy_at(
    opened_source: _OpenedSource,
    target_name: str,
    target_directory_fd: int,
    *,
    expected_source_content_hash: str | None,
    content_hasher: FileContentHasher,
) -> _ClaimedTarget:
    try:
        target_fd = os.open(
            target_name,
            os.O_CREAT | os.O_EXCL | os.O_RDWR,
            dir_fd=target_directory_fd,
        )
    except FileNotFoundError as exc:
        raise ValueError(TARGET_BELOW_ROOT_MESSAGE) from exc
    try:
        source_stat_after_copy = _copy_open_source(
            opened_source.file_descriptor,
            opened_source.stat_result,
            target_fd,
            expected_source_content_hash=expected_source_content_hash,
            content_hasher=content_hasher,
        )
        claimed_target_stat = os.fstat(target_fd)
    except BaseException:
        _unlink_if_matches(target_name, os.fstat(target_fd), dir_fd=target_directory_fd)
        raise
    finally:
        os.close(target_fd)
    return _ClaimedTarget(
        stat_result=claimed_target_stat,
        source_stat_after_claim=source_stat_after_copy,
    )


def _copy_open_source(
    source_fd: int,
    source_stat: os.stat_result,
    target_fd: int,
    *,
    expected_source_content_hash: str | None,
    content_hasher: FileContentHasher,
) -> os.stat_result:
    if not _file_states_match(os.fstat(source_fd), source_stat):
        raise ValueError(SOURCE_REPLACED_MESSAGE)
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
    if not _file_states_match(os.fstat(source_fd), source_stat):
        raise ValueError(SOURCE_REPLACED_MESSAGE)
    os.fchmod(target_fd, stat.S_IMODE(source_stat.st_mode))
    os.utime(target_fd, ns=(source_stat.st_atime_ns, source_stat.st_mtime_ns))
    _verify_expected_content_hash(target_fd, expected_source_content_hash, content_hasher)
    _verify_expected_content_hash(source_fd, expected_source_content_hash, content_hasher)
    source_stat_after_copy = os.fstat(source_fd)
    if not _file_states_match(source_stat_after_copy, source_stat):
        raise ValueError(SOURCE_REPLACED_MESSAGE)
    return source_stat_after_copy


def _verify_source_below_root(
    opened_source: _OpenedSource,
    expected_source_stat: os.stat_result | None = None,
) -> None:
    if (
        opened_source.root_path is None
        or opened_source.root_descriptor is None
        or opened_source.parent_descriptor is None
        or opened_source.name is None
    ):
        return

    expected_stat = opened_source.stat_result if expected_source_stat is None else expected_source_stat
    anchored_directory_fd = os.dup(opened_source.root_descriptor)
    try:
        _require_path_match(
            condition=_path_matches_stat(opened_source.root_path, os.fstat(opened_source.root_descriptor)),
            message=SOURCE_BELOW_ROOT_MESSAGE,
        )
        for part in opened_source.parent_parts:
            next_directory_fd = _open_anchored_directory(
                part,
                dir_fd=anchored_directory_fd,
                message=SOURCE_BELOW_ROOT_MESSAGE,
            )
            os.close(anchored_directory_fd)
            anchored_directory_fd = next_directory_fd

        _require_path_match(
            condition=_stats_match(os.fstat(anchored_directory_fd), os.fstat(opened_source.parent_descriptor)),
            message=SOURCE_BELOW_ROOT_MESSAGE,
        )
        source_path_stat = os.stat(
            opened_source.name,
            dir_fd=opened_source.parent_descriptor,
            follow_symlinks=False,
        )
        anchored_source_stat = os.stat(
            opened_source.name,
            dir_fd=anchored_directory_fd,
            follow_symlinks=False,
        )
        _require_path_match(
            condition=_stats_match(source_path_stat, anchored_source_stat)
            and _file_states_match(source_path_stat, expected_stat),
            message=SOURCE_REPLACED_MESSAGE,
        )
    except FileNotFoundError:
        raise
    except ValueError:
        raise
    except OSError as exc:
        raise ValueError(SOURCE_BELOW_ROOT_MESSAGE) from exc
    finally:
        os.close(anchored_directory_fd)


def _verify_opened_source(
    opened_source: _OpenedSource,
    expected_source_stat: os.stat_result | None = None,
) -> None:
    expected_stat = opened_source.stat_result if expected_source_stat is None else expected_source_stat
    _verify_source_below_root(opened_source, expected_stat)
    if not _opened_source_state_is_unchanged(opened_source, expected_stat):
        raise ValueError(SOURCE_REPLACED_MESSAGE)


def _opened_source_state_is_unchanged(
    opened_source: _OpenedSource,
    expected_source_stat: os.stat_result,
) -> bool:
    return _file_states_match(os.fstat(opened_source.file_descriptor), expected_source_stat)


def _unlink_verified_source(
    opened_source: _OpenedSource,
    expected_source_stat: os.stat_result,
    *,
    expected_source_content_hash: str | None,
    content_hasher: FileContentHasher,
) -> None:
    _verify_opened_source(opened_source, expected_source_stat)
    _verify_expected_content_hash(
        opened_source.file_descriptor,
        expected_source_content_hash,
        content_hasher,
    )
    if opened_source.parent_descriptor is not None and opened_source.name is not None:
        if not _path_matches_source(
            opened_source.name,
            expected_source_stat,
            dir_fd=opened_source.parent_descriptor,
        ):
            raise ValueError(SOURCE_REPLACED_MESSAGE)
        os.unlink(opened_source.name, dir_fd=opened_source.parent_descriptor)
        return

    if not _path_matches_source(opened_source.path, expected_source_stat):
        raise ValueError(SOURCE_REPLACED_MESSAGE)
    opened_source.path.unlink()


def _verify_expected_content_hash(
    file_descriptor: int,
    expected_content_hash: str | None,
    content_hasher: FileContentHasher,
) -> None:
    """Reject a claimed file whose bytes differ from the apply-time snapshot."""
    if (
        expected_content_hash is not None
        and content_hasher.calculate_descriptor(file_descriptor) != expected_content_hash
    ):
        raise ValueError(SOURCE_REPLACED_MESSAGE)


def _unlink_if_matches(
    path: Path | str,
    expected_stat: os.stat_result,
    *,
    dir_fd: int | None = None,
) -> None:
    if not _path_matches_source(path, expected_stat, dir_fd=dir_fd):
        return
    with suppress(FileNotFoundError):
        os.unlink(path, dir_fd=dir_fd)


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


def _require_path_match(*, condition: bool, message: str) -> None:
    if not condition:
        raise ValueError(message)


def _path_matches_stat(path: Path, expected_stat: os.stat_result) -> bool:
    try:
        path_stat = path.stat(follow_symlinks=False)
    except OSError:
        return False
    return _stats_match(path_stat, expected_stat)


def _stats_match(left: os.stat_result, right: os.stat_result) -> bool:
    return left.st_dev == right.st_dev and left.st_ino == right.st_ino


def _file_states_match(left: os.stat_result, right: os.stat_result) -> bool:
    return _file_states_match_except_ctime(left, right) and stat_change_marker_ns(left) == stat_change_marker_ns(right)


def _file_states_match_except_ctime(left: os.stat_result, right: os.stat_result) -> bool:
    return _stats_match(left, right) and left.st_size == right.st_size and left.st_mtime_ns == right.st_mtime_ns


def _stat_matches_identity(source_stat: os.stat_result, expected_identity: FilesystemIdentity) -> bool:
    return (
        source_stat.st_dev == expected_identity.device_id
        and source_stat.st_ino == expected_identity.inode
        and source_stat.st_size == expected_identity.size
        and source_stat.st_mtime_ns == expected_identity.mtime_ns
        and stat_change_marker_ns(source_stat) == expected_identity.ctime_ns
    )
