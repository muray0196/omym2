"""
Summary: Inventories every regular file below one retained source root.
Why: Gives companion and unprocessed classification complete symlink-safe input.
"""

from __future__ import annotations

import errno
import ntpath
import os
import stat
from dataclasses import dataclass, field
from pathlib import Path
from typing import TYPE_CHECKING

from omym2.adapters.fs.win32_file_handles import (
    default_win32_file_handle_backend,
    win32_directory_prefixes,
)
from omym2.features.common_ports import SourceInventoryEntry, SourceInventoryRequest

if TYPE_CHECKING:
    from collections.abc import Iterator

    from omym2.adapters.fs.win32_file_handles import Win32FileHandle, Win32FileHandleBackend
    from omym2.features.common_ports import FileSystemPath

SOURCE_INVENTORY_CHANGED_MESSAGE = "Source inventory root or directory changed during discovery."
SOURCE_INVENTORY_ROOT_SYMLINK_MESSAGE = "Source inventory root must not be a symbolic link."
SOURCE_INVENTORY_UNSUPPORTED_MESSAGE = "Anchored source inventory operations are not supported."

_OPEN_SUPPORTS_DIR_FD = os.open in os.supports_dir_fd
_SCANDIR_SUPPORTS_FD = os.scandir in os.supports_fd
_STAT_SUPPORTS_DIR_FD = os.stat in os.supports_dir_fd
_STAT_SUPPORTS_NOFOLLOW = os.stat in os.supports_follow_symlinks


@dataclass(frozen=True, slots=True)
class FilesystemSourceInventoryReader:
    """Discover regular files without following file or directory symlinks."""

    windows_backend: Win32FileHandleBackend | None = field(
        default_factory=default_win32_file_handle_backend,
        repr=False,
        compare=False,
    )

    def scan(self, request: SourceInventoryRequest) -> tuple[SourceInventoryEntry, ...]:
        """Return source-relative ordered entries outside excluded subtrees."""
        root_path = _absolute_path(request.root)
        excluded_roots, excludes_source_root = _relative_excluded_roots(root_path, request.excluded_roots)
        if self.windows_backend is not None:
            traversal = _InventoryTraversal(root_path, _normalize_windows_exclusions(excluded_roots), [])
            _scan_with_windows_handles(
                traversal,
                self.windows_backend,
                excludes_source_root=excludes_source_root,
            )
            return tuple(sorted(traversal.entries, key=lambda entry: entry.relative_path))

        traversal = _InventoryTraversal(root_path, excluded_roots, [])
        root_identity = root_path.stat(follow_symlinks=False)
        if _is_link_like(root_identity):
            raise ValueError(SOURCE_INVENTORY_ROOT_SYMLINK_MESSAGE)
        if not stat.S_ISDIR(root_identity.st_mode):
            raise NotADirectoryError(root_path)
        if excludes_source_root:
            return ()

        if _descriptor_inventory_supported():
            _scan_with_descriptors(traversal, root_identity)
        else:
            _scan_with_paths(traversal, root_identity)

        return tuple(sorted(traversal.entries, key=lambda entry: entry.relative_path))


def _scan_with_windows_handles(
    traversal: _InventoryTraversal,
    backend: Win32FileHandleBackend,
    *,
    excludes_source_root: bool,
) -> None:
    root_handles: list[Win32FileHandle] = []
    try:
        root_handles.extend(backend.open_directory(prefix) for prefix in win32_directory_prefixes(traversal.root_path))
    except (NotADirectoryError, ValueError) as exc:
        _close_windows_handles(root_handles, primary_error=exc)
        raise ValueError(SOURCE_INVENTORY_ROOT_SYMLINK_MESSAGE) from exc
    except BaseException as exc:
        _close_windows_handles(root_handles, primary_error=exc)
        raise
    root_handle = root_handles[-1]
    try:
        if excludes_source_root:
            return
        _scan_windows_directory(
            traversal=traversal,
            backend=backend,
            directory_handle=root_handle,
            relative_parts=(),
        )
        for handle in root_handles:
            _require_windows_directory_current(handle)
    finally:
        _close_windows_handles(root_handles)


