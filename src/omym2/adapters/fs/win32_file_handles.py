"""
Summary: Retains no-follow Win32 file handles behind a typed adapter boundary.
Why: Prevents Windows path replacement while files are observed or moved.
"""

from __future__ import annotations

import ctypes
import ntpath
import os
import stat
from dataclasses import dataclass, field
from importlib import import_module
from pathlib import Path
from typing import TYPE_CHECKING, Protocol, Self, cast, final

if TYPE_CHECKING:
    from collections.abc import Callable
    from types import TracebackType

WIN32_FILE_ATTRIBUTE_DEVICE = 0x00000040
WIN32_FILE_ATTRIBUTE_NORMAL = 0x00000080
WIN32_FILE_ATTRIBUTE_READONLY = 0x00000001
WIN32_FILE_ATTRIBUTE_REPARSE_POINT = 0x00000400
WIN32_FILE_FLAG_BACKUP_SEMANTICS = 0x02000000
WIN32_FILE_FLAG_OPEN_REPARSE_POINT = 0x00200000
WIN32_FILE_LIST_DIRECTORY = 0x00000001
WIN32_FILE_READ_ATTRIBUTES = 0x00000080
WIN32_FILE_SHARE_READ = 0x00000001
WIN32_FILE_SHARE_WRITE = 0x00000002
WIN32_FILE_WRITE_ATTRIBUTES = 0x00000100
WIN32_DELETE_ACCESS = 0x00010000
WIN32_GENERIC_READ = 0x80000000
WIN32_GENERIC_WRITE = 0x40000000
WIN32_OPEN_EXISTING = 3
WIN32_CREATE_NEW = 1
WIN32_PATH_CHANGED_MESSAGE = "Win32 path changed while its retained handle was open."
WIN32_REPARSE_POINT_MESSAGE = "Win32 retained handles must not name reparse points."
WIN32_EXPECTED_DIRECTORY_MESSAGE = "Win32 retained handle must name a directory."
WIN32_EXPECTED_FILE_MESSAGE = "Win32 retained handle must name a regular file."
WIN32_UNAVAILABLE_MESSAGE = "Win32 retained handles are unavailable on this platform."
WIN32_HANDLE_CLOSED_MESSAGE = "Win32 retained handle is already closed."
WIN32_IDENTITY_UNAVAILABLE_MESSAGE = "Win32 filesystem identity is unavailable for the retained handle."
_WINDOWS_TO_UNIX_EPOCH_100NS = 116_444_736_000_000_000
_HUNDRED_NS_PER_NS = 100
_DUPLICATE_SAME_ACCESS = 0x00000002
_FILE_ATTRIBUTE_TAG_INFO_CLASS = 9
_FILE_BASIC_INFO_CLASS = 0
_FILE_DISPOSITION_INFO_CLASS = 4
_FILE_ID_INFO_CLASS = 18
_FILE_STANDARD_INFO_CLASS = 1
_INVALID_HANDLE_VALUE = ctypes.c_void_p(-1).value
_WIN32_ALREADY_EXISTS_ERROR_CODES = frozenset({80, 183})
_WIN32_NOT_FOUND_ERROR_CODES = frozenset({2, 3})


@final
class _FileBasicInfo(ctypes.Structure):
    """ctypes layout of FILE_BASIC_INFO."""

    _fields_ = [
        ("creation_time", ctypes.c_int64),
        ("last_access_time", ctypes.c_int64),
        ("last_write_time", ctypes.c_int64),
        ("change_time", ctypes.c_int64),
        ("file_attributes", ctypes.c_uint32),
    ]


@final
class _FileStandardInfo(ctypes.Structure):
    """ctypes layout of FILE_STANDARD_INFO."""

    _fields_ = [
        ("allocation_size", ctypes.c_int64),
        ("end_of_file", ctypes.c_int64),
        ("number_of_links", ctypes.c_uint32),
        ("delete_pending", ctypes.c_ubyte),
        ("directory", ctypes.c_ubyte),
    ]


@final
class _FileAttributeTagInfo(ctypes.Structure):
    """ctypes layout of FILE_ATTRIBUTE_TAG_INFO."""

    _fields_ = [
        ("file_attributes", ctypes.c_uint32),
        ("reparse_tag", ctypes.c_uint32),
    ]


@final
class _FileId128(ctypes.Structure):
    """ctypes layout of FILE_ID_128."""

    _fields_ = [("identifier", ctypes.c_ubyte * 16)]


@final
class _FileIdInfo(ctypes.Structure):
    """ctypes layout of FILE_ID_INFO."""

    _fields_ = [
        ("volume_serial_number", ctypes.c_uint64),
        ("file_id", _FileId128),
    ]


