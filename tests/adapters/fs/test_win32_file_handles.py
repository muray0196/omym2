"""
Summary: Tests retained Win32 handle validation and native ownership mechanics.
Why: Keeps Windows observation and mutation anchored without requiring Windows for pure checks.
"""

from __future__ import annotations

import ctypes
import os
import stat
from dataclasses import dataclass, field
from typing import TYPE_CHECKING

import pytest

from omym2.adapters.fs import win32_file_handles as win32_module
from omym2.adapters.fs.win32_file_handles import (
    WIN32_CREATE_NEW,
    WIN32_FILE_ATTRIBUTE_READONLY,
    WIN32_FILE_ATTRIBUTE_REPARSE_POINT,
    WIN32_FILE_FLAG_BACKUP_SEMANTICS,
    WIN32_FILE_FLAG_OPEN_REPARSE_POINT,
    WIN32_FILE_READ_ATTRIBUTES,
    WIN32_FILE_SHARE_DELETE,
    WIN32_FILE_SHARE_READ,
    WIN32_FILE_SHARE_WRITE,
    WIN32_FILE_WRITE_ATTRIBUTES,
    WIN32_GENERIC_READ,
    WIN32_IDENTITY_UNAVAILABLE_MESSAGE,
    WIN32_OPEN_EXISTING,
    WIN32_PATH_CHANGED_MESSAGE,
    WIN32_REPARSE_POINT_MESSAGE,
    CtypesWin32FileHandleBackend,
    normalize_win32_path,
)

if TYPE_CHECKING:
    from pathlib import Path

NATIVE_HANDLE = 41
DUPLICATED_HANDLE = 42
FILE_ID = bytes(range(16))
VOLUME_SERIAL_NUMBER = 7
DESCRIPTOR_CONVERSION_MESSAGE = "descriptor conversion failed"
FILE_DISPOSITION_INFO_SIZE = 1
FILE_STANDARD_DIRECTORY_OFFSET = 21
FILE_STANDARD_INFO_SIZE = 24
FILE_STANDARD_PENDING_OFFSET = 20
BY_HANDLE_FILE_INDEX_HIGH_OFFSET = 44
BY_HANDLE_FILE_INDEX_LOW_OFFSET = 48
BY_HANDLE_FILE_INFORMATION_SIZE = 52
EXPECTED_METADATA_ROLLBACK_CALLS = 2
NATIVE_BINARY_PAYLOAD = b"\x00\r\n\xffnative"
NATIVE_WINDOWS = os.name == "nt"


@dataclass(slots=True)
class RecordingWin32Api:
    """Record high-level backend calls while returning one controlled object."""

    identity: win32_module._KernelFileIdentity  # pyright: ignore[reportPrivateUsage]  # Tests the private ABI bridge.
    final_path: str | None = None
    create_calls: list[tuple[str, int, int, int, int]] = field(default_factory=list)
    closed_handles: list[int] = field(default_factory=list)
    deleted_handles: list[int] = field(default_factory=list)
    metadata_calls: list[tuple[int, int, int, int]] = field(default_factory=list)
    delete_error: OSError | None = None

    def create_file(
        self,
        path: str,
        *,
        desired_access: int,
        share_mode: int,
        creation_disposition: int,
        flags: int,
    ) -> int:
        """Return one deterministic native handle and record flags."""
        self.create_calls.append((path, desired_access, share_mode, creation_disposition, flags))
        if self.final_path is None:
            self.final_path = path
        return NATIVE_HANDLE

    def close_handle(self, handle: int) -> None:
        """Record one native close."""
        self.closed_handles.append(handle)

    def duplicate_handle(self, handle: int) -> int:
        """Return a deterministic duplicate."""
        assert handle == NATIVE_HANDLE
        return DUPLICATED_HANDLE

    def query_kernel_identity(
        self,
        handle: int,
    ) -> win32_module._KernelFileIdentity:  # pyright: ignore[reportPrivateUsage]  # Tests the private ABI bridge.
        """Return the controlled identity."""
        assert handle == NATIVE_HANDLE
        return self.identity

    def query_final_path(self, handle: int) -> str:
        """Return the controlled final path."""
        assert handle == NATIVE_HANDLE
        assert self.final_path is not None
        return self.final_path

    def mark_delete(self, handle: int) -> None:
        """Record exact-handle deletion."""
        self.deleted_handles.append(handle)
        if self.delete_error is not None:
            raise self.delete_error

    def set_basic_info(
        self,
        handle: int,
        *,
        attributes: int,
        atime_100ns: int,
        mtime_100ns: int,
    ) -> None:
        """Record exact-handle metadata updates."""
        self.metadata_calls.append((handle, attributes, atime_100ns, mtime_100ns))


