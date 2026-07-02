"""
Summary: Defines artist ID generation request and result data.
Why: Gives adapters a stable contract for editable artist ID workflows.
"""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True, slots=True)
class ArtistIdGenerationRequest:
    """Request to generate and save missing artist IDs."""

    artist_names: tuple[str, ...]
    overwrite_existing: bool = False


@dataclass(frozen=True, slots=True)
class ArtistIdGenerationEntry:
    """One artist ID generation outcome."""

    source_artist: str
    artist_id: str
    generated_from: str
    language: str | None
    saved: bool
    preserved_existing: bool


@dataclass(frozen=True, slots=True)
class ArtistIdGenerationResult:
    """Result of generating artist ID config entries."""

    entries: tuple[ArtistIdGenerationEntry, ...]
