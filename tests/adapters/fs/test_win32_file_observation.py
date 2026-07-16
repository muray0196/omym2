"""
Summary: Tests Windows retained-handle dispatch for content and inventory reads.
Why: Prevents junction-parent swaps from redirecting reviewed observation paths.
"""

from __future__ import annotations

import os
import shutil
import stat
import subprocess
from dataclasses import dataclass, field
from datetime import UTC, datetime
from typing import TYPE_CHECKING, Self

import pytest

from omym2.adapters.fs.file_content_snapshot_reader import (
    CONTENT_SNAPSHOT_SYMLINK_MESSAGE,
    FilesystemFileContentSnapshotReader,
)
from omym2.adapters.fs.source_inventory_reader import FilesystemSourceInventoryReader
from omym2.adapters.fs.win32_file_handles import (
    WIN32_PATH_CHANGED_MESSAGE,
    WIN32_REPARSE_POINT_MESSAGE,
    CtypesWin32FileHandleBackend,
    Win32FileHandle,
    Win32FileHandleBackend,
    Win32FileIdentity,
    stat_change_marker_ns,
    win32_directory_prefixes,
)
from omym2.features.common_ports import SourceInventoryRequest
from tests.fakes.content_fingerprint import calculate_content_fingerprint
from tests.fakes.runtime import FixedClock

if TYPE_CHECKING:
    from pathlib import Path
    from types import TracebackType

CAPTURED_TIME = datetime(2026, 1, 1, tzinfo=UTC)
INCLUDED_CONTENT = b"included"
OUTSIDE_CONTENT = b"outside"
SOURCE_CONTENT = b"source"
NATIVE_WINDOWS = os.name == "nt"
OBSERVATION_MUTATION_MESSAGE = "Observation fakes must not mutate files."


@dataclass(slots=True)
class PosixRetainedHandle:
    """Use a POSIX descriptor to exercise the Windows reader orchestration on Linux."""

    path: str
    final_path: str
    identity: Win32FileIdentity
    file_descriptor: int
    close_events: list[str]
    closed: bool = False

    def duplicate_binary_fd(self, *, writable: bool = False) -> int:
        """Return one duplicate descriptor for hashing."""
        assert not writable
        return os.dup(self.file_descriptor)

    def refresh_identity(self) -> Win32FileIdentity:
        """Return current state from the retained descriptor."""
        return self.verify_current(expected_path=self.path)

    def verify_current(
        self,
        *,
        expected_path: os.PathLike[str] | str | None = None,
        expected_identity: Win32FileIdentity | None = None,
    ) -> Win32FileIdentity:
        """Verify the fake path and exact state through its retained descriptor."""
        if self.closed:
            raise OSError(WIN32_PATH_CHANGED_MESSAGE)
        if expected_path is not None and os.path.abspath(_string_path(expected_path)) != self.path:  # noqa: PTH100  # Fake mirrors lexical adapter paths.
            raise FileNotFoundError(WIN32_PATH_CHANGED_MESSAGE)
        current = _win32_identity(os.fstat(self.file_descriptor))
        if expected_identity is not None and not expected_identity.same_file_state(current):
            raise FileNotFoundError(WIN32_PATH_CHANGED_MESSAGE)
        return current

    def delete_exact(self, *, expected_identity: Win32FileIdentity | None = None) -> None:
        """Reject mutation through an observation-only fake."""
        _ = expected_identity
        raise AssertionError(OBSERVATION_MUTATION_MESSAGE)

    def set_metadata(self, *, mode: int, atime_ns: int, mtime_ns: int) -> Win32FileIdentity:
        """Reject mutation through an observation-only fake."""
        _ = (mode, atime_ns, mtime_ns)
        raise AssertionError(OBSERVATION_MUTATION_MESSAGE)

    def close(self) -> None:
        """Close once and record reverse-lifetime behavior."""
        if self.closed:
            return
        os.close(self.file_descriptor)
        self.closed = True
        self.close_events.append(self.path)

    def __enter__(self) -> Self:
        """Retain the fake descriptor for a context lifetime."""
        return self

    def __exit__(
        self,
        exception_type: type[BaseException] | None,
        exception: BaseException | None,
        traceback: TracebackType | None,
    ) -> None:
        """Close the fake descriptor after a context lifetime."""
        self.close()


