"""
Summary: Tests read-only filesystem adapters.
Why: Verifies scanning, hashing, snapshots, and path resolution.
"""

from __future__ import annotations

import errno
import os
from datetime import UTC, datetime
from pathlib import Path
from threading import Barrier, Lock
from typing import TYPE_CHECKING

import pytest

from omym2.adapters.fs.file_mover import FilesystemFileMover
from omym2.adapters.fs.file_presence import FilesystemFilePresence
from omym2.adapters.fs.file_scanner import FilesystemFileScanner
from omym2.adapters.fs.file_snapshot_reader import (
    INVALID_SNAPSHOT_CAPTURE_WORKER_COUNT_MESSAGE,
    SCAN_OBSERVATION_PATH_MISMATCH_MESSAGE,
    FilesystemFileSnapshotReader,
)
from omym2.adapters.fs.hash_calculator import INVALID_CHUNK_SIZE_MESSAGE, FileContentHasher
from omym2.adapters.fs.path_resolver import PATH_OUTSIDE_LIBRARY_MESSAGE, FilesystemPathResolver
from omym2.config import FILE_SNAPSHOT_CAPTURE_MIN_WORKER_COUNT
from omym2.domain.models.file_scan_entry import FileScanEntry
from omym2.domain.models.track_metadata import TrackMetadata
from omym2.domain.services.content_fingerprint import calculate_content_fingerprint
from omym2.domain.services.metadata_fingerprint import calculate_metadata_fingerprint
from omym2.features.common_ports import FileSnapshotCaptureRequest, MetadataReadError
from tests.fakes.runtime import FixedClock

if TYPE_CHECKING:
    from omym2.features.common_ports import FileSystemPath

AUDIO_CONTENT = b"fake audio bytes"
AUDIO_FILE_NAME = "Track.FLAC"
AUDIO_FILE_EXTENSION = ".flac"
BATCH_FILE_COUNT = 4
BATCH_BARRIER_TIMEOUT_SECONDS = 5.0
BATCH_WORKER_COUNT = 2
SECOND_AUDIO_FILE_NAME = "Second.FLAC"
MISSING_AUDIO_FILE_NAME = "Missing.FLAC"
METADATA_READ_FAILURE_MESSAGE = "metadata read failed"
DIRECTORY_NAMED_LIKE_MUSIC_FILE = "fake.flac"
IGNORED_FILE_NAME = "cover.jpg"
EXPECTED_CANONICAL_PATH = "Artist/Album/Track.flac"
EXPECTED_RESOLVED_PARTS = ("Artist", "Album", "Track.flac")
FIXED_TIME = datetime(2026, 1, 1, tzinfo=UTC)
INVALID_CHUNK_SIZE = 0
INVALID_SNAPSHOT_WORKER_COUNT = FILE_SNAPSHOT_CAPTURE_MIN_WORKER_COUNT - 1
NESTED_DIRECTORY_NAME = "Artist"
RELATIVE_PATH_WITH_CURRENT_DIR = "./Artist/Album/Track.flac"
TRACK_ALBUM = "Album"
TRACK_ARTIST = "Artist"
TRACK_TITLE = "Track"
TARGET_FILE_NAME = "Moved.flac"
SECOND_TARGET_FILE_NAME = "Second-Moved.flac"
UNEXPECTED_STAT_MESSAGE = "snapshot capture must reuse the supplied scan observation"


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
    assert entry.file_extension == AUDIO_FILE_EXTENSION
    assert entry.mtime.tzinfo is UTC
    assert not hasattr(entry, "content_hash")


def test_file_stat_reader_observes_one_regular_file(tmp_path: Path) -> None:
    """Single-file stat reads preserve path, size, UTC mtime, and normalized extension."""
    audio_path = tmp_path / AUDIO_FILE_NAME
    _ = audio_path.write_bytes(AUDIO_CONTENT)

    entry = FilesystemFileScanner().observe(audio_path)

    assert entry.path == str(audio_path)
    assert entry.size == len(AUDIO_CONTENT)
    assert entry.mtime.tzinfo is UTC
    assert entry.file_extension == AUDIO_FILE_EXTENSION


