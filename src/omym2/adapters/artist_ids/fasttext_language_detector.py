"""
Summary: Implements fastText-backed language detection.
Why: Lets artist ID generation decide when Japanese MusicBrainz lookup applies.
"""

from __future__ import annotations

import importlib
from dataclasses import dataclass
from pathlib import Path
from typing import TYPE_CHECKING, Protocol, cast

if TYPE_CHECKING:
    from collections.abc import Sequence

FASTTEXT_LABEL_PREFIX = "__label__"
FASTTEXT_MISSING_MESSAGE = "fastText is not installed."
FASTTEXT_MODEL_LOAD_MESSAGE = "fastText model load failed:"
FASTTEXT_MODEL_MISSING_MESSAGE = "fastText model file was not found."
FASTTEXT_TOP_K = 1


class _FastTextModel(Protocol):
    """Small fastText model surface used by this adapter."""

    def predict(self, text: str, *, k: int) -> tuple[Sequence[str], Sequence[float]]:
        """Return predicted labels and probabilities."""
        ...


class _FastTextModule(Protocol):
    """Small fastText module surface used by this adapter."""

    def load_model(self, model_path: str) -> _FastTextModel:
        """Load a fastText language model."""
        ...


class FastTextLanguageDetectorError(RuntimeError):
    """Raised when fastText detection cannot be initialized or executed."""


@dataclass(frozen=True, slots=True)
class FastTextLanguageDetector:
    """Detect artist language with a local fastText model file."""

    model_path: str

    def detect_language(self, text: str) -> str | None:
        """Return a fastText language code for non-empty text."""
        if text.strip() == "":
            return None

        model = _load_model(self.model_path)
        labels, _probabilities = model.predict(text, k=FASTTEXT_TOP_K)
        if len(labels) == 0:
            return None
        return str(labels[0]).removeprefix(FASTTEXT_LABEL_PREFIX)


def _load_model(model_path: str) -> _FastTextModel:
    if not Path(model_path).is_file():
        raise FastTextLanguageDetectorError(FASTTEXT_MODEL_MISSING_MESSAGE)

    try:
        fasttext_module = cast("_FastTextModule", cast("object", importlib.import_module("fasttext")))
    except ImportError as exc:
        raise FastTextLanguageDetectorError(FASTTEXT_MISSING_MESSAGE) from exc

    try:
        return fasttext_module.load_model(model_path)
    except Exception as exc:
        message = f"{FASTTEXT_MODEL_LOAD_MESSAGE} {exc}"
        raise FastTextLanguageDetectorError(message) from exc
