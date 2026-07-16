"""
Summary: Tests read-only filesystem adapters.
Why: Verifies scanning, hashing, snapshots, and path resolution.
"""

from __future__ import annotations

import errno
import os
import shutil
import stat
from dataclasses import dataclass, field, replace
from datetime import UTC, datetime
from pathlib import Path
from threading import Barrier, Lock
from typing import TYPE_CHECKING, Self

import pytest

from omym2.adapters.fs.file_mover import (
    SOURCE_BELOW_ROOT_MESSAGE,
    SOURCE_REPLACED_MESSAGE,
    SOURCE_SYMLINK_MESSAGE,
    TARGET_BELOW_ROOT_MESSAGE,
    TARGET_REPLACED_MESSAGE,
    FilesystemFileMover,
)
from omym2.adapters.fs.file_presence import FilesystemFilePresence
from omym2.adapters.fs.file_scanner import FilesystemFileScanner
from omym2.adapters.fs.file_snapshot_reader import (
    INVALID_SNAPSHOT_CAPTURE_WORKER_COUNT_MESSAGE,
    SOURCE_CHANGED_DURING_SNAPSHOT_MESSAGE,
    FilesystemFileSnapshotReader,
)
from omym2.adapters.fs.hash_calculator import INVALID_CHUNK_SIZE_MESSAGE, FileContentHasher
from omym2.adapters.fs.path_resolver import PATH_OUTSIDE_LIBRARY_MESSAGE, FilesystemPathResolver
from omym2.adapters.fs.win32_file_handles import Win32FileHandle, Win32FileIdentity
from omym2.config import FILE_SNAPSHOT_CAPTURE_MIN_WORKER_COUNT
from omym2.domain.models.file_snapshot import FilesystemIdentity
from omym2.domain.models.track_metadata import TrackMetadata
from omym2.domain.services.metadata_fingerprint import calculate_metadata_fingerprint
from omym2.features.common_ports import FileSnapshotCaptureRequest, MetadataReadError
from tests.fakes.content_fingerprint import calculate_content_fingerprint
from tests.fakes.runtime import FixedClock

if TYPE_CHECKING:
    from collections.abc import Callable, Iterator
    from types import TracebackType
    from typing import BinaryIO

    from omym2.adapters.fs.win32_file_handles import Win32FileHandleBackend
    from omym2.features.common_ports import FileSystemPath

AUDIO_CONTENT = b"fake audio bytes"
CHANGED_AUDIO_CONTENT = b"changed source!!"
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
TARGET_VERIFICATION_STAT_CALL_COUNT = 2
SECOND_TARGET_FILE_NAME = "Second-Moved.flac"
SIMULATED_CLOSED_HANDLE_MESSAGE = "simulated closed handle"
SIMULATED_DELETE_FAILURE_MESSAGE = "simulated exact delete failure"
SIMULATED_EXPECTED_IDENTITY_MISMATCH_MESSAGE = "simulated expected identity mismatch"
SIMULATED_FINAL_PATH_MISMATCH_MESSAGE = "simulated final path mismatch"
SIMULATED_LISTED_IDENTITY_MISMATCH_MESSAGE = "simulated listed/opened identity mismatch"
SIMULATED_REPARSE_DIRECTORY_MESSAGE = "simulated reparse directory"
SIMULATED_REPARSE_FILE_MESSAGE = "simulated reparse file"
SIMULATED_CURRENT_IDENTITY_MISMATCH_MESSAGE = "simulated current identity mismatch"


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


def test_file_scanner_skips_linked_audio_files_and_directories(tmp_path: Path) -> None:
    """Discovery never follows a linked leaf or directory outside its source root."""
    source_root = tmp_path / "source"
    outside_root = tmp_path / "outside"
    source_root.mkdir()
    outside_root.mkdir()
    outside_audio = outside_root / AUDIO_FILE_NAME
    _ = outside_audio.write_bytes(AUDIO_CONTENT)
    linked_audio = source_root / AUDIO_FILE_NAME
    linked_directory = source_root / "linked"
    try:
        linked_audio.symlink_to(outside_audio)
        linked_directory.symlink_to(outside_root, target_is_directory=True)
    except OSError:
        pytest.skip("This host does not permit symlink creation.")

    assert FilesystemFileScanner().scan(source_root) == ()
    with pytest.raises(OSError, match="not a regular file"):
        _ = FilesystemFileScanner().observe(linked_audio)


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


