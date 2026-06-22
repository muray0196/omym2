"""
Summary: Tests read-only filesystem adapters.
Why: Verifies Phase 6 scanning, hashing, snapshots, and path resolution.
"""

from __future__ import annotations

from datetime import UTC, datetime
from typing import TYPE_CHECKING

import pytest

from omym2.adapters.fs.file_scanner import FilesystemFileScanner
from omym2.adapters.fs.file_snapshot_reader import FilesystemFileSnapshotReader
from omym2.adapters.fs.hash_calculator import INVALID_CHUNK_SIZE_MESSAGE, FileContentHasher
from omym2.adapters.fs.path_resolver import PATH_OUTSIDE_LIBRARY_MESSAGE, FilesystemPathResolver
from omym2.domain.models.track_metadata import TrackMetadata
from omym2.domain.services.content_fingerprint import calculate_content_fingerprint
from omym2.domain.services.metadata_fingerprint import calculate_metadata_fingerprint
from tests.fakes.runtime import FixedClock

if TYPE_CHECKING:
    from pathlib import Path

    from omym2.features.common_ports import FileSystemPath

AUDIO_CONTENT = b"fake audio bytes"
AUDIO_FILE_NAME = "Track.FLAC"
IGNORED_FILE_NAME = "cover.jpg"
EXPECTED_CANONICAL_PATH = "Artist/Album/Track.flac"
EXPECTED_RESOLVED_PARTS = ("Artist", "Album", "Track.flac")
FIXED_TIME = datetime(2026, 1, 1, tzinfo=UTC)
INVALID_CHUNK_SIZE = 0
NESTED_DIRECTORY_NAME = "Artist"
RELATIVE_PATH_WITH_CURRENT_DIR = "./Artist/Album/Track.flac"
TRACK_ALBUM = "Album"
TRACK_ARTIST = "Artist"
TRACK_TITLE = "Track"


def test_file_scanner_returns_file_scan_entries_not_snapshots(tmp_path: Path) -> None:
    """FileScanner finds supported music files without reading tags or hashes."""
    nested_dir = tmp_path / NESTED_DIRECTORY_NAME
    nested_dir.mkdir()
    audio_path = nested_dir / AUDIO_FILE_NAME
    _ = audio_path.write_bytes(AUDIO_CONTENT)
    _ = (nested_dir / IGNORED_FILE_NAME).write_bytes(AUDIO_CONTENT)

    entries = FilesystemFileScanner().scan(tmp_path)

    assert len(entries) == 1
    entry = entries[0]
    assert entry.path == str(audio_path)
    assert entry.size == len(AUDIO_CONTENT)
    assert entry.file_extension == ".flac"
    assert entry.mtime.tzinfo is UTC
    assert not hasattr(entry, "content_hash")


def test_file_snapshot_reader_captures_metadata_and_hash(tmp_path: Path) -> None:
    """FileSnapshotReader captures stat data, metadata, and both hashes."""
    audio_path = tmp_path / AUDIO_FILE_NAME
    _ = audio_path.write_bytes(AUDIO_CONTENT)
    metadata = _metadata()
    reader = FilesystemFileSnapshotReader(
        metadata_reader=StaticMetadataReader(metadata),
        clock=FixedClock(FIXED_TIME),
        hasher=FileContentHasher(chunk_size_bytes=4),
    )

    snapshot = reader.capture(audio_path)

    assert snapshot.path == str(audio_path)
    assert snapshot.size == len(AUDIO_CONTENT)
    assert snapshot.file_extension == ".flac"
    assert snapshot.content_hash == calculate_content_fingerprint(AUDIO_CONTENT)
    assert snapshot.metadata_hash == calculate_metadata_fingerprint(metadata)
    assert snapshot.metadata == metadata
    assert snapshot.captured_at == FIXED_TIME


def test_path_resolver_maps_library_relative_paths(tmp_path: Path) -> None:
    """PathResolver combines Library roots with normalized stored paths."""
    resolver = FilesystemPathResolver()
    library_root = tmp_path / "library"

    resolved_path = resolver.resolve_library_path(library_root, RELATIVE_PATH_WITH_CURRENT_DIR)

    assert resolved_path == library_root.joinpath(*EXPECTED_RESOLVED_PARTS)
    assert resolver.relative_to_library(library_root, resolved_path) == EXPECTED_CANONICAL_PATH


def test_path_resolver_rejects_paths_outside_library(tmp_path: Path) -> None:
    """PathResolver refuses to convert unrelated paths into Library-relative data."""
    resolver = FilesystemPathResolver()

    with pytest.raises(ValueError, match=PATH_OUTSIDE_LIBRARY_MESSAGE):
        _ = resolver.relative_to_library(tmp_path / "library", tmp_path / "outside" / AUDIO_FILE_NAME)


def test_file_content_hasher_rejects_invalid_chunk_size() -> None:
    """Hasher validates chunk sizing before opening files."""
    with pytest.raises(ValueError, match=INVALID_CHUNK_SIZE_MESSAGE):
        _ = FileContentHasher(chunk_size_bytes=INVALID_CHUNK_SIZE)


class StaticMetadataReader:
    """MetadataReader fake that returns one predetermined metadata value."""

    def __init__(self, metadata: TrackMetadata) -> None:
        """Store metadata for later capture calls."""
        self._metadata: TrackMetadata = metadata

    def read(self, path: FileSystemPath) -> TrackMetadata:
        """Return metadata without reading the supplied test fixture."""
        del path
        return self._metadata


def _metadata() -> TrackMetadata:
    return TrackMetadata(title=TRACK_TITLE, artist=TRACK_ARTIST, album=TRACK_ALBUM)
