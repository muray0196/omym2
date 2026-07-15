"""
Summary: Projects artist metadata and derives stable provider-cache keys.
Why: Keeps path names and lookup identity derived without changing source tags.
"""

from __future__ import annotations

import unicodedata
from dataclasses import dataclass
from types import MappingProxyType
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from collections.abc import Mapping

    from omym2.domain.models.track_metadata import TrackMetadata

_ARTIST_NAME_SOURCE_KEY_NORMALIZATION_FORM = "NFC"


def derive_artist_name_source_key(source_name: str | None) -> str | None:
    """Return one normalized whole-string key, or no key for missing text."""
    if source_name is None:
        return None
    normalized = unicodedata.normalize(_ARTIST_NAME_SOURCE_KEY_NORMALIZATION_FORM, source_name)
    source_key = " ".join(normalized.split())
    return source_key or None


@dataclass(frozen=True, slots=True)
class ArtistNameProjection:
    """Artist fields after exact preference lookup."""

    artist: str | None
    album_artist: str | None


@dataclass(frozen=True, slots=True)
class ArtistNameProjector:
    """Apply immutable exact-match display preferences to raw artist text."""

    preferences: Mapping[str, str] | None = None

    def __post_init__(self) -> None:
        """Freeze the preference snapshot used for deterministic projection."""
        object.__setattr__(self, "preferences", MappingProxyType(dict(self.preferences or {})))

    def project(self, metadata: TrackMetadata) -> ArtistNameProjection:
        """Return display artist values without modifying raw metadata."""
        return ArtistNameProjection(
            artist=self._preferred_name(metadata.artist),
            album_artist=self._preferred_name(metadata.album_artist),
        )

    def _preferred_name(self, source_name: str | None) -> str | None:
        if source_name is None:
            return None
        preferences = self.preferences
        if preferences is None:
            return source_name
        return preferences.get(source_name, source_name)