def _close_windows_handles(
    handles: list[Win32FileHandle],
    *,
    primary_error: BaseException | None = None,
) -> None:
    cleanup_error: BaseException | None = None
    for handle in reversed(handles):
        try:
            handle.close()
        except BaseException as close_error:  # noqa: BLE001  # Every retained prefix still needs closing.
            if primary_error is not None:
                primary_error.add_note(f"Retained Win32 prefix close also failed: {close_error!r}")
            elif cleanup_error is None:
                cleanup_error = close_error
            else:
                cleanup_error.add_note(f"Another retained Win32 prefix close also failed: {close_error!r}")
    if cleanup_error is not None:
        raise cleanup_error


def _scan_windows_directory(
    *,
    traversal: _InventoryTraversal,
    backend: Win32FileHandleBackend,
    directory_handle: Win32FileHandle,
    relative_parts: tuple[str, ...],
) -> None:
    directory_path = traversal.root_path.joinpath(*relative_parts)
    _require_windows_directory_current(directory_handle)
    entry_names = _read_windows_entry_names(directory_path)

    for entry_name in entry_names:
        _scan_windows_entry(
            traversal=traversal,
            backend=backend,
            relative_parts=relative_parts,
            entry_name=entry_name,
        )

    _require_windows_directory_current(directory_handle)


def _read_windows_entry_names(directory_path: Path) -> tuple[str, ...]:
    try:
        with os.scandir(directory_path) as iterator:
            return tuple(sorted(entry.name for entry in iterator))
    except (FileNotFoundError, NotADirectoryError) as exc:
        raise ValueError(SOURCE_INVENTORY_CHANGED_MESSAGE) from exc


def _scan_windows_entry(
    *,
    traversal: _InventoryTraversal,
    backend: Win32FileHandleBackend,
    relative_parts: tuple[str, ...],
    entry_name: str,
) -> None:
    entry_parts = (*relative_parts, entry_name)
    normalized_entry_parts = tuple(ntpath.normcase(part) for part in entry_parts)
    if normalized_entry_parts in traversal.excluded_roots:
        return
    entry_path = traversal.root_path.joinpath(*entry_parts)
    try:
        entry_handle = backend.open_entry(entry_path)
    except FileNotFoundError, ValueError:
        return
    try:
        if entry_handle.identity.is_regular_file:
            traversal.entries.append(
                SourceInventoryEntry(
                    path=str(entry_path),
                    relative_path="/".join(entry_parts),
                )
            )
        elif entry_handle.identity.is_directory:
            _scan_windows_directory(
                traversal=traversal,
                backend=backend,
                directory_handle=entry_handle,
                relative_parts=entry_parts,
            )
    finally:
        entry_handle.close()


def _normalize_windows_exclusions(
    excluded_roots: frozenset[tuple[str, ...]],
) -> frozenset[tuple[str, ...]]:
    return frozenset(tuple(ntpath.normcase(part) for part in relative_root) for relative_root in excluded_roots)


def _require_windows_directory_current(directory_handle: Win32FileHandle) -> None:
    try:
        current_identity = directory_handle.refresh_identity()
    except (OSError, ValueError) as exc:
        raise ValueError(SOURCE_INVENTORY_CHANGED_MESSAGE) from exc
    if not directory_handle.identity.same_object(current_identity):
        raise ValueError(SOURCE_INVENTORY_CHANGED_MESSAGE)


def _scan_with_descriptors(traversal: _InventoryTraversal, root_identity: os.stat_result) -> None:
    _require_descriptor_support()
    root_path = traversal.root_path
    root_descriptor = _open_root(root_path)
    try:
        if not _same_directory_entry(root_identity, os.fstat(root_descriptor)):
            raise ValueError(SOURCE_INVENTORY_CHANGED_MESSAGE)
        _scan_descriptor_directory(
            traversal=traversal,
            directory_descriptor=root_descriptor,
            relative_parts=(),
        )
        try:
            completed_root_identity = root_path.stat(follow_symlinks=False)
        except OSError as exc:
            raise ValueError(SOURCE_INVENTORY_CHANGED_MESSAGE) from exc
        if not _same_directory_entry(completed_root_identity, os.fstat(root_descriptor)):
            raise ValueError(SOURCE_INVENTORY_CHANGED_MESSAGE)
    finally:
        os.close(root_descriptor)


