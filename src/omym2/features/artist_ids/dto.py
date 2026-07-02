"""
Summary: Defines artist ID feature request and response data.
Why: Gives adapters stable contracts for generation and editing flows.
"""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True, slots=True)
class GenerateArtistIdsRequest:
    """Request to generate and save missing artist ID entries."""

    artist_names: tuple[str, ...]
    overwrite: bool = False


@dataclass(frozen=True, slots=True)
class ArtistIdEntryResult:
    """Generated or preserved artist ID entry outcome."""

    source_artist: str
    generation_artist: str
    artist_id: str
    saved: bool
    overwritten: bool


@dataclass(frozen=True, slots=True)
class GenerateArtistIdsResult:
    """Result of artist ID generation."""

    entries: tuple[ArtistIdEntryResult, ...]