@final
class _FileDispositionInfo(ctypes.Structure):
    """ctypes layout of FILE_DISPOSITION_INFO."""

    _fields_ = [("delete_file", ctypes.c_ubyte)]


@final
class _FileTime(ctypes.Structure):
    """ctypes layout of FILETIME."""

    _fields_ = [
        ("low_date_time", ctypes.c_uint32),
        ("high_date_time", ctypes.c_uint32),
    ]


@final
class _ByHandleFileInformation(ctypes.Structure):
    """ctypes layout of BY_HANDLE_FILE_INFORMATION."""

    _fields_ = [
        ("file_attributes", ctypes.c_uint32),
        ("creation_time", _FileTime),
        ("last_access_time", _FileTime),
        ("last_write_time", _FileTime),
        ("volume_serial_number", ctypes.c_uint32),
        ("file_size_high", ctypes.c_uint32),
        ("file_size_low", ctypes.c_uint32),
        ("number_of_links", ctypes.c_uint32),
        ("file_index_high", ctypes.c_uint32),
        ("file_index_low", ctypes.c_uint32),
    ]


@dataclass(frozen=True, slots=True)
class Win32FileIdentity:
    """Stable object identity plus Python-compatible mutable file state."""

    device_id: int
    inode: int
    size: int
    mtime_ns: int
    ctime_ns: int
    volume_serial_number: int
    file_id: bytes
    attributes: int
    reparse_tag: int
    is_directory: bool

    @property
    def is_regular_file(self) -> bool:
        """Return whether the entry is an ordinary non-reparse file."""
        return (
            not self.is_directory
            and not self.is_reparse_point
            and not bool(self.attributes & WIN32_FILE_ATTRIBUTE_DEVICE)
        )

    @property
    def is_reparse_point(self) -> bool:
        """Return whether Windows marked the retained entry as a reparse point."""
        return bool(self.attributes & WIN32_FILE_ATTRIBUTE_REPARSE_POINT) or self.reparse_tag != 0

    def same_object(self, other: Win32FileIdentity) -> bool:
        """Compare stable volume and file identifiers without mutable state."""
        return (
            self.volume_serial_number == other.volume_serial_number
            and self.file_id == other.file_id
            and self.is_directory == other.is_directory
        )

    def same_file_state(self, other: Win32FileIdentity) -> bool:
        """Compare the object and the domain filesystem precondition fields."""
        return (
            self.same_object(other)
            and self.device_id == other.device_id
            and self.inode == other.inode
            and self.size == other.size
            and self.mtime_ns == other.mtime_ns
            and self.ctime_ns == other.ctime_ns
        )


class Win32FileHandle(Protocol):
    """Retained Win32 handle behavior shared by observation and mutation adapters."""

    path: str
    final_path: str
    identity: Win32FileIdentity

    def duplicate_binary_fd(self, *, writable: bool = False) -> int:
        """Return an owned non-inheritable binary descriptor for the same object."""
        ...

    def refresh_identity(self) -> Win32FileIdentity:
        """Re-query identity after verifying the retained path and entry kind."""
        ...

    def verify_current(
        self,
        *,
        expected_path: os.PathLike[str] | str | None = None,
        expected_identity: Win32FileIdentity | None = None,
    ) -> Win32FileIdentity:
        """Return current state after optional path and exact-state verification."""
        ...

    def delete_exact(self, *, expected_identity: Win32FileIdentity | None = None) -> None:
        """Mark this exact verified object for deletion when the handle closes."""
        ...

    def set_metadata(self, *, mode: int, atime_ns: int, mtime_ns: int) -> Win32FileIdentity:
        """Set read-only state and timestamps through the retained handle."""
        ...

    def close(self) -> None:
        """Release the retained native handle."""
        ...

    def __enter__(self) -> Self:
        """Retain this handle for a context lifetime."""
        ...

    def __exit__(
        self,
        exception_type: type[BaseException] | None,
        exception: BaseException | None,
        traceback: TracebackType | None,
    ) -> None:
        """Release this handle after a context lifetime."""
        ...


class Win32FileHandleBackend(Protocol):
    """Open retained Win32 handles without following a final reparse point."""

    def open_entry(self, path: os.PathLike[str] | str) -> Win32FileHandle:
        """Open one file or directory for identity-only traversal."""
        ...

    def open_directory(self, path: os.PathLike[str] | str) -> Win32FileHandle:
        """Open and require one ordinary directory."""
        ...

    def open_file(self, path: os.PathLike[str] | str) -> Win32FileHandle:
        """Open one ordinary file for retained reading."""
        ...

    def open_source(self, path: os.PathLike[str] | str) -> Win32FileHandle:
        """Open one ordinary source file for retained reading and deletion."""
        ...

    def create_file_new(self, path: os.PathLike[str] | str) -> Win32FileHandle:
        """Exclusively create one ordinary retained target file."""
        ...


