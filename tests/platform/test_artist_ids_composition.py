"""
Summary: Tests artist ID adapter selection builders.
Why: Guards the moved selection logic used by ArtistIdsCommandPorts against drift.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

import pytest

from omym2.adapters.artist_ids.musicbrainz_artist_lookup import MusicBrainzArtistLookup
from omym2.adapters.artist_ids.no_op_artist_name_resolver import NoOpArtistNameResolver
from omym2.adapters.artist_ids.no_op_language_detector import NoOpLanguageDetector
from omym2.platform.artist_ids_composition import (
    default_artist_resolver,
    language_detector_for_model,
    web_artist_language_detector,
    web_artist_name_resolver,
)

if TYPE_CHECKING:
    from pathlib import Path


def test_language_detector_for_model_returns_no_op_when_model_path_is_none() -> None:
    """A missing --fasttext-model option selects the no-op detector, as artist_ids.py does."""
    detector = language_detector_for_model(None)

    assert isinstance(detector, NoOpLanguageDetector)


def test_language_detector_for_model_does_not_check_existence_for_nonexistent_path(tmp_path: Path) -> None:
    """language_detector_for_model performs no existence check; a missing model surfaces fastText's own load error.

    fastText is an optional, uninstalled dependency in this environment, so building
    FastTextLanguageDetector(model_path=...) fails at model-load time with ModuleNotFoundError,
    exactly as artist_ids.py's command error handling expects before converting it into a CLI message.
    """
    nonexistent_model_path = tmp_path / "does-not-exist.bin"
    assert not nonexistent_model_path.exists()

    with pytest.raises(ModuleNotFoundError):
        _ = language_detector_for_model(nonexistent_model_path)


def test_default_artist_resolver_returns_musicbrainz_lookup() -> None:
    """default_artist_resolver mirrors artist_ids.py's MusicBrainzArtistLookup() default resolver."""
    resolver = default_artist_resolver()

    assert isinstance(resolver, MusicBrainzArtistLookup)


def test_web_artist_language_detector_returns_no_op() -> None:
    """The Web adapter never needs fastText, so it always gets the no-op detector."""
    detector = web_artist_language_detector()

    assert isinstance(detector, NoOpLanguageDetector)


def test_web_artist_name_resolver_returns_no_op() -> None:
    """The Web adapter never contacts MusicBrainz, so it always gets the no-op resolver."""
    resolver = web_artist_name_resolver()

    assert isinstance(resolver, NoOpArtistNameResolver)
