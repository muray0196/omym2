"""
Summary: Composes shared artist-name resolution adapters.
Why: Lets every naming consumer share cache, model, and provider behavior.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import TYPE_CHECKING

from omym2 import __version__
from omym2.adapters.artist_ids.fasttext_language_detector import (
    FastTextLanguageDetector,
    OptionalFastTextLanguageDetector,
)
from omym2.adapters.artist_ids.musicbrainz_artist_lookup import MusicBrainzArtistLookup
from omym2.adapters.artist_ids.no_op_language_detector import NoOpLanguageDetector
from omym2.adapters.db.sqlite.provider_request_cadence import SQLiteProviderRequestCadence
from omym2.adapters.db.sqlite.unit_of_work import SQLiteUnitOfWork
from omym2.features.artist_names.ports import ResolveArtistNamesPorts
from omym2.features.artist_names.usecases.resolve_artist_names import ResolveArtistNamesUseCase
from omym2.features.common_ports import SystemClock

if TYPE_CHECKING:
    from omym2.domain.models.app_config import FastTextConfig, MusicBrainzConfig
    from omym2.features.artist_names.ports import ArtistLanguagePredictor, ArtistNameProvider

type _ProviderConfigKey = tuple[str, str, float, int, float]


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


@dataclass(slots=True)
class ArtistNameRuntime:
    """Reuse optional model and provider adapters until their persisted controls change."""

    database_file: Path
    application_root: Path
    _predictor_key: str | None = field(default=None, init=False)
    _predictor: ArtistLanguagePredictor | None = field(default=None, init=False)
    _provider_key: _ProviderConfigKey | None = field(default=None, init=False)
    _provider: ArtistNameProvider | None = field(default=None, init=False)

    def language_predictor_for(self, config: FastTextConfig) -> ArtistLanguagePredictor:
        """Return one lazy predictor for the current persisted model path."""
        model_path = None if config.model_path is None else config.model_path.strip()
        if self._predictor is None or model_path != self._predictor_key:
            self._predictor_key = model_path
            resolved_model_path = None
            if model_path is not None:
                configured_path = Path(model_path).expanduser()
                resolved_model_path = (
                    configured_path if configured_path.is_absolute() else self.application_root / configured_path
                )
            self._predictor = automatic_language_predictor_for_model(resolved_model_path)
        return self._predictor

    def provider_for(self, config: MusicBrainzConfig) -> ArtistNameProvider:
        """Return one provider whose identity and bounds match persisted settings."""
        key = (
            config.application_name,
            config.contact,
            config.timeout_seconds,
            config.retry_limit,
            config.rate_limit_seconds,
        )
        if self._provider is None or key != self._provider_key:
            self._provider_key = key
            self._provider = MusicBrainzArtistLookup(
                user_agent=_musicbrainz_user_agent(config.application_name, config.contact),
                timeout_seconds=config.timeout_seconds,
                retry_limit=config.retry_limit,
                rate_limit_seconds=config.rate_limit_seconds,
                request_cadence=SQLiteProviderRequestCadence(self.database_file, "musicbrainz"),
            )
        return self._provider


def artist_name_resolver_for(
    database_file: Path,
    language_predictor: ArtistLanguagePredictor,
    artist_name_provider: ArtistNameProvider,
    *,
    automatic_lookup_enabled: bool = True,
    minimum_confidence: float,
) -> ResolveArtistNamesUseCase:
    """Build the shared resolver over one application's accepted-name cache."""
    return ResolveArtistNamesUseCase(
        ResolveArtistNamesPorts(
            uow=SQLiteUnitOfWork(database_file),
            language_predictor=language_predictor,
            artist_name_provider=artist_name_provider,
            clock=SystemClock(),
            automatic_lookup_enabled=automatic_lookup_enabled,
            minimum_confidence=minimum_confidence,
        )
    )


def _musicbrainz_user_agent(application_name: str, contact: str) -> str:
    return f"{application_name.strip()}/{__version__} ({contact.strip()})"
