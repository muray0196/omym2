"""
Summary: Implements Japanese detection with fastText.
Why: Keeps optional model loading behind the artist ID feature port.
"""

from __future__ import annotations

import importlib
from dataclasses import dataclass
from typing import TYPE_CHECKING, Protocol, cast

from omym2.config import FASTTEXT_JAPANESE_LABEL

if TYPE_CHECKING:
    from collections.abc import Callable
    from pathlib import Path

FASTTEXT_MODEL_PATH_REQUIRED_MESSAGE = "fastText model_path is required when model is not injected."


class _FastTextModel(Protocol):
    """Minimum fastText model surface used by the adapter."""

    def predict(self, text: str, k: int = 1) -> tuple[list[str], list[float]]:
        """Return predicted labels and confidence scores."""
        ...


@dataclass(frozen=True, slots=True)
class FastTextLanguageDetector:
    """Detect Japanese artist names through a fastText model."""

    model_path: Path | None = None
    model: _FastTextModel | None = None

    def __post_init__(self) -> None:
        """Load the model lazily when tests did not inject one."""
        if self.model is not None:
            return
        if self.model_path is None:
            raise ValueError(FASTTEXT_MODEL_PATH_REQUIRED_MESSAGE)
        fasttext_module = importlib.import_module("fasttext")
        load_model = cast("Callable[[str], object]", fasttext_module.load_model)
        object.__setattr__(self, "model", cast("_FastTextModel", load_model(str(self.model_path))))

    def is_japanese(self, text: str) -> bool:
        """Return true when fastText predicts the Japanese label."""
        normalized_text = text.strip()
        if normalized_text == "":
            return False
        model = self.model
        if model is None:
            return False
        labels, _scores = model.predict(normalized_text, k=1)
        return bool(labels) and labels[0] == FASTTEXT_JAPANESE_LABEL
