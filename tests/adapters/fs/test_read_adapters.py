"""
Summary: Tests read-only filesystem adapters.
Why: Verifies scanning, hashing, snapshots, and path resolution.
"""

from __future__ import annotations

import errno
import os
import shutil
from dataclasses import dataclass, replace
from datetime import UTC, datetime
from pathlib import Path
from threading import Barrier, Lock
from typing import TYPE_CHECKING

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
from omym2.config import FILE_SNAPSHOT_CAPTURE_MIN_WORKER_COUNT
from omym2.domain.models.file_snapshot import FilesystemIdentity
from omym2.domain.models.track_metadata import TrackMetadata
from omym2.domain.services.content_fingerprint import calculate_content_fingerprint
from omym2.domain.services.metadata_fingerprint import calculate_metadata_fingerprint
from omym2.features.common_ports import FileSnapshotCaptureRequest, MetadataReadError
from tests.fakes.runtime import FixedClock

if TYPE_CHECKING:
    from typing import BinaryIO

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


def _filesystem_identity(path: Path) -> FilesystemIdentity:
    source_stat = path.stat()
    return FilesystemIdentity(
        device_id=source_stat.st_dev,
        inode=source_stat.st_ino,
        size=source_stat.st_size,
        mtime_ns=source_stat.st_mtime_ns,
        ctime_ns=source_stat.st_ctime_ns,
    )


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
