"""
Summary: Defines artist-name resolution requests and raw provider observations.
Why: Gives naming usecases typed model and catalog inputs without adapter coupling.
"""

from __future__ import annotations

from dataclasses import dataclass
from types import MappingProxyType
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from collections.abc import Mapping

    from omym2.domain.models.accepted_artist_name import AcceptedArtistName


@dataclass(frozen=True, slots=True)
class ResolveArtistNamesRequest:
    """Batch of source names to resolve through the editable mapping cache."""

    source_names: tuple[str | None, ...]


@dataclass(frozen=True, slots=True)
class ArtistNameMappingsResult:
    """One revisioned snapshot of editable artist-name mappings."""

    mappings: tuple[AcceptedArtistName, ...]
    revision: str


@dataclass(frozen=True, slots=True)
class SaveArtistNameMappingsRequest:
    """Complete editable mapping candidate tied to the snapshot the user saw."""

    entries: Mapping[str, str]
    expected_revision: str

    def __post_init__(self) -> None:
        """Freeze the complete browser candidate for deterministic validation."""
        object.__setattr__(self, "entries", MappingProxyType(dict(self.entries)))


@dataclass(frozen=True, slots=True)
class ArtistNameAliasCandidate:
    """One provider alias fact used for deterministic display-name selection."""

    name: str
    locale: str | None
    sort_name: str | None = None
    primary: bool = False


@dataclass(frozen=True, slots=True)
class ArtistNameProviderCandidate:
    """One scored MusicBrainz artist identity and its usable naming facts."""

    provider_artist_id: str
    score: int
    name: str
    sort_name: str | None = None
    aliases: tuple[ArtistNameAliasCandidate, ...] = ()


@dataclass(frozen=True, slots=True)
class ArtistNameSearchResult:
    """Raw provider candidates or an explicit unavailable observation."""

    available: bool
    candidates: tuple[ArtistNameProviderCandidate, ...] = ()