def test_file_stat_reader_rejects_missing_and_non_regular_paths(tmp_path: Path) -> None:
    """Only an existing regular file can become a trust-stat observation."""
    directory_path = tmp_path / NESTED_DIRECTORY_NAME
    directory_path.mkdir()

    with pytest.raises(FileNotFoundError):
        _ = FilesystemFileScanner().observe(tmp_path / MISSING_AUDIO_FILE_NAME)
    with pytest.raises(IsADirectoryError):
        _ = FilesystemFileScanner().observe(directory_path)


def test_file_scanner_excludes_directories_named_like_music_files(tmp_path: Path) -> None:
    """FileScanner never lists a directory whose name carries a music extension."""
    disguised_dir = tmp_path / DIRECTORY_NAMED_LIKE_MUSIC_FILE
    disguised_dir.mkdir()
    audio_path = disguised_dir / AUDIO_FILE_NAME
    _ = audio_path.write_bytes(AUDIO_CONTENT)

    entries = FilesystemFileScanner().scan(tmp_path)

    assert [entry.path for entry in entries] == [str(audio_path)]


def test_file_scanner_sorts_entries_by_posix_path_across_directories(tmp_path: Path) -> None:
    """FileScanner returns nested-tree entries ordered by their posix paths."""
    relative_paths = ("track0.flac", "b/track1.flac", "a/track2.flac", "a/z/track3.mp3")
    for relative_path in relative_paths:
        file_path = tmp_path.joinpath(*relative_path.split("/"))
        file_path.parent.mkdir(parents=True, exist_ok=True)
        _ = file_path.write_bytes(AUDIO_CONTENT)

    entries = FilesystemFileScanner().scan(tmp_path)

    assert [entry.path for entry in entries] == [
        str(tmp_path / "a" / "track2.flac"),
        str(tmp_path / "a" / "z" / "track3.mp3"),
        str(tmp_path / "b" / "track1.flac"),
        str(tmp_path / "track0.flac"),
    ]


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
    assert snapshot.file_extension == AUDIO_FILE_EXTENSION
    assert snapshot.content_hash == calculate_content_fingerprint(AUDIO_CONTENT)
    assert snapshot.metadata_hash == calculate_metadata_fingerprint(metadata)
    assert snapshot.metadata == metadata
    assert snapshot.captured_at == FIXED_TIME


