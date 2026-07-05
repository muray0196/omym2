"""
Summary: Resolves effective album years from track metadata batches.
Why: Keeps album-group year policy pure and outside PathPolicy rendering.
"""

from __future__ import annotations

from collections import Counter
from dataclasses import dataclass, replace
from typing import TYPE_CHECKING

from omym2.config import (
    ALBUM_YEAR_RESOLUTION_LATEST,
    ALBUM_YEAR_RESOLUTION_MOST_FREQUENT,
    ALBUM_YEAR_RESOLUTION_OLDEST,
)

if TYPE_CHECKING:
    from collections.abc import Iterable, Mapping

    from omym2.domain.models.app_config import PathPolicyConfig
    from omym2.domain.models.track_metadata import TrackMetadata

UNSUPPORTED_ALBUM_YEAR_RESOLUTION_MESSAGE = "Unsupported album-year resolution method."


@dataclass(frozen=True, slots=True)
class AlbumYearGroup:
    """Deterministic grouping key for album-level year resolution."""

    album: str
    album_artist: str


def album_year_group(metadata: TrackMetadata, config: PathPolicyConfig) -> AlbumYearGroup:
    """Return the album group used for resolving an effective `{year}` value."""
    # Mirror PathPolicy's album/album_artist fallback behavior so group-level
    # year calculation matches the same path components that can contain year.
    return AlbumYearGroup(
        album=metadata.album or config.unknown_album,
        album_artist=metadata.album_artist or metadata.artist or config.unknown_artist,
    )


def resolve_album_years(
    metadata_items: Iterable[TrackMetadata],
    config: PathPolicyConfig,
    method: str,
) -> dict[AlbumYearGroup, int | None]:
    """Return the effective year for every album group in a metadata batch."""
    years_by_group: dict[AlbumYearGroup, list[int]] = {}
    for metadata in metadata_items:
        group = album_year_group(metadata, config)
        group_years = years_by_group.setdefault(group, [])
        if metadata.year is not None:
            group_years.append(metadata.year)

    return {group: _resolve_year(years, method) for group, years in years_by_group.items()}


def metadata_with_resolved_album_year(
    metadata: TrackMetadata,
    config: PathPolicyConfig,
    resolved_years: Mapping[AlbumYearGroup, int | None],
) -> TrackMetadata:
    """Return a copy whose year is the resolved album-group year."""
    group = album_year_group(metadata, config)
    if group not in resolved_years:
        return metadata
    return replace(metadata, year=resolved_years[group])


def _resolve_year(years: list[int], method: str) -> int | None:
    if len(years) == 0:
        return None
    if method == ALBUM_YEAR_RESOLUTION_LATEST:
        return max(years)
    if method == ALBUM_YEAR_RESOLUTION_OLDEST:
        return min(years)
    if method == ALBUM_YEAR_RESOLUTION_MOST_FREQUENT:
        year_counts = Counter(years)
        # When counts tie, choose the latest tied year for deterministic output.
        return max(year_counts, key=lambda year: (year_counts[year], year))
    raise ValueError(UNSUPPORTED_ALBUM_YEAR_RESOLUTION_MESSAGE)
