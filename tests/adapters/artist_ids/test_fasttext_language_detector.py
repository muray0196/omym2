"""
Summary: Tests the fastText artist language predictor adapter.
Why: Verifies raw model observations remain available to naming usecases.
"""

from __future__ import annotations

from dataclasses import dataclass

from omym2.adapters.artist_ids.fasttext_language_detector import FastTextLanguageDetector
from omym2.adapters.artist_ids.no_op_language_detector import NoOpLanguageDetector
from omym2.features.artist_names.dto import ArtistLanguagePrediction


@dataclass(frozen=True, slots=True)
class _FakeModel:
    label: str
    confidence: float = 0.99

    def predict(self, text: str, k: int = 1) -> tuple[list[str], list[float]]:
        assert text
        assert k == 1
        return [self.label], [self.confidence]


def test_fasttext_language_detector_returns_raw_top_prediction() -> None:
    """The adapter preserves the top label and confidence for feature policy."""
    detector = FastTextLanguageDetector(model=_FakeModel("__label__ja"))

    assert detector.predict_language("米津玄師") == ArtistLanguagePrediction(
        label="__label__ja",
        confidence=0.99,
        available=True,
    )


def test_fasttext_language_detector_does_not_decide_label_eligibility() -> None:
    """A non-Japanese label remains an available raw observation."""
    detector = FastTextLanguageDetector(model=_FakeModel("__label__en", confidence=0.75))

    assert detector.predict_language("Aimer") == ArtistLanguagePrediction(
        label="__label__en",
        confidence=0.75,
        available=True,
    )


def test_fasttext_language_detector_reports_invalid_prediction_unavailable() -> None:
    """Out-of-range model confidence cannot cross the adapter schema boundary."""
    detector = FastTextLanguageDetector(model=_FakeModel("__label__ja", confidence=1.1))

    assert detector.predict_language("米津玄師") == ArtistLanguagePrediction(
        label=None,
        confidence=None,
        available=False,
    )


def test_no_op_language_detector_reports_model_unavailable() -> None:
    """The no-op predictor distinguishes model absence from a non-Japanese label."""

    assert NoOpLanguageDetector().predict_language("米津玄師") == ArtistLanguagePrediction(
        label=None,
        confidence=None,
        available=False,
    )
