"""
Summary: Implements an unavailable artist language predictor.
Why: Lets local naming continue without loading an optional fastText model.
"""

from __future__ import annotations

from dataclasses import dataclass

from omym2.features.artist_names.dto import ArtistLanguagePrediction


@dataclass(frozen=True, slots=True)
class NoOpLanguageDetector:
    """Language predictor that explicitly reports model unavailability."""

    def predict_language(self, text: str) -> ArtistLanguagePrediction:
        """Return an unavailable observation without inspecting text."""
        _ = text
        return ArtistLanguagePrediction(label=None, confidence=None, available=False)