@dataclass(slots=True)
class RejectingDescriptorBridge:
    """Fail descriptor conversion after a native duplicate is created."""

    def open_binary_fd(self, handle: int, *, writable: bool) -> int:
        """Raise without consuming the duplicate."""
        assert handle == DUPLICATED_HANDLE
        assert not writable
        raise OSError(DESCRIPTOR_CONVERSION_MESSAGE)


@dataclass(frozen=True, slots=True)
class DuplicatingDescriptorBridge:
    """Project Python stat fields from one ordinary Linux test descriptor."""

    file_descriptor: int

    def open_binary_fd(self, handle: int, *, writable: bool) -> int:
        """Return a fresh descriptor while leaving fake native ownership separate."""
        assert handle == DUPLICATED_HANDLE
        _ = writable
        return os.dup(self.file_descriptor)


def test_win32_ctypes_structures_match_the_native_abi() -> None:
    """BOOLEAN fields remain one byte at their documented native offsets."""
    standard_info = win32_module._FileStandardInfo  # noqa: SLF001  # pyright: ignore[reportPrivateUsage]  # ABI contract.
    disposition_info = win32_module._FileDispositionInfo  # noqa: SLF001  # pyright: ignore[reportPrivateUsage]  # ABI contract.
    legacy_info = win32_module._ByHandleFileInformation  # noqa: SLF001  # pyright: ignore[reportPrivateUsage]  # ABI contract.

    assert ctypes.sizeof(standard_info) == FILE_STANDARD_INFO_SIZE
    assert standard_info.delete_pending.offset == FILE_STANDARD_PENDING_OFFSET
    assert standard_info.directory.offset == FILE_STANDARD_DIRECTORY_OFFSET
    assert ctypes.sizeof(disposition_info) == FILE_DISPOSITION_INFO_SIZE
    assert ctypes.sizeof(legacy_info) == BY_HANDLE_FILE_INFORMATION_SIZE
    assert legacy_info.file_index_high.offset == BY_HANDLE_FILE_INDEX_HIGH_OFFSET
    assert legacy_info.file_index_low.offset == BY_HANDLE_FILE_INDEX_LOW_OFFSET


def test_zero_extended_file_id_uses_legacy_index() -> None:
    """FAT-like volumes use the nonzero 64-bit file index instead of a shared zero ID."""
    legacy_file_index = 123

    volume_serial, selected_file_id = win32_module._select_file_identifier(  # noqa: SLF001  # pyright: ignore[reportPrivateUsage]  # Pure native rule.
        extended_file_id=bytes(16),
        extended_volume_serial=VOLUME_SERIAL_NUMBER,
        legacy_volume_serial=VOLUME_SERIAL_NUMBER,
        legacy_file_index=legacy_file_index,
    )

    assert volume_serial == VOLUME_SERIAL_NUMBER
    assert int.from_bytes(selected_file_id, byteorder="little") == legacy_file_index


def test_failed_extended_file_id_query_fails_closed() -> None:
    """An unavailable extended query is not truncated to a potentially ambiguous ReFS index."""
    with pytest.raises(OSError, match=WIN32_IDENTITY_UNAVAILABLE_MESSAGE):
        _ = win32_module._select_file_identifier(  # noqa: SLF001  # pyright: ignore[reportPrivateUsage]  # Pure native rule.
            extended_file_id=None,
            extended_volume_serial=None,
            legacy_volume_serial=VOLUME_SERIAL_NUMBER,
            legacy_file_index=123,
        )


def test_nonzero_extended_file_id_remains_authoritative() -> None:
    """A ReFS-style 128-bit identifier is retained instead of truncating to legacy width."""
    extended_volume = 999

    volume_serial, selected_file_id = win32_module._select_file_identifier(  # noqa: SLF001  # pyright: ignore[reportPrivateUsage]  # Pure native rule.
        extended_file_id=FILE_ID,
        extended_volume_serial=extended_volume,
        legacy_volume_serial=VOLUME_SERIAL_NUMBER,
        legacy_file_index=123,
    )

    assert volume_serial == extended_volume
    assert selected_file_id == FILE_ID


def test_missing_extended_and_legacy_file_ids_fail_closed() -> None:
    """A volume with no stable identifier cannot collapse all entries into one identity."""
    with pytest.raises(OSError, match=WIN32_IDENTITY_UNAVAILABLE_MESSAGE):
        _ = win32_module._select_file_identifier(  # noqa: SLF001  # pyright: ignore[reportPrivateUsage]  # Pure native rule.
            extended_file_id=None,
            extended_volume_serial=None,
            legacy_volume_serial=VOLUME_SERIAL_NUMBER,
            legacy_file_index=0,
        )


