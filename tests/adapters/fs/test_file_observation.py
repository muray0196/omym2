"""
Summary: Tests metadata-free snapshots and complete source inventories.
Why: Protects no-follow observation before reviewed companion and leftover moves.
"""

from __future__ import annotations

import os
from datetime import UTC, datetime
from typing import TYPE_CHECKING

import pytest

from omym2.adapters.fs import file_content_snapshot_reader as content_snapshot_reader_module
from omym2.adapters.fs import source_inventory_reader as source_inventory_module
from omym2.adapters.fs.file_content_snapshot_reader import (
    CONTENT_SNAPSHOT_CHANGED_MESSAGE,
    CONTENT_SNAPSHOT_NOT_REGULAR_MESSAGE,
    CONTENT_SNAPSHOT_OUTSIDE_ROOT_MESSAGE,
    CONTENT_SNAPSHOT_SYMLINK_MESSAGE,
    FilesystemFileContentSnapshotReader,
)
from omym2.adapters.fs.hash_calculator import FileContentHasher
from omym2.adapters.fs.source_inventory_reader import (
    SOURCE_INVENTORY_CHANGED_MESSAGE,
    SOURCE_INVENTORY_ROOT_SYMLINK_MESSAGE,
    FilesystemSourceInventoryReader,
)
from omym2.domain.models.file_snapshot import FilesystemIdentity
from omym2.domain.services.content_fingerprint import calculate_content_fingerprint
from omym2.features.common_ports import SourceInventoryRequest
from tests.fakes.runtime import FixedClock

if TYPE_CHECKING:
    from collections.abc import Iterator
    from pathlib import Path

    from omym2.features.common_ports import FileSystemPath

AUDIO_CONTENT = b"arbitrary file bytes"
CAPTURED_TIME = datetime(2026, 1, 1, tzinfo=UTC)
DEFAULT_OPEN_MODE = 0o777
EXCLUDED_DIRECTORY_NAME = "Unprocessed"
EXPECTED_DESCRIPTOR_CALL_COUNT = 1
HASH_CHUNK_SIZE_BYTES = 4
NESTED_DIRECTORY_NAME = "nested"
OUTSIDE_DIRECTORY_NAME = "outside"
SECOND_FILE_NAME = "second.bin"
SOURCE_FILE_NAME = "notes.txt"
SOURCE_ROOT_NAME = "source"
SOURCE_ROOT_SYMLINK_NAME = "source-link"
SYMLINK_DIRECTORY_NAME = "linked-directory"
SYMLINK_FILE_NAME = "linked-file"


@pytest.mark.parametrize("use_path_fallback", [False, True], ids=("descriptor-relative", "path-fallback"))
def test_content_snapshot_reader_hashes_retained_descriptor_without_metadata(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    *,
    use_path_fallback: bool,
) -> None:
    """Content capture returns stat/hash evidence and never calls the path hashing entrypoint."""
    source_root = tmp_path / SOURCE_ROOT_NAME
    source_path = source_root / NESTED_DIRECTORY_NAME / SOURCE_FILE_NAME
    source_path.parent.mkdir(parents=True)
    _ = source_path.write_bytes(AUDIO_CONTENT)
    descriptor_calls: list[int] = []
    original_descriptor_hash = FileContentHasher.calculate_descriptor

    def record_descriptor_hash(hasher: FileContentHasher, file_descriptor: int) -> str:
        descriptor_calls.append(file_descriptor)
        return original_descriptor_hash(hasher, file_descriptor)

    def reject_path_hash(_hasher: FileContentHasher, _path: object) -> str:
        pytest.fail("Content snapshots must hash the retained descriptor.")

    if use_path_fallback:
        monkeypatch.setattr(content_snapshot_reader_module, "_OPEN_SUPPORTS_DIR_FD", False)
    monkeypatch.setattr(FileContentHasher, "calculate_descriptor", record_descriptor_hash)
    monkeypatch.setattr(FileContentHasher, "calculate", reject_path_hash)
    reader = FilesystemFileContentSnapshotReader(
        clock=FixedClock(CAPTURED_TIME),
        hasher=FileContentHasher(chunk_size_bytes=HASH_CHUNK_SIZE_BYTES),
    )

    snapshot = reader.capture(source_path, root=source_root)
    source_identity = source_path.stat()

    assert snapshot.path == str(source_path)
    assert snapshot.size == len(AUDIO_CONTENT)
    assert snapshot.content_hash == calculate_content_fingerprint(AUDIO_CONTENT)
    assert snapshot.filesystem_identity == FilesystemIdentity(
        device_id=source_identity.st_dev,
        inode=source_identity.st_ino,
        size=source_identity.st_size,
        mtime_ns=source_identity.st_mtime_ns,
        ctime_ns=source_identity.st_ctime_ns,
    )
    assert snapshot.captured_at == CAPTURED_TIME
    assert len(descriptor_calls) == EXPECTED_DESCRIPTOR_CALL_COUNT
    assert not hasattr(snapshot, "metadata")