class _Win32HandleApi(Protocol):
    """Typed low-level Win32 calls used by the retained-handle implementation."""

    def create_file(
        self,
        path: str,
        *,
        desired_access: int,
        share_mode: int,
        creation_disposition: int,
        flags: int,
    ) -> int:
        """Return one native handle or raise the translated Windows error."""
        ...

    def close_handle(self, handle: int) -> None:
        """Close one native handle."""
        ...

    def duplicate_handle(self, handle: int) -> int:
        """Return a non-inheritable duplicate in the current process."""
        ...

    def query_kernel_identity(self, handle: int) -> _KernelFileIdentity:
        """Return stable and mutable state directly from the retained handle."""
        ...

    def query_final_path(self, handle: int) -> str:
        """Return the normalized DOS final path for a retained handle."""
        ...

    def mark_delete(self, handle: int) -> None:
        """Mark the exact object referenced by a DELETE-capable handle."""
        ...

    def set_basic_info(
        self,
        handle: int,
        *,
        attributes: int,
        atime_100ns: int,
        mtime_100ns: int,
    ) -> None:
        """Update timestamps and attributes through one retained handle."""
        ...


class _DescriptorBridge(Protocol):
    """Convert a duplicated native handle into an owned C-runtime descriptor."""

    def open_binary_fd(self, handle: int, *, writable: bool) -> int:
        """Consume one duplicated native handle and return its descriptor."""
        ...


@dataclass(frozen=True, slots=True)
class _KernelFileIdentity:
    """File state reported directly by Win32 handle queries."""

    volume_serial_number: int
    file_id: bytes
    size: int
    creation_time_100ns: int
    last_write_time_100ns: int
    attributes: int
    reparse_tag: int
    is_directory: bool


@dataclass(slots=True)
class RetainedWin32Handle:
    """Own one native handle whose sharing mode blocks rename and deletion."""

    path: str
    final_path: str
    identity: Win32FileIdentity
    _raw_handle: int
    _api: _Win32HandleApi = field(repr=False)
    _descriptor_bridge: _DescriptorBridge = field(repr=False)
    _project_stat: bool = field(repr=False)
    _closed: bool = field(default=False, init=False, repr=False)

    def duplicate_binary_fd(self, *, writable: bool = False) -> int:
        """Return an owned non-inheritable binary descriptor for the same object."""
        self._require_open()
        duplicate = self._api.duplicate_handle(self._raw_handle)
        try:
            return self._descriptor_bridge.open_binary_fd(duplicate, writable=writable)
        except BaseException:
            self._api.close_handle(duplicate)
            raise

    def refresh_identity(self) -> Win32FileIdentity:
        """Re-query identity after verifying the retained path and entry kind."""
        return self.verify_current(expected_path=self.path)

    def verify_current(
        self,
        *,
        expected_path: os.PathLike[str] | str | None = None,
        expected_identity: Win32FileIdentity | None = None,
    ) -> Win32FileIdentity:
        """Return current state after optional path and exact-state verification."""
        self._require_open()
        expected_kind = self.identity.is_directory
        current = _query_identity(
            self._raw_handle,
            api=self._api,
            descriptor_bridge=self._descriptor_bridge,
            project_stat=self._project_stat,
        )
        _require_supported_identity(current, expected_directory=expected_kind)
        current_final_path = normalize_win32_path(self._api.query_final_path(self._raw_handle))
        required_path = self.path if expected_path is None else _string_path(expected_path)
        if current_final_path != normalize_win32_path(required_path):
            raise FileNotFoundError(WIN32_PATH_CHANGED_MESSAGE)
        if expected_identity is not None and not expected_identity.same_file_state(current):
            raise FileNotFoundError(WIN32_PATH_CHANGED_MESSAGE)
        self.final_path = current_final_path
        return current

    def delete_exact(self, *, expected_identity: Win32FileIdentity | None = None) -> None:
        """Mark this exact verified object for deletion when the handle closes."""
        current = self.verify_current(expected_path=self.path, expected_identity=expected_identity)
        original_attributes = current.attributes
        cleared_readonly = bool(original_attributes & WIN32_FILE_ATTRIBUTE_READONLY)
        if cleared_readonly:
            writable_attributes = original_attributes & ~(WIN32_FILE_ATTRIBUTE_READONLY | WIN32_FILE_ATTRIBUTE_NORMAL)
            if writable_attributes == 0:
                writable_attributes = WIN32_FILE_ATTRIBUTE_NORMAL
            self._api.set_basic_info(
                self._raw_handle,
                attributes=writable_attributes,
                atime_100ns=0,
                mtime_100ns=0,
            )
        try:
            self._api.mark_delete(self._raw_handle)
        except BaseException as exc:
            if cleared_readonly:
                try:
                    self._api.set_basic_info(
                        self._raw_handle,
                        attributes=original_attributes,
                        atime_100ns=0,
                        mtime_100ns=0,
                    )
                except BaseException as restore_error:  # noqa: BLE001  # Preserve the deletion failure.
                    exc.add_note(f"Read-only attribute restore also failed: {restore_error!r}")
            raise

    def set_metadata(self, *, mode: int, atime_ns: int, mtime_ns: int) -> Win32FileIdentity:
        """Set read-only state and timestamps through the retained handle."""
        current = self.verify_current(expected_path=self.path)
        attributes = current.attributes & ~WIN32_FILE_ATTRIBUTE_NORMAL
        if mode & stat.S_IWRITE:
            attributes &= ~WIN32_FILE_ATTRIBUTE_READONLY
        else:
            attributes |= WIN32_FILE_ATTRIBUTE_READONLY
        if attributes == 0:
            attributes = WIN32_FILE_ATTRIBUTE_NORMAL
        self._api.set_basic_info(
            self._raw_handle,
            attributes=attributes,
            atime_100ns=_unix_ns_to_filetime_100ns(atime_ns),
            mtime_100ns=_unix_ns_to_filetime_100ns(mtime_ns),
        )
        return self.refresh_identity()

    def close(self) -> None:
        """Release the retained native handle once."""
        if self._closed:
            return
        self._api.close_handle(self._raw_handle)
        self._closed = True

    def __enter__(self) -> Self:
        """Retain this handle for a context lifetime."""
        self._require_open()
        return self

    def __exit__(
        self,
        exception_type: type[BaseException] | None,
        exception: BaseException | None,
        traceback: TracebackType | None,
    ) -> None:
        """Release this handle after a context lifetime."""
        self.close()

    def _require_open(self) -> None:
        if self._closed:
            raise OSError(WIN32_HANDLE_CLOSED_MESSAGE)


