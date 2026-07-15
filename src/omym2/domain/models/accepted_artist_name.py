"""
Summary: Defines one sticky accepted artist display name from an external provider.
Why: Preserves provider identity and selection provenance without changing raw track metadata.
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


class ArtistNameProvider(StrEnum):
    """Supported providers for accepted artist names."""

    MUSICBRAINZ = "musicbrainz"


class SelectedArtistNameKind(StrEnum):
    """MusicBrainz field that supplied the accepted artist name."""

    ALIAS = "alias"
    NAME = "name"


@dataclass(frozen=True, slots=True)
class AcceptedArtistName:
    """One immutable provider result accepted for an artist source lookup key."""

    source_key: str
    source_name: str
    resolved_name: str
    provider: ArtistNameProvider
    provider_artist_id: str
    selected_name_kind: SelectedArtistNameKind
    selected_locale: str | None
    accepted_at: datetime

    def __post_init__(self) -> None:
        """Reject incomplete provenance and normalize the acceptance timestamp."""
        required_text = (self.source_key, self.source_name, self.resolved_name, self.provider_artist_id)
        if any(value.strip() == "" for value in required_text):
            raise ValueError(EMPTY_ACCEPTED_ARTIST_NAME_FIELD_MESSAGE)
        try:
            provider_artist_id = str(UUID(self.provider_artist_id))
        except ValueError as exc:
            raise ValueError(INVALID_PROVIDER_ARTIST_ID_MESSAGE) from exc
        if self.selected_locale is not None and (
            self.selected_locale.strip() == "" or self.selected_name_kind is not SelectedArtistNameKind.ALIAS
        ):
            raise ValueError(INVALID_SELECTED_LOCALE_MESSAGE)
        object.__setattr__(self, "provider_artist_id", provider_artist_id)
        object.__setattr__(self, "accepted_at", as_utc(self.accepted_at))
