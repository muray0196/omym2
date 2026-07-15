"""
Summary: Composes shared artist-name resolution adapters.
Why: Lets every naming consumer share cache, model, and provider behavior.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from omym2.adapters.artist_ids.fasttext_language_detector import FastTextLanguageDetector
from omym2.adapters.artist_ids.musicbrainz_artist_lookup import MusicBrainzArtistLookup
from omym2.adapters.artist_ids.no_op_language_detector import NoOpLanguageDetector
from omym2.adapters.db.sqlite.unit_of_work import SQLiteUnitOfWork
from omym2.features.artist_names.ports import ResolveArtistNamesPorts
from omym2.features.artist_names.usecases.resolve_artist_names import ResolveArtistNamesUseCase
from omym2.features.common_ports import SystemClock

if TYPE_CHECKING:
    from pathlib import Path

    from omym2.features.artist_names.ports import ArtistLanguagePredictor, ArtistNameProvider
    from omym2.platform.runtime_context import RuntimeContext


def language_predictor_for_model(model_path: Path | None) -> ArtistLanguagePredictor:
    """Select a fastText predictor when a model path is given, else a no-op predictor."""
    if model_path is None:
        return NoOpLanguageDetector()
    return FastTextLanguageDetector(model_path=model_path)


def default_artist_name_provider() -> ArtistNameProvider:
    """Build the default MusicBrainz-backed artist name provider."""
    return MusicBrainzArtistLookup()


def artist_name_resolver_for(
    runtime: RuntimeContext,
    language_predictor: ArtistLanguagePredictor,
    artist_name_provider: ArtistNameProvider,
) -> ResolveArtistNamesUseCase:
    """Build the shared resolver over one application's accepted-name cache."""
    return ResolveArtistNamesUseCase(
        ResolveArtistNamesPorts(
            uow=SQLiteUnitOfWork(runtime.database_file),
            language_predictor=language_predictor,
            artist_name_provider=artist_name_provider,
            clock=SystemClock(),
        )
    )


def local_artist_name_resolver_for(runtime: RuntimeContext) -> ResolveArtistNamesUseCase:
    """Build the normal local resolver until persisted automatic-lookup controls exist."""
    return artist_name_resolver_for(
        runtime,
        language_predictor_for_model(None),
        default_artist_name_provider(),
    )
