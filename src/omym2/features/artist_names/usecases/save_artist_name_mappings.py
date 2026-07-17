"""
Summary: Saves a revision-checked editable artist-name mapping snapshot.
Why: Lets users correct or add English names without a second preference store.
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from hashlib import new
from typing import TYPE_CHECKING

from omym2.config import (
    CONFIG_FINGERPRINT_ALGORITHM,
    CONFIG_FINGERPRINT_ENCODING,
    CONFIG_FINGERPRINT_JSON_ITEM_SEPARATOR,
    CONFIG_FINGERPRINT_JSON_KEY_SEPARATOR,
)
from omym2.domain.models.accepted_artist_name import AcceptedArtistName, ArtistNameProvider
from omym2.domain.services.artist_name import derive_artist_name_source_key, is_usable_english_artist_name
from omym2.features.artist_names.dto import ArtistNameMappingsResult

if TYPE_CHECKING:
    from collections.abc import Mapping, Sequence

    from omym2.features.artist_names.dto import SaveArtistNameMappingsRequest
    from omym2.features.common_ports import Clock, UnitOfWork

EMPTY_ARTIST_NAME_MAPPING_MESSAGE = "Original and English artist names must not be empty."
INVALID_ENGLISH_ARTIST_NAME_MESSAGE = "English artist names must use Latin-script alphabetic text."
DUPLICATE_ARTIST_NAME_MAPPING_MESSAGE = "Original artist names must have distinct normalized keys."
ARTIST_NAME_MAPPINGS_CHANGED_MESSAGE = "Artist-name mappings changed after this edit began."


class ArtistNameMappingsRevisionMismatchError(RuntimeError):
    """Raised when an editable mapping snapshot is stale."""


@dataclass(frozen=True, slots=True)
class SaveArtistNameMappingsUseCase:
    """Replace the editable mapping snapshot without overwriting concurrent changes."""

    uow: UnitOfWork
    clock: Clock

    def execute(self, request: SaveArtistNameMappingsRequest) -> ArtistNameMappingsResult:
        """Validate and save one complete original-to-English mapping candidate."""
        candidate = _normalized_candidate(request.entries)
        with self.uow.usecase_scope(), self.uow as uow:
            current = uow.accepted_artist_names.list_all()
            if artist_name_mappings_revision(current) != request.expected_revision:
                raise ArtistNameMappingsRevisionMismatchError(ARTIST_NAME_MAPPINGS_CHANGED_MESSAGE)
            final = self._save_changes(uow, current, candidate)
            uow.commit()
        return ArtistNameMappingsResult(
            mappings=final,
            revision=artist_name_mappings_revision(final),
        )

    def _save_changes(
        self,
        uow: UnitOfWork,
        current: Sequence[AcceptedArtistName],
        candidate: Mapping[str, tuple[str, str]],
    ) -> tuple[AcceptedArtistName, ...]:
        current_by_key = {mapping.source_key: mapping for mapping in current}
        for source_key in sorted(set(current_by_key) - set(candidate)):
            uow.accepted_artist_names.delete_by_source_key(source_key)

        accepted_at = self.clock.now()
        final: list[AcceptedArtistName] = []
        for source_key, (source_name, english_name) in sorted(candidate.items()):
            existing = current_by_key.get(source_key)
            if existing is not None and existing.source_name == source_name and existing.resolved_name == english_name:
                final.append(existing)
                continue
            mapping = AcceptedArtistName(
                source_key=source_key,
                source_name=source_name,
                resolved_name=english_name,
                provider=ArtistNameProvider.USER,
                provider_artist_id=None,
                selected_name_kind=None,
                selected_locale=None,
                accepted_at=accepted_at,
            )
            uow.accepted_artist_names.save(mapping)
            final.append(mapping)
        return tuple(final)


def artist_name_mappings_revision(mappings: Sequence[AcceptedArtistName]) -> str:
    """Return a stable revision for the effective mapping snapshot."""
    payload = json.dumps(
        tuple(
            (mapping.source_key, mapping.source_name, mapping.resolved_name)
            for mapping in sorted(mappings, key=lambda item: item.source_key)
        ),
        separators=(CONFIG_FINGERPRINT_JSON_ITEM_SEPARATOR, CONFIG_FINGERPRINT_JSON_KEY_SEPARATOR),
    )
    digest = new(CONFIG_FINGERPRINT_ALGORITHM)
    digest.update(payload.encode(CONFIG_FINGERPRINT_ENCODING))
    return digest.hexdigest()


def _normalized_candidate(entries: Mapping[str, str]) -> dict[str, tuple[str, str]]:
    candidate: dict[str, tuple[str, str]] = {}
    for raw_source_name, raw_english_name in entries.items():
        source_key = derive_artist_name_source_key(raw_source_name)
        english_name = raw_english_name.strip()
        if source_key is None or english_name == "":
            raise ValueError(EMPTY_ARTIST_NAME_MAPPING_MESSAGE)
        if not is_usable_english_artist_name(english_name):
            raise ValueError(INVALID_ENGLISH_ARTIST_NAME_MESSAGE)
        if source_key in candidate:
            raise ValueError(DUPLICATE_ARTIST_NAME_MAPPING_MESSAGE)
        candidate[source_key] = (raw_source_name, english_name)
    return candidate
