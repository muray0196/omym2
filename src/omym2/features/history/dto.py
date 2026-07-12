"""
Summary: Defines history feature request and response data.
Why: Gives CLI and Web inspection stable Run/FileEvent browsing contracts.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import TYPE_CHECKING

from omym2.shared.pagination import PageRequest

if TYPE_CHECKING:
    from omym2.domain.models.file_event import FileEventStatus
    from omym2.domain.models.run import RunStatus
    from omym2.shared.ids import LibraryId, PlanId, RunId
    from omym2.shared.pagination import FacetValue


@dataclass(frozen=True, slots=True)
class ListRunsRequest:
    """Request one keyset page of Runs for a Library or every known Library."""

    library_id: LibraryId | None = None
    search: str | None = None
    plan_id: PlanId | None = None
    status: RunStatus | None = None
    page: PageRequest = field(default_factory=PageRequest)


@dataclass(frozen=True, slots=True)
class GetRunHeaderRequest:
    """Request to load one Run header by ID, without its durable FileEvents."""

    run_id: RunId


@dataclass(frozen=True, slots=True)
class ListRunEventsRequest:
    """Request one keyset page of a Run's durable FileEvents.

    An optional `status` filter is pushed into the query itself, not applied
    as a post-fetch Python filter.
    """

    run_id: RunId
    status: FileEventStatus | None = None
    page: PageRequest = field(default_factory=PageRequest)


@dataclass(frozen=True, slots=True)
class RunStatusFacetsRequest:
    """Request Run status facet counts for a Library or every known Library."""

    library_id: LibraryId | None = None


@dataclass(frozen=True, slots=True)
class RunStatusFacetsResult:
    """Run status facet counts plus the total Run count in scope."""

    facets: tuple[FacetValue, ...]
    total: int


@dataclass(frozen=True, slots=True)
class FileEventStatusFacetsRequest:
    """Request FileEvent status facet counts for one Run."""

    run_id: RunId


@dataclass(frozen=True, slots=True)
class FileEventStatusFacetsResult:
    """FileEvent status facet counts plus the total event count in scope."""

    facets: tuple[FacetValue, ...]
    total: int


@dataclass(frozen=True, slots=True)
class GroupRunEventsRequest:
    """Request one keyset page of a Run's FileEvents grouped by target directory."""

    run_id: RunId
    page: PageRequest = field(default_factory=PageRequest)