@pytest.mark.parametrize("use_path_fallback", [False, True], ids=("descriptor-relative", "path-fallback"))
def test_content_snapshot_reader_rejects_root_file_and_directory_symlinks(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    *,
    use_path_fallback: bool,
) -> None:
    """No selected root, source file, or traversed parent may be a symlink."""
    source_root = tmp_path / SOURCE_ROOT_NAME
    outside_root = tmp_path / OUTSIDE_DIRECTORY_NAME
    source_root.mkdir()
    outside_root.mkdir()
    outside_file = outside_root / SOURCE_FILE_NAME
    _ = outside_file.write_bytes(AUDIO_CONTENT)
    root_symlink = tmp_path / SOURCE_ROOT_SYMLINK_NAME
    root_symlink.symlink_to(source_root, target_is_directory=True)
    file_symlink = source_root / SYMLINK_FILE_NAME
    file_symlink.symlink_to(outside_file)
    directory_symlink = source_root / SYMLINK_DIRECTORY_NAME
    directory_symlink.symlink_to(outside_root, target_is_directory=True)
    if use_path_fallback:
        monkeypatch.setattr(content_snapshot_reader_module, "_OPEN_SUPPORTS_DIR_FD", False)
    reader = FilesystemFileContentSnapshotReader(clock=FixedClock(CAPTURED_TIME))

    with pytest.raises(ValueError, match=CONTENT_SNAPSHOT_SYMLINK_MESSAGE):
        _ = reader.capture(root_symlink / SOURCE_FILE_NAME, root=root_symlink)
    with pytest.raises(ValueError, match=CONTENT_SNAPSHOT_SYMLINK_MESSAGE):
        _ = reader.capture(file_symlink, root=source_root)
    with pytest.raises(ValueError, match=CONTENT_SNAPSHOT_SYMLINK_MESSAGE):
        _ = reader.capture(directory_symlink / SOURCE_FILE_NAME, root=source_root)


@pytest.mark.parametrize("use_path_fallback", [False, True], ids=("descriptor-relative", "path-fallback"))
def test_content_snapshot_reader_rejects_nonregular_and_outside_paths(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    *,
    use_path_fallback: bool,
) -> None:
    """Only a regular descendant of the supplied root can be captured."""
    source_root = tmp_path / SOURCE_ROOT_NAME
    outside_root = tmp_path / OUTSIDE_DIRECTORY_NAME
    source_root.mkdir()
    outside_root.mkdir()
    outside_file = outside_root / SOURCE_FILE_NAME
    _ = outside_file.write_bytes(AUDIO_CONTENT)

    if use_path_fallback:
        monkeypatch.setattr(content_snapshot_reader_module, "_OPEN_SUPPORTS_DIR_FD", False)
    reader = FilesystemFileContentSnapshotReader(clock=FixedClock(CAPTURED_TIME))

    with pytest.raises(ValueError, match=CONTENT_SNAPSHOT_NOT_REGULAR_MESSAGE):
        _ = reader.capture(source_root, root=tmp_path)
    with pytest.raises(ValueError, match=CONTENT_SNAPSHOT_OUTSIDE_ROOT_MESSAGE):
        _ = reader.capture(outside_file, root=source_root)


@pytest.mark.parametrize("use_path_fallback", [False, True], ids=("descriptor-relative", "path-fallback"))
def test_content_snapshot_reader_detects_path_replacement_during_hash(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    *,
    use_path_fallback: bool,
) -> None:
    """Replacing a pathname while its old descriptor is hashed invalidates the capture."""
    source_root = tmp_path / SOURCE_ROOT_NAME
    source_path = source_root / SOURCE_FILE_NAME
    retained_path = source_root / SECOND_FILE_NAME
    source_root.mkdir()
    _ = source_path.write_bytes(AUDIO_CONTENT)
    original_descriptor_hash = FileContentHasher.calculate_descriptor

    def replace_after_hash(hasher: FileContentHasher, file_descriptor: int) -> str:
        content_hash = original_descriptor_hash(hasher, file_descriptor)
        _ = source_path.rename(retained_path)
        _ = source_path.write_bytes(AUDIO_CONTENT)
        return content_hash

    if use_path_fallback:
        monkeypatch.setattr(content_snapshot_reader_module, "_OPEN_SUPPORTS_DIR_FD", False)
    monkeypatch.setattr(FileContentHasher, "calculate_descriptor", replace_after_hash)
    reader = FilesystemFileContentSnapshotReader(clock=FixedClock(CAPTURED_TIME))

    with pytest.raises(ValueError, match=CONTENT_SNAPSHOT_CHANGED_MESSAGE):
        _ = reader.capture(source_path, root=source_root)

    assert source_path.read_bytes() == AUDIO_CONTENT
    assert retained_path.read_bytes() == AUDIO_CONTENT


