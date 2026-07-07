"""
Summary: Implements a no-op artist name resolver.
Why: Lets callers skip MusicBrainz lookups when external resolution isn't needed.
"""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True, slots=True)
class NoOpArtistNameResolver:
    """Artist name resolver that never contacts MusicBrainz and returns no match."""

    def english_or_latin_name(self, source_artist: str) -> str | None:
        """Return none without resolving the supplied artist name."""
        _ = source_artist
        return None
