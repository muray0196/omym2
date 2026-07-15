"""
Summary: Composes shared artist-name resolution adapters.
Why: Lets every naming consumer share cache, model, and provider behavior.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from omym2.adapters.artist_ids.fasttext_language_detector import (
    FastTextLanguageDetector,
    OptionalFastTextLanguageDetector,
)
from omym2.adapters.artist_ids.musicbrainz_artist_lookup import MusicBrainzArtistLookup
from omym2.adapters.artist_ids.no_op_language_detector import NoOpLanguageDetector
from omym2.adapters.db.sqlite.unit_of_work import SQLiteUnitOfWork
from omym2.features.artist_names.ports import ResolveArtistNamesPorts
from omym2.features.artist_names.usecases.resolve_artist_names import ResolveArtistNamesUseCase
from omym2.features.common_ports import SystemClock

if TYPE_CHECKING:
    from pathlib import Path

    from omym2.features.artist_names.ports import ArtistLanguagePredictor, ArtistNameProvider


def language_predictor_for_model(model_path: Path | None) -> ArtistLanguagePredictor:
    """Select a fastText predictor when a model path is given, else a no-op predictor."""
    if model_path is None:
        return NoOpLanguageDetector()
    return FastTextLanguageDetector(model_path=model_path)


def automatic_language_predictor_for_model(model_path: Path | None) -> ArtistLanguagePredictor:
    """Select a lazy fail-soft predictor only when the process opts in with a model path."""
    if model_path is None:
        return NoOpLanguageDetector()
    return OptionalFastTextLanguageDetector(model_path=model_path)


def default_artist_name_provider() -> ArtistNameProvider:
    """Build the default MusicBrainz-backed artist name provider."""
    return MusicBrainzArtistLookup()


def artist_name_resolver_for(
    database_file: Path,
    language_predictor: ArtistLanguagePredictor,
    artist_name_provider: ArtistNameProvider,
) -> ResolveArtistNamesUseCase:
    """Build the shared resolver over one application's accepted-name cache."""
    return ResolveArtistNamesUseCase(
        ResolveArtistNamesPorts(
            uow=SQLiteUnitOfWork(database_file),
            language_predictor=language_predictor,
            artist_name_provider=artist_name_provider,
            clock=SystemClock(),
        )
    )


def plan_artist_name_resolver_for(
    database_file: Path,
    language_predictor: ArtistLanguagePredictor,
    artist_name_provider: ArtistNameProvider,
) -> ResolveArtistNamesUseCase:
    """Build normal Plan resolution over the process-shared optional model and provider."""
    return artist_name_resolver_for(
        database_file,
        language_predictor,
        artist_name_provider,
    )
