"""
Summary: Tests fastText language detector adapter.
Why: Verifies optional model loading without requiring the fastText package.
"""

from __future__ import annotations

import importlib
from dataclasses import dataclass
from types import ModuleType
from typing import TYPE_CHECKING

import pytest

from omym2.adapters.artist_ids.fasttext_language_detector import (
    FastTextLanguageDetector,
    FastTextLanguageDetectorError,
)

if TYPE_CHECKING:
    from pathlib import Path

EXPECTED_LANGUAGE = "ja"


def test_fasttext_language_detector_returns_label_without_prefix(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    """Detector loads fastText lazily and normalizes the predicted label."""
    model_path = tmp_path / "lid.bin"
    _ = model_path.write_bytes(b"model")
    fake_module = FakeFastTextModule("fasttext")

    def fake_import_module(_name: str) -> ModuleType:
        return fake_module

    monkeypatch.setattr(importlib, "import_module", fake_import_module)

    result = FastTextLanguageDetector(str(model_path)).detect_language("宇多田ヒカル")

    assert result == EXPECTED_LANGUAGE
    assert fake_module.loaded_model_path == str(model_path)


def test_fasttext_language_detector_rejects_missing_model() -> None:
    """Missing model files are reported through the adapter error type."""
    with pytest.raises(FastTextLanguageDetectorError, match="model file"):
        _ = FastTextLanguageDetector("/missing/lid.bin").detect_language("Aimer")


@dataclass(slots=True)
class FakeFastTextModel:
    """Minimal fastText model fake."""

    def predict(self, _text: str, k: int) -> tuple[list[str], list[float]]:
        """Return one Japanese label."""
        assert k == 1
        return ["__label__ja"], [0.99]


class FakeFastTextModule(ModuleType):
    """Minimal fastText module fake."""

    def __init__(self, name: str) -> None:
        """Initialize the fake as a module-like object."""
        super().__init__(name)
        self.loaded_model_path: str | None = None

    def load_model(self, model_path: str) -> FakeFastTextModel:
        """Record the model path and return a fake model."""
        self.loaded_model_path = model_path
        return FakeFastTextModel()
