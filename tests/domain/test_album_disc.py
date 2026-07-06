"""
Summary: Tests album-level disc inference.
Why: Protects multi-disc-only path rendering context.
"""

from __future__ import annotations

from omym2.domain.models.track_metadata import TrackMetadata
from omym2.domain.services.album_disc import infer_album_disc_totals

ALBUM = "Album"
ARTIST = "Artist"
FIRST_DISC_NUMBER = 1
SECOND_DISC_NUMBER = 2
TOTAL_DISC_COUNT = 2
UNKNOWN_ALBUM = "Unknown Album"
UNKNOWN_ARTIST = "Unknown Artist"
YEAR = 2026


def test_album_disc_totals_use_explicit_disc_totals() -> None:
    """Explicit disc_total values make every peer track in the album multi-disc."""
    first_disc = TrackMetadata(
        artist=ARTIST,
        album=ALBUM,
        year=YEAR,
        disc_number=FIRST_DISC_NUMBER,
        disc_total=TOTAL_DISC_COUNT,
    )
    second_disc = TrackMetadata(
        artist=ARTIST,
        album=ALBUM,
        year=YEAR,
        disc_number=SECOND_DISC_NUMBER,
        disc_total=TOTAL_DISC_COUNT,
    )

    totals = infer_album_disc_totals(
        (first_disc, second_disc),
        unknown_artist=UNKNOWN_ARTIST,
        unknown_album=UNKNOWN_ALBUM,
    )

    assert totals.for_metadata(first_disc) == TOTAL_DISC_COUNT
    assert totals.for_metadata(second_disc) == TOTAL_DISC_COUNT


def test_album_disc_totals_use_max_bare_disc_number() -> None:
    """Bare disc numbers infer a multi-disc album from the max positive value."""
    first_disc = TrackMetadata(artist=ARTIST, album=ALBUM, year=YEAR, disc_number=FIRST_DISC_NUMBER)
    second_disc = TrackMetadata(artist=ARTIST, album=ALBUM, year=YEAR, disc_number=SECOND_DISC_NUMBER)

    totals = infer_album_disc_totals(
        (first_disc, second_disc),
        unknown_artist=UNKNOWN_ARTIST,
        unknown_album=UNKNOWN_ALBUM,
    )

    assert totals.for_metadata(first_disc) == TOTAL_DISC_COUNT
    assert totals.for_metadata(second_disc) == TOTAL_DISC_COUNT


def test_album_disc_totals_ignore_missing_zero_and_negative_values() -> None:
    """Non-positive disc values do not make an album look multi-disc."""
    metadata = TrackMetadata(artist=ARTIST, album=ALBUM, year=YEAR, disc_number=0, disc_total=-1)

    totals = infer_album_disc_totals(
        (metadata,),
        unknown_artist=UNKNOWN_ARTIST,
        unknown_album=UNKNOWN_ALBUM,
    )

    assert totals.for_metadata(metadata) is None


def test_album_disc_totals_use_metadata_fallback_identity() -> None:
    """Album grouping falls back to artist, unknown album, and year."""
    first_disc = TrackMetadata(artist=ARTIST, year=YEAR, disc_number=FIRST_DISC_NUMBER)
    second_disc = TrackMetadata(artist=ARTIST, year=YEAR, disc_number=SECOND_DISC_NUMBER)

    totals = infer_album_disc_totals(
        (first_disc, second_disc),
        unknown_artist=UNKNOWN_ARTIST,
        unknown_album=UNKNOWN_ALBUM,
    )

    assert totals.for_metadata(first_disc) == TOTAL_DISC_COUNT