@pytest.mark.parametrize(
    ("raw_path", "expected"),
    [
        (r"\\?\C:\Music\..\Incoming", r"c:\incoming"),
        (r"\\?\UNC\server\share\folder", r"\\server\share\folder"),
        (r"C:/Music/Album", r"c:\music\album"),
    ],
)
def test_normalize_win32_path_compares_extended_and_dos_spellings(raw_path: str, expected: str) -> None:
    """Final-path checks use one case-insensitive normalized spelling."""
    assert normalize_win32_path(raw_path) == expected


def test_backend_opens_directory_with_no_follow_and_no_delete_sharing(tmp_path: Path) -> None:
    """Retained parents reject reparses and block rename/delete sharing."""
    api = RecordingWin32Api(identity=_kernel_identity(is_directory=True))
    backend = CtypesWin32FileHandleBackend(
        _api=api,
        _descriptor_bridge=RejectingDescriptorBridge(),
    )
    directory_path = tmp_path / "root"

    with backend.open_directory(directory_path) as handle:
        assert handle.identity.is_directory

    [(opened_path, _access, share_mode, disposition, flags)] = api.create_calls
    assert opened_path == str(directory_path)
    assert disposition == WIN32_OPEN_EXISTING
    assert share_mode == WIN32_FILE_SHARE_READ | WIN32_FILE_SHARE_WRITE
    assert not share_mode & WIN32_FILE_SHARE_DELETE
    assert flags == WIN32_FILE_FLAG_OPEN_REPARSE_POINT | WIN32_FILE_FLAG_BACKUP_SEMANTICS
    assert api.closed_handles == [NATIVE_HANDLE]


def test_backend_uses_stricter_sharing_and_attribute_access_for_mutation_handles(tmp_path: Path) -> None:
    """Mutation handles admit readers but block every writer, rename, and delete race."""
    projection_path = tmp_path / "projection.bin"
    _ = projection_path.write_bytes(b"")
    projection_descriptor = os.open(projection_path, os.O_RDONLY)
    try:
        source_api = RecordingWin32Api(identity=_kernel_identity(is_directory=False))
        source_backend = CtypesWin32FileHandleBackend(
            _api=source_api,
            _descriptor_bridge=DuplicatingDescriptorBridge(projection_descriptor),
        )
        with source_backend.open_source(tmp_path / "source.bin"):
            pass

        target_api = RecordingWin32Api(identity=_kernel_identity(is_directory=False))
        target_backend = CtypesWin32FileHandleBackend(
            _api=target_api,
            _descriptor_bridge=DuplicatingDescriptorBridge(projection_descriptor),
        )
        with target_backend.create_file_new(tmp_path / "target.bin"):
            pass
    finally:
        os.close(projection_descriptor)

    [_source_path, source_access, source_share, _source_disposition, _source_flags] = source_api.create_calls[0]
    [_target_path, _target_access, target_share, _target_disposition, _target_flags] = target_api.create_calls[0]
    assert source_access & (WIN32_GENERIC_READ | WIN32_FILE_READ_ATTRIBUTES | WIN32_FILE_WRITE_ATTRIBUTES)
    assert source_share == WIN32_FILE_SHARE_READ
    assert target_share == WIN32_FILE_SHARE_READ
    assert not source_share & (WIN32_FILE_SHARE_WRITE | WIN32_FILE_SHARE_DELETE)
    assert not target_share & (WIN32_FILE_SHARE_WRITE | WIN32_FILE_SHARE_DELETE)


def test_readonly_exact_delete_clears_attribute_through_retained_handle(tmp_path: Path) -> None:
    """A read-only source is made writable only on the exact object being deleted."""
    projection_path = tmp_path / "projection.bin"
    _ = projection_path.write_bytes(b"")
    projection_descriptor = os.open(projection_path, os.O_RDONLY)
    try:
        api = RecordingWin32Api(
            identity=_kernel_identity(
                is_directory=False,
                attributes=WIN32_FILE_ATTRIBUTE_READONLY,
            )
        )
        backend = CtypesWin32FileHandleBackend(
            _api=api,
            _descriptor_bridge=DuplicatingDescriptorBridge(projection_descriptor),
        )
        with backend.open_source(tmp_path / "source.bin") as handle:
            handle.delete_exact(expected_identity=handle.identity)
    finally:
        os.close(projection_descriptor)

    assert len(api.metadata_calls) == 1
    assert not api.metadata_calls[0][1] & WIN32_FILE_ATTRIBUTE_READONLY
    assert api.deleted_handles == [NATIVE_HANDLE]


