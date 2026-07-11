"""
Summary: Tests opt-in reconstruction from persisted Track stat baselines.
Why: Keeps every trust-stat eligibility boundary fail-closed and deterministic.
"""

from __future__ import annotations

from dataclasses import replace
from datetime import UTC, datetime, timedelta
from uuid import UUID

from omym2.domain.models.file_scan_entry import FileScanEntry
from omym2.domain.models.track import Track, TrackStatus
from omym2.domain.models.track_metadata import TrackMetadata
from omym2.domain.services.snapshot_baseline import snapshot_from_trusted_stat
from omym2.shared.ids import LibraryId, TrackId

BASE_TIME = datetime(2026, 1, 1, tzinfo=UTC)
CONTENT_HASH = "content-hash"
EXPECTED_PATH = "/music/Artist/Album/Title.flac"
FILE_EXTENSION = ".flac"
FILE_SIZE = 1024
LIBRARY_ID = LibraryId(UUID("018f6a4f-3c2d-7b8a-9abc-def012345678"))
METADATA = TrackMetadata(title="Title", artist="Artist", album="Album")
METADATA_HASH = "metadata-hash"
SOURCE_PATH = "Artist/Album/Title.flac"
TRACK_ID = TrackId(UUID("018f6a4f-3c2d-7b8a-9abc-def012345679"))


def test_matching_complete_active_baseline_reconstructs_snapshot() -> None:
    """A complete exact stat match reuses every persisted managed value."""
    track = _track()
    observation = _observation()

    snapshot = snapshot_from_trusted_stat(
        track,
        SOURCE_PATH,
        EXPECTED_PATH,
        observation,
        BASE_TIME,
    )

    assert snapshot is not None
    assert snapshot.path == EXPECTED_PATH
    assert snapshot.content_hash == CONTENT_HASH
    assert snapshot.metadata_hash == METADATA_HASH
    assert snapshot.metadata == METADATA
    assert snapshot.size == FILE_SIZE
    assert snapshot.mtime == BASE_TIME


def test_incomplete_or_mismatching_stat_baseline_is_not_trusted() -> None:
    """Null, size-changed, and mtime-changed baselines all require a full capture."""
    observation = _observation()
    candidates = (
        replace(_track(), size=None),
        replace(_track(), mtime=None),
        replace(_track(), size=FILE_SIZE + 1),
        replace(_track(), mtime=BASE_TIME + timedelta(seconds=1)),
    )

    for track in candidates:
        assert (
            snapshot_from_trusted_stat(
                track,
                SOURCE_PATH,
                EXPECTED_PATH,
                observation,
                BASE_TIME,
            )
            is None
        )


def test_inactive_or_path_mismatching_track_is_not_trusted() -> None:
    """Track status plus logical and observed path identity must all match."""
    observation = _observation()

    assert (
        snapshot_from_trusted_stat(
            replace(_track(), status=TrackStatus.REMOVED),
            SOURCE_PATH,
            EXPECTED_PATH,
            observation,
            BASE_TIME,
        )
        is None
    )
    assert (
        snapshot_from_trusted_stat(
            _track(),
            "Other/Title.flac",
            EXPECTED_PATH,
            observation,
            BASE_TIME,
        )
        is None
    )
    assert (
        snapshot_from_trusted_stat(
            _track(),
            SOURCE_PATH,
            "/music/Other.flac",
            observation,
            BASE_TIME,
        )
        is None
    )


def _track() -> Track:
    return Track(
        track_id=TRACK_ID,
        library_id=LIBRARY_ID,
        current_path=SOURCE_PATH,
        canonical_path=SOURCE_PATH,
        content_hash=CONTENT_HASH,
        metadata_hash=METADATA_HASH,
        size=FILE_SIZE,
        mtime=BASE_TIME,
        metadata=METADATA,
        status=TrackStatus.ACTIVE,
        first_seen_at=BASE_TIME,
        last_seen_at=BASE_TIME,
        updated_at=BASE_TIME,
    )


def _observation() -> FileScanEntry:
    return FileScanEntry(
        path=EXPECTED_PATH,
        size=FILE_SIZE,
        mtime=BASE_TIME,
        file_extension=FILE_EXTENSION,
    )
