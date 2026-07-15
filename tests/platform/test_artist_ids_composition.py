"""
Summary: Tests artist ID adapter selection builders.
Why: Guards the moved selection logic used by ArtistIdsCommandPorts against drift.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

import pytest

from omym2.adapters.artist_ids.musicbrainz_artist_lookup import MusicBrainzArtistLookup
from omym2.adapters.artist_ids.no_op_language_detector import NoOpLanguageDetector
from omym2.platform.artist_name_composition import default_artist_name_provider, language_predictor_for_model

if TYPE_CHECKING:
    from pathlib import Path


def test_language_predictor_for_model_returns_no_op_when_model_path_is_none() -> None:
    """A missing --fasttext-model option selects the no-op predictor."""
    detector = language_predictor_for_model(None)

    assert isinstance(detector, NoOpLanguageDetector)


def test_language_predictor_for_model_does_not_check_existence_for_nonexistent_path(tmp_path: Path) -> None:
    """language_predictor_for_model leaves model-file validation to fastText.

    fastText is an optional, uninstalled dependency in this environment, so building
    FastTextLanguageDetector(model_path=...) fails at model-load time with ModuleNotFoundError,
    exactly as artist_ids.py's command error handling expects before converting it into a CLI message.
    """
    nonexistent_model_path = tmp_path / "does-not-exist.bin"
    assert not nonexistent_model_path.exists()

    with pytest.raises(ModuleNotFoundError):
        _ = language_predictor_for_model(nonexistent_model_path)


def test_default_artist_name_provider_returns_musicbrainz_lookup() -> None:
    """The default provider uses the MusicBrainz HTTP adapter."""
    resolver = default_artist_name_provider()

    assert isinstance(resolver, MusicBrainzArtistLookup)