def test_file_scanner_prunes_excluded_root_before_entering_it(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Caller exclusions prevent traversal rather than filtering completed results."""
    excluded_root = tmp_path / "excluded"
    included_root = tmp_path / "included"
    excluded_root.mkdir()
    included_root.mkdir()
    _ = (excluded_root / AUDIO_FILE_NAME).write_bytes(AUDIO_CONTENT)
    included_audio = included_root / SECOND_AUDIO_FILE_NAME
    _ = included_audio.write_bytes(AUDIO_CONTENT)
    original_scandir = os.scandir

    def reject_excluded_scan(path: FileSystemPath) -> Iterator[os.DirEntry[str]]:
        if Path(path) == excluded_root:
            pytest.fail("Excluded root must not be entered during traversal.")
        return original_scandir(path)

    monkeypatch.setattr(os, "scandir", reject_excluded_scan)

    entries = FilesystemFileScanner().scan(tmp_path, excluded_roots=(excluded_root,))

    assert [entry.path for entry in entries] == [str(included_audio)]


def test_file_scanner_prunes_windows_junction_before_entering_it(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """A Windows junction cannot redirect discovery outside the selected root."""
    junction_root = tmp_path / "junction"
    included_root = tmp_path / "included"
    junction_root.mkdir()
    included_root.mkdir()
    _ = (junction_root / AUDIO_FILE_NAME).write_bytes(AUDIO_CONTENT)
    included_audio = included_root / SECOND_AUDIO_FILE_NAME
    _ = included_audio.write_bytes(AUDIO_CONTENT)
    original_is_junction = Path.is_junction
    original_scandir = os.scandir

    def report_fixture_junction(path: Path) -> bool:
        return path == junction_root or original_is_junction(path)

    def reject_junction_scan(path: FileSystemPath) -> Iterator[os.DirEntry[str]]:
        if Path(path) == junction_root:
            pytest.fail("Junctions must be pruned before traversal.")
        return original_scandir(path)

    monkeypatch.setattr(Path, "is_junction", report_fixture_junction)
    monkeypatch.setattr(os, "scandir", reject_junction_scan)

    entries = FilesystemFileScanner().scan(tmp_path)

    assert [entry.path for entry in entries] == [str(included_audio)]


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
    source_stat = audio_path.stat()

    assert snapshot.path == str(audio_path)
    assert snapshot.size == len(AUDIO_CONTENT)
    assert snapshot.file_extension == AUDIO_FILE_EXTENSION
    assert snapshot.content_hash == calculate_content_fingerprint(AUDIO_CONTENT)
    assert snapshot.metadata_hash == calculate_metadata_fingerprint(metadata)
    assert snapshot.metadata == metadata
    assert snapshot.filesystem_identity == FilesystemIdentity(
        device_id=source_stat.st_dev,
        inode=source_stat.st_ino,
        size=source_stat.st_size,
        mtime_ns=source_stat.st_mtime_ns,
        ctime_ns=source_stat.st_ctime_ns,
    )
    assert snapshot.captured_at == FIXED_TIME


def test_file_snapshot_reader_rejects_source_replaced_during_capture(tmp_path: Path) -> None:
    """A same-content replacement cannot reuse the initial filesystem token."""
    audio_path = tmp_path / AUDIO_FILE_NAME
    backup_path = tmp_path / SECOND_AUDIO_FILE_NAME
    _ = audio_path.write_bytes(AUDIO_CONTENT)
    original_stat = audio_path.stat()
    reader = FilesystemFileSnapshotReader(
        metadata_reader=ReplacingMetadataReader(backup_path),
        clock=FixedClock(FIXED_TIME),
    )

    with pytest.raises(ValueError, match=SOURCE_CHANGED_DURING_SNAPSHOT_MESSAGE):
        _ = reader.capture(audio_path)

    assert audio_path.read_bytes() == AUDIO_CONTENT
    assert backup_path.read_bytes() == AUDIO_CONTENT
    assert audio_path.stat().st_mtime_ns == original_stat.st_mtime_ns


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


def test_file_presence_reports_broken_symlink_as_occupied(tmp_path: Path) -> None:
    """A broken symlink cannot look like an available no-overwrite target during review."""
    broken_link = tmp_path / "occupied.flac"
    try:
        broken_link.symlink_to(tmp_path / "missing-target.flac")
    except OSError:
        pytest.skip("This host does not permit symlink creation.")

    assert FilesystemFilePresence().exists(broken_link)


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


def test_file_mover_forced_windows_backend_preserves_bytes_and_metadata(tmp_path: Path) -> None:
    """The injected retained-handle backend moves binary content with source metadata."""
    library_root = tmp_path / "library"
    source_path = library_root / "source" / AUDIO_FILE_NAME
    target_path = library_root / NESTED_DIRECTORY_NAME / TARGET_FILE_NAME
    binary_content = AUDIO_CONTENT + b"\x1a\x00"
    source_path.parent.mkdir(parents=True)
    _ = source_path.write_bytes(binary_content)
    source_mode = stat.S_IRUSR | stat.S_IWUSR | stat.S_IRGRP
    source_path.chmod(source_mode)
    source_stat = source_path.stat()

    _forced_windows_mover().move(
        source_path,
        target_path,
        source_root=library_root,
        target_root=library_root,
        expected_source_identity=_filesystem_identity(source_path),
        expected_source_content_hash=calculate_content_fingerprint(binary_content),
    )

    target_stat = target_path.stat()
    assert not source_path.exists()
    assert target_path.read_bytes() == binary_content
    assert stat.S_IMODE(target_stat.st_mode) == source_mode
    assert target_stat.st_mtime_ns == source_stat.st_mtime_ns


def test_file_mover_forced_windows_backend_moves_external_source_into_root(tmp_path: Path) -> None:
    """An unrooted external Add source is retained from its volume root through deletion."""
    source_path = tmp_path / "incoming" / AUDIO_FILE_NAME
    library_root = tmp_path / "library"
    target_path = library_root / NESTED_DIRECTORY_NAME / TARGET_FILE_NAME
    source_path.parent.mkdir()
    library_root.mkdir()
    _ = source_path.write_bytes(AUDIO_CONTENT)

    _forced_windows_mover().move(
        source_path,
        target_path,
        target_root=library_root,
        expected_source_identity=_filesystem_identity(source_path),
        expected_source_content_hash=calculate_content_fingerprint(AUDIO_CONTENT),
    )

    assert not source_path.exists()
    assert target_path.read_bytes() == AUDIO_CONTENT


def test_file_mover_forced_windows_backend_rejects_expected_identity_mismatch(tmp_path: Path) -> None:
    """The retained source handle must match the exact apply-time identity token."""
    library_root = tmp_path / "library"
    source_path = library_root / "source" / AUDIO_FILE_NAME
    target_path = library_root / NESTED_DIRECTORY_NAME / TARGET_FILE_NAME
    source_path.parent.mkdir(parents=True)
    _ = source_path.write_bytes(AUDIO_CONTENT)
    expected_identity = _filesystem_identity(source_path)

    with pytest.raises(ValueError, match=SOURCE_REPLACED_MESSAGE):
        _forced_windows_mover().move(
            source_path,
            target_path,
            source_root=library_root,
            target_root=library_root,
            expected_source_identity=replace(expected_identity, inode=expected_identity.inode + 1),
        )

    assert source_path.read_bytes() == AUDIO_CONTENT
    assert not target_path.exists()


def test_file_mover_forced_windows_backend_never_overwrites_existing_target(tmp_path: Path) -> None:
    """CREATE_NEW preserves both user files when the reviewed target is occupied."""
    library_root = tmp_path / "library"
    source_path = library_root / "source" / AUDIO_FILE_NAME
    target_path = library_root / NESTED_DIRECTORY_NAME / TARGET_FILE_NAME
    source_path.parent.mkdir(parents=True)
    target_path.parent.mkdir()
    _ = source_path.write_bytes(AUDIO_CONTENT)
    _ = target_path.write_bytes(b"existing")

    with pytest.raises(FileExistsError):
        _forced_windows_mover().move(
            source_path,
            target_path,
            source_root=library_root,
            target_root=library_root,
            expected_source_identity=_filesystem_identity(source_path),
        )

    assert source_path.read_bytes() == AUDIO_CONTENT
    assert target_path.read_bytes() == b"existing"


def test_file_mover_forced_windows_backend_rejects_symlinked_target_parent(tmp_path: Path) -> None:
    """The retained target chain rejects a link before any outside claim."""
    library_root = tmp_path / "library"
    outside_root = tmp_path / "outside"
    source_path = library_root / "source" / AUDIO_FILE_NAME
    target_parent = library_root / NESTED_DIRECTORY_NAME
    target_path = target_parent / TARGET_FILE_NAME
    source_path.parent.mkdir(parents=True)
    outside_root.mkdir()
    _ = source_path.write_bytes(AUDIO_CONTENT)
    target_parent.symlink_to(outside_root, target_is_directory=True)

    with pytest.raises(ValueError, match=TARGET_BELOW_ROOT_MESSAGE):
        _forced_windows_mover().move(
            source_path,
            target_path,
            source_root=library_root,
            target_root=library_root,
            expected_source_identity=_filesystem_identity(source_path),
        )

    assert source_path.read_bytes() == AUDIO_CONTENT
    assert not (outside_root / TARGET_FILE_NAME).exists()


def test_file_mover_forced_windows_backend_rejects_lexical_root_escape(tmp_path: Path) -> None:
    """Fallback traversal rejects parent segments before opening any target handle."""
    library_root = tmp_path / "library"
    outside_root = tmp_path / "outside"
    source_path = library_root / "source" / AUDIO_FILE_NAME
    escaped_target = library_root / NESTED_DIRECTORY_NAME / ".." / ".." / "outside" / TARGET_FILE_NAME
    source_path.parent.mkdir(parents=True)
    outside_root.mkdir()
    _ = source_path.write_bytes(AUDIO_CONTENT)

    with pytest.raises(ValueError, match=TARGET_BELOW_ROOT_MESSAGE):
        _forced_windows_mover().move(
            source_path,
            escaped_target,
            source_root=library_root,
            target_root=library_root,
            expected_source_identity=_filesystem_identity(source_path),
        )

    assert source_path.read_bytes() == AUDIO_CONTENT
    assert not (outside_root / TARGET_FILE_NAME).exists()


def test_file_mover_forced_windows_backend_cleans_hash_mismatch_target(tmp_path: Path) -> None:
    """A copied target is exactly deleted when the retained bytes do not match review."""
    library_root = tmp_path / "library"
    source_path = library_root / "source" / AUDIO_FILE_NAME
    target_path = library_root / NESTED_DIRECTORY_NAME / TARGET_FILE_NAME
    source_path.parent.mkdir(parents=True)
    _ = source_path.write_bytes(AUDIO_CONTENT)

    with pytest.raises(ValueError, match=SOURCE_REPLACED_MESSAGE):
        _forced_windows_mover().move(
            source_path,
            target_path,
            source_root=library_root,
            target_root=library_root,
            expected_source_identity=_filesystem_identity(source_path),
            expected_source_content_hash=calculate_content_fingerprint(CHANGED_AUDIO_CONTENT),
        )

    assert source_path.read_bytes() == AUDIO_CONTENT
    assert not target_path.exists()


def test_file_mover_forced_windows_backend_cleans_readonly_target_when_source_delete_fails(
    tmp_path: Path,
) -> None:
    """A failed exact source deletion preserves source and removes the read-only claim."""
    library_root = tmp_path / "library"
    source_path = library_root / "source" / AUDIO_FILE_NAME
    target_path = library_root / NESTED_DIRECTORY_NAME / TARGET_FILE_NAME
    source_path.parent.mkdir(parents=True)
    _ = source_path.write_bytes(AUDIO_CONTENT)
    source_path.chmod(stat.S_IRUSR)
    backend = _PathBackedWin32Backend(fail_delete_path=source_path)

    with pytest.raises(PermissionError, match=SIMULATED_DELETE_FAILURE_MESSAGE):
        FilesystemFileMover(windows_backend=backend).move(
            source_path,
            target_path,
            source_root=library_root,
            target_root=library_root,
            expected_source_identity=_filesystem_identity(source_path),
            expected_source_content_hash=calculate_content_fingerprint(AUDIO_CONTENT),
        )

    assert source_path.read_bytes() == AUDIO_CONTENT
    assert not source_path.stat().st_mode & stat.S_IWRITE
    assert not target_path.exists()
    assert backend.deleted_paths == [target_path]


def test_file_mover_forced_windows_backend_rechecks_source_after_target_claim(tmp_path: Path) -> None:
    """A post-open source change preserves the source and removes the exact target claim."""
    library_root = tmp_path / "library"
    source_path = library_root / "source" / AUDIO_FILE_NAME
    target_path = library_root / NESTED_DIRECTORY_NAME / TARGET_FILE_NAME
    source_path.parent.mkdir(parents=True)
    _ = source_path.write_bytes(AUDIO_CONTENT)
    expected_identity = _filesystem_identity(source_path)

    def replace_source_state() -> None:
        _ = source_path.write_bytes(CHANGED_AUDIO_CONTENT)
        os.utime(source_path, ns=(expected_identity.mtime_ns, expected_identity.mtime_ns))

    backend = _PathBackedWin32Backend(before_target_create=replace_source_state)

    with pytest.raises(ValueError, match=SOURCE_REPLACED_MESSAGE):
        FilesystemFileMover(windows_backend=backend).move(
            source_path,
            target_path,
            source_root=library_root,
            target_root=library_root,
            expected_source_identity=expected_identity,
        )

    assert source_path.read_bytes() == CHANGED_AUDIO_CONTENT
    assert not target_path.exists()
    assert backend.deleted_paths == [target_path]


def test_file_mover_forced_windows_backend_retains_ancestors_above_selected_root(tmp_path: Path) -> None:
    """Replacing an ancestor with a link cannot hide behind the same selected root object."""
    container = tmp_path / "container"
    moved_container = tmp_path / "moved-container"
    library_root = container / "library"
    source_path = library_root / "source" / AUDIO_FILE_NAME
    target_path = library_root / NESTED_DIRECTORY_NAME / TARGET_FILE_NAME
    source_path.parent.mkdir(parents=True)
    _ = source_path.write_bytes(AUDIO_CONTENT)

    def replace_root_ancestor() -> None:
        _ = container.rename(moved_container)
        container.symlink_to(moved_container, target_is_directory=True)

    backend = _PathBackedWin32Backend(before_target_create=replace_root_ancestor)

    with pytest.raises(ValueError, match=SOURCE_BELOW_ROOT_MESSAGE):
        FilesystemFileMover(windows_backend=backend).move(
            source_path,
            target_path,
            source_root=library_root,
            target_root=library_root,
            expected_source_identity=_filesystem_identity(source_path),
            expected_source_content_hash=calculate_content_fingerprint(AUDIO_CONTENT),
        )

    assert (moved_container / "library" / "source" / AUDIO_FILE_NAME).read_bytes() == AUDIO_CONTENT
    assert not (moved_container / "library" / NESTED_DIRECTORY_NAME / TARGET_FILE_NAME).exists()
    assert container.is_symlink()
    assert backend.deleted_paths == [target_path]


def test_file_mover_moves_file_across_filesystems(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """FileMover handles cross-device moves used by separate Incoming and Library drives."""
    source_path = tmp_path / "incoming" / AUDIO_FILE_NAME
    target_path = tmp_path / "library" / TARGET_FILE_NAME
    source_path.parent.mkdir()
    target_path.parent.mkdir()
    _ = source_path.write_bytes(AUDIO_CONTENT)

    def raise_cross_device_error(
        source: os.PathLike[str] | str,
        target: os.PathLike[str] | str,
        **kwargs: object,
    ) -> None:
        del kwargs
        del target
        raise OSError(errno.EXDEV, "Invalid cross-device link", source)

    # Simulate os.link failing the way it does across mounted filesystems.
    monkeypatch.setattr(os, "link", raise_cross_device_error)

    FilesystemFileMover().move(source_path, target_path, target_root=target_path.parent)

    assert not source_path.exists()
    assert target_path.read_bytes() == AUDIO_CONTENT


def test_file_mover_moves_managed_source_through_forced_copy(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """A managed source remains anchored when hardlink claim falls back to copy."""
    library_root = tmp_path / "library"
    source_path = library_root / "source" / AUDIO_FILE_NAME
    target_path = library_root / NESTED_DIRECTORY_NAME / TARGET_FILE_NAME
    source_path.parent.mkdir(parents=True)
    _ = source_path.write_bytes(AUDIO_CONTENT)
    expected_identity = _filesystem_identity(source_path)

    def force_cross_device_copy(
        source: os.PathLike[str] | str,
        target: os.PathLike[str] | str,
        **kwargs: object,
    ) -> None:
        del source, target, kwargs
        raise OSError(errno.EXDEV, "Invalid cross-device link")

    monkeypatch.setattr(os, "link", force_cross_device_copy)

    FilesystemFileMover().move(
        source_path,
        target_path,
        source_root=library_root,
        target_root=library_root,
        expected_source_identity=expected_identity,
    )

    assert not source_path.exists()
    assert target_path.read_bytes() == AUDIO_CONTENT


def test_file_mover_removes_never_claimed_copy_when_content_hash_differs(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """A copied target with unexpected bytes cannot cause the source to be removed."""
    library_root = tmp_path / "library"
    source_path = library_root / "source" / AUDIO_FILE_NAME
    target_path = library_root / NESTED_DIRECTORY_NAME / TARGET_FILE_NAME
    source_path.parent.mkdir(parents=True)
    _ = source_path.write_bytes(AUDIO_CONTENT)
    expected_identity = _filesystem_identity(source_path)
    expected_content_hash = calculate_content_fingerprint(AUDIO_CONTENT)

    def force_cross_device_copy(
        source: os.PathLike[str] | str,
        target: os.PathLike[str] | str,
        **kwargs: object,
    ) -> None:
        del source, target, kwargs
        raise OSError(errno.EXDEV, "Invalid cross-device link")

    def write_wrong_content(source_file: BinaryIO, target_file: BinaryIO, length: int = -1) -> None:
        del source_file, length
        _ = target_file.write(CHANGED_AUDIO_CONTENT)

    monkeypatch.setattr(os, "link", force_cross_device_copy)
    monkeypatch.setattr(shutil, "copyfileobj", write_wrong_content)

    with pytest.raises(ValueError, match=SOURCE_REPLACED_MESSAGE):
        FilesystemFileMover().move(
            source_path,
            target_path,
            source_root=library_root,
            target_root=library_root,
            expected_source_identity=expected_identity,
            expected_source_content_hash=expected_content_hash,
        )

    assert source_path.read_bytes() == AUDIO_CONTENT
    assert not target_path.exists()


def test_file_mover_moves_file_when_filesystem_refuses_hardlinks(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """FileMover falls back to the exclusive copy claim when hardlinks are refused."""
    source_path = tmp_path / AUDIO_FILE_NAME
    target_path = tmp_path / TARGET_FILE_NAME
    _ = source_path.write_bytes(AUDIO_CONTENT)

    def raise_permission_error(
        source: os.PathLike[str] | str,
        target: os.PathLike[str] | str,
        **kwargs: object,
    ) -> None:
        del kwargs
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
    real_unlink = os.unlink

    def fail_source_unlink(
        path: os.PathLike[str] | str,
        *,
        dir_fd: int | None = None,
    ) -> None:
        if path == source_path.name and dir_fd is not None:
            raise PermissionError(errno.EACCES, "Permission denied", path)
        real_unlink(path, dir_fd=dir_fd)

    monkeypatch.setattr(os, "unlink", fail_source_unlink)

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


def test_file_mover_refuses_symlinked_parent_below_target_root(tmp_path: Path) -> None:
    """Library-target traversal never follows a symlinked descendant."""
    library_root = tmp_path / "library"
    source_path = library_root / "source" / AUDIO_FILE_NAME
    outside_root = tmp_path / "outside"
    target_parent = library_root / NESTED_DIRECTORY_NAME
    target_path = target_parent / TARGET_FILE_NAME
    source_path.parent.mkdir(parents=True)
    _ = source_path.write_bytes(AUDIO_CONTENT)
    outside_root.mkdir()
    target_parent.symlink_to(outside_root, target_is_directory=True)

    with pytest.raises(ValueError, match=TARGET_BELOW_ROOT_MESSAGE):
        FilesystemFileMover().move(
            source_path,
            target_path,
            source_root=library_root,
            target_root=library_root,
            expected_source_identity=_filesystem_identity(source_path),
        )

    assert source_path.read_bytes() == AUDIO_CONTENT
    assert not (outside_root / TARGET_FILE_NAME).exists()


def test_file_mover_rejects_parent_segments_below_target_root(tmp_path: Path) -> None:
    """Library-target traversal never walks dot-dot segments out of its root."""
    library_root = tmp_path / "library"
    source_path = library_root / "source" / AUDIO_FILE_NAME
    outside_root = tmp_path / "outside"
    target_path = library_root / NESTED_DIRECTORY_NAME / ".." / ".." / "outside" / TARGET_FILE_NAME
    source_path.parent.mkdir(parents=True)
    _ = source_path.write_bytes(AUDIO_CONTENT)
    outside_root.mkdir()

    with pytest.raises(ValueError, match=TARGET_BELOW_ROOT_MESSAGE):
        FilesystemFileMover().move(
            source_path,
            target_path,
            source_root=library_root,
            target_root=library_root,
            expected_source_identity=_filesystem_identity(source_path),
        )

    assert source_path.read_bytes() == AUDIO_CONTENT
    assert not (outside_root / TARGET_FILE_NAME).exists()


def test_file_mover_removes_target_if_parent_directory_escapes_root_during_claim(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """A renamed target directory cannot receive a successful Library move outside the root."""
    library_root = tmp_path / "library"
    source_path = library_root / "source" / AUDIO_FILE_NAME
    escaped_root = tmp_path / "escaped"
    target_parent = library_root / NESTED_DIRECTORY_NAME
    target_path = target_parent / TARGET_FILE_NAME
    source_path.parent.mkdir(parents=True)
    _ = source_path.write_bytes(AUDIO_CONTENT)
    escaped_root.mkdir()
    real_link = os.link

    def escape_target_parent_then_link(
        source: os.PathLike[str] | str,
        target: os.PathLike[str] | str,
        *,
        src_dir_fd: int | None = None,
        dst_dir_fd: int | None = None,
        follow_symlinks: bool = True,
    ) -> None:
        escaped_parent = escaped_root / NESTED_DIRECTORY_NAME
        _ = target_parent.rename(escaped_parent)
        real_link(
            source,
            target,
            src_dir_fd=src_dir_fd,
            dst_dir_fd=dst_dir_fd,
            follow_symlinks=follow_symlinks,
        )

    monkeypatch.setattr(os, "link", escape_target_parent_then_link)

    with pytest.raises(ValueError, match=TARGET_BELOW_ROOT_MESSAGE):
        FilesystemFileMover().move(
            source_path,
            target_path,
            source_root=library_root,
            target_root=library_root,
            expected_source_identity=_filesystem_identity(source_path),
        )

    assert source_path.read_bytes() == AUDIO_CONTENT
    assert not target_path.exists()
    assert not (escaped_root / NESTED_DIRECTORY_NAME / TARGET_FILE_NAME).exists()


def test_file_mover_rejects_escaped_parent_when_root_path_is_also_replaced(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """A replacement root path cannot validate a target claimed through the opened root."""
    library_root = tmp_path / "library"
    source_path = library_root / "source" / AUDIO_FILE_NAME
    moved_library_root = tmp_path / "moved-library"
    escaped_root = tmp_path / "escaped"
    target_parent = library_root / NESTED_DIRECTORY_NAME
    target_path = target_parent / TARGET_FILE_NAME
    source_path.parent.mkdir(parents=True)
    _ = source_path.write_bytes(AUDIO_CONTENT)
    escaped_root.mkdir()
    real_link = os.link

    def escape_target_parent_replace_root_then_link(
        source: os.PathLike[str] | str,
        target: os.PathLike[str] | str,
        *,
        src_dir_fd: int | None = None,
        dst_dir_fd: int | None = None,
        follow_symlinks: bool = True,
    ) -> None:
        _ = target_parent.rename(escaped_root / NESTED_DIRECTORY_NAME)
        _ = library_root.rename(moved_library_root)
        library_root.symlink_to(tmp_path, target_is_directory=True)
        real_link(
            source,
            target,
            src_dir_fd=src_dir_fd,
            dst_dir_fd=dst_dir_fd,
            follow_symlinks=follow_symlinks,
        )

    monkeypatch.setattr(os, "link", escape_target_parent_replace_root_then_link)

    with pytest.raises(ValueError, match=TARGET_BELOW_ROOT_MESSAGE):
        FilesystemFileMover().move(
            source_path,
            target_path,
            source_root=library_root,
            target_root=library_root,
            expected_source_identity=_filesystem_identity(source_path),
        )

    assert (moved_library_root / "source" / AUDIO_FILE_NAME).read_bytes() == AUDIO_CONTENT
    assert not (escaped_root / NESTED_DIRECTORY_NAME / TARGET_FILE_NAME).exists()


def test_file_mover_normalizes_target_removed_after_hardlink_claim(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """A vanished claimed target is invalid_path rather than source_missing."""
    library_root = tmp_path / "library"
    source_path = library_root / "source" / AUDIO_FILE_NAME
    target_path = library_root / NESTED_DIRECTORY_NAME / TARGET_FILE_NAME
    source_path.parent.mkdir(parents=True)
    _ = source_path.write_bytes(AUDIO_CONTENT)
    expected_identity = _filesystem_identity(source_path)
    real_stat = os.stat
    target_was_removed = False

    def remove_target_before_claim_verification(
        path: os.PathLike[str] | str,
        *,
        dir_fd: int | None = None,
        follow_symlinks: bool = True,
    ) -> os.stat_result:
        nonlocal target_was_removed
        if path == TARGET_FILE_NAME and dir_fd is not None and not target_was_removed:
            target_was_removed = True
            os.unlink(path, dir_fd=dir_fd)
        return real_stat(path, dir_fd=dir_fd, follow_symlinks=follow_symlinks)

    monkeypatch.setattr(os, "stat", remove_target_before_claim_verification)

    with pytest.raises(ValueError, match=TARGET_BELOW_ROOT_MESSAGE):
        FilesystemFileMover().move(
            source_path,
            target_path,
            source_root=library_root,
            target_root=library_root,
            expected_source_identity=expected_identity,
        )

    assert source_path.read_bytes() == AUDIO_CONTENT
    assert not target_path.exists()


def test_file_mover_preserves_managed_source_and_attacker_target_replacement(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Rooted-target cleanup never removes an attacker replacement inode."""
    library_root = tmp_path / "library"
    source_path = library_root / "source" / AUDIO_FILE_NAME
    target_path = library_root / NESTED_DIRECTORY_NAME / TARGET_FILE_NAME
    claimed_backup = target_path.with_name("claimed.flac")
    source_path.parent.mkdir(parents=True)
    _ = source_path.write_bytes(AUDIO_CONTENT)
    expected_identity = _filesystem_identity(source_path)
    real_stat = os.stat
    target_stat_call_count = 0
    target_was_replaced = False

    def replace_managed_target_before_containment_verification(
        path: os.PathLike[str] | str,
        *,
        dir_fd: int | None = None,
        follow_symlinks: bool = True,
    ) -> os.stat_result:
        nonlocal target_stat_call_count, target_was_replaced
        if path == TARGET_FILE_NAME and dir_fd is not None:
            target_stat_call_count += 1
        if target_stat_call_count == TARGET_VERIFICATION_STAT_CALL_COUNT and not target_was_replaced:
            target_was_replaced = True
            _ = target_path.rename(claimed_backup)
            _ = target_path.write_bytes(b"attacker")
        return real_stat(path, dir_fd=dir_fd, follow_symlinks=follow_symlinks)

    monkeypatch.setattr(os, "stat", replace_managed_target_before_containment_verification)

    with pytest.raises(ValueError, match=TARGET_BELOW_ROOT_MESSAGE):
        FilesystemFileMover().move(
            source_path,
            target_path,
            source_root=library_root,
            target_root=library_root,
            expected_source_identity=expected_identity,
        )

    assert source_path.read_bytes() == AUDIO_CONTENT
    assert target_path.read_bytes() == b"attacker"
    assert claimed_backup.read_bytes() == AUDIO_CONTENT


def test_file_mover_refuses_symlink_source(tmp_path: Path) -> None:
    """A symlink is never claimed into managed storage as a moved file."""
    real_file = tmp_path / AUDIO_FILE_NAME
    source_path = tmp_path / "incoming" / TARGET_FILE_NAME
    library_root = tmp_path / "library"
    target_path = library_root / TARGET_FILE_NAME
    _ = real_file.write_bytes(AUDIO_CONTENT)
    source_path.parent.mkdir()
    source_path.symlink_to(real_file)
    library_root.mkdir()

    with pytest.raises(ValueError, match=SOURCE_SYMLINK_MESSAGE):
        FilesystemFileMover().move(source_path, target_path, target_root=library_root)

    assert source_path.is_symlink()
    assert not target_path.exists()


def test_file_mover_refuses_symlinked_parent_below_source_root_even_for_matching_inode(
    tmp_path: Path,
) -> None:
    """A matching source inode cannot bypass Library-root containment."""
    library_root = tmp_path / "library"
    outside_root = tmp_path / "outside"
    genuine_parent = library_root / "genuine"
    linked_parent = library_root / "linked"
    genuine_source = genuine_parent / AUDIO_FILE_NAME
    outside_source = outside_root / AUDIO_FILE_NAME
    source_path = linked_parent / AUDIO_FILE_NAME
    target_path = library_root / NESTED_DIRECTORY_NAME / TARGET_FILE_NAME
    genuine_parent.mkdir(parents=True)
    outside_root.mkdir()
    _ = genuine_source.write_bytes(AUDIO_CONTENT)
    os.link(genuine_source, outside_source)
    linked_parent.symlink_to(outside_root, target_is_directory=True)

    with pytest.raises(ValueError, match=SOURCE_BELOW_ROOT_MESSAGE):
        FilesystemFileMover().move(
            source_path,
            target_path,
            source_root=library_root,
            target_root=library_root,
            expected_source_identity=_filesystem_identity(genuine_source),
        )

    assert genuine_source.read_bytes() == AUDIO_CONTENT
    assert outside_source.read_bytes() == AUDIO_CONTENT
    assert not target_path.exists()


def test_file_mover_rejects_each_expected_source_identity_mismatch(tmp_path: Path) -> None:
    """Every ephemeral identity field is required before a target claim."""
    library_root = tmp_path / "library"
    source_path = library_root / "source" / AUDIO_FILE_NAME
    target_path = library_root / NESTED_DIRECTORY_NAME / TARGET_FILE_NAME
    source_path.parent.mkdir(parents=True)
    _ = source_path.write_bytes(AUDIO_CONTENT)
    expected_identity = _filesystem_identity(source_path)
    mismatches = (
        replace(expected_identity, device_id=expected_identity.device_id + 1),
        replace(expected_identity, inode=expected_identity.inode + 1),
        replace(expected_identity, size=expected_identity.size + 1),
        replace(expected_identity, mtime_ns=expected_identity.mtime_ns + 1),
        replace(expected_identity, ctime_ns=expected_identity.ctime_ns + 1),
    )

    for mismatched_identity in mismatches:
        with pytest.raises(ValueError, match=SOURCE_REPLACED_MESSAGE):
            FilesystemFileMover().move(
                source_path,
                target_path,
                source_root=library_root,
                target_root=library_root,
                expected_source_identity=mismatched_identity,
            )

    assert source_path.read_bytes() == AUDIO_CONTENT
    assert not target_path.exists()


def test_file_mover_rejects_source_parent_escape_during_hardlink_claim(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """A retained parent descriptor cannot be renamed outside before source removal."""
    library_root = tmp_path / "library"
    outside_root = tmp_path / "outside"
    attacker_root = tmp_path / "attacker"
    source_parent = library_root / "source"
    source_path = source_parent / AUDIO_FILE_NAME
    target_path = library_root / NESTED_DIRECTORY_NAME / TARGET_FILE_NAME
    escaped_parent = outside_root / source_parent.name
    source_parent.mkdir(parents=True)
    outside_root.mkdir()
    attacker_root.mkdir()
    _ = source_path.write_bytes(AUDIO_CONTENT)
    _ = (attacker_root / AUDIO_FILE_NAME).write_bytes(b"attacker")
    expected_identity = _filesystem_identity(source_path)
    real_link = os.link

    def escape_source_parent_then_link(
        source: os.PathLike[str] | str,
        target: os.PathLike[str] | str,
        *,
        src_dir_fd: int | None = None,
        dst_dir_fd: int | None = None,
        follow_symlinks: bool = True,
    ) -> None:
        _ = source_parent.rename(escaped_parent)
        source_parent.symlink_to(attacker_root, target_is_directory=True)
        real_link(
            source,
            target,
            src_dir_fd=src_dir_fd,
            dst_dir_fd=dst_dir_fd,
            follow_symlinks=follow_symlinks,
        )

    monkeypatch.setattr(os, "link", escape_source_parent_then_link)

    with pytest.raises(ValueError, match=SOURCE_BELOW_ROOT_MESSAGE):
        FilesystemFileMover().move(
            source_path,
            target_path,
            source_root=library_root,
            target_root=library_root,
            expected_source_identity=expected_identity,
        )

    assert (escaped_parent / AUDIO_FILE_NAME).read_bytes() == AUDIO_CONTENT
    assert (attacker_root / AUDIO_FILE_NAME).read_bytes() == b"attacker"
    assert not target_path.exists()


def test_file_mover_rejects_source_parent_escape_during_forced_copy(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Forced-copy fallback retains containment when the source parent escapes."""
    library_root = tmp_path / "library"
    outside_root = tmp_path / "outside"
    attacker_root = tmp_path / "attacker"
    source_parent = library_root / "source"
    source_path = source_parent / AUDIO_FILE_NAME
    target_path = library_root / NESTED_DIRECTORY_NAME / TARGET_FILE_NAME
    escaped_parent = outside_root / source_parent.name
    source_parent.mkdir(parents=True)
    outside_root.mkdir()
    attacker_root.mkdir()
    _ = source_path.write_bytes(AUDIO_CONTENT)
    _ = (attacker_root / AUDIO_FILE_NAME).write_bytes(b"attacker")
    expected_identity = _filesystem_identity(source_path)

    def escape_source_parent_then_force_copy(
        source: os.PathLike[str] | str,
        target: os.PathLike[str] | str,
        **kwargs: object,
    ) -> None:
        del source, target, kwargs
        _ = source_parent.rename(escaped_parent)
        source_parent.symlink_to(attacker_root, target_is_directory=True)
        raise OSError(errno.EXDEV, "Invalid cross-device link")

    monkeypatch.setattr(os, "link", escape_source_parent_then_force_copy)

    with pytest.raises(ValueError, match=SOURCE_BELOW_ROOT_MESSAGE):
        FilesystemFileMover().move(
            source_path,
            target_path,
            source_root=library_root,
            target_root=library_root,
            expected_source_identity=expected_identity,
        )

    assert (escaped_parent / AUDIO_FILE_NAME).read_bytes() == AUDIO_CONTENT
    assert (attacker_root / AUDIO_FILE_NAME).read_bytes() == b"attacker"
    assert not target_path.exists()


def test_file_mover_cleans_forced_copy_target_when_source_state_changes(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Forced-copy fallback never commits a source changed after its retained open."""
    library_root = tmp_path / "library"
    source_path = library_root / "source" / AUDIO_FILE_NAME
    target_path = library_root / NESTED_DIRECTORY_NAME / TARGET_FILE_NAME
    source_path.parent.mkdir(parents=True)
    _ = source_path.write_bytes(AUDIO_CONTENT)
    expected_identity = _filesystem_identity(source_path)

    def change_source_then_force_copy(
        source: os.PathLike[str] | str,
        target: os.PathLike[str] | str,
        **kwargs: object,
    ) -> None:
        del source, target, kwargs
        _ = source_path.write_bytes(CHANGED_AUDIO_CONTENT)
        os.utime(source_path, ns=(expected_identity.mtime_ns, expected_identity.mtime_ns))
        raise OSError(errno.EXDEV, "Invalid cross-device link")

    monkeypatch.setattr(os, "link", change_source_then_force_copy)

    with pytest.raises(ValueError, match=SOURCE_REPLACED_MESSAGE):
        FilesystemFileMover().move(
            source_path,
            target_path,
            source_root=library_root,
            target_root=library_root,
            expected_source_identity=expected_identity,
        )

    assert source_path.read_bytes() == CHANGED_AUDIO_CONTENT
    assert not target_path.exists()


def test_file_mover_rechecks_source_after_forced_copy_target_metadata(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """A source changed after copy bytes complete is preserved and the target is removed."""
    library_root = tmp_path / "library"
    source_path = library_root / "source" / AUDIO_FILE_NAME
    target_path = library_root / NESTED_DIRECTORY_NAME / TARGET_FILE_NAME
    source_path.parent.mkdir(parents=True)
    _ = source_path.write_bytes(AUDIO_CONTENT)
    expected_identity = _filesystem_identity(source_path)
    real_utime = os.utime

    def force_copy(
        source: os.PathLike[str] | str,
        target: os.PathLike[str] | str,
        **kwargs: object,
    ) -> None:
        del source, target, kwargs
        raise OSError(errno.EXDEV, "Invalid cross-device link")

    def change_source_after_target_metadata(
        path: int,
        *,
        ns: tuple[int, int],
    ) -> None:
        real_utime(path, ns=ns)
        _ = source_path.write_bytes(CHANGED_AUDIO_CONTENT)
        real_utime(
            source_path,
            ns=(expected_identity.mtime_ns, expected_identity.mtime_ns),
        )

    monkeypatch.setattr(os, "link", force_copy)
    monkeypatch.setattr(os, "utime", change_source_after_target_metadata)

    with pytest.raises(ValueError, match=SOURCE_REPLACED_MESSAGE):
        FilesystemFileMover().move(
            source_path,
            target_path,
            source_root=library_root,
            target_root=library_root,
            expected_source_identity=expected_identity,
        )

    assert source_path.read_bytes() == CHANGED_AUDIO_CONTENT
    assert not target_path.exists()


def test_file_mover_anchors_managed_source_for_absolute_restore_target(tmp_path: Path) -> None:
    """An external Undo target keeps its managed source anchored to the Library."""
    library_root = tmp_path / "library"
    source_path = library_root / "source" / AUDIO_FILE_NAME
    restore_path = tmp_path / "restored" / TARGET_FILE_NAME
    source_path.parent.mkdir(parents=True)
    _ = source_path.write_bytes(AUDIO_CONTENT)

    FilesystemFileMover().move(
        source_path,
        restore_path,
        source_root=library_root,
        expected_source_identity=_filesystem_identity(source_path),
    )

    assert not source_path.exists()
    assert restore_path.read_bytes() == AUDIO_CONTENT


def test_file_mover_preserves_source_and_attacker_entry_when_absolute_target_is_replaced(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """An external target swap cannot delete the managed source or attacker entry."""
    library_root = tmp_path / "library"
    source_path = library_root / "source" / AUDIO_FILE_NAME
    restore_path = tmp_path / "restored" / TARGET_FILE_NAME
    claimed_backup = restore_path.with_name("claimed.flac")
    source_path.parent.mkdir(parents=True)
    _ = source_path.write_bytes(AUDIO_CONTENT)
    expected_identity = _filesystem_identity(source_path)
    real_stat = os.stat
    target_was_replaced = False
    target_stat_call_count = 0

    def replace_target_before_verification(
        path: os.PathLike[str] | str,
        *,
        dir_fd: int | None = None,
        follow_symlinks: bool = True,
    ) -> os.stat_result:
        nonlocal target_stat_call_count, target_was_replaced
        if Path(path) == restore_path:
            target_stat_call_count += 1
        if target_stat_call_count == TARGET_VERIFICATION_STAT_CALL_COUNT and not target_was_replaced:
            target_was_replaced = True
            _ = restore_path.rename(claimed_backup)
            _ = restore_path.write_bytes(b"attacker")
        return real_stat(path, dir_fd=dir_fd, follow_symlinks=follow_symlinks)

    monkeypatch.setattr(os, "stat", replace_target_before_verification)

    with pytest.raises(ValueError, match=TARGET_REPLACED_MESSAGE):
        FilesystemFileMover().move(
            source_path,
            restore_path,
            source_root=library_root,
            expected_source_identity=expected_identity,
        )

    assert source_path.read_bytes() == AUDIO_CONTENT
    assert restore_path.read_bytes() == b"attacker"
    assert claimed_backup.read_bytes() == AUDIO_CONTENT


def test_file_mover_refuses_source_replaced_with_symlink_during_claim(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """A source pathname swap cannot plant a symlink inside the Library."""
    source_path = tmp_path / "incoming" / AUDIO_FILE_NAME
    outside_file = tmp_path / "outside" / AUDIO_FILE_NAME
    library_root = tmp_path / "library"
    target_path = library_root / TARGET_FILE_NAME
    source_path.parent.mkdir()
    outside_file.parent.mkdir()
    library_root.mkdir()
    _ = source_path.write_bytes(AUDIO_CONTENT)
    _ = outside_file.write_bytes(b"outside")
    real_open = os.open

    def replace_source_then_open(
        path: os.PathLike[str] | str,
        flags: int,
        mode: int = 0o777,
        *,
        dir_fd: int | None = None,
    ) -> int:
        if path == TARGET_FILE_NAME and flags & os.O_EXCL:
            source_path.unlink()
            source_path.symlink_to(outside_file)
        return real_open(path, flags, mode, dir_fd=dir_fd)

    monkeypatch.setattr(os, "open", replace_source_then_open)

    with pytest.raises(ValueError, match=SOURCE_REPLACED_MESSAGE):
        FilesystemFileMover().move(source_path, target_path, target_root=library_root)

    assert source_path.is_symlink()
    assert source_path.resolve() == outside_file
    assert not target_path.exists()


def test_file_mover_links_retained_managed_source_when_leaf_is_replaced_during_claim(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """A managed leaf swap cannot make the hardlink claim retain a wrong inode."""
    library_root = tmp_path / "library"
    source_path = library_root / "source" / AUDIO_FILE_NAME
    outside_file = tmp_path / "outside" / AUDIO_FILE_NAME
    target_path = library_root / NESTED_DIRECTORY_NAME / TARGET_FILE_NAME
    source_path.parent.mkdir(parents=True)
    outside_file.parent.mkdir()
    _ = source_path.write_bytes(AUDIO_CONTENT)
    _ = outside_file.write_bytes(b"outside")
    expected_identity = _filesystem_identity(source_path)
    real_link = os.link

    def replace_source_leaf_then_link_open_file(
        source: os.PathLike[str] | str,
        target: os.PathLike[str] | str,
        *,
        src_dir_fd: int | None = None,
        dst_dir_fd: int | None = None,
        follow_symlinks: bool = True,
    ) -> None:
        source_path.unlink()
        source_path.symlink_to(outside_file)
        real_link(
            source,
            target,
            src_dir_fd=src_dir_fd,
            dst_dir_fd=dst_dir_fd,
            follow_symlinks=follow_symlinks,
        )

    monkeypatch.setattr(os, "link", replace_source_leaf_then_link_open_file)

    with pytest.raises(ValueError, match=SOURCE_REPLACED_MESSAGE):
        FilesystemFileMover().move(
            source_path,
            target_path,
            source_root=library_root,
            target_root=library_root,
            expected_source_identity=expected_identity,
        )

    assert source_path.is_symlink()
    assert source_path.resolve() == outside_file
    assert outside_file.read_bytes() == b"outside"
    assert not target_path.exists()


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


def _forced_windows_mover() -> FilesystemFileMover:
    """Build the mover with a retained-handle test backend on this Linux host."""
    backend: Win32FileHandleBackend = _PathBackedWin32Backend()
    return FilesystemFileMover(windows_backend=backend)


@dataclass(slots=True)
class _PathBackedWin32Backend:
    """Exercise the Win32 mover branch with retained Linux descriptors."""

    fail_delete_path: Path | None = None
    before_target_create: Callable[[], None] | None = None
    deleted_paths: list[Path] = field(default_factory=list)

    def open_entry(self, path: os.PathLike[str] | str) -> Win32FileHandle:
        """Retain one ordinary file or directory without following a link."""
        path_object = Path(path)
        listed_stat = path_object.stat(follow_symlinks=False)
        return self._open(path_object, listed_stat, writable=False)

    def open_directory(self, path: os.PathLike[str] | str) -> Win32FileHandle:
        """Retain one ordinary directory without following a link."""
        path_object = Path(path)
        listed_stat = path_object.stat(follow_symlinks=False)
        if not stat.S_ISDIR(listed_stat.st_mode) or stat.S_ISLNK(listed_stat.st_mode):
            raise ValueError(SIMULATED_REPARSE_DIRECTORY_MESSAGE)
        return self._open(path_object, listed_stat, writable=False)

    def open_file(self, path: os.PathLike[str] | str) -> Win32FileHandle:
        """Retain one ordinary file for reading."""
        return self._open_regular_file(Path(path), writable=False)

    def open_source(self, path: os.PathLike[str] | str) -> Win32FileHandle:
        """Retain one ordinary source file for reading and exact deletion."""
        return self._open_regular_file(Path(path), writable=False)

    def create_file_new(self, path: os.PathLike[str] | str) -> Win32FileHandle:
        """Create one exclusive target and retain its descriptor."""
        if self.before_target_create is not None:
            self.before_target_create()
        path_object = Path(path)
        descriptor = os.open(
            path_object,
            os.O_CREAT | os.O_EXCL | os.O_RDWR | getattr(os, "O_NOFOLLOW", 0),
        )
        return _PathBackedWin32Handle(
            path=str(path_object),
            final_path=str(path_object),
            identity=_win32_identity(os.fstat(descriptor)),
            _descriptor=descriptor,
            _backend=self,
        )

    def _open_regular_file(self, path: Path, *, writable: bool) -> Win32FileHandle:
        listed_stat = path.stat(follow_symlinks=False)
        if not stat.S_ISREG(listed_stat.st_mode) or stat.S_ISLNK(listed_stat.st_mode):
            raise ValueError(SIMULATED_REPARSE_FILE_MESSAGE)
        return self._open(path, listed_stat, writable=writable)

    def _open(self, path: Path, listed_stat: os.stat_result, *, writable: bool) -> Win32FileHandle:
        flags = os.O_RDWR if writable else os.O_RDONLY
        if stat.S_ISDIR(listed_stat.st_mode):
            flags |= getattr(os, "O_DIRECTORY", 0)
        flags |= getattr(os, "O_NOFOLLOW", 0)
        descriptor = os.open(path, flags)
        opened_stat = os.fstat(descriptor)
        if not _same_test_object(listed_stat, opened_stat):
            os.close(descriptor)
            raise FileNotFoundError(SIMULATED_LISTED_IDENTITY_MISMATCH_MESSAGE)
        return _PathBackedWin32Handle(
            path=str(path),
            final_path=str(path),
            identity=_win32_identity(opened_stat),
            _descriptor=descriptor,
            _backend=self,
        )


@dataclass(slots=True)
class _PathBackedWin32Handle:
    """Linux descriptor implementing the retained Win32 handle test contract."""

    path: str
    final_path: str
    identity: Win32FileIdentity
    _descriptor: int
    _backend: _PathBackedWin32Backend
    _closed: bool = field(default=False, init=False)

    def duplicate_binary_fd(self, *, writable: bool = False) -> int:
        """Duplicate the retained descriptor for binary copy and hashing."""
        del writable
        return os.dup(self._descriptor)

    def refresh_identity(self) -> Win32FileIdentity:
        """Return current state after path/handle identity verification."""
        return self.verify_current(expected_path=self.path)

    def verify_current(
        self,
        *,
        expected_path: os.PathLike[str] | str | None = None,
        expected_identity: Win32FileIdentity | None = None,
    ) -> Win32FileIdentity:
        """Require the current path to name this retained object and optional state."""
        if self._closed:
            raise OSError(SIMULATED_CLOSED_HANDLE_MESSAGE)
        current_path = Path(self.path)
        path_stat = current_path.stat(follow_symlinks=False)
        handle_stat = os.fstat(self._descriptor)
        if stat.S_ISLNK(path_stat.st_mode) or not _same_test_object(path_stat, handle_stat):
            raise FileNotFoundError(SIMULATED_CURRENT_IDENTITY_MISMATCH_MESSAGE)
        if expected_path is not None and Path(expected_path) != current_path:
            raise FileNotFoundError(SIMULATED_FINAL_PATH_MISMATCH_MESSAGE)
        current_identity = _win32_identity(handle_stat)
        if expected_identity is not None and not expected_identity.same_file_state(current_identity):
            raise FileNotFoundError(SIMULATED_EXPECTED_IDENTITY_MISMATCH_MESSAGE)
        return current_identity

    def delete_exact(self, *, expected_identity: Win32FileIdentity | None = None) -> None:
        """Delete only when the current path still names this exact descriptor."""
        _ = self.verify_current(expected_path=self.path, expected_identity=expected_identity)
        path = Path(self.path)
        if self._backend.fail_delete_path == path:
            raise PermissionError(SIMULATED_DELETE_FAILURE_MESSAGE)
        path.unlink()
        self._backend.deleted_paths.append(path)

    def set_metadata(self, *, mode: int, atime_ns: int, mtime_ns: int) -> Win32FileIdentity:
        """Preserve mode and timestamps on the retained target descriptor."""
        os.fchmod(self._descriptor, mode)
        os.utime(self._descriptor, ns=(atime_ns, mtime_ns))
        return self.refresh_identity()

    def close(self) -> None:
        """Close the retained descriptor once."""
        if self._closed:
            return
        os.close(self._descriptor)
        self._closed = True

    def __enter__(self) -> Self:
        """Retain the descriptor for one context lifetime."""
        return self

    def __exit__(
        self,
        exception_type: type[BaseException] | None,
        exception: BaseException | None,
        traceback: TracebackType | None,
    ) -> None:
        """Close the descriptor after a context lifetime."""
        del exception_type, exception, traceback
        self.close()


def _win32_identity(path_stat: os.stat_result) -> Win32FileIdentity:
    """Project one Linux stat result into the shared retained-handle identity."""
    inode_bytes = path_stat.st_ino.to_bytes(16, byteorder="little", signed=False)
    return Win32FileIdentity(
        device_id=path_stat.st_dev,
        inode=path_stat.st_ino,
        size=path_stat.st_size,
        mtime_ns=path_stat.st_mtime_ns,
        ctime_ns=path_stat.st_ctime_ns,
        volume_serial_number=path_stat.st_dev,
        file_id=inode_bytes,
        attributes=0,
        reparse_tag=0,
        is_directory=stat.S_ISDIR(path_stat.st_mode),
    )


def _same_test_object(left: os.stat_result, right: os.stat_result) -> bool:
    """Compare stable object identity for the forced retained-handle backend."""
    return left.st_dev == right.st_dev and left.st_ino == right.st_ino


def _filesystem_identity(path: Path) -> FilesystemIdentity:
    source_stat = path.stat()
    return FilesystemIdentity(
        device_id=source_stat.st_dev,
        inode=source_stat.st_ino,
        size=source_stat.st_size,
        mtime_ns=source_stat.st_mtime_ns,
        ctime_ns=source_stat.st_ctime_ns,
    )


def test_file_content_hash_is_independent_of_configured_read_chunk_size(tmp_path: Path) -> None:
    """Operational throughput tuning cannot change stable content identity."""
    source_path = tmp_path / AUDIO_FILE_NAME
    _ = source_path.write_bytes(AUDIO_CONTENT)

    byte_at_a_time = FileContentHasher(chunk_size_bytes=1).calculate(source_path)
    whole_fixture = FileContentHasher(chunk_size_bytes=len(AUDIO_CONTENT)).calculate(source_path)
    with source_path.open("rb") as source_file:
        descriptor_byte_at_a_time = FileContentHasher(chunk_size_bytes=1).calculate_descriptor(source_file.fileno())
        descriptor_whole_fixture = FileContentHasher(chunk_size_bytes=len(AUDIO_CONTENT)).calculate_descriptor(
            source_file.fileno()
        )

    assert byte_at_a_time == whole_fixture == descriptor_byte_at_a_time == descriptor_whole_fixture


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


@dataclass(frozen=True, slots=True)
class ReplacingMetadataReader:
    """MetadataReader fake that replaces the observed path during capture."""

    backup_path: Path

    def read(self, path: FileSystemPath) -> TrackMetadata:
        """Replace the source with same bytes and mtime before returning metadata."""
        source_path = Path(path)
        source_stat = source_path.stat()
        content = source_path.read_bytes()
        _ = source_path.rename(self.backup_path)
        _ = source_path.write_bytes(content)
        os.utime(
            source_path,
            ns=(source_stat.st_atime_ns, source_stat.st_mtime_ns),
        )
        return _metadata()


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
