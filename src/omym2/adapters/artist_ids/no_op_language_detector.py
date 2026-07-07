"""
Summary: Implements a no-op Japanese-language detector.
Why: Lets callers skip fastText model loading when detection isn't needed.
"""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True, slots=True)
class NoOpLanguageDetector:
    """Language detector that always reports text as non-Japanese."""

    def is_japanese(self, text: str) -> bool:
        """Return false without inspecting the supplied text."""
        _ = text
        return False