@dataclass(slots=True)
class PosixRecordingWin32Backend:
    """Open no-follow POSIX descriptors while recording Windows reader order."""

    open_events: list[tuple[str, str]] = field(default_factory=list)
    close_events: list[str] = field(default_factory=list)
    failing_path: str | None = None

    def open_entry(self, path: os.PathLike[str] | str) -> Win32FileHandle:
        """Open one ordinary file or directory without following a symlink."""
        return self._open("entry", path, expected_directory=None)

    def open_directory(self, path: os.PathLike[str] | str) -> Win32FileHandle:
        """Open one ordinary directory."""
        return self._open("directory", path, expected_directory=True)

    def open_file(self, path: os.PathLike[str] | str) -> Win32FileHandle:
        """Open one ordinary file."""
        return self._open("file", path, expected_directory=False)

    def open_source(self, path: os.PathLike[str] | str) -> Win32FileHandle:
        """Open one ordinary file for the unused mutation protocol role."""
        return self.open_file(path)

    def create_file_new(self, path: os.PathLike[str] | str) -> Win32FileHandle:
        """Reject mutation through an observation-only fake."""
        _ = path
        raise AssertionError(OBSERVATION_MUTATION_MESSAGE)

    def _open(
        self,
        role: str,
        path: os.PathLike[str] | str,
        *,
        expected_directory: bool | None,
    ) -> Win32FileHandle:
        lexical_path = os.path.abspath(_string_path(path))  # noqa: PTH100  # Fake mirrors lexical adapter paths.
        if lexical_path == self.failing_path:
            raise PermissionError(lexical_path)
        listed = os.lstat(lexical_path)
        if stat.S_ISLNK(listed.st_mode):
            raise ValueError(WIN32_REPARSE_POINT_MESSAGE)
        if expected_directory is True and not stat.S_ISDIR(listed.st_mode):
            raise NotADirectoryError(lexical_path)
        if expected_directory is False and not stat.S_ISREG(listed.st_mode):
            raise ValueError(lexical_path)
        flags = os.O_RDONLY | getattr(os, "O_NOFOLLOW", 0)
        if stat.S_ISDIR(listed.st_mode):
            flags |= os.O_DIRECTORY
        file_descriptor = os.open(lexical_path, flags)
        identity = _win32_identity(os.fstat(file_descriptor))
        self.open_events.append((role, lexical_path))
        return PosixRetainedHandle(
            path=lexical_path,
            final_path=lexical_path,
            identity=identity,
            file_descriptor=file_descriptor,
            close_events=self.close_events,
        )


@dataclass(slots=True)
class RenameAttemptBackend:
    """Attempt a parent swap immediately before the child file is opened."""

    delegate: Win32FileHandleBackend
    parent_path: Path
    retained_parent_path: Path
    rename_blocked: bool = False

    def open_entry(self, path: os.PathLike[str] | str) -> Win32FileHandle:
        """Delegate identity-only traversal."""
        return self.delegate.open_entry(path)

    def open_directory(self, path: os.PathLike[str] | str) -> Win32FileHandle:
        """Delegate retained parent opening."""
        return self.delegate.open_directory(path)

    def open_file(self, path: os.PathLike[str] | str) -> Win32FileHandle:
        """Try to rename the already retained parent before opening its child."""
        try:
            _ = self.parent_path.rename(self.retained_parent_path)
        except OSError:
            self.rename_blocked = True
        return self.delegate.open_file(path)

    def open_source(self, path: os.PathLike[str] | str) -> Win32FileHandle:
        """Delegate the unused mutation role."""
        return self.delegate.open_source(path)

    def create_file_new(self, path: os.PathLike[str] | str) -> Win32FileHandle:
        """Delegate the unused mutation role."""
        return self.delegate.create_file_new(path)


@pytest.mark.skipif(NATIVE_WINDOWS, reason="Uses a POSIX descriptor fake.")
def test_snapshot_injected_windows_backend_retains_parent_chain_before_file(tmp_path: Path) -> None:
    """Windows orchestration opens every parent before the file descriptor is hashed."""
    root_path = tmp_path / "source"
    parent_path = root_path / "nested"
    source_path = parent_path / "notes.bin"
    parent_path.mkdir(parents=True)
    _ = source_path.write_bytes(SOURCE_CONTENT)
    backend = PosixRecordingWin32Backend()
    reader = FilesystemFileContentSnapshotReader(
        clock=FixedClock(CAPTURED_TIME),
        windows_backend=backend,
    )

    snapshot = reader.capture(source_path, root=root_path)

    assert snapshot.content_hash == calculate_content_fingerprint(SOURCE_CONTENT)
    assert backend.open_events[-3:] == [
        ("directory", str(root_path)),
        ("directory", str(parent_path)),
        ("file", str(source_path)),
    ]
    assert backend.close_events[:3] == [str(source_path), str(parent_path), str(root_path)]


@pytest.mark.skipif(NATIVE_WINDOWS, reason="Uses a POSIX descriptor fake.")
def test_inventory_injected_windows_backend_prunes_exclusion_case_insensitively(tmp_path: Path) -> None:
    """Protected Windows roots are pruned before opening despite spelling case differences."""
    root_path = tmp_path / "source"
    protected_path = root_path / "Protected"
    included_path = root_path / "included.bin"
    protected_path.mkdir(parents=True)
    _ = (protected_path / "secret.bin").write_bytes(OUTSIDE_CONTENT)
    _ = included_path.write_bytes(INCLUDED_CONTENT)
    backend = PosixRecordingWin32Backend()
    reader = FilesystemSourceInventoryReader(windows_backend=backend)

    entries = reader.scan(
        SourceInventoryRequest(
            root=root_path,
            excluded_roots=(root_path / "protected",),
        )
    )

    assert [entry.relative_path for entry in entries] == [included_path.name]
    assert all(path != str(protected_path) for _role, path in backend.open_events)


