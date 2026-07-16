"""
Summary: Tests metadata-free file content snapshot invariants.
Why: Keeps generic companion and unprocessed observations deterministic.
"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta, timezone

import pytest

from omym2.domain.models.file_snapshot import FileContentSnapshot, FilesystemIdentity

CAPTURED_TIME = datetime(2026, 1, 2, 3, tzinfo=UTC)
CONTENT_HASH = "content-hash"
DEVICE_ID = 11
FILE_CTIME_NS = 1_234_567_892
FILE_INODE = 22
FILE_MTIME_NS = 1_234_567_890
FILE_PATH = "/source/notes.txt"
FILE_SIZE = 17
NEGATIVE_FILE_SIZE = -1
OBSERVED_TIME_OFFSET_HOURS = 9
OBSERVED_TIME = datetime(
    2026,
    1,
    2,
    12,
    tzinfo=timezone(timedelta(hours=OBSERVED_TIME_OFFSET_HOURS)),
)


def test_file_content_snapshot_normalizes_timestamps_and_preserves_identity() -> None:
    """Generic snapshots retain content and ephemeral filesystem evidence without metadata."""
    identity = FilesystemIdentity(
        device_id=DEVICE_ID,
        inode=FILE_INODE,
        size=FILE_SIZE,
        mtime_ns=FILE_MTIME_NS,
        ctime_ns=FILE_CTIME_NS,
    )

    snapshot = FileContentSnapshot(
        path=FILE_PATH,
        size=FILE_SIZE,
        mtime=OBSERVED_TIME,
        content_hash=CONTENT_HASH,
        filesystem_identity=identity,
        captured_at=OBSERVED_TIME,
    )

    assert snapshot.path == FILE_PATH
    assert snapshot.size == FILE_SIZE
    assert snapshot.mtime == CAPTURED_TIME
    assert snapshot.content_hash == CONTENT_HASH
    assert snapshot.filesystem_identity == identity
    assert snapshot.captured_at == CAPTURED_TIME
    assert not hasattr(snapshot, "metadata")
    assert not hasattr(snapshot, "metadata_hash")


def test_file_content_snapshot_rejects_negative_size() -> None:
    """A regular-file observation cannot report a negative byte count."""
    with pytest.raises(ValueError, match="must not be negative"):
        _ = FileContentSnapshot(
            path=FILE_PATH,
            size=NEGATIVE_FILE_SIZE,
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
