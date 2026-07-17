"""
Summary: Defines external collaborators required by artist-name resolution.
Why: Keeps provider I/O behind feature-owned contracts.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING, Protocol

if TYPE_CHECKING:
    from omym2.features.artist_names.dto import ArtistNameSearchResult
    from omym2.features.common_ports import Clock, UnitOfWork


class ArtistNameProvider(Protocol):
    """Search an external artist catalog without accepting a match."""

    def search_artists(self, source_name: str) -> ArtistNameSearchResult:
        """Return raw scored candidates or an unavailable observation."""
        ...


@dataclass(frozen=True, slots=True)
class ResolveArtistNamesPorts:
    """Collaborators used by the shared artist-name resolution usecase."""

    uow: UnitOfWork
    artist_name_provider: ArtistNameProvider
    clock: Clock
    automatic_lookup_enabled: bool = True