def _new_ctypes_api() -> _Win32HandleApi:
    return _CtypesWin32HandleApi()


def _new_descriptor_bridge() -> _DescriptorBridge:
    return _MsvcrtDescriptorBridge()


@dataclass(frozen=True, slots=True)
class CtypesWin32FileHandleBackend:
    """Open retained handles through kernel32 and the Microsoft C runtime."""

    _api: _Win32HandleApi = field(default_factory=_new_ctypes_api, repr=False)
    _descriptor_bridge: _DescriptorBridge = field(default_factory=_new_descriptor_bridge, repr=False)

    def open_entry(self, path: os.PathLike[str] | str) -> Win32FileHandle:
        """Open one file or directory for identity-only traversal."""
        return self._open(
            path,
            desired_access=WIN32_FILE_READ_ATTRIBUTES,
            share_mode=WIN32_FILE_SHARE_READ | WIN32_FILE_SHARE_WRITE,
            creation_disposition=WIN32_OPEN_EXISTING,
            expected_directory=None,
            project_stat=False,
        )

    def open_directory(self, path: os.PathLike[str] | str) -> Win32FileHandle:
        """Open and require one ordinary directory."""
        # LIST_DIRECTORY data access enrolls the retained handle in NT share
        # arbitration; attributes-only handles never block a parent rename.
        return self._open(
            path,
            desired_access=WIN32_FILE_READ_ATTRIBUTES | WIN32_FILE_LIST_DIRECTORY,
            share_mode=WIN32_FILE_SHARE_READ | WIN32_FILE_SHARE_WRITE,
            creation_disposition=WIN32_OPEN_EXISTING,
            expected_directory=True,
            project_stat=False,
        )

    def open_file(self, path: os.PathLike[str] | str) -> Win32FileHandle:
        """Open one ordinary file for retained reading."""
        return self._open(
            path,
            desired_access=WIN32_GENERIC_READ | WIN32_FILE_READ_ATTRIBUTES,
            share_mode=WIN32_FILE_SHARE_READ | WIN32_FILE_SHARE_WRITE,
            creation_disposition=WIN32_OPEN_EXISTING,
            expected_directory=False,
            project_stat=True,
        )

    def open_source(self, path: os.PathLike[str] | str) -> Win32FileHandle:
        """Open one ordinary source file for retained reading and deletion."""
        return self._open(
            path,
            desired_access=(
                WIN32_GENERIC_READ | WIN32_FILE_READ_ATTRIBUTES | WIN32_FILE_WRITE_ATTRIBUTES | WIN32_DELETE_ACCESS
            ),
            share_mode=WIN32_FILE_SHARE_READ,
            creation_disposition=WIN32_OPEN_EXISTING,
            expected_directory=False,
            project_stat=True,
        )

    def create_file_new(self, path: os.PathLike[str] | str) -> Win32FileHandle:
        """Exclusively create one ordinary retained target file."""
        return self._open(
            path,
            desired_access=(
                WIN32_GENERIC_READ
                | WIN32_GENERIC_WRITE
                | WIN32_FILE_READ_ATTRIBUTES
                | WIN32_FILE_WRITE_ATTRIBUTES
                | WIN32_DELETE_ACCESS
            ),
            share_mode=WIN32_FILE_SHARE_READ,
            creation_disposition=WIN32_CREATE_NEW,
            expected_directory=False,
            project_stat=True,
        )

    def _open(  # noqa: PLR0913  # Native role policy is explicit at the single CreateFile boundary.
        self,
        path: os.PathLike[str] | str,
        *,
        desired_access: int,
        share_mode: int,
        creation_disposition: int,
        expected_directory: bool | None,
        project_stat: bool,
    ) -> RetainedWin32Handle:
        # Path.resolve() would follow the exact reparse points this boundary rejects.
        lexical_path = os.path.abspath(_string_path(path))  # noqa: PTH100  # Lexical normalization only.
        raw_handle = self._api.create_file(
            lexical_path,
            desired_access=desired_access,
            share_mode=share_mode,
            creation_disposition=creation_disposition,
            flags=WIN32_FILE_FLAG_OPEN_REPARSE_POINT | WIN32_FILE_FLAG_BACKUP_SEMANTICS,
        )
        try:
            identity = _query_identity(
                raw_handle,
                api=self._api,
                descriptor_bridge=self._descriptor_bridge,
                project_stat=project_stat,
            )
            _require_supported_identity(identity, expected_directory=expected_directory)
            final_path = normalize_win32_path(self._api.query_final_path(raw_handle))
            _require_expected_path(final_path, lexical_path)
        except BaseException as exc:
            if creation_disposition == WIN32_CREATE_NEW:
                try:
                    self._api.mark_delete(raw_handle)
                except BaseException as cleanup_error:  # noqa: BLE001  # Preserve the primary validation failure.
                    exc.add_note(f"Exact invalid-target cleanup also failed: {cleanup_error!r}")
            try:
                self._api.close_handle(raw_handle)
            except BaseException as close_error:  # noqa: BLE001  # Preserve the primary validation failure.
                exc.add_note(f"Retained Win32 handle close also failed: {close_error!r}")
            raise
        return RetainedWin32Handle(
            path=lexical_path,
            final_path=final_path,
            identity=identity,
            _raw_handle=raw_handle,
            _api=self._api,
            _descriptor_bridge=self._descriptor_bridge,
            _project_stat=project_stat,
        )


