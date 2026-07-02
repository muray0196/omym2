"""
Summary: Defines artist ID feature ports.
Why: Keeps model and network I/O behind adapter-owned boundaries.
"""

from __future__ import annotations

from typing import Protocol


class ArtistLanguageDetector(Protocol):
    """Detect whether artist text should use Japanese-name resolution."""

    def is_japanese(self, text: str) -> bool:
        """Return true when text is detected as Japanese."""
        ...


class ArtistNameResolver(Protocol):
    """Resolve a generation-ready artist name from an external catalog."""

    def english_or_latin_name(self, source_artist: str) -> str | None:
        """Return a usable English or Latin artist name when one is found."""
        ...
