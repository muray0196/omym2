"""
Summary: Tests Library-relative path helpers.
Why: Ensures stored Library-managed paths cannot become absolute or escaping.
"""

from __future__ import annotations

import pytest

from omym2.shared.paths import (
    ESCAPING_LIBRARY_PATH_MESSAGE,
    ROOTED_LIBRARY_PATH_MESSAGE,
    is_library_relative_path,
    normalize_library_relative_path,
)

ABSOLUTE_PATH = "/Album/Track.flac"
CURRENT_DIRECTORY_PATH = "./Album//Track.flac"
ESCAPING_PATH = "Album/../Track.flac"
NORMALIZED_PATH = "Album/Track.flac"
WINDOWS_SEPARATOR_PATH = "Album\\Track.flac"


def test_library_relative_path_normalizes_to_logical_separator() -> None:
    """Stored Library paths use `/` as the logical separator."""
    assert normalize_library_relative_path(WINDOWS_SEPARATOR_PATH) == NORMALIZED_PATH
    assert normalize_library_relative_path(CURRENT_DIRECTORY_PATH) == NORMALIZED_PATH


def test_library_relative_path_rejects_absolute_path() -> None:
    """Stored Library paths must not be absolute filesystem paths."""
    with pytest.raises(ValueError, match=ROOTED_LIBRARY_PATH_MESSAGE):
        normalize_library_relative_path(ABSOLUTE_PATH)


def test_library_relative_path_rejects_parent_reference() -> None:
    """Stored Library paths must not escape the Library root."""
    with pytest.raises(ValueError, match=ESCAPING_LIBRARY_PATH_MESSAGE):
        normalize_library_relative_path(ESCAPING_PATH)


def test_is_library_relative_path_reports_validity() -> None:
    """Validity helper mirrors normalization without leaking exceptions."""
    assert is_library_relative_path(NORMALIZED_PATH)
    assert not is_library_relative_path(ABSOLUTE_PATH)
