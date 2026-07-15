"""
Summary: Adapts eager and optional lazy fastText predictions to naming contracts.
Why: Keeps model loading, failure fallback, and parsing outside naming usecases.
"""

from __future__ import annotations

import importlib
from dataclasses import dataclass, field
from math import isfinite
from typing import TYPE_CHECKING, Protocol, cast

from omym2.features.artist_names.dto import ArtistLanguagePrediction

if TYPE_CHECKING:
    from collections.abc import Callable, Sequence
    from pathlib import Path

    from omym2.features.artist_names.ports import ArtistLanguagePredictor

FASTTEXT_MODEL_PATH_REQUIRED_MESSAGE = "fastText model_path is required when model is not injected."


class _FastTextModel(Protocol):
    """Minimum fastText model surface used by the adapter."""

    def predict(self, text: str, k: int = 1) -> tuple[Sequence[str], Sequence[float]]:
        """Return predicted labels and confidence scores."""
        ...


@dataclass(frozen=True, slots=True)
class FastTextLanguageDetector:
    """Expose the top fastText language prediction without deciding eligibility."""

    model_path: Path | None = None
    model: _FastTextModel | None = None

    def __post_init__(self) -> None:
        """Load the model during construction when tests did not inject one."""
        if self.model is not None:
            return
        if self.model_path is None:
            raise ValueError(FASTTEXT_MODEL_PATH_REQUIRED_MESSAGE)
        fasttext_module = importlib.import_module("fasttext")
        load_model = cast("Callable[[str], object]", fasttext_module.load_model)
        object.__setattr__(self, "model", cast("_FastTextModel", load_model(str(self.model_path))))

    def predict_language(self, text: str) -> ArtistLanguagePrediction:
        """Return one parsed label and confidence, or an unavailable observation."""
        normalized_text = text.strip()
        if normalized_text == "":
            return _unavailable_prediction()
        model = self.model
        if model is None:
            return _unavailable_prediction()
        try:
            labels, scores = model.predict(normalized_text, k=1)
        except RuntimeError, ValueError:
            return _unavailable_prediction()
        return _prediction_from(labels, scores)


def _fasttext_detector_for(model_path: Path) -> ArtistLanguagePredictor:
    return FastTextLanguageDetector(model_path=model_path)


@dataclass(slots=True)
class OptionalFastTextLanguageDetector:
    """Load fastText on first prediction and degrade unavailable runtimes locally."""

    model_path: Path
    detector_factory: Callable[[Path], ArtistLanguagePredictor] = _fasttext_detector_for
    _detector: ArtistLanguagePredictor | None = field(default=None, init=False)
    _load_attempted: bool = field(default=False, init=False)

    def predict_language(self, text: str) -> ArtistLanguagePrediction:
        """Return one prediction, or unavailable when optional model work cannot run."""
        if text.strip() == "":
            return _unavailable_prediction()
        detector = self._load_detector()
        if detector is None:
            return _unavailable_prediction()
        try:
            return detector.predict_language(text)
        except AttributeError, ImportError, OSError, RuntimeError, TypeError, ValueError:
            self._detector = None
            return _unavailable_prediction()

    def _load_detector(self) -> ArtistLanguagePredictor | None:
        if self._load_attempted:
            return self._detector
        self._load_attempted = True
        try:
            self._detector = self.detector_factory(self.model_path)
        except AttributeError, ImportError, OSError, RuntimeError, TypeError, ValueError:
            self._detector = None
        return self._detector


def _prediction_from(labels: Sequence[object], scores: Sequence[float]) -> ArtistLanguagePrediction:
    if len(labels) < 1 or len(scores) < 1:
        return _unavailable_prediction()
    label = labels[0]
    raw_confidence = scores[0]
    if not isinstance(label, str) or label.strip() == "" or isinstance(raw_confidence, bool):
        return _unavailable_prediction()
    try:
        confidence = float(raw_confidence)
    except TypeError, ValueError, OverflowError:
        return _unavailable_prediction()
    if not isfinite(confidence) or not 0.0 <= confidence <= 1.0:
        return _unavailable_prediction()
    return ArtistLanguagePrediction(label=label, confidence=confidence, available=True)


def _unavailable_prediction() -> ArtistLanguagePrediction:
    return ArtistLanguagePrediction(label=None, confidence=None, available=False)