def _scan_with_paths(traversal: _InventoryTraversal, root_identity: os.stat_result) -> None:
    _scan_path_directory(
        traversal=traversal,
        directory_path=traversal.root_path,
        directory_identity=root_identity,
        relative_parts=(),
    )
    _require_same_path_directory(traversal.root_path, root_identity)


def _absolute_path(path: FileSystemPath) -> Path:
    # Path.resolve() would follow a selected root before the no-follow check.
    return Path(os.path.abspath(os.fspath(path)))  # noqa: PTH100  # Require lexical normalization only.


def _relative_excluded_roots(
    root_path: Path,
    excluded_roots: tuple[FileSystemPath, ...],
) -> tuple[frozenset[tuple[str, ...]], bool]:
    relative_roots: set[tuple[str, ...]] = set()
    for excluded_root in excluded_roots:
        excluded_path = _absolute_path(excluded_root)
        try:
            relative_path = excluded_path.relative_to(root_path)
        except ValueError:
            continue
        if not relative_path.parts:
            return frozenset(), True
        relative_roots.add(relative_path.parts)
    return frozenset(relative_roots), False


def _require_descriptor_support() -> None:
    if not _descriptor_inventory_supported():
        raise ValueError(SOURCE_INVENTORY_UNSUPPORTED_MESSAGE)


def _descriptor_inventory_supported() -> bool:
    return (
        _OPEN_SUPPORTS_DIR_FD
        and _SCANDIR_SUPPORTS_FD
        and _STAT_SUPPORTS_DIR_FD
        and _STAT_SUPPORTS_NOFOLLOW
        and hasattr(os, "O_DIRECTORY")
        and hasattr(os, "O_NOFOLLOW")
    )


def _open_root(root_path: Path) -> int:
    try:
        return _open_directory(root_path)
    except ValueError as exc:
        raise ValueError(SOURCE_INVENTORY_ROOT_SYMLINK_MESSAGE) from exc


def _open_directory(path: Path | str, *, dir_fd: int | None = None) -> int:
    try:
        return os.open(
            path,
            os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW,
            dir_fd=dir_fd,
        )
    except OSError as exc:
        if exc.errno in {errno.ELOOP, errno.ENOTDIR}:
            raise ValueError(SOURCE_INVENTORY_CHANGED_MESSAGE) from exc
        raise


@dataclass(frozen=True, slots=True)
class _InventoryTraversal:
    """Shared mechanical state for one recursive source inventory."""

    root_path: Path
    excluded_roots: frozenset[tuple[str, ...]]
    entries: list[SourceInventoryEntry]


@dataclass(frozen=True, slots=True)
class _DirectoryEntryObservation:
    """One directory entry retained long enough for safe recursive traversal."""

    name: str
    identity: os.stat_result
    relative_parts: tuple[str, ...]


def _scan_descriptor_directory(
    *,
    traversal: _InventoryTraversal,
    directory_descriptor: int,
    relative_parts: tuple[str, ...],
) -> None:
    with os.scandir(directory_descriptor) as iterator:
        directory_entries = sorted(iterator, key=lambda entry: entry.name)

    for entry in directory_entries:
        _scan_descriptor_entry(
            traversal=traversal,
            entry=entry,
            directory_descriptor=directory_descriptor,
            relative_parts=relative_parts,
        )


def _scan_descriptor_entry(
    *,
    traversal: _InventoryTraversal,
    entry: os.DirEntry[str],
    directory_descriptor: int,
    relative_parts: tuple[str, ...],
) -> None:
    entry_parts = (*relative_parts, entry.name)
    if entry_parts in traversal.excluded_roots:
        return
    try:
        entry_identity = entry.stat(follow_symlinks=False)
    except FileNotFoundError:
        return
    if _is_link_like(entry_identity):
        return
    if stat.S_ISREG(entry_identity.st_mode):
        traversal.entries.append(
            SourceInventoryEntry(
                path=str(traversal.root_path.joinpath(*entry_parts)),
                relative_path="/".join(entry_parts),
            )
        )
        return
    if stat.S_ISDIR(entry_identity.st_mode):
        _scan_descriptor_child_directory(
            traversal=traversal,
            observation=_DirectoryEntryObservation(entry.name, entry_identity, entry_parts),
            parent_descriptor=directory_descriptor,
        )


