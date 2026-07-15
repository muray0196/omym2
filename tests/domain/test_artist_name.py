"""
Summary: Tests artist display projection and provider-cache key derivation.
Why: Keeps naming deterministic without changing or sanitizing raw metadata.
"""

from __future__ import annotations

from omym2.domain.models.track_metadata import TrackMetadata
from omym2.domain.services.artist_name import (
    ArtistNameProjection,
    ArtistNameProjector,
    derive_artist_name_source_key,
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


def test_artist_name_projector_is_identity_without_preferences() -> None:
    """The default empty preference set preserves current naming behavior."""
    metadata = TrackMetadata(artist=ARTIST, album_artist=ALBUM_ARTIST)

    assert ArtistNameProjector().project(metadata) == ArtistNameProjection(
        artist=ARTIST,
        album_artist=ALBUM_ARTIST,
    )


def test_artist_name_projector_applies_exact_preferences_independently() -> None:
    """Artist and album-artist source strings are independent exact keys."""
    metadata = TrackMetadata(artist=ARTIST, album_artist=ALBUM_ARTIST)

    projection = ArtistNameProjector({ARTIST: DISPLAY_ARTIST}).project(metadata)

    assert projection == ArtistNameProjection(artist=DISPLAY_ARTIST, album_artist=ALBUM_ARTIST)
    assert metadata == TrackMetadata(artist=ARTIST, album_artist=ALBUM_ARTIST)


def test_artist_name_projector_treats_multi_artist_text_as_one_opaque_key() -> None:
    """A full composite preference replaces the composite without splitting it."""
    display_album_artist = "Hikaru Utada, Sheena Ringo"
    metadata = TrackMetadata(artist=ARTIST, album_artist=ALBUM_ARTIST)

    projection = ArtistNameProjector({ALBUM_ARTIST: display_album_artist}).project(metadata)

    assert projection == ArtistNameProjection(artist=ARTIST, album_artist=display_album_artist)


def test_artist_name_projector_freezes_its_preference_snapshot() -> None:
    """Later caller mutation cannot change an in-progress naming projection."""
    preferences = {ARTIST: DISPLAY_ARTIST}
    projector = ArtistNameProjector(preferences)
    preferences[ARTIST] = "Changed"

    assert projector.project(TrackMetadata(artist=ARTIST)).artist == DISPLAY_ARTIST
