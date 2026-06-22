"""
Summary: Resolves Library-relative paths at filesystem boundaries.
Why: Keeps stored Library paths relative while adapters can access files.
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import TYPE_CHECKING

from omym2.config import LOGICAL_PATH_SEPARATOR
from omym2.shared.paths import normalize_library_relative_path

if TYPE_CHECKING:
    from omym2.features.common_ports import FileSystemPath

PATH_OUTSIDE_LIBRARY_MESSAGE = "Filesystem path is outside the Library root."


@dataclass(frozen=True, slots=True)
class FilesystemPathResolver:
    """Resolve between absolute filesystem paths and stored Library paths."""

    def resolve_library_path(self, library_root: FileSystemPath, library_relative_path: str) -> Path:
        """Return an absolute path for a normalized Library-relative path."""
        normalized_path = normalize_library_relative_path(library_relative_path)
        return Path(library_root).expanduser() / Path(*normalized_path.split(LOGICAL_PATH_SEPARATOR))

    def relative_to_library(self, library_root: FileSystemPath, path: FileSystemPath) -> str:
        """Return the stored Library-relative form for a filesystem path."""
        # strict=False keeps this usable while planning targets that may not exist yet.
        root_path = Path(library_root).expanduser().resolve(strict=False)
        file_path = Path(path).expanduser().resolve(strict=False)
        try:
            relative_path = file_path.relative_to(root_path)
        except ValueError as exc:
            raise ValueError(PATH_OUTSIDE_LIBRARY_MESSAGE) from exc
        return normalize_library_relative_path(relative_path.as_posix())