def test_readonly_delete_failure_restores_attribute(tmp_path: Path) -> None:
    """A failed exact deletion restores the source read-only bit before returning the error."""
    projection_path = tmp_path / "projection.bin"
    _ = projection_path.write_bytes(b"")
    projection_descriptor = os.open(projection_path, os.O_RDONLY)
    try:
        api = RecordingWin32Api(
            identity=_kernel_identity(
                is_directory=False,
                attributes=WIN32_FILE_ATTRIBUTE_READONLY,
            ),
            delete_error=PermissionError("delete denied"),
        )
        backend = CtypesWin32FileHandleBackend(
            _api=api,
            _descriptor_bridge=DuplicatingDescriptorBridge(projection_descriptor),
        )
        with (
            backend.open_source(tmp_path / "source.bin") as handle,
            pytest.raises(PermissionError, match="delete denied"),
        ):
            handle.delete_exact(expected_identity=handle.identity)
    finally:
        os.close(projection_descriptor)

    assert len(api.metadata_calls) == EXPECTED_METADATA_ROLLBACK_CALLS
    assert not api.metadata_calls[0][1] & WIN32_FILE_ATTRIBUTE_READONLY
    assert api.metadata_calls[1][1] & WIN32_FILE_ATTRIBUTE_READONLY


def test_backend_rejects_reparse_before_returning_handle(tmp_path: Path) -> None:
    """A final junction or symbolic link is closed without becoming observable input."""
    api = RecordingWin32Api(
        identity=_kernel_identity(
            is_directory=True,
            attributes=WIN32_FILE_ATTRIBUTE_REPARSE_POINT,
            reparse_tag=1,
        )
    )
    backend = CtypesWin32FileHandleBackend(
        _api=api,
        _descriptor_bridge=RejectingDescriptorBridge(),
    )

    with pytest.raises(ValueError, match=WIN32_REPARSE_POINT_MESSAGE):
        _ = backend.open_entry(tmp_path / "junction")

    assert api.closed_handles == [NATIVE_HANDLE]


def test_backend_rejects_mismatched_final_path_and_closes_handle(tmp_path: Path) -> None:
    """Opening through a redirected ancestor fails before a caller can read it."""
    api = RecordingWin32Api(
        identity=_kernel_identity(is_directory=True),
        final_path=str(tmp_path / "outside"),
    )
    backend = CtypesWin32FileHandleBackend(
        _api=api,
        _descriptor_bridge=RejectingDescriptorBridge(),
    )

    with pytest.raises(FileNotFoundError, match=WIN32_PATH_CHANGED_MESSAGE):
        _ = backend.open_directory(tmp_path / "root")

    assert api.closed_handles == [NATIVE_HANDLE]


def test_create_validation_failure_exact_deletes_claim_before_close(tmp_path: Path) -> None:
    """A CREATE_NEW claim cannot leak when post-open final-path validation fails."""
    api = RecordingWin32Api(
        identity=_kernel_identity(is_directory=False),
        final_path=str(tmp_path / "redirected"),
    )
    projection_path = tmp_path / "projection.bin"
    _ = projection_path.write_bytes(b"")
    projection_descriptor = os.open(projection_path, os.O_RDONLY)
    try:
        backend = CtypesWin32FileHandleBackend(
            _api=api,
            _descriptor_bridge=DuplicatingDescriptorBridge(projection_descriptor),
        )

        with pytest.raises(OSError, match=WIN32_PATH_CHANGED_MESSAGE):
            _ = backend.create_file_new(tmp_path / "target.bin")
    finally:
        os.close(projection_descriptor)

    assert api.create_calls[0][3] == WIN32_CREATE_NEW
    assert api.deleted_handles == [NATIVE_HANDLE]
    assert api.closed_handles == [NATIVE_HANDLE]


def test_duplicate_conversion_failure_closes_only_the_duplicate(tmp_path: Path) -> None:
    """A failed CRT conversion neither leaks its duplicate nor closes the retained handle."""
    api = RecordingWin32Api(identity=_kernel_identity(is_directory=True))
    backend = CtypesWin32FileHandleBackend(
        _api=api,
        _descriptor_bridge=RejectingDescriptorBridge(),
    )
    handle = backend.open_directory(tmp_path / "root")

    with pytest.raises(OSError, match=DESCRIPTOR_CONVERSION_MESSAGE):
        _ = handle.duplicate_binary_fd()

    assert api.closed_handles == [DUPLICATED_HANDLE]
    _ = handle.refresh_identity()
    handle.close()
    assert api.closed_handles == [DUPLICATED_HANDLE, NATIVE_HANDLE]


