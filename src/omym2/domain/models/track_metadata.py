"""
Summary: Defines music tag metadata used by domain policy.
Why: Separates track metadata from filesystem and adapter details.
"""

from __future__ import annotations

from dataclasses import dataclass

type MetadataFingerprintPayload = dict[str, int | str | None]


@dataclass(frozen=True, slots=True)
class TrackMetadata:
    """Metadata read from a music file tag."""

    title: str | None = None
    artist: str | None = None
    album: str | None = None
    album_artist: str | None = None
    genre: str | None = None
    year: int | None = None
    track_number: int | None = None
    track_total: int | None = None
    disc_number: int | None = None
    disc_total: int | None = None

    def fingerprint_payload(self) -> MetadataFingerprintPayload:
        """Return a stable primitive representation for metadata hashing."""
        return {
            "album": self.album,
            "album_artist": self.album_artist,
            "artist": self.artist,
            "disc_number": self.disc_number,
            "disc_total": self.disc_total,
            "genre": self.genre,
            "title": self.title,
            "track_number": self.track_number,
            "track_total": self.track_total,
            "year": self.year,
        }
