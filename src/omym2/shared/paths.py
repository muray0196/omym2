"""
Summary: Provides pure helpers for logical Library-relative paths.
Why: Protects stored paths from absolute paths and root escape.
"""

from __future__ import annotations

from pathlib import PurePosixPath

from omym2.config import CURRENT_DIRECTORY_REFERENCE, LOGICAL_PATH_SEPARATOR, PARENT_DIRECTORY_REFERENCE

EMPTY_LIBRARY_PATH_MESSAGE = "Library-relative path must not be empty."
ESCAPING_LIBRARY_PATH_MESSAGE = "Library-relative path must not contain parent-directory references."
ROOTED_LIBRARY_PATH_MESSAGE = "Library-relative path must not be absolute."


def normalize_library_relative_path(raw_path: str) -> str:
    """Normalize a stored path as a Library-root-relative logical path.

    Args:
        raw_path: Path string supplied by domain or adapter code.

    Returns:
        A normalized path using `/` as the logical separator.

    Raises:
        ValueError: The path is empty, absolute, or contains `..`.
    """
    if raw_path == "":
        raise ValueError(EMPTY_LIBRARY_PATH_MESSAGE)

    posix_path = raw_path.replace("\\", LOGICAL_PATH_SEPARATOR)
    parsed_path = PurePosixPath(posix_path)
    if parsed_path.is_absolute():
        raise ValueError(ROOTED_LIBRARY_PATH_MESSAGE)

    normalized_parts: list[str] = []
    for part in parsed_path.parts:
        if part == CURRENT_DIRECTORY_REFERENCE:
            continue
        if part == PARENT_DIRECTORY_REFERENCE:
            raise ValueError(ESCAPING_LIBRARY_PATH_MESSAGE)
        normalized_parts.append(part)

    if not normalized_parts:
        raise ValueError(EMPTY_LIBRARY_PATH_MESSAGE)

    return LOGICAL_PATH_SEPARATOR.join(normalized_parts)