def default_win32_file_handle_backend() -> Win32FileHandleBackend | None:
    """Return the native backend only on Windows without importing msvcrt elsewhere."""
    if os.name != "nt":
        return None
    return CtypesWin32FileHandleBackend()


def stat_change_marker_ns(stat_result: os.stat_result) -> int:
    """Return the change marker compared across observation boundaries.

    Python 3.14 maps Windows st_ctime to NTFS ChangeTime, which by-name stats
    can report stale for freshly written files; creation time is the stable
    Windows marker with the same replaced-object detection value.
    """
    if os.name == "nt":
        return cast("int", getattr(stat_result, "st_birthtime_ns"))  # noqa: B009  # Hidden from POSIX type stubs.
    return stat_result.st_ctime_ns


def normalize_win32_path(path: os.PathLike[str] | str) -> str:
    """Normalize DOS, extended DOS, and UNC spellings for final-path checks."""
    value = _string_path(path).replace("/", "\\")
    if value.startswith("\\\\?\\UNC\\"):
        value = f"\\\\{value[8:]}"
    elif value.startswith("\\\\?\\"):
        value = value[4:]
    return ntpath.normcase(ntpath.normpath(value))


def win32_directory_prefixes(path: os.PathLike[str] | str) -> tuple[str, ...]:
    """Return absolute anchor-to-directory prefixes for retained traversal."""
    # Path.resolve() would follow the exact reparse points this boundary rejects.
    absolute_path = Path(os.path.abspath(_string_path(path)))  # noqa: PTH100  # Lexical normalization only.
    anchor = Path(absolute_path.anchor)
    if not absolute_path.anchor:
        raise ValueError(WIN32_PATH_CHANGED_MESSAGE)
    prefixes = [anchor]
    current_path = anchor
    for part in absolute_path.relative_to(anchor).parts:
        current_path /= part
        prefixes.append(current_path)
    return tuple(str(prefix) for prefix in prefixes)


def _string_path(path: os.PathLike[str] | str) -> str:
    return path if isinstance(path, str) else path.__fspath__()


