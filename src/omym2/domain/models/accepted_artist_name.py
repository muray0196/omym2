"""
Summary: Defines one editable original-to-English artist-name mapping.
Why: Unifies automatic MusicBrainz results and user corrections without changing raw metadata.
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum
from typing import TYPE_CHECKING
from uuid import UUID

from omym2.shared.time import as_utc

if TYPE_CHECKING:
    from datetime import datetime

EMPTY_ACCEPTED_ARTIST_NAME_FIELD_MESSAGE = "Accepted artist-name text fields must not be empty."
INVALID_SELECTED_LOCALE_MESSAGE = "Only an alias selection may carry a locale."
INVALID_PROVIDER_ARTIST_ID_MESSAGE = "MusicBrainz artist identity must be a valid UUID."
INVALID_PROVIDER_PROVENANCE_MESSAGE = "Artist-name mapping provenance is incomplete or inconsistent."


class ArtistNameProvider(StrEnum):
    """Source that last supplied an editable artist-name mapping."""

    MUSICBRAINZ = "musicbrainz"
    USER = "user"


class SelectedArtistNameKind(StrEnum):
    """MusicBrainz field that supplied the accepted artist name."""

    ALIAS = "alias"
    ALIAS_SORT_NAME = "alias_sort_name"
    SORT_NAME = "sort_name"


@dataclass(frozen=True, slots=True)
class AcceptedArtistName:
    """One editable original-name to English-name mapping."""

    source_key: str
    source_name: str
    resolved_name: str
    provider: ArtistNameProvider
    provider_artist_id: str | None
    selected_name_kind: SelectedArtistNameKind | None
    selected_locale: str | None
    accepted_at: datetime

    def __post_init__(self) -> None:
        """Reject incomplete provenance and normalize the acceptance timestamp."""
        required_text = (self.source_key, self.source_name, self.resolved_name)
        if any(value.strip() == "" for value in required_text):
            raise ValueError(EMPTY_ACCEPTED_ARTIST_NAME_FIELD_MESSAGE)
        provider_artist_id = self.provider_artist_id
        if self.provider is ArtistNameProvider.MUSICBRAINZ:
            if provider_artist_id is None or self.selected_name_kind is None:
                raise ValueError(INVALID_PROVIDER_PROVENANCE_MESSAGE)
            try:
                provider_artist_id = str(UUID(provider_artist_id))
            except ValueError as exc:
                raise ValueError(INVALID_PROVIDER_ARTIST_ID_MESSAGE) from exc
        elif provider_artist_id is not None or self.selected_name_kind is not None or self.selected_locale is not None:
            raise ValueError(INVALID_PROVIDER_PROVENANCE_MESSAGE)
        locale_kinds = {
            SelectedArtistNameKind.ALIAS,
            SelectedArtistNameKind.ALIAS_SORT_NAME,
        }
        if self.selected_locale is not None and (
            self.selected_locale.strip() == "" or self.selected_name_kind not in locale_kinds
        ):
            raise ValueError(INVALID_SELECTED_LOCALE_MESSAGE)
        object.__setattr__(self, "provider_artist_id", provider_artist_id)
        object.__setattr__(self, "accepted_at", as_utc(self.accepted_at))
