"""
Summary: Tests artist-name keys, English-name validation, and diagnostics.
Why: Keeps naming deterministic without changing or sanitizing raw metadata.
"""

from __future__ import annotations

import pytest

from omym2.domain.models.artist_name_resolution import (
    ArtistNameDiagnostics,
    ArtistNameResolution,
    ArtistNameResolutionDiagnostic,
    ArtistNameResolutionIssue,
    ArtistNameResolutionProvenance,
)
from omym2.domain.models.track_metadata import TrackMetadata
from omym2.domain.services.artist_name import (
    ARTIST_NAME_RESOLUTION_CARDINALITY_MESSAGE,
    artist_name_diagnostics,
    contains_non_latin_artist_name_letters,
    derive_artist_name_source_key,
    is_usable_english_artist_name,
)

ALBUM_ARTIST = "宇多田ヒカル, 椎名林檎"
ARTIST = "宇多田ヒカル"
DISPLAY_ARTIST = "Hikaru Utada"


def test_artist_name_source_key_normalizes_unicode_and_whitespace() -> None:
    """Canonically equivalent text and Unicode whitespace share one cache key."""
    source_name = "\tCafe\u0301\u00a0\u3000  Duo\n"
    expected_key = "Café Duo"

    assert derive_artist_name_source_key(source_name) == expected_key
    assert derive_artist_name_source_key(expected_key) == expected_key


def test_artist_name_source_key_preserves_opaque_source_text() -> None:
    """Key derivation does not case-fold, sanitize, or split composite names."""
    source_name = "\uff21rtist's / duo, Guest"

    assert derive_artist_name_source_key(source_name) == source_name


def test_artist_name_source_key_omits_missing_or_blank_text() -> None:
    """Absent metadata cannot produce a cache lookup or persisted key."""
    assert derive_artist_name_source_key(None) is None
    assert derive_artist_name_source_key("") is None
    assert derive_artist_name_source_key("\t \n") is None


@pytest.mark.parametrize("name", ["Hikaru Utada", "Beyoncé", "175R", "AC/DC"])
def test_usable_english_artist_name_accepts_latin_text(name: str) -> None:
    """English mappings may contain punctuation, numbers, and accented Latin letters."""
    assert is_usable_english_artist_name(name)


@pytest.mark.parametrize("name", ["宇多田ヒカル", "Aimer 宇多田", "!!!"])
def test_usable_english_artist_name_rejects_non_latin_or_missing_letters(name: str) -> None:
    """English mappings need at least one letter and cannot mix non-Latin letters."""
    assert not is_usable_english_artist_name(name)


@pytest.mark.parametrize("name", ["宇多田ヒカル", "아이유", "Молчат Дома", "Aimer 宇多田"])
def test_non_latin_artist_name_letters_detect_provider_eligible_sources(name: str) -> None:
    """Any alphabetic script outside Latin makes a source eligible for romanization."""
    assert contains_non_latin_artist_name_letters(name)


@pytest.mark.parametrize("name", ["IOSYS", "Beyoncé", "Mötley Crüe", "175R", "!!!"])
def test_non_latin_artist_name_letters_preserve_latin_or_non_alphabetic_sources(name: str) -> None:
    """Latin letters, modifiers, digits, and punctuation do not need romanization."""
    assert not contains_non_latin_artist_name_letters(name)


def test_artist_name_diagnostics_pair_flat_results_by_metadata_field() -> None:
    """Resolver results retain artist and album-artist roles in durable review data."""
    metadata = TrackMetadata(artist=ARTIST, album_artist=ALBUM_ARTIST)
    artist_resolution = ArtistNameResolution(
        source_name=ARTIST,
        source_key=ARTIST,
        resolved_name=DISPLAY_ARTIST,
        provenance=ArtistNameResolutionProvenance.ACCEPTED_MUSICBRAINZ,
    )
    album_artist_resolution = ArtistNameResolution(
        source_name=ALBUM_ARTIST,
        source_key=ALBUM_ARTIST,
        resolved_name=ALBUM_ARTIST,
        provenance=ArtistNameResolutionProvenance.ORIGINAL,
        issue=ArtistNameResolutionIssue.AMBIGUOUS_MATCH,
    )

    diagnostics = artist_name_diagnostics((metadata,), (artist_resolution, album_artist_resolution))

    assert diagnostics == (
        ArtistNameDiagnostics(
            artist=ArtistNameResolutionDiagnostic.from_resolution(artist_resolution),
            album_artist=ArtistNameResolutionDiagnostic.from_resolution(album_artist_resolution),
        ),
    )


def test_artist_name_diagnostics_reject_misaligned_results() -> None:
    """Every metadata value requires one artist and one album-artist result."""
    metadata = TrackMetadata(artist=ARTIST, album_artist=ALBUM_ARTIST)
    resolution = ArtistNameResolution(
        source_name=ARTIST,
        source_key=ARTIST,
        resolved_name=DISPLAY_ARTIST,
        provenance=ArtistNameResolutionProvenance.ACCEPTED_MUSICBRAINZ,
    )

    with pytest.raises(ValueError, match=ARTIST_NAME_RESOLUTION_CARDINALITY_MESSAGE):
        _ = artist_name_diagnostics((metadata,), (resolution,))
