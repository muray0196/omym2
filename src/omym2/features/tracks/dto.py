"""
Summary: Defines track inspection request and response data.
Why: Gives Web adapters a read-only Track query, facet, and group-by contract.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import TYPE_CHECKING

from omym2.shared.pagination import PageRequest

if TYPE_CHECKING:
    from omym2.domain.models.track import TrackGrouping, TrackStatus
    from omym2.shared.ids import LibraryId, TrackId
    from omym2.shared.pagination import FacetValue


@dataclass(frozen=True, slots=True)
class ListTracksRequest:
    """Request one keyset page of Tracks for a Library or every known Library."""

    library_id: LibraryId | None = None
    track_id: TrackId | None = None
    search: str | None = None
    status: TrackStatus | None = None
    page: PageRequest = field(default_factory=PageRequest)


@dataclass(frozen=True, slots=True)
class TrackStatusFacetsRequest:
    """Request Track status facet counts for a Library or every known Library."""

    library_id: LibraryId | None = None


@dataclass(frozen=True, slots=True)
class TrackStatusFacetsResult:
    """Track status facet counts plus the total Track count in scope."""

    facets: tuple[FacetValue, ...]
    total: int


@dataclass(frozen=True, slots=True)
class GroupTracksRequest:
    """Request one keyset page of Track groups for a Library or every known Library."""

    grouping: TrackGrouping
    library_id: LibraryId | None = None
    page: PageRequest = field(default_factory=PageRequest)
