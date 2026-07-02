"""
Summary: Generates missing editable artist ID config entries.
Why: Saves deterministic artist IDs without doing lookup during path rendering.
"""

from __future__ import annotations

from dataclasses import dataclass, replace
from typing import TYPE_CHECKING

from omym2.domain.models.app_config import ArtistIdConfig, ArtistIdEntry
from omym2.domain.services.artist_id import generate_artist_id
from omym2.features.artist_ids.dto import ArtistIdGenerationEntry, ArtistIdGenerationResult

if TYPE_CHECKING:
    from omym2.domain.models.app_config import AppConfig
    from omym2.features.artist_ids.dto import ArtistIdGenerationRequest
    from omym2.features.artist_ids.ports import ArtistIdPorts

JAPANESE_LANGUAGE_PREFIX = "ja"


@dataclass(frozen=True, slots=True)
class GenerateArtistIdsUseCase:
    """Generate and persist artist ID entries for supplied artist names."""

    ports: ArtistIdPorts

    def execute(self, request: ArtistIdGenerationRequest) -> ArtistIdGenerationResult:
        """Generate missing artist IDs and save updated AppConfig."""
        config = self.ports.config_store.load()
        existing_entries = {entry.source_artist: entry.artist_id for entry in config.artist_ids.entries}
        next_entries = dict(existing_entries)
        results: list[ArtistIdGenerationEntry] = []

        for source_artist in _unique_non_empty_artists(request.artist_names):
            existing_artist_id = existing_entries.get(source_artist)
            if existing_artist_id is not None and not request.overwrite_existing:
                results.append(
                    ArtistIdGenerationEntry(
                        source_artist=source_artist,
                        artist_id=existing_artist_id,
                        generated_from=source_artist,
                        language=None,
                        saved=False,
                        preserved_existing=True,
                    )
                )
                continue

            language = self.ports.language_detector.detect_language(source_artist)
            resolved_artist = self._resolved_artist_name(source_artist, language)
            artist_id = generate_artist_id(resolved_artist, config.artist_ids)
            next_entries[source_artist] = artist_id
            results.append(
                ArtistIdGenerationEntry(
                    source_artist=source_artist,
                    artist_id=artist_id,
                    generated_from=resolved_artist,
                    language=language,
                    saved=True,
                    preserved_existing=False,
                )
            )

        if next_entries != existing_entries:
            self.ports.config_store.save(_with_artist_id_entries(config, next_entries))

        return ArtistIdGenerationResult(entries=tuple(results))

    def _resolved_artist_name(self, source_artist: str, language: str | None) -> str:
        if language is None or not language.lower().startswith(JAPANESE_LANGUAGE_PREFIX):
            return source_artist
        return self.ports.musicbrainz_lookup.find_latin_artist_name(source_artist) or source_artist


def _unique_non_empty_artists(artist_names: tuple[str, ...]) -> tuple[str, ...]:
    seen: set[str] = set()
    artists: list[str] = []
    for artist_name in artist_names:
        normalized_artist = artist_name.strip()
        if normalized_artist == "" or normalized_artist in seen:
            continue
        artists.append(normalized_artist)
        seen.add(normalized_artist)
    return tuple(artists)


def _with_artist_id_entries(config: AppConfig, entries: dict[str, str]) -> AppConfig:
    sorted_entries = tuple(
        ArtistIdEntry(source_artist=source_artist, artist_id=artist_id)
        for source_artist, artist_id in sorted(entries.items())
    )
    artist_ids = ArtistIdConfig(
        max_length=config.artist_ids.max_length,
        fallback=config.artist_ids.fallback,
        entries=sorted_entries,
    )
    return replace(config, artist_ids=artist_ids)
