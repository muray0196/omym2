"""
Summary: Implements the application-root cross-process exclusive operation lock.
Why: Serializes Web and CLI mutations with crash-safe native file locking.
"""

from __future__ import annotations

import errno
import os
from contextlib import contextmanager
from dataclasses import dataclass, field
from importlib import import_module
from threading import Lock
from typing import TYPE_CHECKING, Protocol, cast

from omym2.features.common_ports import (
    ExclusiveOperationBusyError,
    ExclusiveOperationLease,
)

if TYPE_CHECKING:
    from collections.abc import Callable, Generator
    from pathlib import Path
    from typing import BinaryIO

    from omym2.features.common_ports import ExclusiveOperationRequest

LOCK_BUSY_MESSAGE = "Another state-changing operation is already in progress."
WINDOWS_LOCK_BYTE_COUNT = 1
WINDOWS_LOCK_BYTE_OFFSET = 0
WINDOWS_LOCK_SENTINEL = b"\0"
_BUSY_ERRNOS = frozenset({errno.EACCES, errno.EAGAIN, errno.EDEADLK})
_WINDOWS_BUSY_ERROR_CODES = frozenset({33, 36})
_HELD_LOCK_PATHS: set[Path] = set()
_HELD_LOCK_PATHS_GUARD = Lock()


class _NativeLockBusyError(OSError):
    """Signal native nonblocking lock contention inside the adapter."""


class _NativeLockBackend(Protocol):
    """Platform-specific operations over one retained binary file handle."""

    def acquire(self, handle: BinaryIO) -> None:
        """Acquire the native lock without waiting or raise on contention."""
        ...

    def release(self, handle: BinaryIO) -> None:
        """Release the native lock held by the file handle."""
        ...


class _UnixLockModule(Protocol):
    """Typed subset of fcntl used by the native backend factory."""

    LOCK_EX: int
    LOCK_NB: int
    LOCK_UN: int

    def flock(self, file_descriptor: int, operation: int) -> object:
        """Apply one flock operation."""
        ...


class _WindowsLockModule(Protocol):
    """Typed subset of msvcrt used by the native backend factory."""

    LK_NBLCK: int
    LK_UNLCK: int

    def locking(self, file_descriptor: int, mode: int, byte_count: int) -> object:
        """Apply one byte-range locking operation."""
        ...


@dataclass(frozen=True, slots=True)
class _UnixFlockBackend:
    """Use Unix flock over the complete retained file handle."""

    flock: Callable[[int, int], object]
    lock_exclusive_nonblocking: int
    unlock: int

    def acquire(self, handle: BinaryIO) -> None:
        """Acquire an exclusive nonblocking flock."""
        try:
            _ = self.flock(handle.fileno(), self.lock_exclusive_nonblocking)
        except OSError as exc:
            if exc.errno in _BUSY_ERRNOS:
                raise _NativeLockBusyError from exc
            raise

    def release(self, handle: BinaryIO) -> None:
        """Release the flock before its retained handle closes."""
        _ = self.flock(handle.fileno(), self.unlock)


@dataclass(frozen=True, slots=True)
class WindowsByteRangeLockBackend:
    """Use a Windows nonblocking byte-range lock over a sentinel byte."""

    locking: Callable[[int, int, int], object]
    lock_nonblocking: int
    unlock: int

    def acquire(self, handle: BinaryIO) -> None:
        """Ensure and nonblockingly lock the first sentinel byte."""
        _ensure_windows_lock_sentinel(handle)
        try:
            _ = self.locking(handle.fileno(), self.lock_nonblocking, WINDOWS_LOCK_BYTE_COUNT)
        except OSError as exc:
            if exc.errno in _BUSY_ERRNOS or getattr(exc, "winerror", None) in _WINDOWS_BUSY_ERROR_CODES:
                raise _NativeLockBusyError from exc
            raise

    def release(self, handle: BinaryIO) -> None:
        """Unlock the first sentinel byte before its retained handle closes."""
        _ = handle.seek(WINDOWS_LOCK_BYTE_OFFSET, os.SEEK_SET)
        _ = self.locking(handle.fileno(), self.unlock, WINDOWS_LOCK_BYTE_COUNT)


def _native_lock_backend() -> _NativeLockBackend:
    if os.name == "nt":
        windows_lock_module = cast("_WindowsLockModule", cast("object", import_module("msvcrt")))
        return WindowsByteRangeLockBackend(
            locking=windows_lock_module.locking,
            lock_nonblocking=windows_lock_module.LK_NBLCK,
            unlock=windows_lock_module.LK_UNLCK,
        )

    unix_lock_module = cast("_UnixLockModule", cast("object", import_module("fcntl")))
    return _UnixFlockBackend(
        flock=unix_lock_module.flock,
        lock_exclusive_nonblocking=unix_lock_module.LOCK_EX | unix_lock_module.LOCK_NB,
        unlock=unix_lock_module.LOCK_UN,
    )


@dataclass(frozen=True, slots=True)
class FilesystemExclusiveOperationLock:
    """Hold one native nonblocking lock for the complete mutation lifetime."""

    lock_file: Path
    backend: _NativeLockBackend = field(default_factory=_native_lock_backend, repr=False, compare=False)

    @contextmanager
    def hold(self, request: ExclusiveOperationRequest) -> Generator[ExclusiveOperationLease]:
        """Yield a lease while retaining both process-local and native exclusion."""
        lock_path = self.lock_file.expanduser().resolve(strict=False)
        if not _try_claim_process_lock_path(lock_path):
            raise ExclusiveOperationBusyError(request, LOCK_BUSY_MESSAGE)

        handle: BinaryIO | None = None
        acquired = False
        try:
            lock_path.parent.mkdir(parents=True, exist_ok=True)
            handle = lock_path.open("a+b", buffering=0)
            try:
                self.backend.acquire(handle)
            except _NativeLockBusyError as exc:
                raise ExclusiveOperationBusyError(request, LOCK_BUSY_MESSAGE) from exc
            acquired = True
            yield ExclusiveOperationLease(request=request)
        finally:
            try:
                if acquired and handle is not None:
                    self.backend.release(handle)
            finally:
                try:
                    if handle is not None:
                        handle.close()
                finally:
                    _release_process_lock_path(lock_path)


def _ensure_windows_lock_sentinel(handle: BinaryIO) -> None:
    _ = handle.seek(WINDOWS_LOCK_BYTE_OFFSET, os.SEEK_END)
    if handle.tell() == WINDOWS_LOCK_BYTE_OFFSET:
        _ = handle.write(WINDOWS_LOCK_SENTINEL)
        handle.flush()
    _ = handle.seek(WINDOWS_LOCK_BYTE_OFFSET, os.SEEK_SET)


def _try_claim_process_lock_path(lock_path: Path) -> bool:
    with _HELD_LOCK_PATHS_GUARD:
        if lock_path in _HELD_LOCK_PATHS:
            return False
        _HELD_LOCK_PATHS.add(lock_path)
        return True


def _release_process_lock_path(lock_path: Path) -> None:
    with _HELD_LOCK_PATHS_GUARD:
        _HELD_LOCK_PATHS.discard(lock_path)
