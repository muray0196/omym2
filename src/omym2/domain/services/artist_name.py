"""
Summary: Projects artist metadata and derives stable provider-cache keys.
Why: Keeps path names and lookup identity derived without changing source tags.
"""

from __future__ import annotations

import unicodedata
from dataclasses import dataclass
from itertools import batched
from typing import TYPE_CHECKING

from omym2.domain.models.artist_name_resolution import (
    ArtistNameDiagnostics,
    ArtistNameResolution,
    ArtistNameResolutionDiagnostic,
)

if TYPE_CHECKING:
    from collections.abc import Sequence

    from omym2.domain.models.track_metadata import TrackMetadata

_ARTIST_NAME_SOURCE_KEY_NORMALIZATION_FORM = "NFC"
ARTIST_NAME_RESOLUTION_CARDINALITY_MESSAGE = "Resolved artist names must align with artist and album-artist sources."
ARTIST_NAME_FIELD_COUNT = 2  # artist and album-artist values per TrackMetadata


def derive_artist_name_source_key(source_name: str | None) -> str | None:
    """Return one normalized whole-string key, or no key for missing text."""
    if source_name is None:
        return None
    normalized = unicodedata.normalize(_ARTIST_NAME_SOURCE_KEY_NORMALIZATION_FORM, source_name)
    source_key = " ".join(normalized.split())
    return source_key or None


def is_usable_english_artist_name(name: str) -> bool:
    """Return whether text contains only Latin-script alphabetic characters."""
    alphabetic = tuple(character for character in name if character.isalpha())
    return bool(alphabetic) and all("LATIN" in unicodedata.name(character, "") for character in alphabetic)


def contains_non_latin_artist_name_letters(name: str) -> bool:
    """Return whether a source name contains an alphabetic character outside Latin script."""
    return any("LATIN" not in unicodedata.name(character, "") for character in name if character.isalpha())


@dataclass(frozen=True, slots=True)
class ArtistNameProjection:
    """Artist fields after shared mapping resolution."""

    artist: str | None
    album_artist: str | None


def artist_name_sources(metadata_batch: Sequence[TrackMetadata]) -> tuple[str | None, ...]:
    """Flatten artist and album-artist values in metadata order."""
    return tuple(source for metadata in metadata_batch for source in (metadata.artist, metadata.album_artist))


def artist_name_projections(
    metadata_batch: Sequence[TrackMetadata],
    resolved_names: Sequence[str | None],
) -> tuple[ArtistNameProjection, ...]:
    """Restore aligned resolver output into one projection per metadata value."""
    if len(resolved_names) != len(metadata_batch) * ARTIST_NAME_FIELD_COUNT:
        raise ValueError(ARTIST_NAME_RESOLUTION_CARDINALITY_MESSAGE)
    return tuple(
        ArtistNameProjection(artist=artist, album_artist=album_artist)
        for artist, album_artist in batched(resolved_names, ARTIST_NAME_FIELD_COUNT, strict=True)
    )


def artist_name_diagnostics(
    metadata_batch: Sequence[TrackMetadata],
    resolutions: Sequence[ArtistNameResolution],
) -> tuple[ArtistNameDiagnostics, ...]:
    """Pair aligned resolver outcomes into durable artist-field diagnostics."""
    if len(resolutions) != len(metadata_batch) * ARTIST_NAME_FIELD_COUNT:
        raise ValueError(ARTIST_NAME_RESOLUTION_CARDINALITY_MESSAGE)
    return tuple(
        ArtistNameDiagnostics(
            artist=ArtistNameResolutionDiagnostic.from_resolution(artist),
            album_artist=ArtistNameResolutionDiagnostic.from_resolution(album_artist),
        )
        for artist, album_artist in batched(resolutions, ARTIST_NAME_FIELD_COUNT, strict=True)
    )
