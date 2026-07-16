"""
Summary: Tests shared feature ports for metadata-free file observation.
Why: Keeps companion and unprocessed usecases independent from filesystem adapters.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime
from typing import TYPE_CHECKING

from omym2.domain.models.file_snapshot import FileContentSnapshot, FilesystemIdentity
from omym2.features.common_ports import (
    FileContentSnapshotReader,
    SourceInventoryEntry,
    SourceInventoryReader,
    SourceInventoryRequest,
)

if TYPE_CHECKING:
    from collections.abc import Sequence

    from omym2.features.common_ports import FileSystemPath

CAPTURED_TIME = datetime(2026, 1, 1, tzinfo=UTC)
CONTENT_HASH = "content-hash"
DEVICE_ID = 11
EXCLUDED_ROOT = "/source/Unprocessed"
FILE_CTIME_NS = 1_234_567_892
FILE_INODE = 22
FILE_MTIME_NS = 1_234_567_890
FILE_PATH = "/source/notes.txt"
FILE_RELATIVE_PATH = "notes.txt"
FILE_SIZE = 5
SOURCE_ROOT = "/source"


def test_content_snapshot_reader_contract_is_metadata_free_and_root_anchored() -> None:
    """Feature callers supply the root and consume only generic content evidence."""
    expected = FileContentSnapshot(
        path=FILE_PATH,
        size=FILE_SIZE,
        mtime=CAPTURED_TIME,
        content_hash=CONTENT_HASH,
        filesystem_identity=FilesystemIdentity(
            device_id=DEVICE_ID,
            inode=FILE_INODE,
            size=FILE_SIZE,
            mtime_ns=FILE_MTIME_NS,
            ctime_ns=FILE_CTIME_NS,
        ),
        captured_at=CAPTURED_TIME,
    )
    reader: FileContentSnapshotReader = StaticFileContentSnapshotReader(expected)

    captured = _capture(reader, FILE_PATH, SOURCE_ROOT)

    assert captured == expected
    assert reader.requests == [(FILE_PATH, SOURCE_ROOT)]


def test_source_inventory_contract_carries_exclusions_and_relative_paths() -> None:
    """Feature callers own excluded-root policy while adapters return mechanical path facts."""
    expected = (SourceInventoryEntry(path=FILE_PATH, relative_path=FILE_RELATIVE_PATH),)
    reader: SourceInventoryReader = StaticSourceInventoryReader(expected)
    request = SourceInventoryRequest(root=SOURCE_ROOT, excluded_roots=(EXCLUDED_ROOT,))

    entries = _scan(reader, request)

    assert entries == expected
    assert reader.requests == [request]


def _capture(
    reader: FileContentSnapshotReader,
    path: FileSystemPath,
    root: FileSystemPath,
) -> FileContentSnapshot:
    return reader.capture(path, root=root)


def _scan(reader: SourceInventoryReader, request: SourceInventoryRequest) -> Sequence[SourceInventoryEntry]:
    return reader.scan(request)


@dataclass(slots=True)
class StaticFileContentSnapshotReader:
    """Record generic snapshot requests without filesystem I/O."""

    result: FileContentSnapshot
    requests: list[tuple[FileSystemPath, FileSystemPath]]

    def __init__(self, result: FileContentSnapshot) -> None:
        """Initialize one fixed result and an empty request log."""
        self.result = result
        self.requests = []

    def capture(self, path: FileSystemPath, *, root: FileSystemPath) -> FileContentSnapshot:
        """Record the root-anchored request and return fixed evidence."""
        self.requests.append((path, root))
        return self.result


@dataclass(slots=True)
class StaticSourceInventoryReader:
    """Record source inventory requests without filesystem I/O."""

    result: tuple[SourceInventoryEntry, ...]
    requests: list[SourceInventoryRequest]

    def __init__(self, result: tuple[SourceInventoryEntry, ...]) -> None:
        """Initialize fixed entries and an empty request log."""
        self.result = result
        self.requests = []

    def scan(self, request: SourceInventoryRequest) -> tuple[SourceInventoryEntry, ...]:
        """Record the request and return fixed path facts."""
        self.requests.append(request)
        return self.result