def _require_supported_identity(identity: Win32FileIdentity, *, expected_directory: bool | None) -> None:
    if not any(identity.file_id):
        raise OSError(WIN32_IDENTITY_UNAVAILABLE_MESSAGE)
    if identity.is_reparse_point:
        raise ValueError(WIN32_REPARSE_POINT_MESSAGE)
    if expected_directory is True and not identity.is_directory:
        raise NotADirectoryError(WIN32_EXPECTED_DIRECTORY_MESSAGE)
    if expected_directory is False and not identity.is_regular_file:
        raise ValueError(WIN32_EXPECTED_FILE_MESSAGE)


def _require_expected_path(final_path: str, expected_path: os.PathLike[str] | str) -> None:
    if final_path != normalize_win32_path(expected_path):
        raise FileNotFoundError(WIN32_PATH_CHANGED_MESSAGE)


def _query_identity(
    raw_handle: int,
    *,
    api: _Win32HandleApi,
    descriptor_bridge: _DescriptorBridge,
    project_stat: bool,
) -> Win32FileIdentity:
    kernel_identity = api.query_kernel_identity(raw_handle)
    device_id = kernel_identity.volume_serial_number
    inode = int.from_bytes(kernel_identity.file_id, byteorder="little")
    size = kernel_identity.size
    mtime_ns = _filetime_100ns_to_unix_ns(kernel_identity.last_write_time_100ns)
    ctime_ns = _filetime_100ns_to_unix_ns(kernel_identity.creation_time_100ns)
    if project_stat:
        duplicate = api.duplicate_handle(raw_handle)
        try:
            file_descriptor = descriptor_bridge.open_binary_fd(duplicate, writable=False)
        except BaseException:
            api.close_handle(duplicate)
            raise
        try:
            stat_result = os.fstat(file_descriptor)
        finally:
            os.close(file_descriptor)
        device_id = stat_result.st_dev
        inode = stat_result.st_ino
        size = stat_result.st_size
        mtime_ns = stat_result.st_mtime_ns
        ctime_ns = stat_change_marker_ns(stat_result)
    return Win32FileIdentity(
        device_id=device_id,
        inode=inode,
        size=size,
        mtime_ns=mtime_ns,
        ctime_ns=ctime_ns,
        volume_serial_number=kernel_identity.volume_serial_number,
        file_id=kernel_identity.file_id,
        attributes=kernel_identity.attributes,
        reparse_tag=kernel_identity.reparse_tag,
        is_directory=kernel_identity.is_directory,
    )


def _unix_ns_to_filetime_100ns(timestamp_ns: int) -> int:
    return timestamp_ns // _HUNDRED_NS_PER_NS + _WINDOWS_TO_UNIX_EPOCH_100NS


def _filetime_100ns_to_unix_ns(timestamp_100ns: int) -> int:
    return (timestamp_100ns - _WINDOWS_TO_UNIX_EPOCH_100NS) * _HUNDRED_NS_PER_NS


def _select_file_identifier(
    *,
    extended_file_id: bytes | None,
    extended_volume_serial: int | None,
    legacy_volume_serial: int,
    legacy_file_index: int,
) -> tuple[int, bytes]:
    if extended_file_id is None:
        raise OSError(WIN32_IDENTITY_UNAVAILABLE_MESSAGE)
    if any(extended_file_id):
        if extended_volume_serial is None:
            raise OSError(WIN32_IDENTITY_UNAVAILABLE_MESSAGE)
        return extended_volume_serial, extended_file_id
    if legacy_file_index == 0:
        raise OSError(WIN32_IDENTITY_UNAVAILABLE_MESSAGE)
    return legacy_volume_serial, legacy_file_index.to_bytes(16, byteorder="little", signed=False)


