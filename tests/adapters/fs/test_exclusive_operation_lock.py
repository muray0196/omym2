"""
Summary: Tests the native application-root exclusive operation lock.
Why: Proves contention, release, crash safety, persistence, and Windows semantics.
"""

from __future__ import annotations

import errno
import os
import subprocess
import sys
from dataclasses import dataclass, field
from pathlib import Path
from typing import TYPE_CHECKING, cast

import pytest

from omym2.adapters.fs.exclusive_operation_lock import (
    WINDOWS_LOCK_BYTE_COUNT,
    WINDOWS_LOCK_BYTE_OFFSET,
    WINDOWS_LOCK_SENTINEL,
    FilesystemExclusiveOperationLock,
    WindowsByteRangeLockBackend,
)
from omym2.config import EXCLUSIVE_OPERATION_LOCK_FILE_NAME
from omym2.features.common_ports import (
    ExclusiveOperationBusyError,
    ExclusiveOperationRequest,
)
from tests.adapters.fs.exclusive_operation_lock_process import LOCK_HELD_MARKER

if TYPE_CHECKING:
    from typing import BinaryIO, TextIO

HELPER_PROCESS_FILE = Path(__file__).with_name("exclusive_operation_lock_process.py")
PROCESS_TIMEOUT_SECONDS = 5.0
TEST_OPERATION_NAME = "test_operation"
WINDOWS_LOCK_MODE = 11
WINDOWS_UNLOCK_MODE = 12
EXPECTED_BACKEND_ACQUISITION_COUNT = 2
REQUEST = ExclusiveOperationRequest(operation_name=TEST_OPERATION_NAME)


def test_independent_process_reports_immediate_contention(tmp_path: Path) -> None:
    """A second process cannot enter while the native owner retains its handle."""
    lock_file = tmp_path / EXCLUSIVE_OPERATION_LOCK_FILE_NAME
    process = _start_holding_process(lock_file)
    try:
        with (
            pytest.raises(ExclusiveOperationBusyError) as error,
            FilesystemExclusiveOperationLock(lock_file).hold(REQUEST),
        ):
            pytest.fail("A contending process entered the exclusive lease.")

        assert error.value.request == REQUEST
    finally:
        _release_holding_process(process)


def test_independent_process_normal_release_allows_next_owner(tmp_path: Path) -> None:
    """Leaving the owner context releases native exclusion for another process."""
    lock_file = tmp_path / EXCLUSIVE_OPERATION_LOCK_FILE_NAME
    process = _start_holding_process(lock_file)

    _release_holding_process(process)

    with FilesystemExclusiveOperationLock(lock_file).hold(REQUEST) as lease:
        assert lease.request == REQUEST


def test_independent_process_crash_releases_native_lock(tmp_path: Path) -> None:
    """Terminating a lock owner releases exclusion without stale-owner recovery."""
    lock_file = tmp_path / EXCLUSIVE_OPERATION_LOCK_FILE_NAME
    process = _start_holding_process(lock_file)

    process.kill()
    _ = process.communicate(timeout=PROCESS_TIMEOUT_SECONDS)

    with FilesystemExclusiveOperationLock(lock_file).hold(REQUEST) as lease:
        assert lease.request == REQUEST


def test_unlocked_lock_file_persists_and_can_be_reused(tmp_path: Path) -> None:
    """File presence after release is harmless and never treated as ownership."""
    lock_file = tmp_path / EXCLUSIVE_OPERATION_LOCK_FILE_NAME
    lock = FilesystemExclusiveOperationLock(lock_file)

    with lock.hold(REQUEST):
        assert lock_file.is_file()

    assert lock_file.is_file()
    with lock.hold(REQUEST):
        assert lock_file.is_file()


def test_same_process_guard_reports_busy_for_permissive_native_backend(tmp_path: Path) -> None:
    """Two adapter instances still contend when the native API permits reentry."""
    backend = PermissiveLockBackend()
    lock_file = tmp_path / EXCLUSIVE_OPERATION_LOCK_FILE_NAME
    first = FilesystemExclusiveOperationLock(lock_file, backend=backend)
    second = FilesystemExclusiveOperationLock(lock_file, backend=backend)

    with first.hold(REQUEST), pytest.raises(ExclusiveOperationBusyError), second.hold(REQUEST):
        pytest.fail("The same-process contender entered the lease.")

    with second.hold(REQUEST):
        pass

    assert backend.acquire_count == EXPECTED_BACKEND_ACQUISITION_COUNT
    assert backend.release_count == EXPECTED_BACKEND_ACQUISITION_COUNT


