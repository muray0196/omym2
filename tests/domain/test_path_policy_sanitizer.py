"""
Summary: Tests migrated OMYM string sanitizer behavior.
Why: Protects filename normalization, byte limits, and extension handling.
"""

from __future__ import annotations

import pytest

from omym2.config import SANITIZER_ALBUM_MAX_BYTES, SANITIZER_ARTIST_MAX_BYTES, SANITIZER_FALLBACK_TITLE
from omym2.domain.services.path_policy import (
    sanitize_album_name,
    sanitize_artist_name,
    sanitize_path_components,
    sanitize_string,
    sanitize_track_title,
)


@pytest.mark.parametrize(
    ("value", "expected"),
    [
        (None, ""),
        ("", ""),
        (0.0, ""),
        (12.5, "12-5"),
        ("John's Song", "Johns-Song"),
        ("Rock & Roll!!!", "Rock-Roll"),
        ("  --Hello---World--  ", "Hello-World"),
        ("...", ""),
        ("hello world", "hello-world"),
        ("Beyoncé", "Beyonce"),
        ("München", "Munchen"),
        ("東京", "Dong-Jing"),
        ("\uff11\uff12 \uff21\uff22\uff23", "12-ABC"),
        ("① test", "1-test"),
        ("★ Track ♪", "Track"),
        ("µ", "u"),
    ],
)
def test_sanitize_string_matches_migrated_golden_inputs(value: str | float | None, expected: str) -> None:
    """Golden sanitizer inputs cover falsy, symbols, Unicode, and NFKC behavior."""
    assert sanitize_string(value) == expected


def test_sanitize_string_preserves_allowed_extension_only_when_requested() -> None:
    """Extension preservation is opt-in and only preserves final alphanumeric suffixes."""
    assert sanitize_string("Hello World.mp3") == "Hello-World-mp3"
    assert sanitize_string("Hello World.mp3", preserve_extension=True) == "Hello-World.mp3"
    assert sanitize_string("hello.tar.gz", preserve_extension=True) == "hello-tar.gz"
    assert sanitize_string("hello.", preserve_extension=True) == "hello"
    assert sanitize_string("hello.m-4a", preserve_extension=True) == "hello-m-4a"


def test_sanitize_string_limits_utf8_bytes_while_preserving_extension() -> None:
    """The byte limit applies to the final result while keeping the extension intact."""
    assert sanitize_string("Hello World.mp3", max_length=12, preserve_extension=True) == "Hello-Wo.mp3"
    assert sanitize_string("Hello World.mp3", max_length=10, preserve_extension=True) == "Hello.mp3"
    assert sanitize_string("Hello World.mp3", max_length=3, preserve_extension=True) == ""


def test_sanitizer_wrappers_apply_target_limits_and_title_fallback() -> None:
    """OMYM wrapper limits and the title fallback stay centralized."""
    assert len(sanitize_artist_name("A" * 60).encode()) == SANITIZER_ARTIST_MAX_BYTES
    assert len(sanitize_album_name("B" * 100).encode()) == SANITIZER_ALBUM_MAX_BYTES
    assert sanitize_track_title(None) == SANITIZER_FALLBACK_TITLE
    assert sanitize_track_title("") == SANITIZER_FALLBACK_TITLE
    assert sanitize_track_title("!!!") == SANITIZER_FALLBACK_TITLE


def test_sanitize_path_components_preserves_extension_on_final_component() -> None:
    """Logical path sanitization preserves extensions only on the final component."""
    assert sanitize_path_components("Artist Name/Album: One/01 Title.flac") == "Artist-Name/Album-One/01-Title.flac"
    assert sanitize_path_components("bad///final?.mp3") == "bad/final.mp3"
