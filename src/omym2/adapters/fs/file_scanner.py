"""
Summary: Implements read-only filesystem discovery.
Why: Provides FileScanner entries before planning or file mutation exists.
"""

from __future__ import annotations

import os
import stat
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import TYPE_CHECKING

from omym2.config import SUPPORTED_MUSIC_FILE_EXTENSIONS
from omym2.domain.models.file_scan_entry import FileScanEntry

if TYPE_CHECKING:
    from omym2.features.common_ports import FileSystemPath

NOT_A_REGULAR_FILE_MESSAGE = "Path is not a regular file"


@dataclass(frozen=True, slots=True)
class FilesystemFileScanner:
    """Read candidate music files from a directory tree."""

    supported_extensions: frozenset[str] = SUPPORTED_MUSIC_FILE_EXTENSIONS

    def observe(self, path: FileSystemPath) -> FileScanEntry:
        """Return one cheap regular-file observation without metadata or hashes."""
        file_path = Path(path)
        stat_result = file_path.stat(follow_symlinks=False)
        if _is_link_like_identity(stat_result) or not stat.S_ISREG(stat_result.st_mode):
            if stat.S_ISDIR(stat_result.st_mode):
                raise IsADirectoryError(file_path)
            message = f"{NOT_A_REGULAR_FILE_MESSAGE}: {file_path}"
            raise OSError(message)
        return FileScanEntry(
            path=str(file_path),
            size=stat_result.st_size,
            mtime=datetime.fromtimestamp(stat_result.st_mtime, UTC),
            file_extension=file_path.suffix.lower(),
        )

    def scan(
        self,
        root: FileSystemPath,
        *,
        excluded_roots: tuple[FileSystemPath, ...] = (),
    ) -> tuple[FileScanEntry, ...]:
        """Return sorted entries while pruning excluded roots before traversal."""
        root_path = Path(root)
        if not root_path.exists():
            raise FileNotFoundError(root_path)
        if root_path.is_symlink() or root_path.is_junction() or not root_path.is_dir():
            raise NotADirectoryError(root_path)

        normalized_excluded_roots = tuple(_normalized_absolute_path(path) for path in excluded_roots)
        if _is_excluded(_normalized_absolute_path(root_path), normalized_excluded_roots):
            return ()

        entries: list[FileScanEntry] = []
        for directory, directory_names, file_names in os.walk(root_path, topdown=True, followlinks=False):
            directory_path = Path(directory)
            directory_names[:] = sorted(
                name
                for name in directory_names
                if not _is_link_like_directory(directory_path / name)
                and not _is_excluded(
                    _normalized_absolute_path(directory_path / name),
                    normalized_excluded_roots,
                )
            )
            for file_name in sorted(file_names):
                candidate = directory_path / file_name
                if candidate.suffix.lower() not in self.supported_extensions or _is_excluded(
                    _normalized_absolute_path(candidate), normalized_excluded_roots
                ):
                    continue
                try:
                    stat_result = candidate.stat(follow_symlinks=False)
                except OSError, ValueError:
                    # Skip entries that vanish or become unreadable between the
                    # directory listing and this stat, mirroring what
                    # Path.is_file() swallowed before.
                    continue
                if _is_link_like_identity(stat_result) or not stat.S_ISREG(stat_result.st_mode):
                    continue

                entries.append(
                    FileScanEntry(
                        path=str(candidate),
                        size=stat_result.st_size,
                        mtime=datetime.fromtimestamp(stat_result.st_mtime, UTC),
                        file_extension=candidate.suffix.lower(),
                    )
                )
        return tuple(sorted(entries, key=lambda entry: Path(entry.path).as_posix()))


def _normalized_absolute_path(path: FileSystemPath) -> Path:
    return Path(os.path.abspath(os.fspath(path)))  # noqa: PTH100  # Lexical exclusion only; never follow symlinks.


def _is_excluded(path: Path, excluded_roots: tuple[Path, ...]) -> bool:
    for excluded_root in excluded_roots:
        try:
            _ = path.relative_to(excluded_root)
        except ValueError:
            continue
        return True
    return False


def _is_link_like_directory(path: Path) -> bool:
    """Return whether traversal would enter a symlink or Windows junction."""
    try:
        return path.is_symlink() or path.is_junction()
    except OSError:
        return True


def _is_link_like_identity(identity: os.stat_result) -> bool:
    if stat.S_ISLNK(identity.st_mode):
        return True
    file_attributes = getattr(identity, "st_file_attributes", None)
    return isinstance(file_attributes, int) and bool(file_attributes & stat.FILE_ATTRIBUTE_REPARSE_POINT)