def test_windows_backend_uses_first_sentinel_byte_and_explicit_unlock(tmp_path: Path) -> None:
    """Windows locking retains one non-empty byte and resets the byte offset."""
    lock_file = tmp_path / EXCLUSIVE_OPERATION_LOCK_FILE_NAME
    recording_locking = RecordingWindowsLocking()
    backend = WindowsByteRangeLockBackend(
        locking=recording_locking,
        lock_nonblocking=WINDOWS_LOCK_MODE,
        unlock=WINDOWS_UNLOCK_MODE,
    )

    with lock_file.open("a+b", buffering=0) as handle:
        backend.acquire(handle)
        backend.release(handle)

    assert lock_file.read_bytes() == WINDOWS_LOCK_SENTINEL
    assert recording_locking.calls == [
        (WINDOWS_LOCK_MODE, WINDOWS_LOCK_BYTE_COUNT, WINDOWS_LOCK_BYTE_OFFSET),
        (WINDOWS_UNLOCK_MODE, WINDOWS_LOCK_BYTE_COUNT, WINDOWS_LOCK_BYTE_OFFSET),
    ]


def test_windows_contention_is_translated_and_releases_same_process_guard(tmp_path: Path) -> None:
    """A Windows byte-lock conflict becomes the shared typed busy error."""
    lock_file = tmp_path / EXCLUSIVE_OPERATION_LOCK_FILE_NAME
    busy_backend = WindowsByteRangeLockBackend(
        locking=BusyWindowsLocking(),
        lock_nonblocking=WINDOWS_LOCK_MODE,
        unlock=WINDOWS_UNLOCK_MODE,
    )

    with (
        pytest.raises(ExclusiveOperationBusyError) as error,
        FilesystemExclusiveOperationLock(lock_file, backend=busy_backend).hold(REQUEST),
    ):
        pytest.fail("The simulated Windows contender entered the lease.")

    assert error.value.request == REQUEST
    with FilesystemExclusiveOperationLock(lock_file, backend=PermissiveLockBackend()).hold(REQUEST):
        pass


def _start_holding_process(lock_file: Path) -> subprocess.Popen[str]:
    process = subprocess.Popen(  # noqa: S603  # Fixed interpreter and repository-owned helper script.
        [sys.executable, str(HELPER_PROCESS_FILE), str(lock_file)],
        stdin=subprocess.PIPE,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
    )
    assert process.stdout is not None
    process_stdout = cast("TextIO", process.stdout)
    marker = process_stdout.readline().strip()
    if marker != LOCK_HELD_MARKER:
        _, stderr = process.communicate(timeout=PROCESS_TIMEOUT_SECONDS)
        pytest.fail(f"Lock helper failed before acquisition: {stderr}")
    return process


def _release_holding_process(process: subprocess.Popen[str]) -> None:
    assert process.stdin is not None
    _ = process.stdin.write("\n")
    _ = process.stdin.flush()
    _, stderr = process.communicate(timeout=PROCESS_TIMEOUT_SECONDS)
    assert process.returncode == 0, stderr


@dataclass(slots=True)
class PermissiveLockBackend:
    """Native-backend fake that allows same-process reentry without exclusion."""

    acquire_count: int = 0
    release_count: int = 0

    def acquire(self, handle: BinaryIO) -> None:
        """Record an acquisition without providing native exclusion."""
        _ = handle
        self.acquire_count += 1

    def release(self, handle: BinaryIO) -> None:
        """Record a release without providing native exclusion."""
        _ = handle
        self.release_count += 1


@dataclass(slots=True)
class RecordingWindowsLocking:
    """Record Windows locking mode, length, and current file offset."""

    calls: list[tuple[int, int, int]] = field(default_factory=list)

    def __call__(self, file_descriptor: int, mode: int, byte_count: int) -> None:
        """Capture one msvcrt.locking-compatible invocation."""
        offset = os.lseek(file_descriptor, 0, os.SEEK_CUR)
        self.calls.append((mode, byte_count, offset))


@dataclass(frozen=True, slots=True)
class BusyWindowsLocking:
    """Simulate msvcrt contention on nonblocking byte-range acquisition."""

    def __call__(self, _file_descriptor: int, _mode: int, _byte_count: int) -> None:
        """Raise the errno emitted for a contended Windows lock."""
        raise OSError(errno.EACCES, "simulated lock contention")
