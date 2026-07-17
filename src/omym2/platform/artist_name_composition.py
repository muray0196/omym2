"""
Summary: Composes shared artist-name resolution adapters.
Why: Lets every naming consumer share cache and provider behavior.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import TYPE_CHECKING

from omym2 import __version__
from omym2.adapters.artist_ids.musicbrainz_artist_lookup import MusicBrainzArtistLookup
from omym2.adapters.db.sqlite.provider_request_cadence import SQLiteProviderRequestCadence
from omym2.adapters.db.sqlite.unit_of_work import SQLiteUnitOfWork
from omym2.features.artist_names.ports import ResolveArtistNamesPorts
from omym2.features.artist_names.usecases.resolve_artist_names import ResolveArtistNamesUseCase
from omym2.features.common_ports import SystemClock

if TYPE_CHECKING:
    from pathlib import Path

    from omym2.domain.models.app_config import MusicBrainzConfig
    from omym2.features.artist_names.ports import ArtistNameProvider

type _ProviderConfigKey = tuple[str, str, float, int, float]


@dataclass(slots=True)
class ArtistNameRuntime:
    """Reuse the provider adapter until its persisted controls change."""

    database_file: Path
    _provider_key: _ProviderConfigKey | None = field(default=None, init=False)
    _provider: ArtistNameProvider | None = field(default=None, init=False)

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
    artist_name_provider: ArtistNameProvider,
    *,
    automatic_lookup_enabled: bool = True,
) -> ResolveArtistNamesUseCase:
    """Build the shared resolver over one application's accepted-name cache."""
    return ResolveArtistNamesUseCase(
        ResolveArtistNamesPorts(
            uow=SQLiteUnitOfWork(database_file),
            artist_name_provider=artist_name_provider,
            clock=SystemClock(),
            automatic_lookup_enabled=automatic_lookup_enabled,
        )
    )


def _musicbrainz_user_agent(application_name: str, contact: str) -> str:
    return f"{application_name.strip()}/{__version__} ({contact.strip()})"