def test_content_snapshot_reader_path_fallback_detects_symlink_swap_before_open(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """The path fallback rejects a source replaced by a symlink after its no-follow stat."""
    source_root = tmp_path / SOURCE_ROOT_NAME
    outside_root = tmp_path / OUTSIDE_DIRECTORY_NAME
    source_path = source_root / SOURCE_FILE_NAME
    retained_path = source_root / SECOND_FILE_NAME
    outside_path = outside_root / SOURCE_FILE_NAME
    source_root.mkdir()
    outside_root.mkdir()
    _ = source_path.write_bytes(AUDIO_CONTENT)
    outside_content = b"outside bytes"
    _ = outside_path.write_bytes(outside_content)
    original_open = os.open
    replaced = False

    def replace_before_open(
        path: os.PathLike[str] | str,
        flags: int,
        mode: int = DEFAULT_OPEN_MODE,
        *,
        dir_fd: int | None = None,
    ) -> int:
        nonlocal replaced
        if os.fspath(path) == os.fspath(source_path) and dir_fd is None and not replaced:
            replaced = True
            _ = source_path.rename(retained_path)
            source_path.symlink_to(outside_path)
        return original_open(path, flags, mode, dir_fd=dir_fd)

    monkeypatch.setattr(content_snapshot_reader_module, "_OPEN_SUPPORTS_DIR_FD", False)
    monkeypatch.setattr(os, "open", replace_before_open)

    with pytest.raises(ValueError, match=CONTENT_SNAPSHOT_CHANGED_MESSAGE):
        _ = FilesystemFileContentSnapshotReader(clock=FixedClock(CAPTURED_TIME)).capture(
            source_path,
            root=source_root,
        )

    assert source_path.is_symlink()
    assert retained_path.read_bytes() == AUDIO_CONTENT
    assert outside_path.read_bytes() == outside_content


def test_content_snapshot_reader_path_fallback_detects_parent_swap_during_hash(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """The path fallback invalidates a capture when a retained parent path is redirected."""
    source_root = tmp_path / SOURCE_ROOT_NAME
    source_parent = source_root / NESTED_DIRECTORY_NAME
    retained_parent = source_root / f"{NESTED_DIRECTORY_NAME}-retained"
    outside_root = tmp_path / OUTSIDE_DIRECTORY_NAME
    source_path = source_parent / SOURCE_FILE_NAME
    source_parent.mkdir(parents=True)
    outside_root.mkdir()
    _ = source_path.write_bytes(AUDIO_CONTENT)
    original_descriptor_hash = FileContentHasher.calculate_descriptor

    def replace_parent_after_hash(hasher: FileContentHasher, file_descriptor: int) -> str:
        content_hash = original_descriptor_hash(hasher, file_descriptor)
        _ = source_parent.rename(retained_parent)
        source_parent.symlink_to(outside_root, target_is_directory=True)
        return content_hash

    monkeypatch.setattr(content_snapshot_reader_module, "_OPEN_SUPPORTS_DIR_FD", False)
    monkeypatch.setattr(FileContentHasher, "calculate_descriptor", replace_parent_after_hash)

    with pytest.raises(ValueError, match=CONTENT_SNAPSHOT_CHANGED_MESSAGE):
        _ = FilesystemFileContentSnapshotReader(clock=FixedClock(CAPTURED_TIME)).capture(
            source_path,
            root=source_root,
        )

    assert source_parent.is_symlink()
    assert (retained_parent / SOURCE_FILE_NAME).read_bytes() == AUDIO_CONTENT


def test_source_inventory_returns_all_regular_files_in_relative_order_and_skips_symlinks(tmp_path: Path) -> None:
    """Inventory is extension-agnostic and never follows linked files or directories."""
    source_root = tmp_path / SOURCE_ROOT_NAME
    outside_root = tmp_path / OUTSIDE_DIRECTORY_NAME
    source_root.mkdir()
    outside_root.mkdir()
    relative_paths = (
        "z.bin",
        "a/cover.jpg",
        "a/track.flac",
        "b/readme",
    )
    for relative_path in relative_paths:
        file_path = source_root.joinpath(*relative_path.split("/"))
        file_path.parent.mkdir(parents=True, exist_ok=True)
        _ = file_path.write_bytes(AUDIO_CONTENT)
    outside_file = outside_root / SOURCE_FILE_NAME
    _ = outside_file.write_bytes(AUDIO_CONTENT)
    (source_root / SYMLINK_FILE_NAME).symlink_to(outside_file)
    (source_root / SYMLINK_DIRECTORY_NAME).symlink_to(outside_root, target_is_directory=True)

    entries = FilesystemSourceInventoryReader().scan(SourceInventoryRequest(root=source_root))

    assert [entry.relative_path for entry in entries] == [
        "a/cover.jpg",
        "a/track.flac",
        "b/readme",
        "z.bin",
    ]
    assert [entry.path for entry in entries] == [
        str(source_root / "a" / "cover.jpg"),
        str(source_root / "a" / "track.flac"),
        str(source_root / "b" / "readme"),
        str(source_root / "z.bin"),
    ]


def test_source_inventory_prunes_excluded_root_before_opening_it(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Caller exclusions stop descent mechanically rather than filtering completed results."""
    source_root = tmp_path / SOURCE_ROOT_NAME
    excluded_root = source_root / EXCLUDED_DIRECTORY_NAME
    included_file = source_root / SOURCE_FILE_NAME
    excluded_file = excluded_root / SECOND_FILE_NAME
    excluded_root.mkdir(parents=True)
    _ = included_file.write_bytes(AUDIO_CONTENT)
    _ = excluded_file.write_bytes(AUDIO_CONTENT)
    original_open = os.open

    def reject_excluded_open(
        path: os.PathLike[str] | str,
        flags: int,
        mode: int = DEFAULT_OPEN_MODE,
        *,
        dir_fd: int | None = None,
    ) -> int:
        if path == EXCLUDED_DIRECTORY_NAME and dir_fd is not None:
            pytest.fail("Excluded roots must be pruned before traversal.")
        return original_open(path, flags, mode, dir_fd=dir_fd)

    monkeypatch.setattr(os, "open", reject_excluded_open)

    entries = FilesystemSourceInventoryReader().scan(
        SourceInventoryRequest(root=source_root, excluded_roots=(excluded_root,))
    )

    assert [entry.relative_path for entry in entries] == [SOURCE_FILE_NAME]


def test_source_inventory_descriptor_traversal_does_not_follow_replaced_directory(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Descriptor traversal skips a child replaced by a symlink before open."""
    if (
        os.open not in os.supports_dir_fd
        or os.scandir not in os.supports_fd
        or os.stat not in os.supports_dir_fd
        or os.stat not in os.supports_follow_symlinks
        or not hasattr(os, "O_DIRECTORY")
        or not hasattr(os, "O_NOFOLLOW")
    ):
        pytest.skip("Descriptor-relative inventory primitives are unavailable.")
    source_root = tmp_path / SOURCE_ROOT_NAME
    nested_root = source_root / NESTED_DIRECTORY_NAME
    retained_root = source_root / f"{NESTED_DIRECTORY_NAME}-retained"
    outside_root = tmp_path / OUTSIDE_DIRECTORY_NAME
    nested_root.mkdir(parents=True)
    outside_root.mkdir()
    _ = (nested_root / SOURCE_FILE_NAME).write_bytes(AUDIO_CONTENT)
    _ = (outside_root / SECOND_FILE_NAME).write_bytes(AUDIO_CONTENT)
    original_open = os.open
    replaced = False

    def replace_before_open(
        path: FileSystemPath,
        flags: int,
        mode: int = DEFAULT_OPEN_MODE,
        *,
        dir_fd: int | None = None,
    ) -> int:
        nonlocal replaced
        if not replaced and path == NESTED_DIRECTORY_NAME and dir_fd is not None:
            replaced = True
            _ = nested_root.rename(retained_root)
            nested_root.symlink_to(outside_root, target_is_directory=True)
        return original_open(path, flags, mode, dir_fd=dir_fd)

    monkeypatch.setattr(os, "open", replace_before_open)

    entries = FilesystemSourceInventoryReader().scan(SourceInventoryRequest(root=source_root))

    assert entries == ()


def test_source_inventory_path_fallback_is_complete_and_no_follow(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """The non-descriptor traversal remains usable without following linked entries."""
    source_root = tmp_path / SOURCE_ROOT_NAME
    outside_root = tmp_path / OUTSIDE_DIRECTORY_NAME
    nested_file = source_root / NESTED_DIRECTORY_NAME / SOURCE_FILE_NAME
    outside_file = outside_root / SECOND_FILE_NAME
    nested_file.parent.mkdir(parents=True)
    outside_root.mkdir()
    _ = nested_file.write_bytes(AUDIO_CONTENT)
    _ = outside_file.write_bytes(AUDIO_CONTENT)
    (source_root / SYMLINK_FILE_NAME).symlink_to(outside_file)
    (source_root / SYMLINK_DIRECTORY_NAME).symlink_to(outside_root, target_is_directory=True)
    monkeypatch.setattr(source_inventory_module, "_descriptor_inventory_supported", lambda: False)

    entries = FilesystemSourceInventoryReader().scan(SourceInventoryRequest(root=source_root))

    assert [(entry.path, entry.relative_path) for entry in entries] == [
        (str(nested_file), f"{NESTED_DIRECTORY_NAME}/{SOURCE_FILE_NAME}")
    ]


def test_source_inventory_path_fallback_prunes_excluded_root_before_scanning_it(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """The fallback never enters a caller-pruned subtree."""
    source_root = tmp_path / SOURCE_ROOT_NAME
    excluded_root = source_root / EXCLUDED_DIRECTORY_NAME
    included_file = source_root / SOURCE_FILE_NAME
    excluded_file = excluded_root / SECOND_FILE_NAME
    excluded_root.mkdir(parents=True)
    _ = included_file.write_bytes(AUDIO_CONTENT)
    _ = excluded_file.write_bytes(AUDIO_CONTENT)
    original_scandir = os.scandir

    def reject_excluded_scan(path: FileSystemPath) -> Iterator[os.DirEntry[str]]:
        if os.fspath(path) == os.fspath(excluded_root):
            pytest.fail("Excluded roots must be pruned before fallback traversal.")
        return original_scandir(path)

    monkeypatch.setattr(source_inventory_module, "_descriptor_inventory_supported", lambda: False)
    monkeypatch.setattr(os, "scandir", reject_excluded_scan)

    entries = FilesystemSourceInventoryReader().scan(
        SourceInventoryRequest(root=source_root, excluded_roots=(excluded_root,))
    )

    assert [entry.relative_path for entry in entries] == [SOURCE_FILE_NAME]


def test_source_inventory_path_fallback_rejects_directory_replacement(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """An observed directory swap fails closed instead of retaining redirected entries."""
    source_root = tmp_path / SOURCE_ROOT_NAME
    nested_root = source_root / NESTED_DIRECTORY_NAME
    retained_root = source_root / f"{NESTED_DIRECTORY_NAME}-retained"
    outside_root = tmp_path / OUTSIDE_DIRECTORY_NAME
    nested_root.mkdir(parents=True)
    outside_root.mkdir()
    _ = (nested_root / SOURCE_FILE_NAME).write_bytes(AUDIO_CONTENT)
    _ = (outside_root / SECOND_FILE_NAME).write_bytes(AUDIO_CONTENT)
    original_scandir = os.scandir
    replaced = False

    def replace_before_scan(path: FileSystemPath) -> Iterator[os.DirEntry[str]]:
        nonlocal replaced
        if not replaced and os.fspath(path) == os.fspath(nested_root):
            replaced = True
            _ = nested_root.rename(retained_root)
            nested_root.symlink_to(outside_root, target_is_directory=True)
        return original_scandir(path)

    monkeypatch.setattr(source_inventory_module, "_descriptor_inventory_supported", lambda: False)
    monkeypatch.setattr(os, "scandir", replace_before_scan)

    with pytest.raises(ValueError, match=SOURCE_INVENTORY_CHANGED_MESSAGE):
        _ = FilesystemSourceInventoryReader().scan(SourceInventoryRequest(root=source_root))


def test_source_inventory_rejects_a_symlink_root(tmp_path: Path) -> None:
    """A selected source root cannot redirect discovery through a symbolic link."""
    source_root = tmp_path / SOURCE_ROOT_NAME
    source_root.mkdir()
    root_symlink = tmp_path / SOURCE_ROOT_SYMLINK_NAME
    root_symlink.symlink_to(source_root, target_is_directory=True)

    with pytest.raises(ValueError, match=SOURCE_INVENTORY_ROOT_SYMLINK_MESSAGE):
        _ = FilesystemSourceInventoryReader().scan(SourceInventoryRequest(root=root_symlink))
