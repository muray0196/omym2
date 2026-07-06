"""
Summary: Tests album-year resolution policy.
Why: Protects batch path planning when album track years differ.
"""

from __future__ import annotations

from omym2.config import (
    ALBUM_YEAR_RESOLUTION_LATEST,
    ALBUM_YEAR_RESOLUTION_MOST_FREQUENT,
    ALBUM_YEAR_RESOLUTION_OLDEST,
)
from omym2.domain.models.app_config import PathPolicyConfig
from omym2.domain.models.track_metadata import TrackMetadata
from omym2.domain.services.album_year import metadata_with_resolved_album_year, resolve_album_years

ALBUM = "Album"
ARTIST = "Artist"
OTHER_ALBUM = "Other Album"
OTHER_ARTIST = "Other Artist"
YEAR_1998 = 1998
YEAR_2002 = 2002
YEAR_2004 = 2004
YEAR_2020 = 2020
YEAR_2026 = 2026


def test_album_year_resolution_defaults_to_latest_year() -> None:
    """Latest uses the newest usable year in an album group."""
    metadata = (_metadata(YEAR_1998), _metadata(YEAR_2002), _metadata(YEAR_2004))

    resolved = _resolved_year(_metadata(YEAR_2002), metadata, ALBUM_YEAR_RESOLUTION_LATEST)

    assert resolved == YEAR_2004


def test_album_year_resolution_can_choose_oldest_year() -> None:
    """Oldest uses the oldest usable year in an album group."""
    metadata = (_metadata(YEAR_1998), _metadata(YEAR_2002), _metadata(YEAR_2004))

    resolved = _resolved_year(_metadata(YEAR_2002), metadata, ALBUM_YEAR_RESOLUTION_OLDEST)

    assert resolved == YEAR_1998


def test_album_year_resolution_most_frequent_uses_latest_tied_year() -> None:
    """Most frequent chooses the modal year and breaks ties by latest year."""
    metadata = (_metadata(YEAR_1998), _metadata(YEAR_1998), _metadata(YEAR_2004), _metadata(YEAR_2004))

    resolved = _resolved_year(_metadata(YEAR_1998), metadata, ALBUM_YEAR_RESOLUTION_MOST_FREQUENT)

    assert resolved == YEAR_2004


def test_album_year_resolution_ignores_missing_years() -> None:
    """Missing years do not override a usable album-group year."""
    metadata = (_metadata(None), _metadata(YEAR_2002), _metadata(None))

    resolved = _resolved_year(_metadata(None), metadata, ALBUM_YEAR_RESOLUTION_LATEST)

    assert resolved == YEAR_2002


def test_album_year_resolution_keeps_all_missing_group_empty() -> None:
    """An all-missing group resolves to None for existing empty `{year}` output."""
    metadata = (_metadata(None), _metadata(None))

    resolved = _resolved_year(_metadata(None), metadata, ALBUM_YEAR_RESOLUTION_LATEST)

    assert resolved is None


def test_album_year_resolution_groups_by_album_and_album_artist_signal() -> None:
    """Different album groups do not influence each other's resolved year."""
    metadata = (
        _metadata(YEAR_1998),
        _metadata(YEAR_2004),
        _metadata(YEAR_2020, album=OTHER_ALBUM),
        _metadata(YEAR_2026, artist=OTHER_ARTIST, album_artist=None),
    )

    same_group_year = _resolved_year(_metadata(1998), metadata, ALBUM_YEAR_RESOLUTION_LATEST)
    other_album_year = _resolved_year(_metadata(None, album=OTHER_ALBUM), metadata, ALBUM_YEAR_RESOLUTION_LATEST)
    other_artist_year = _resolved_year(
        _metadata(None, artist=OTHER_ARTIST, album_artist=None),
        metadata,
        ALBUM_YEAR_RESOLUTION_LATEST,
    )

    assert same_group_year == YEAR_2004
    assert other_album_year == YEAR_2020
    assert other_artist_year == YEAR_2026


def test_album_year_group_uses_album_artist_before_artist_like_path_policy() -> None:
    """Album artist and artist fallback match PathPolicy grouping behavior."""
    metadata = (
        _metadata(YEAR_1998, album_artist=ARTIST),
        _metadata(YEAR_2004, artist=ARTIST, album_artist=None),
    )

    resolved = _resolved_year(_metadata(YEAR_1998, album_artist=ARTIST), metadata, ALBUM_YEAR_RESOLUTION_LATEST)

    assert resolved == YEAR_2004


def _resolved_year(
    target: TrackMetadata,
    metadata: tuple[TrackMetadata, ...],
    method: str,
) -> int | None:
    config = PathPolicyConfig()
    resolved_years = resolve_album_years(metadata, config, method)
    return metadata_with_resolved_album_year(target, config, resolved_years).year


def _metadata(
    year: int | None,
    *,
    album: str = ALBUM,
    artist: str = ARTIST,
    album_artist: str | None = ARTIST,
) -> TrackMetadata:
    return TrackMetadata(
        title="Song",
        artist=artist,
        album=album,
        album_artist=album_artist,
        year=year,
        track_number=1,
        disc_number=1,
    )
