"""
Summary: Generates artist ID entries against an in-memory Settings draft.
Why: Lets Web preview generated values without writing Config.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING

from omym2.domain.models.app_config import ArtistIdConfig
from omym2.domain.services.artist_id import generate_artist_id
from omym2.features.artist_ids.dto import ArtistIdDraftEntryResult, GenerateArtistIdDraftResult

if TYPE_CHECKING:
    from omym2.features.artist_ids.dto import GenerateArtistIdDraftRequest


class ArtistIdDraftValidationError(ValueError):
    """Raised when generated entries cannot form a valid ArtistIdConfig draft."""


@dataclass(frozen=True, slots=True)
class GenerateArtistIdDraftUseCase:
    """Generate or preserve artist IDs without a ConfigStore dependency."""

    def execute(self, request: GenerateArtistIdDraftRequest) -> GenerateArtistIdDraftResult:
        """Return deterministic entries derived only from the supplied form draft."""
        draft_entries = dict(request.artist_ids.entries or {})
        source_artists = _normalized_artist_names(request.artist_names)
        results: list[ArtistIdDraftEntryResult] = []
        for source_artist in source_artists:
            existing_artist_id = draft_entries.get(source_artist)
            if existing_artist_id is not None and not request.overwrite:
                results.append(
                    ArtistIdDraftEntryResult(
                        source_artist=source_artist,
                        generation_artist=source_artist,
                        artist_id=existing_artist_id,
                        overwritten=False,
                    )
                )
                continue

            generation_artist = source_artist
            artist_id = generate_artist_id(
                generation_artist,
                max_length=request.artist_ids.max_length,
                fallback_id=request.artist_ids.fallback_id,
            )
            draft_entries[source_artist] = artist_id
            results.append(
                ArtistIdDraftEntryResult(
                    source_artist=source_artist,
                    generation_artist=generation_artist,
                    artist_id=artist_id,
                    overwritten=existing_artist_id is not None,
                )
            )

        try:
            _ = ArtistIdConfig(
                max_length=request.artist_ids.max_length,
                fallback_id=request.artist_ids.fallback_id,
                entries=draft_entries,
            )
        except ValueError as exc:
            raise ArtistIdDraftValidationError(str(exc)) from exc
        return GenerateArtistIdDraftResult(entries=tuple(results))


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
