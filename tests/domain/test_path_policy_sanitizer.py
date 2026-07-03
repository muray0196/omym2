"""
Summary: Tests migrated OMYM string sanitizer behavior.
Why: Pins filename-safe normalization, byte limits, and path component fallback.
"""

from __future__ import annotations

import pytest

from omym2.config import SANITIZER_ALBUM_MAX_BYTES, SANITIZER_ARTIST_MAX_BYTES, SANITIZER_FALLBACK_TITLE
from omym2.domain.services.path_policy import (
    sanitize_album_name,
    sanitize_artist_name,
    sanitize_path_component,
    sanitize_path_components,
    sanitize_string,
    sanitize_track_title,
)

EXTENSION_STEM_LIMIT = 3
FULL_COMPONENT_LIMIT = 11
FULL_STEM_LIMIT = 7
LONG_ALBUM = "B" * 100
LONG_ARTIST = "A" * 60
LONG_UNICODE_REPEAT = 80


@pytest.mark.parametrize(
    ("value", "expected"),
    [
        (None, ""),
        ("", ""),
        (0.0, ""),
        ("   ", ""),
        ("!!!", ""),
        ("John's Song", "Johns-Song"),
        ("Hello World!", "Hello-World"),
        ("A---B!!!C", "A-B-C"),
        ("---hello---", "hello"),
        ("\uff11\uff12 Café / Song???", "12-Café-Song"),
        ("Beyonce\u0301", "Beyoncé"),
        ("\u2116\uff11\uff12", "No12"),
        ("こんにちは", "こんにちは"),
        ("안녕하세요", "안녕하세요"),
        ("你好", "你好"),
        ("Café", "Café"),
        ("über", "über"),
        ("東京", "東京"),
        ("½", "1-2"),
        (12.5, "12-5"),
    ],
)
def test_sanitize_string_matches_migrated_golden_values(value: str | float | None, expected: str) -> None:
    """The migrated sanitizer preserves Unicode letters after NFKC normalization."""
    assert sanitize_string(value) == expected


def test_sanitize_string_limits_utf8_bytes_after_sanitizing() -> None:
    """Byte limits are enforced after normalization and unsafe replacement."""
    sanitized = sanitize_string("é" * LONG_UNICODE_REPEAT, max_length=SANITIZER_ARTIST_MAX_BYTES)

    assert sanitized == "é" * (SANITIZER_ARTIST_MAX_BYTES // len("é".encode()))
    assert len(sanitized.encode()) == SANITIZER_ARTIST_MAX_BYTES
    assert sanitize_string("ab-cd", max_length=EXTENSION_STEM_LIMIT) == "ab"


def test_sanitize_string_preserves_only_allowed_final_extension() -> None:
    """Only a final alphanumeric suffix is preserved outside base sanitization.

    max_length budgets the TOTAL output (stem + preserved extension); the
    extension is never truncated and a non-empty stem keeps at least its
    first character even when the budget is smaller than the extension.
    """
    assert sanitize_string("My Song.FLAC", max_length=FULL_STEM_LIMIT, preserve_extension=True) == "My.FLAC"
    assert sanitize_string("Aimer.flac", max_length=EXTENSION_STEM_LIMIT, preserve_extension=True) == "A.flac"
    assert sanitize_string("v1.track.mp3", preserve_extension=True) == "v1-track.mp3"
    assert sanitize_string("Track.bad-ext", preserve_extension=True) == "Track-bad-ext"
    assert sanitize_string("Track.", preserve_extension=True) == "Track"


def test_preserved_extension_uses_fallback_when_sanitized_stem_is_empty() -> None:
    """A preserved suffix never becomes a directory-like empty filename."""
    assert sanitize_string("!!!.flac", max_length=EXTENSION_STEM_LIMIT, preserve_extension=True) == "_.flac"
    assert sanitize_path_component("!!!.flac", max_length=EXTENSION_STEM_LIMIT, preserve_extension=True) == "_.flac"


def test_wrappers_apply_artist_album_limits_and_title_fallback() -> None:
    """Wrapper helpers keep OMYM byte limits and title fallback behavior."""
    assert sanitize_artist_name(LONG_ARTIST) == "A" * SANITIZER_ARTIST_MAX_BYTES
    assert sanitize_album_name(LONG_ALBUM) == "B" * SANITIZER_ALBUM_MAX_BYTES
    assert sanitize_track_title("!!!") == SANITIZER_FALLBACK_TITLE
    assert sanitize_track_title(None) == SANITIZER_FALLBACK_TITLE
    assert sanitize_track_title(0.0) == SANITIZER_FALLBACK_TITLE


def test_path_component_sanitizer_uses_safe_fallback_for_non_empty_input() -> None:
    """Path components differ from raw strings because stored paths cannot be empty."""
    assert sanitize_string("!!!") == ""
    assert sanitize_path_component("!!!") == "_"
    assert sanitize_path_component("   ") == "_"


def test_path_components_preserve_extension_on_final_component_only() -> None:
    """Path sanitization preserves the suffix only for the final component."""
    assert sanitize_path_components("Artist Name/Album.Name/!!!.flac", max_length=FULL_COMPONENT_LIMIT) == (
        "Artist-Name/Album-Name/_.flac"
    )


@pytest.mark.parametrize(
    ("value", "expected"),
    [
        ("CON", "_"),
        ("nul", "_"),
        ("COM1", "_"),
        ("CONCERT", "CONCERT"),
        ("COM", "COM"),
    ],
)
def test_sanitize_reserved_windows_device_names(value: str, expected: str) -> None:
    """Reserved Windows device name components fall back like a sanitized-to-empty component.

    A component whose sanitized form case-insensitively equals CON, PRN, AUX,
    NUL, COM1-COM9, or LPT1-LPT9 is treated as sanitized to empty so the
    existing "_" fallback applies. A near match such as "CONCERT" or a
    non-reserved prefix such as "COM" passes through unchanged.
    """
    assert sanitize_path_component(value) == expected


def test_sanitize_reserved_windows_device_name_stem_with_preserved_extension() -> None:
    """A reserved device name stem falls back even when a final extension is preserved.

    Windows treats "con.mp3" as reserved too because it only looks at the
    stem, so the check must apply before the extension is reattached.
    """
    assert sanitize_path_component("con.mp3", preserve_extension=True) == "_.mp3"
