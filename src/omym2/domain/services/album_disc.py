"""
Summary: Infers album-level disc totals from loaded metadata.
Why: Lets path rendering suppress single-disc numbers without I/O.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from types import MappingProxyType
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from collections.abc import Iterable, Mapping

    from omym2.domain.models.track_metadata import TrackMetadata

type AlbumDiscIdentity = tuple[str, str, int | None]


def _empty_totals() -> dict[AlbumDiscIdentity, int]:
    return {}


@dataclass(frozen=True, slots=True)
class AlbumDiscTotals:
    """Album-disc totals keyed by stable metadata identity."""

    totals: Mapping[AlbumDiscIdentity, int] = field(default_factory=_empty_totals)
    unknown_artist: str = ""
    unknown_album: str = ""

    def __post_init__(self) -> None:
        """Freeze inferred totals so plan-time context cannot drift."""
        object.__setattr__(self, "totals", MappingProxyType(dict(self.totals)))

    def for_metadata(self, metadata: TrackMetadata) -> int | None:
        """Return the inferred disc total for a track's album identity."""
        return self.totals.get(_album_identity(metadata, self.unknown_artist, self.unknown_album))


def infer_album_disc_totals(
    metadatas: Iterable[TrackMetadata],
    *,
    unknown_artist: str,
    unknown_album: str,
) -> AlbumDiscTotals:
    """Infer album disc totals from already-loaded track metadata."""
    totals: dict[AlbumDiscIdentity, int] = {}
    for metadata in metadatas:
        positive_disc_values = tuple(_positive_disc_values(metadata))
        if len(positive_disc_values) == 0:
            continue
        identity = _album_identity(metadata, unknown_artist, unknown_album)
        totals[identity] = max(totals.get(identity, 0), *positive_disc_values)
    return AlbumDiscTotals(totals=totals, unknown_artist=unknown_artist, unknown_album=unknown_album)


def _album_identity(metadata: TrackMetadata, unknown_artist: str, unknown_album: str) -> AlbumDiscIdentity:
    artist = _metadata_text(metadata.album_artist) or _metadata_text(metadata.artist) or unknown_artist
    album = _metadata_text(metadata.album) or unknown_album
    return (artist, album, metadata.year)


def _metadata_text(value: str | None) -> str | None:
    if value is None or value.strip() == "":
        return None
    return value


def _positive_disc_values(metadata: TrackMetadata) -> Iterable[int]:
    for value in (metadata.disc_total, metadata.disc_number):
        if value is not None and value > 0:
            yield value