@final
class _CtypesWin32HandleApi:
    """Kernel32 implementation loaded lazily so POSIX imports stay valid."""

    def __init__(self) -> None:
        if os.name != "nt":
            raise OSError(WIN32_UNAVAILABLE_MESSAGE)
        library_loader = cast("Callable[..., object]", ctypes.WinDLL)
        self._kernel32: _Kernel32 = cast("_Kernel32", library_loader("kernel32", use_last_error=True))
        _configure_kernel32(self._kernel32)

    def create_file(
        self,
        path: str,
        *,
        desired_access: int,
        share_mode: int,
        creation_disposition: int,
        flags: int,
    ) -> int:
        """Return one native handle or raise the translated Windows error."""
        result = cast(
            "int | None",
            self._kernel32.CreateFileW(
                path,
                desired_access,
                share_mode,
                None,
                creation_disposition,
                flags,
                None,
            ),
        )
        if result is None or result == _INVALID_HANDLE_VALUE:
            raise self._last_error()
        return result

    def close_handle(self, handle: int) -> None:
        """Close one native handle."""
        if not bool(self._kernel32.CloseHandle(handle)):
            raise self._last_error()

    def duplicate_handle(self, handle: int) -> int:
        """Return a non-inheritable duplicate in the current process."""
        current_process = self._kernel32.GetCurrentProcess()
        duplicated = ctypes.c_void_p()
        if not bool(
            self._kernel32.DuplicateHandle(
                current_process,
                handle,
                current_process,
                ctypes.byref(duplicated),
                0,
                False,  # noqa: FBT003  # External Win32 BOOL positional parameter.
                _DUPLICATE_SAME_ACCESS,
            )
        ):
            raise self._last_error()
        if duplicated.value is None:
            raise self._last_error()
        return duplicated.value

    def query_kernel_identity(self, handle: int) -> _KernelFileIdentity:
        """Return stable and mutable state directly from the retained handle."""
        basic_info = self._query_information(handle, _FILE_BASIC_INFO_CLASS, _FileBasicInfo)
        standard_info = self._query_information(handle, _FILE_STANDARD_INFO_CLASS, _FileStandardInfo)
        attribute_info = self._query_information(
            handle,
            _FILE_ATTRIBUTE_TAG_INFO_CLASS,
            _FileAttributeTagInfo,
        )
        id_info = self._query_information(handle, _FILE_ID_INFO_CLASS, _FileIdInfo)
        file_id_value = cast("_FileId128", id_info.file_id)
        extended_file_id = ctypes.string_at(
            ctypes.addressof(file_id_value),
            ctypes.sizeof(_FileId128),
        )
        extended_volume_serial = cast("int", id_info.volume_serial_number)
        if any(extended_file_id):
            volume_serial_number, file_id = _select_file_identifier(
                extended_file_id=extended_file_id,
                extended_volume_serial=extended_volume_serial,
                legacy_volume_serial=0,
                legacy_file_index=0,
            )
        else:
            legacy_info = self._query_legacy_information(handle)
            volume_serial_number, file_id = _select_file_identifier(
                extended_file_id=extended_file_id,
                extended_volume_serial=extended_volume_serial,
                legacy_volume_serial=cast("int", legacy_info.volume_serial_number),
                legacy_file_index=(cast("int", legacy_info.file_index_high) << 32)
                | cast("int", legacy_info.file_index_low),
            )
        return _KernelFileIdentity(
            volume_serial_number=volume_serial_number,
            file_id=file_id,
            size=cast("int", standard_info.end_of_file),
            creation_time_100ns=cast("int", basic_info.creation_time),
            last_write_time_100ns=cast("int", basic_info.last_write_time),
            attributes=cast("int", attribute_info.file_attributes),
            reparse_tag=cast("int", attribute_info.reparse_tag),
            is_directory=bool(cast("int", standard_info.directory)),
        )

    def _query_legacy_information(self, handle: int) -> _ByHandleFileInformation:
        information = _ByHandleFileInformation()
        if not bool(self._kernel32.GetFileInformationByHandle(handle, ctypes.byref(information))):
            raise self._last_error()
        return information

    def query_final_path(self, handle: int) -> str:
        """Return the normalized DOS final path for a retained handle."""
        required_size = int(cast("int", self._kernel32.GetFinalPathNameByHandleW(handle, None, 0, 0)))
        if required_size == 0:
            raise self._last_error()
        buffer = ctypes.create_unicode_buffer(required_size + 1)
        written = int(
            cast(
                "int",
                self._kernel32.GetFinalPathNameByHandleW(
                    handle,
                    buffer,
                    len(buffer),
                    0,
                ),
            )
        )
        if written == 0:
            raise self._last_error()
        if written >= len(buffer):
            buffer = ctypes.create_unicode_buffer(written + 1)
            written = int(
                cast(
                    "int",
                    self._kernel32.GetFinalPathNameByHandleW(
                        handle,
                        buffer,
                        len(buffer),
                        0,
                    ),
                )
            )
            if written == 0 or written >= len(buffer):
                raise self._last_error()
        return cast("str", buffer.value)

    def mark_delete(self, handle: int) -> None:
        """Mark the exact object referenced by a DELETE-capable handle."""
        disposition = _FileDispositionInfo(delete_file=True)
        self._set_information(handle, _FILE_DISPOSITION_INFO_CLASS, disposition)

    def set_basic_info(
        self,
        handle: int,
        *,
        attributes: int,
        atime_100ns: int,
        mtime_100ns: int,
    ) -> None:
        """Update timestamps and attributes through one retained handle."""
        basic_info = _FileBasicInfo(
            creation_time=0,
            last_access_time=atime_100ns,
            last_write_time=mtime_100ns,
            change_time=0,
            file_attributes=attributes,
        )
        self._set_information(handle, _FILE_BASIC_INFO_CLASS, basic_info)

    def _query_information[
        StructureT: ctypes.Structure,
    ](
        self,
        handle: int,
        information_class: int,
        structure_type: type[StructureT],
    ) -> StructureT:
        information = structure_type()
        if not bool(
            self._kernel32.GetFileInformationByHandleEx(
                handle,
                information_class,
                ctypes.byref(information),
                ctypes.sizeof(information),
            )
        ):
            raise self._last_error()
        return information

    def _set_information(
        self,
        handle: int,
        information_class: int,
        information: ctypes.Structure,
    ) -> None:
        if not bool(
            self._kernel32.SetFileInformationByHandle(
                handle,
                information_class,
                ctypes.byref(information),
                ctypes.sizeof(information),
            )
        ):
            raise self._last_error()

    def _last_error(self) -> OSError:
        error_code = ctypes.get_last_error()
        error_factory = cast("Callable[[int], OSError]", ctypes.WinError)
        native_error = error_factory(error_code)
        if error_code in _WIN32_ALREADY_EXISTS_ERROR_CODES:
            return FileExistsError(error_code, str(native_error))
        if error_code in _WIN32_NOT_FOUND_ERROR_CODES:
            return FileNotFoundError(error_code, str(native_error))
        return native_error


