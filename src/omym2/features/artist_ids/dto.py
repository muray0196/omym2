"""
Summary: Defines artist ID feature request and response data.
Why: Gives adapters stable contracts for generation and editing flows.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from omym2.domain.models.app_config import ArtistIdConfig


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


@dataclass(frozen=True, slots=True)
class GenerateArtistIdDraftRequest:
    """Request to generate artist IDs against the current form draft only."""

    artist_names: tuple[str, ...]
    overwrite: bool
    artist_ids: ArtistIdConfig


@dataclass(frozen=True, slots=True)
class ArtistIdDraftEntryResult:
    """One generated or preserved draft entry without persistence state."""

    source_artist: str
    generation_artist: str
    artist_id: str
    overwritten: bool


@dataclass(frozen=True, slots=True)
class GenerateArtistIdDraftResult:
    """Draft entries returned for a client-side merge."""

    entries: tuple[ArtistIdDraftEntryResult, ...]