@pytest.mark.skipif(NATIVE_WINDOWS, reason="Uses a POSIX descriptor fake.")
def test_inventory_prefix_open_failure_closes_every_retained_ancestor(tmp_path: Path) -> None:
    """A later prefix failure closes already-open ancestors before propagating."""
    root_path = tmp_path / "source"
    root_path.mkdir()
    prefixes = win32_directory_prefixes(root_path)
    backend = PosixRecordingWin32Backend(failing_path=prefixes[1])
    reader = FilesystemSourceInventoryReader(windows_backend=backend)

    with pytest.raises(PermissionError):
        _ = reader.scan(SourceInventoryRequest(root=root_path))

    assert backend.close_events == [prefixes[0]]


@pytest.mark.skipif(not NATIVE_WINDOWS, reason="Requires native junction semantics.")
def test_native_snapshot_parent_cannot_be_swapped_before_child_open(tmp_path: Path) -> None:
    """No-delete parent sharing blocks a junction-parent replacement at the child-open boundary."""
    root_path = tmp_path / "source"
    parent_path = root_path / "nested"
    retained_parent_path = root_path / "nested-retained"
    source_path = parent_path / "notes.bin"
    parent_path.mkdir(parents=True)
    _ = source_path.write_bytes(SOURCE_CONTENT)
    backend = RenameAttemptBackend(
        delegate=CtypesWin32FileHandleBackend(),
        parent_path=parent_path,
        retained_parent_path=retained_parent_path,
    )
    reader = FilesystemFileContentSnapshotReader(
        clock=FixedClock(CAPTURED_TIME),
        windows_backend=backend,
    )

    try:
        snapshot = reader.capture(source_path, root=root_path)
    finally:
        if retained_parent_path.exists() and not parent_path.exists():
            _ = retained_parent_path.rename(parent_path)

    assert backend.rename_blocked
    assert snapshot.content_hash == calculate_content_fingerprint(SOURCE_CONTENT)


@pytest.mark.skipif(not NATIVE_WINDOWS, reason="Requires native junction semantics.")
def test_native_observation_rejects_junction_parent_without_reading_target(tmp_path: Path) -> None:
    """Snapshot and inventory open the junction itself and never enumerate or hash its target."""
    root_path = tmp_path / "source"
    outside_path = tmp_path / "outside"
    junction_path = root_path / "junction"
    outside_file = outside_path / "outside.bin"
    included_file = root_path / "included.bin"
    root_path.mkdir()
    outside_path.mkdir()
    _ = outside_file.write_bytes(OUTSIDE_CONTENT)
    _ = included_file.write_bytes(INCLUDED_CONTENT)
    _create_windows_junction(junction_path, outside_path)

    reader = FilesystemFileContentSnapshotReader(clock=FixedClock(CAPTURED_TIME))
    with pytest.raises(ValueError, match=CONTENT_SNAPSHOT_SYMLINK_MESSAGE):
        _ = reader.capture(junction_path / outside_file.name, root=root_path)

    entries = FilesystemSourceInventoryReader().scan(SourceInventoryRequest(root=root_path))
    assert [entry.relative_path for entry in entries] == [included_file.name]


def _win32_identity(stat_result: os.stat_result) -> Win32FileIdentity:
    return Win32FileIdentity(
        device_id=stat_result.st_dev,
        inode=stat_result.st_ino,
        size=stat_result.st_size,
        mtime_ns=stat_result.st_mtime_ns,
        ctime_ns=stat_change_marker_ns(stat_result),
        volume_serial_number=stat_result.st_dev,
        file_id=stat_result.st_ino.to_bytes(16, byteorder="little", signed=False),
        attributes=0,
        reparse_tag=0,
        is_directory=stat.S_ISDIR(stat_result.st_mode),
    )


def _string_path(path: os.PathLike[str] | str) -> str:
    return path if isinstance(path, str) else path.__fspath__()


def _create_windows_junction(junction_path: Path, target_path: Path) -> None:
    command_interpreter = shutil.which("cmd.exe")
    if command_interpreter is None:
        pytest.fail("The native Windows command interpreter is unavailable.")
    # One token per argument: a single pre-quoted string gets re-escaped by
    # subprocess in a way cmd.exe builtins cannot parse.
    completed = subprocess.run(  # noqa: S603  # Fixed native test command with controlled temporary paths.
        [command_interpreter, "/d", "/c", "mklink", "/J", str(junction_path), str(target_path)],
        check=False,
        capture_output=True,
        text=True,
    )
    if completed.returncode != 0:
        details = f"stdout={completed.stdout.strip()!r} stderr={completed.stderr.strip()!r}"
        pytest.fail(f"Could not create a native directory junction. {details}")
