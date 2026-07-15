"""
Summary: Tests eager and optional lazy fastText artist language predictors.
Why: Verifies raw observations and fail-soft runtime activation for naming.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import TYPE_CHECKING

import pytest

from omym2.adapters.artist_ids.fasttext_language_detector import (
    FastTextLanguageDetector,
    OptionalFastTextLanguageDetector,
)
from omym2.adapters.artist_ids.no_op_language_detector import NoOpLanguageDetector
from omym2.features.artist_names.dto import ArtistLanguagePrediction

if TYPE_CHECKING:
    from pathlib import Path


@dataclass(frozen=True, slots=True)
class _FakeModel:
    label: str
    confidence: float = 0.99

    def predict(self, text: str, k: int = 1) -> tuple[list[str], list[float]]:
        assert text
        assert k == 1
        return [self.label], [self.confidence]


@dataclass(slots=True)
class _RecordingPredictor:
    prediction: ArtistLanguagePrediction
    calls: list[str] = field(default_factory=list)

    def predict_language(self, text: str) -> ArtistLanguagePrediction:
        self.calls.append(text)
        return self.prediction


@dataclass(slots=True)
class _FailingPredictor:
    error: Exception
    calls: int = 0

    def predict_language(self, text: str) -> ArtistLanguagePrediction:
        assert text
        self.calls += 1
        raise self.error


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


def test_optional_fasttext_detector_loads_once_on_first_non_empty_prediction(tmp_path: Path) -> None:
    """The normal Plan runtime defers model work and reuses one loaded predictor."""
    model_path = tmp_path / "lid.176.ftz"
    prediction = ArtistLanguagePrediction(label="__label__ja", confidence=0.99, available=True)
    predictor = _RecordingPredictor(prediction)
    loaded_paths: list[Path] = []

    def load_detector(path: Path) -> _RecordingPredictor:
        loaded_paths.append(path)
        return predictor

    detector = OptionalFastTextLanguageDetector(model_path, detector_factory=load_detector)

    assert detector.predict_language("   ") == ArtistLanguagePrediction(None, None, available=False)
    assert loaded_paths == []
    assert detector.predict_language("米津玄師") == prediction
    assert detector.predict_language("宇多田ヒカル") == prediction
    assert loaded_paths == [model_path]
    assert predictor.calls == ["米津玄師", "宇多田ヒカル"]


@pytest.mark.parametrize(
    "load_error",
    [
        AttributeError("incompatible fasttext module"),
        ModuleNotFoundError("fasttext"),
        OSError("model unavailable"),
        RuntimeError("model rejected"),
        TypeError("incompatible load_model"),
        ValueError("invalid model"),
    ],
)
def test_optional_fasttext_detector_caches_load_failure_as_unavailable(
    tmp_path: Path,
    load_error: Exception,
) -> None:
    """A missing or broken optional runtime cannot block normal Plan creation."""
    load_attempts = 0

    def fail_to_load(_path: Path) -> _RecordingPredictor:
        nonlocal load_attempts
        load_attempts += 1
        raise load_error

    detector = OptionalFastTextLanguageDetector(tmp_path / "lid.176.ftz", detector_factory=fail_to_load)

    expected = ArtistLanguagePrediction(None, None, available=False)
    assert detector.predict_language("米津玄師") == expected
    assert detector.predict_language("米津玄師") == expected
    assert load_attempts == 1


@pytest.mark.parametrize(
    "prediction_error",
    [
        AttributeError("incompatible model"),
        ImportError("missing runtime component"),
        OSError("model read failed"),
        RuntimeError("prediction failed"),
        TypeError("incompatible predict"),
        ValueError("invalid prediction input"),
    ],
)
def test_optional_fasttext_detector_caches_prediction_failure_as_unavailable(
    tmp_path: Path,
    prediction_error: Exception,
) -> None:
    """An incompatible optional model cannot fail every later Plan candidate."""
    predictor = _FailingPredictor(prediction_error)
    detector = OptionalFastTextLanguageDetector(
        tmp_path / "lid.176.ftz",
        detector_factory=lambda _path: predictor,
    )

    expected = ArtistLanguagePrediction(None, None, available=False)
    assert detector.predict_language("米津玄師") == expected
    assert detector.predict_language("宇多田ヒカル") == expected
    assert predictor.calls == 1


def test_no_op_language_detector_reports_model_unavailable() -> None:
    """The no-op predictor distinguishes model absence from a non-Japanese label."""

    assert NoOpLanguageDetector().predict_language("米津玄師") == ArtistLanguagePrediction(
        label=None,
        confidence=None,
        available=False,
    )