def _scan_descriptor_child_directory(
    *,
    traversal: _InventoryTraversal,
    observation: _DirectoryEntryObservation,
    parent_descriptor: int,
) -> None:
    try:
        child_descriptor = _open_directory(observation.name, dir_fd=parent_descriptor)
    except ValueError:
        return
    try:
        child_identity = os.fstat(child_descriptor)
        _require_same_directory_entry(observation.identity, child_identity)
        _scan_descriptor_directory(
            traversal=traversal,
            directory_descriptor=child_descriptor,
            relative_parts=observation.relative_parts,
        )
        completed_child_identity = _read_child_identity(observation.name, parent_descriptor)
        _require_same_directory_entry(completed_child_identity, child_identity)
    finally:
        os.close(child_descriptor)


def _read_child_identity(entry_name: str, parent_descriptor: int) -> os.stat_result:
    try:
        return os.stat(
            entry_name,
            dir_fd=parent_descriptor,
            follow_symlinks=False,
        )
    except OSError as exc:
        raise ValueError(SOURCE_INVENTORY_CHANGED_MESSAGE) from exc


def _require_same_directory_entry(left: os.stat_result, right: os.stat_result) -> None:
    if not _same_directory_entry(left, right):
        raise ValueError(SOURCE_INVENTORY_CHANGED_MESSAGE)


def _same_directory_entry(left: os.stat_result, right: os.stat_result) -> bool:
    return (
        stat.S_ISDIR(left.st_mode)
        and stat.S_ISDIR(right.st_mode)
        and left.st_dev == right.st_dev
        and left.st_ino == right.st_ino
    )


def _scan_path_directory(
    *,
    traversal: _InventoryTraversal,
    directory_path: Path,
    directory_identity: os.stat_result,
    relative_parts: tuple[str, ...],
) -> None:
    _require_same_path_directory(directory_path, directory_identity)
    try:
        with os.scandir(directory_path) as iterator:
            observations = _observe_path_entries(iterator, traversal.excluded_roots, relative_parts)
    except (FileNotFoundError, NotADirectoryError) as exc:
        raise ValueError(SOURCE_INVENTORY_CHANGED_MESSAGE) from exc
    _require_same_path_directory(directory_path, directory_identity)

    for observation in observations:
        if _is_link_like(observation.identity):
            continue
        if stat.S_ISREG(observation.identity.st_mode):
            traversal.entries.append(
                SourceInventoryEntry(
                    path=str(traversal.root_path.joinpath(*observation.relative_parts)),
                    relative_path="/".join(observation.relative_parts),
                )
            )
            continue
        if stat.S_ISDIR(observation.identity.st_mode):
            _scan_path_directory(
                traversal=traversal,
                directory_path=traversal.root_path.joinpath(*observation.relative_parts),
                directory_identity=observation.identity,
                relative_parts=observation.relative_parts,
            )

    _require_same_path_directory(directory_path, directory_identity)


def _observe_path_entries(
    iterator: Iterator[os.DirEntry[str]],
    excluded_roots: frozenset[tuple[str, ...]],
    relative_parts: tuple[str, ...],
) -> tuple[_DirectoryEntryObservation, ...]:
    observations: list[_DirectoryEntryObservation] = []
    for entry in sorted(iterator, key=lambda candidate: candidate.name):
        entry_parts = (*relative_parts, entry.name)
        if entry_parts in excluded_roots:
            continue
        try:
            entry_identity = entry.stat(follow_symlinks=False)
        except FileNotFoundError:
            continue
        observations.append(_DirectoryEntryObservation(entry.name, entry_identity, entry_parts))
    return tuple(observations)


def _require_same_path_directory(directory_path: Path, expected: os.stat_result) -> None:
    try:
        observed = directory_path.stat(follow_symlinks=False)
    except OSError as exc:
        raise ValueError(SOURCE_INVENTORY_CHANGED_MESSAGE) from exc
    if _is_link_like(observed) or not _same_directory_entry(expected, observed):
        raise ValueError(SOURCE_INVENTORY_CHANGED_MESSAGE)


def _is_link_like(identity: os.stat_result) -> bool:
    if stat.S_ISLNK(identity.st_mode):
        return True
    file_attributes = getattr(identity, "st_file_attributes", None)
    return isinstance(file_attributes, int) and bool(file_attributes & stat.FILE_ATTRIBUTE_REPARSE_POINT)
