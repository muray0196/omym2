"""
Summary: Defines artist ID feature ports.
Why: Keeps language detection, MusicBrainz lookup, and config I/O replaceable.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING, Protocol

if TYPE_CHECKING:
    from omym2.features.common_ports import ConfigStore


class LanguageDetector(Protocol):
    """Port for detecting the language of artist text."""

    def detect_language(self, text: str) -> str | None:
        """Return a language code or None when detection is unavailable."""
        ...


class MusicBrainzArtistLookup(Protocol):
    """Port for resolving a usable Latin artist name."""

    def find_latin_artist_name(self, artist_name: str) -> str | None:
        """Return a preferred English/Latin artist name when one is found."""
        ...


@dataclass(frozen=True, slots=True)
class ArtistIdPorts:
    """Ports required for artist ID generation."""

    config_store: ConfigStore
    language_detector: LanguageDetector
    musicbrainz_lookup: MusicBrainzArtistLookup