class _CtypesFunction(Protocol):
    """Configurable ctypes function pointer."""

    argtypes: list[object]
    restype: object

    def __call__(self, *arguments: object) -> object:
        """Invoke the configured function pointer."""
        ...


class _Kernel32(Protocol):
    """Typed kernel32 exports used by the adapter."""

    CreateFileW: _CtypesFunction
    CloseHandle: _CtypesFunction
    DuplicateHandle: _CtypesFunction
    GetCurrentProcess: _CtypesFunction
    GetFileInformationByHandle: _CtypesFunction
    GetFileInformationByHandleEx: _CtypesFunction
    GetFinalPathNameByHandleW: _CtypesFunction
    SetFileInformationByHandle: _CtypesFunction


def _configure_kernel32(kernel32: _Kernel32) -> None:
    handle_type = ctypes.c_void_p
    kernel32.CreateFileW.argtypes = [
        ctypes.c_wchar_p,
        ctypes.c_uint32,
        ctypes.c_uint32,
        ctypes.c_void_p,
        ctypes.c_uint32,
        ctypes.c_uint32,
        handle_type,
    ]
    kernel32.CreateFileW.restype = handle_type
    kernel32.CloseHandle.argtypes = [handle_type]
    kernel32.CloseHandle.restype = ctypes.c_int32
    kernel32.DuplicateHandle.argtypes = [
        handle_type,
        handle_type,
        handle_type,
        ctypes.POINTER(handle_type),
        ctypes.c_uint32,
        ctypes.c_int32,
        ctypes.c_uint32,
    ]
    kernel32.DuplicateHandle.restype = ctypes.c_int32
    kernel32.GetCurrentProcess.argtypes = []
    kernel32.GetCurrentProcess.restype = handle_type
    kernel32.GetFileInformationByHandle.argtypes = [handle_type, ctypes.c_void_p]
    kernel32.GetFileInformationByHandle.restype = ctypes.c_int32
    kernel32.GetFileInformationByHandleEx.argtypes = [
        handle_type,
        ctypes.c_int32,
        ctypes.c_void_p,
        ctypes.c_uint32,
    ]
    kernel32.GetFileInformationByHandleEx.restype = ctypes.c_int32
    kernel32.GetFinalPathNameByHandleW.argtypes = [
        handle_type,
        ctypes.POINTER(ctypes.c_wchar),
        ctypes.c_uint32,
        ctypes.c_uint32,
    ]
    kernel32.GetFinalPathNameByHandleW.restype = ctypes.c_uint32
    kernel32.SetFileInformationByHandle.argtypes = [
        handle_type,
        ctypes.c_int32,
        ctypes.c_void_p,
        ctypes.c_uint32,
    ]
    kernel32.SetFileInformationByHandle.restype = ctypes.c_int32


class _MsvcrtDescriptorBridge:
    """Microsoft C-runtime descriptor conversion loaded only when used."""

    def open_binary_fd(self, handle: int, *, writable: bool) -> int:
        module = cast("_MsvcrtModule", cast("object", import_module("msvcrt")))
        flags = os.O_RDWR if writable else os.O_RDONLY
        flags |= getattr(os, "O_BINARY", 0) | getattr(os, "O_NOINHERIT", 0)
        return module.open_osfhandle(handle, flags)


class _MsvcrtModule(Protocol):
    """Typed msvcrt subset used for native-handle conversion."""

    def open_osfhandle(self, handle: int, flags: int) -> int:
        """Consume a native handle and return a C-runtime descriptor."""
        ...
