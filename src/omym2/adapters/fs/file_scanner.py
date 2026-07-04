"""
Summary: Implements read-only filesystem discovery.
Why: Provides FileScanner entries before planning or file mutation exists.
"""

from __future__ import annotations

import stat
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import TYPE_CHECKING

from omym2.config import SUPPORTED_MUSIC_FILE_EXTENSIONS
from omym2.domain.models.file_scan_entry import FileScanEntry

if TYPE_CHECKING:
    from omym2.features.common_ports import FileSystemPath


@dataclass(frozen=True, slots=True)
class FilesystemFileScanner:
    """Read candidate music files from a directory tree."""

    supported_extensions: frozenset[str] = SUPPORTED_MUSIC_FILE_EXTENSIONS

    def scan(self, root: FileSystemPath) -> tuple[FileScanEntry, ...]:
        """Return sorted file discovery entries without metadata or hashes."""
        root_path = Path(root)
        if not root_path.exists():
            raise FileNotFoundError(root_path)
        if not root_path.is_dir():
            raise NotADirectoryError(root_path)

        candidates = (
            candidate for candidate in root_path.rglob("*") if candidate.suffix.lower() in self.supported_extensions
        )
        entries: list[FileScanEntry] = []
        for candidate in sorted(candidates, key=lambda path: path.as_posix()):
            try:
                stat_result = candidate.stat()
            except OSError, ValueError:
                # Skip entries that vanish or become unreadable between the
                # directory listing and this stat, mirroring what
                # Path.is_file() swallowed before.
                continue
            if not stat.S_ISREG(stat_result.st_mode):
                continue

            entries.append(
                FileScanEntry(
                    path=str(candidate),
                    size=stat_result.st_size,
                    mtime=datetime.fromtimestamp(stat_result.st_mtime, UTC),
                    file_extension=candidate.suffix.lower(),
                )
            )
        return tuple(entries)