@pytest.mark.skipif(not NATIVE_WINDOWS, reason="Requires native Win32 handles.")
def test_native_create_new_collision_preserves_occupied_bytes(tmp_path: Path) -> None:
    """CREATE_NEW reports a collision without opening or truncating the occupied path."""
    occupied_path = tmp_path / "occupied.bin"
    occupied_bytes = b"occupied"
    _ = occupied_path.write_bytes(occupied_bytes)
    backend = CtypesWin32FileHandleBackend()

    with pytest.raises(FileExistsError):
        _ = backend.create_file_new(occupied_path)

    assert occupied_path.read_bytes() == occupied_bytes


@pytest.mark.skipif(not NATIVE_WINDOWS, reason="Requires native Win32 handles.")
def test_native_duplicated_descriptor_reads_and_writes_binary_bytes(tmp_path: Path) -> None:
    """A duplicated C-runtime descriptor retains binary bytes and leaves the raw HANDLE owned."""
    target_path = tmp_path / "binary.bin"
    backend = CtypesWin32FileHandleBackend()

    with backend.create_file_new(target_path) as handle:
        file_descriptor = handle.duplicate_binary_fd(writable=True)
        try:
            _ = os.write(file_descriptor, NATIVE_BINARY_PAYLOAD)
            _ = os.lseek(file_descriptor, 0, os.SEEK_SET)
            observed = os.read(file_descriptor, len(NATIVE_BINARY_PAYLOAD))
        finally:
            os.close(file_descriptor)

    assert observed == NATIVE_BINARY_PAYLOAD
    assert target_path.read_bytes() == NATIVE_BINARY_PAYLOAD


@pytest.mark.skipif(not NATIVE_WINDOWS, reason="Requires native Win32 handles.")
def test_native_readonly_exact_delete_removes_only_retained_source(tmp_path: Path) -> None:
    """Read-only deletion is applied through the source HANDLE without touching a sibling."""
    source_path = tmp_path / "source.bin"
    sibling_path = tmp_path / "sibling.bin"
    source_bytes = b"source"
    sibling_bytes = b"sibling"
    _ = source_path.write_bytes(source_bytes)
    _ = sibling_path.write_bytes(sibling_bytes)
    source_path.chmod(stat.S_IREAD)
    backend = CtypesWin32FileHandleBackend()

    try:
        with backend.open_source(source_path) as handle:
            handle.delete_exact(expected_identity=handle.identity)
    finally:
        if source_path.exists():
            source_path.chmod(stat.S_IWRITE)

    assert not source_path.exists()
    assert sibling_path.read_bytes() == sibling_bytes


@pytest.mark.parametrize(
    ("error_code", "error_type"),
    [
        (2, FileNotFoundError),
        (3, FileNotFoundError),
        (80, FileExistsError),
        (183, FileExistsError),
    ],
)
def test_ctypes_error_translation_preserves_path_and_create_new_categories(
    error_code: int,
    error_type: type[OSError],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Win32 path and collision codes map to the exceptions adapter callers require."""
    monkeypatch.setattr(ctypes, "get_last_error", lambda: error_code, raising=False)
    monkeypatch.setattr(ctypes, "WinError", _fake_win_error, raising=False)
    api = object.__new__(win32_module._CtypesWin32HandleApi)  # noqa: SLF001  # pyright: ignore[reportPrivateUsage]  # No load.

    assert isinstance(api._last_error(), error_type)  # noqa: SLF001  # pyright: ignore[reportPrivateUsage]  # Pure mapping.


def _fake_win_error(error_code: int) -> OSError:
    return OSError(error_code, "native failure")


def _kernel_identity(
    *,
    is_directory: bool,
    attributes: int = 0,
    reparse_tag: int = 0,
) -> win32_module._KernelFileIdentity:  # pyright: ignore[reportPrivateUsage]  # Builds fake kernel output.
    return win32_module._KernelFileIdentity(  # noqa: SLF001  # pyright: ignore[reportPrivateUsage]  # Fake kernel output.
        volume_serial_number=VOLUME_SERIAL_NUMBER,
        file_id=FILE_ID,
        size=0,
        creation_time_100ns=0,
        last_write_time_100ns=0,
        change_time_100ns=0,
        attributes=attributes,
        reparse_tag=reparse_tag,
        is_directory=is_directory,
    )
