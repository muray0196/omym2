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


@dataclass(frozen=True, slots=True)
class ResolveArtistNamesRequest:
    """Batch of source names and an exact preference snapshot to resolve."""

    source_names: tuple[str | None, ...]
    preferences: Mapping[str, str] | None = None

    def __post_init__(self) -> None:
        """Freeze preferences so one batch cannot change during resolution."""
        object.__setattr__(self, "preferences", MappingProxyType(dict(self.preferences or {})))


@dataclass(frozen=True, slots=True)
class ArtistLanguagePrediction:
    """Top fastText language prediction, including detector availability."""

    label: str | None
    confidence: float | None
    available: bool


@dataclass(frozen=True, slots=True)
class ArtistNameAliasCandidate:
    """One provider alias fact used for deterministic display-name selection."""

    name: str
    locale: str | None
    primary: bool = False


@dataclass(frozen=True, slots=True)
class ArtistNameProviderCandidate:
    """One scored MusicBrainz artist identity and its usable naming facts."""

    provider_artist_id: str
    score: int
    name: str
    aliases: tuple[ArtistNameAliasCandidate, ...] = ()


@dataclass(frozen=True, slots=True)
class ArtistNameSearchResult:
    """Raw provider candidates or an explicit unavailable observation."""

    available: bool
    candidates: tuple[ArtistNameProviderCandidate, ...] = ()
