"""
Summary: Defines history feature request and response data.
Why: Gives CLI and Web inspection stable Run/FileEvent browsing contracts.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import StrEnum
from typing import TYPE_CHECKING

from omym2.shared.pagination import PageRequest

if TYPE_CHECKING:
    from omym2.domain.models.file_event import FileEventStatus
    from omym2.domain.models.run import Run, RunStatus
    from omym2.shared.ids import LibraryId, OperationId, PlanId, RunId
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


class RunCapabilityReason(StrEnum):
    """Stable reasons why one Run cannot create an Undo Plan."""

    RUN_NOT_TERMINAL = "run_not_terminal"
    NOTHING_TO_UNDO = "nothing_to_undo"
    UNDO_REFRESH_METADATA_UNSUPPORTED = "undo_refresh_metadata_unsupported"
    PENDING_FILE_EVENT_REQUIRES_REVIEW = "pending_file_event_requires_review"
    ALREADY_UNDONE_OR_IN_PROGRESS = "already_undone_or_in_progress"


@dataclass(frozen=True, slots=True)
class RunCapabilitiesResult:
    """Backend-authoritative Undo Plan availability for one Run."""

    can_create_undo: bool
    disabled_reasons: tuple[RunCapabilityReason, ...]


@dataclass(frozen=True, slots=True)
class RunDetailResult:
    """One Run header with its current read-only capability projection."""

    run: Run
    capabilities: RunCapabilitiesResult
    active_operation_id: OperationId | None = None


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