def test_file_snapshot_reader_reuses_matching_scan_observation(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """A supplied FileScanEntry provides stat fields without a second filesystem stat."""
    audio_path = tmp_path / AUDIO_FILE_NAME
    _ = audio_path.write_bytes(AUDIO_CONTENT)
    observation = FilesystemFileScanner().scan(tmp_path)[0]
    real_stat = Path.stat

    def reject_repeated_audio_stat(path: Path, *, follow_symlinks: bool = True) -> os.stat_result:
        if path == audio_path:
            raise AssertionError(UNEXPECTED_STAT_MESSAGE)
        return real_stat(path, follow_symlinks=follow_symlinks)

    monkeypatch.setattr(Path, "stat", reject_repeated_audio_stat)
    reader = FilesystemFileSnapshotReader(
        metadata_reader=StaticMetadataReader(_metadata()),
        clock=FixedClock(FIXED_TIME),
    )

    snapshot = reader.capture(audio_path, observation=observation)

    assert snapshot.path == observation.path
    assert snapshot.size == observation.size
    assert snapshot.mtime == observation.mtime
    assert snapshot.file_extension == observation.file_extension


def test_file_snapshot_reader_rejects_scan_observation_for_another_path(tmp_path: Path) -> None:
    """A scan observation cannot supply stat identity for a different file path."""
    audio_path = tmp_path / AUDIO_FILE_NAME
    _ = audio_path.write_bytes(AUDIO_CONTENT)
    observation = FileScanEntry(
        path=str(tmp_path / SECOND_AUDIO_FILE_NAME),
        size=len(AUDIO_CONTENT),
        mtime=FIXED_TIME,
        file_extension=AUDIO_FILE_EXTENSION,
    )
    reader = FilesystemFileSnapshotReader(metadata_reader=StaticMetadataReader(_metadata()))

    with pytest.raises(ValueError, match=SCAN_OBSERVATION_PATH_MISMATCH_MESSAGE):
        _ = reader.capture(audio_path, observation=observation)


def test_file_snapshot_reader_batch_preserves_request_order_and_missing_results(tmp_path: Path) -> None:
    """Batch capture keeps input positions while representing vanished files as None."""
    first_path = tmp_path / AUDIO_FILE_NAME
    missing_path = tmp_path / MISSING_AUDIO_FILE_NAME
    second_path = tmp_path / SECOND_AUDIO_FILE_NAME
    _ = first_path.write_bytes(AUDIO_CONTENT)
    _ = second_path.write_bytes(AUDIO_CONTENT)
    reader = FilesystemFileSnapshotReader(
        metadata_reader=StaticMetadataReader(_metadata()),
        clock=FixedClock(FIXED_TIME),
        worker_count=BATCH_WORKER_COUNT,
    )

    snapshots = reader.capture_many(
        tuple(FileSnapshotCaptureRequest(path) for path in (first_path, missing_path, second_path))
    )

    assert tuple(None if snapshot is None else snapshot.path for snapshot in snapshots) == (
        str(first_path),
        None,
        str(second_path),
    )


def test_file_snapshot_reader_batch_bounds_concurrent_capture_workers(tmp_path: Path) -> None:
    """Batch capture never exceeds its configured worker bound."""
    paths = tuple(tmp_path / f"{index}.flac" for index in range(BATCH_FILE_COUNT))
    for path in paths:
        _ = path.write_bytes(AUDIO_CONTENT)
    metadata_reader = PeakConcurrencyMetadataReader(BATCH_WORKER_COUNT)
    reader = FilesystemFileSnapshotReader(
        metadata_reader=metadata_reader,
        clock=FixedClock(FIXED_TIME),
        worker_count=BATCH_WORKER_COUNT,
    )

    snapshots = reader.capture_many(tuple(FileSnapshotCaptureRequest(path) for path in paths))

    assert all(snapshot is not None for snapshot in snapshots)
    assert metadata_reader.peak_active_count == BATCH_WORKER_COUNT


def test_file_snapshot_reader_batch_propagates_non_missing_errors(tmp_path: Path) -> None:
    """Batch capture converts only FileNotFoundError into a missing result."""
    audio_path = tmp_path / AUDIO_FILE_NAME
    _ = audio_path.write_bytes(AUDIO_CONTENT)
    reader = FilesystemFileSnapshotReader(metadata_reader=FailingMetadataReader())

    with pytest.raises(MetadataReadError, match=METADATA_READ_FAILURE_MESSAGE):
        _ = reader.capture_many((FileSnapshotCaptureRequest(audio_path),))


def test_file_snapshot_reader_rejects_invalid_worker_count() -> None:
    """Batch concurrency is validated before any request is submitted."""
    with pytest.raises(ValueError, match=INVALID_SNAPSHOT_CAPTURE_WORKER_COUNT_MESSAGE):
        _ = FilesystemFileSnapshotReader(
            metadata_reader=StaticMetadataReader(_metadata()),
            worker_count=INVALID_SNAPSHOT_WORKER_COUNT,
        )


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


def test_file_presence_reports_existing_paths_without_reading(tmp_path: Path) -> None:
    """FilePresence reports path occupancy for plan-time target conflict checks."""
    audio_path = tmp_path / AUDIO_FILE_NAME
    missing_path = tmp_path / "missing.flac"
    _ = audio_path.write_bytes(AUDIO_CONTENT)
    presence = FilesystemFilePresence()

    assert presence.exists(audio_path)
    assert not presence.exists(missing_path)


def test_file_mover_moves_file_and_creates_parent_directory(tmp_path: Path) -> None:
    """FileMover performs the planned filesystem mutation."""
    source_path = tmp_path / AUDIO_FILE_NAME
    target_path = tmp_path / "Artist" / TARGET_FILE_NAME
    _ = source_path.write_bytes(AUDIO_CONTENT)

    FilesystemFileMover().move(source_path, target_path)

    assert not source_path.exists()
    assert target_path.read_bytes() == AUDIO_CONTENT


def test_file_mover_ensures_shared_parent_directory_once_per_instance(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Repeated moves into one album reuse the directory already ensured by this mover."""
    first_source = tmp_path / AUDIO_FILE_NAME
    second_source = tmp_path / SECOND_AUDIO_FILE_NAME
    target_parent = tmp_path / NESTED_DIRECTORY_NAME
    first_target = target_parent / TARGET_FILE_NAME
    second_target = target_parent / SECOND_TARGET_FILE_NAME
    _ = first_source.write_bytes(AUDIO_CONTENT)
    _ = second_source.write_bytes(AUDIO_CONTENT)
    ensured_paths: list[Path] = []
    real_mkdir = Path.mkdir

    def record_mkdir(
        path: Path,
        mode: int = 0o777,
        *,
        parents: bool = False,
        exist_ok: bool = False,
    ) -> None:
        ensured_paths.append(path)
        real_mkdir(path, mode=mode, parents=parents, exist_ok=exist_ok)

    monkeypatch.setattr(Path, "mkdir", record_mkdir)
    mover = FilesystemFileMover()

    mover.move(first_source, first_target)
    mover.move(second_source, second_target)

    assert ensured_paths == [target_parent]
    assert first_target.read_bytes() == AUDIO_CONTENT
    assert second_target.read_bytes() == AUDIO_CONTENT


def test_file_mover_recreates_cached_parent_removed_between_moves(tmp_path: Path) -> None:
    """A removed cached album directory is recreated before the next planned move."""
    first_source = tmp_path / AUDIO_FILE_NAME
    second_source = tmp_path / SECOND_AUDIO_FILE_NAME
    target_parent = tmp_path / NESTED_DIRECTORY_NAME
    first_target = target_parent / TARGET_FILE_NAME
    second_target = target_parent / SECOND_TARGET_FILE_NAME
    _ = first_source.write_bytes(AUDIO_CONTENT)
    _ = second_source.write_bytes(AUDIO_CONTENT)
    mover = FilesystemFileMover()
    mover.move(first_source, first_target)
    first_target.unlink()
    target_parent.rmdir()

    mover.move(second_source, second_target)

    assert second_target.read_bytes() == AUDIO_CONTENT


def test_file_mover_moves_file_across_filesystems(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """FileMover handles cross-device moves used by separate Incoming and Library drives."""
    source_path = tmp_path / "incoming" / AUDIO_FILE_NAME
    target_path = tmp_path / "library" / TARGET_FILE_NAME
    source_path.parent.mkdir()
    _ = source_path.write_bytes(AUDIO_CONTENT)

    def raise_cross_device_error(source: os.PathLike[str] | str, target: os.PathLike[str] | str) -> None:
        del target
        raise OSError(errno.EXDEV, "Invalid cross-device link", source)

    # Simulate os.link failing the way it does across mounted filesystems.
    monkeypatch.setattr(os, "link", raise_cross_device_error)

    FilesystemFileMover().move(source_path, target_path)

    assert not source_path.exists()
    assert target_path.read_bytes() == AUDIO_CONTENT


def test_file_mover_moves_file_when_filesystem_refuses_hardlinks(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """FileMover falls back to the exclusive copy claim when hardlinks are refused."""
    source_path = tmp_path / AUDIO_FILE_NAME
    target_path = tmp_path / TARGET_FILE_NAME
    _ = source_path.write_bytes(AUDIO_CONTENT)

    def raise_permission_error(source: os.PathLike[str] | str, target: os.PathLike[str] | str) -> None:
        del target
        raise PermissionError(errno.EPERM, "Operation not permitted", source)

    # Simulate os.link failing the way it does on filesystems without hardlink
    # support, such as exFAT and some network mounts.
    monkeypatch.setattr(os, "link", raise_permission_error)

    FilesystemFileMover().move(source_path, target_path)

    assert not source_path.exists()
    assert target_path.read_bytes() == AUDIO_CONTENT


def test_file_mover_removes_claimed_target_when_source_removal_fails(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """FileMover does not leave a Library duplicate when final source removal fails."""
    source_path = tmp_path / AUDIO_FILE_NAME
    target_path = tmp_path / TARGET_FILE_NAME
    _ = source_path.write_bytes(AUDIO_CONTENT)
    real_unlink = Path.unlink

    def fail_source_unlink(path: Path, *, missing_ok: bool = False) -> None:
        if path == source_path:
            raise PermissionError(errno.EACCES, "Permission denied", path)
        real_unlink(path, missing_ok=missing_ok)

    monkeypatch.setattr(Path, "unlink", fail_source_unlink)

    with pytest.raises(PermissionError):
        FilesystemFileMover().move(source_path, target_path)

    assert source_path.read_bytes() == AUDIO_CONTENT
    assert not target_path.exists()


def test_file_mover_refuses_to_overwrite_existing_target(tmp_path: Path) -> None:
    """FileMover leaves both files untouched when the target already exists."""
    source_path = tmp_path / AUDIO_FILE_NAME
    target_path = tmp_path / TARGET_FILE_NAME
    _ = source_path.write_bytes(AUDIO_CONTENT)
    _ = target_path.write_bytes(b"existing")

    with pytest.raises(FileExistsError):
        FilesystemFileMover().move(source_path, target_path)

    assert source_path.read_bytes() == AUDIO_CONTENT
    assert target_path.read_bytes() == b"existing"


def test_file_mover_does_not_silently_overwrite_on_concurrent_target_creation(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """FileMover still refuses to overwrite a target that appears after a stale check.

    A separate exists()-then-move sequence leaves a race window in which a target
    created between the check and the move gets silently replaced on
    same-filesystem moves. This regression test forces exists() to report the
    target as free (as a stale pre-check would) and then creates the target for
    real before the move runs, proving the mover no longer depends on that
    check and still detects the concurrently created target.
    """
    source_path = tmp_path / AUDIO_FILE_NAME
    target_path = tmp_path / TARGET_FILE_NAME
    _ = source_path.write_bytes(AUDIO_CONTENT)
    # Simulate a stale pre-check that reported the target as free.
    monkeypatch.setattr(Path, "exists", _report_path_as_free)
    _ = target_path.write_bytes(b"concurrently created")

    with pytest.raises(FileExistsError):
        FilesystemFileMover().move(source_path, target_path)

    assert source_path.read_bytes() == AUDIO_CONTENT
    assert target_path.read_bytes() == b"concurrently created"


def _report_path_as_free(path: Path) -> bool:
    """Stand in for a stale exists() check that always reports a path as free."""
    del path
    return False


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


class PeakConcurrencyMetadataReader:
    """MetadataReader fake that measures simultaneous batch workers."""

    def __init__(self, worker_count: int) -> None:
        """Synchronize each worker cohort and record its peak size."""
        self._barrier: Barrier = Barrier(worker_count)
        self._lock: Lock = Lock()
        self._active_count: int = 0
        self.peak_active_count: int = 0

    def read(self, path: FileSystemPath) -> TrackMetadata:
        """Block until one full worker cohort is active, then return metadata."""
        del path
        with self._lock:
            self._active_count += 1
            self.peak_active_count = max(self.peak_active_count, self._active_count)
        try:
            _ = self._barrier.wait(timeout=BATCH_BARRIER_TIMEOUT_SECONDS)
            return _metadata()
        finally:
            with self._lock:
                self._active_count -= 1


class FailingMetadataReader:
    """MetadataReader fake that raises one non-missing capture error."""

    def read(self, path: FileSystemPath) -> TrackMetadata:
        """Raise the configured adapter-facing metadata error."""
        del path
        raise MetadataReadError(METADATA_READ_FAILURE_MESSAGE)


def _metadata() -> TrackMetadata:
    return TrackMetadata(title=TRACK_TITLE, artist=TRACK_ARTIST, album=TRACK_ALBUM)
