"""
Summary: Tests fastText language detector adapter.
Why: Verifies model predictions stay behind the feature port.
"""

from __future__ import annotations

from dataclasses import dataclass

from omym2.adapters.artist_ids.fasttext_language_detector import FastTextLanguageDetector


@dataclass(frozen=True, slots=True)
class _FakeModel:
    label: str

    def predict(self, text: str, k: int = 1) -> tuple[list[str], list[float]]:
        assert text
        assert k == 1
        return [self.label], [0.99]


def test_fasttext_language_detector_returns_true_for_japanese_label() -> None:
    """The adapter maps the fastText Japanese label to true."""
    detector = FastTextLanguageDetector(model=_FakeModel("__label__ja"))

    assert detector.is_japanese("米津玄師") is True


def test_fasttext_language_detector_returns_false_for_other_label() -> None:
    """Non-Japanese predictions do not trigger MusicBrainz lookup."""
    detector = FastTextLanguageDetector(model=_FakeModel("__label__en"))

    assert detector.is_japanese("Aimer") is False
