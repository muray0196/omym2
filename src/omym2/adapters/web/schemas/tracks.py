"""
Summary: Defines typed Web API resources for read-only Track inspection.
Why: Exposes persisted metadata and identity without filesystem reads.
"""

from __future__ import annotations

from datetime import datetime  # noqa: TC003  # Pydantic resolves timestamp schema types at runtime.
from uuid import UUID  # noqa: TC003  # Pydantic resolves UUID schema types at runtime.

from omym2.adapters.web.schemas.api_errors import ApiModel
from omym2.adapters.web.schemas.browsing import (
    FacetValueResource,  # noqa: TC001  # Pydantic resolves nested schema types at runtime.
    GroupResource,  # noqa: TC001  # Pydantic resolves nested schema types at runtime.
    NonNegativeCount,  # noqa: TC001  # Pydantic resolves annotated schema types at runtime.
    PageInfo,  # noqa: TC001  # Pydantic resolves nested schema types at runtime.
)
from omym2.domain.models.track import (  # noqa: TC001  # Pydantic resolves enum schema types at runtime.
    TrackGrouping,
    TrackStatus,
)


class TrackMetadataResource(ApiModel):
    """Persisted tag metadata for one managed Track."""

    title: str | None
    artist: str | None
    album: str | None
    album_artist: str | None
    genre: str | None
    year: int | None
    track_number: int | None
    track_total: int | None
    disc_number: int | None
    disc_total: int | None


class TrackResource(ApiModel):
    """One persisted Track inspection resource."""

    track_id: UUID
    library_id: UUID
    current_path: str
    canonical_path: str
    content_hash: str
    metadata_hash: str
    size: NonNegativeCount | None
    mtime: datetime | None
    metadata: TrackMetadataResource
    status: TrackStatus
    first_seen_at: datetime
    last_seen_at: datetime
    updated_at: datetime


class TrackFacetSets(ApiModel):
    """Filter-aware Track status facets."""

    status: tuple[FacetValueResource[TrackStatus], ...]


class TrackFacetsData(ApiModel):
    """Track facets and total count for the current search scope."""

    facets: TrackFacetSets
    total: NonNegativeCount


class TrackGroupsData(ApiModel):
    """One filter-aware page of opaque Track hierarchy groups."""

    group_by: TrackGrouping
    items: tuple[GroupResource, ...]
    page: PageInfo
