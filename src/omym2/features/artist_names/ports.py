"""
Summary: Defines external collaborators required by artist-name resolution.
Why: Keeps language-model and provider I/O behind feature-owned contracts.
"""

from __future__ import annotations

from dataclasses import dataclass
from math import isfinite
from typing import TYPE_CHECKING, Protocol

from omym2.config import ARTIST_NAME_LANGUAGE_CONFIDENCE_MIN

INVALID_MINIMUM_CONFIDENCE_MESSAGE = "Artist-name minimum confidence must be finite and between 0 and 1."

if TYPE_CHECKING:
    from omym2.features.artist_names.dto import ArtistLanguagePrediction, ArtistNameSearchResult
    from omym2.features.common_ports import Clock, UnitOfWork


class ArtistLanguagePredictor(Protocol):
    """Return top language observations without deciding naming eligibility."""

    def predict_language(self, text: str) -> ArtistLanguagePrediction:
        """Return the detector's top label, confidence, and availability."""
        ...


class ArtistNameProvider(Protocol):
    """Search an external artist catalog without accepting a match."""

    def search_artists(self, source_name: str) -> ArtistNameSearchResult:
        """Return raw scored candidates or an unavailable observation."""
        ...


@dataclass(frozen=True, slots=True)
class ResolveArtistNamesPorts:
    """Collaborators used by the shared artist-name resolution usecase."""

    uow: UnitOfWork
    language_predictor: ArtistLanguagePredictor
    artist_name_provider: ArtistNameProvider
    clock: Clock
    automatic_lookup_enabled: bool = True
    minimum_confidence: float = ARTIST_NAME_LANGUAGE_CONFIDENCE_MIN

    def __post_init__(self) -> None:
        """Validate the confidence policy supplied by the composition root."""
        if not isfinite(self.minimum_confidence) or not 0.0 <= self.minimum_confidence <= 1.0:
            raise ValueError(INVALID_MINIMUM_CONFIDENCE_MESSAGE)
