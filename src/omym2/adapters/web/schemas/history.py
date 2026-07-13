"""
Summary: Defines typed Web resources for Run and FileEvent inspection.
Why: Exposes durable execution evidence without embedding mutation behavior.
"""

from __future__ import annotations

from datetime import datetime  # noqa: TC003  # Pydantic resolves timestamp schema types at runtime.
from typing import Literal
from uuid import UUID  # noqa: TC003  # Pydantic resolves UUID schema types at runtime.

from omym2.adapters.web.schemas.api_errors import ApiError, ApiModel
from omym2.adapters.web.schemas.browsing import (
    FacetValueResource,  # noqa: TC001  # Pydantic resolves nested schema types at runtime.
    GroupResource,  # noqa: TC001  # Pydantic resolves nested schema types at runtime.
    NonNegativeCount,  # noqa: TC001  # Pydantic resolves constrained alias at runtime.
    PageInfo,  # noqa: TC001  # Pydantic resolves nested schema types at runtime.
)
from omym2.domain.models.file_event import (  # noqa: TC001  # Pydantic resolves enum schema types at runtime.
    FileEventStatus,
    FileEventType,
)
from omym2.domain.models.run import RunStatus  # noqa: TC001  # Pydantic resolves enum schema types at runtime.

type FileEventGrouping = Literal["target_directory"]


class RunHeader(ApiModel):
    """One apply Run header without embedded FileEvents."""

    run_id: UUID
    plan_id: UUID
    library_id: UUID
    status: RunStatus
    started_at: datetime
    completed_at: datetime | None
    error_summary: str | None


class RunCapabilities(ApiModel):
    """Backend-authoritative Undo Plan availability for one Run."""

    can_create_undo: bool
    disabled_reasons: tuple[ApiError, ...]


class RunDetailData(ApiModel):
    """One Run header with capability and active-operation projections."""

    run: RunHeader
    capabilities: RunCapabilities
    active_operation_id: UUID | None


class FileEventResource(ApiModel):
    """One durable Library music-file mutation record."""

    event_id: UUID
    library_id: UUID
    run_id: UUID
    plan_action_id: UUID
    event_type: FileEventType
    source_path: str
    target_path: str
    status: FileEventStatus
    started_at: datetime
    completed_at: datetime | None
    error_code: str | None
    error_message: str | None
    sequence_no: int


class RunFacetSets(ApiModel):
    """Run status facets."""

    status: tuple[FacetValueResource[RunStatus], ...]


class RunFacetsData(ApiModel):
    """Run status facets plus total Runs in scope."""

    facets: RunFacetSets
    total: NonNegativeCount


class FileEventFacetSets(ApiModel):
    """FileEvent status facets."""

    status: tuple[FacetValueResource[FileEventStatus], ...]


class FileEventFacetsData(ApiModel):
    """FileEvent status facets plus total events for one Run."""

    facets: FileEventFacetSets
    total: NonNegativeCount


class FileEventGroupsData(ApiModel):
    """One page of FileEvent target-directory groups."""

    group_by: FileEventGrouping
    items: tuple[GroupResource, ...]
    page: PageInfo
