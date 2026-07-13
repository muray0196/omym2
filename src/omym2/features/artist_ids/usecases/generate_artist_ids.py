"""
Summary: Generates and saves editable artist ID config entries.
Why: Lets users bootstrap artist IDs without overwriting manual edits.
"""

from __future__ import annotations

from dataclasses import dataclass, replace
from typing import TYPE_CHECKING

from omym2.domain.models.app_config import ArtistIdConfig
from omym2.domain.services.artist_id import generate_artist_id
from omym2.features.artist_ids.dto import ArtistIdEntryResult, GenerateArtistIdsResult
from omym2.features.common_ports import ConfigSnapshotState, ConfigStoreValidationError

if TYPE_CHECKING:
    from omym2.features.artist_ids.dto import GenerateArtistIdsRequest
    from omym2.features.artist_ids.ports import ArtistLanguageDetector, ArtistNameResolver
    from omym2.features.common_ports import ConfigStore


@dataclass(frozen=True, slots=True)
class GenerateArtistIdsUseCase:
    """Generate artist IDs and persist them in AppConfig."""

    config_store: ConfigStore
    language_detector: ArtistLanguageDetector
    artist_resolver: ArtistNameResolver

    def execute(self, request: GenerateArtistIdsRequest) -> GenerateArtistIdsResult:
        """Save missing artist IDs and preserve existing entries by default."""
        snapshot = self.config_store.read_snapshot()
        if snapshot.state is ConfigSnapshotState.INVALID:
            raise ConfigStoreValidationError(snapshot.errors)
        config = snapshot.config
        saved_entries = dict(config.artist_ids.entries or {})
        results: list[ArtistIdEntryResult] = []
        changed = False

        for source_artist in _normalized_artist_names(request.artist_names):
            existing_artist_id = saved_entries.get(source_artist)
            if existing_artist_id is not None and not request.overwrite:
                results.append(
                    ArtistIdEntryResult(
                        source_artist=source_artist,
                        generation_artist=source_artist,
                        artist_id=existing_artist_id,
                        saved=False,
                        overwritten=False,
                    )
                )
                continue

            generation_artist = self._generation_artist(source_artist)
            artist_id = generate_artist_id(
                generation_artist,
                max_length=config.artist_ids.max_length,
                fallback_id=config.artist_ids.fallback_id,
            )
            saved_entries[source_artist] = artist_id
            changed = True
            results.append(
                ArtistIdEntryResult(
                    source_artist=source_artist,
                    generation_artist=generation_artist,
                    artist_id=artist_id,
                    saved=True,
                    overwritten=existing_artist_id is not None,
                )
            )

        if changed:
            try:
                # A configured fallback_id is validated against the entries
                # value pattern by ArtistIdConfig, but that check runs on the
                # full fallback_id, not on the max_length-truncated text saved
                # into entries by generate_artist_id's no-usable-characters
                # branch. A fallback_id that is safe on its own can still
                # truncate into an unsafe saved entry value (e.g. a trailing
                # hyphen), so this construction can still reject it. Translate
                # that domain rejection into the same controlled config error
                # CLI/Web callers already handle, matching config_validator.py's
                # AppConfig(...) construction error translation.
                new_artist_ids = ArtistIdConfig(
                    max_length=config.artist_ids.max_length,
                    fallback_id=config.artist_ids.fallback_id,
                    entries=saved_entries,
                )
            except ValueError as exc:
                raise ConfigStoreValidationError((str(exc),)) from exc
            _ = self.config_store.save(
                replace(config, artist_ids=new_artist_ids),
                expected_config_revision=snapshot.config_revision,
            )
        return GenerateArtistIdsResult(entries=tuple(results))

    def _generation_artist(self, source_artist: str) -> str:
        if self.language_detector.is_japanese(source_artist):
            resolved_artist = self.artist_resolver.english_or_latin_name(source_artist)
            if resolved_artist is not None and resolved_artist.strip() != "":
                return resolved_artist
        return source_artist


def _normalized_artist_names(artist_names: tuple[str, ...]) -> tuple[str, ...]:
    seen: set[str] = set()
    normalized: list[str] = []
    for artist_name in artist_names:
        source_artist = artist_name.strip()
        if source_artist == "" or source_artist in seen:
            continue
        seen.add(source_artist)
        normalized.append(source_artist)
    return tuple(normalized)
