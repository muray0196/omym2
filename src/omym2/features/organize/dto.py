"""
Summary: Defines organize feature request data.
Why: Gives organize usecases stable contracts before adapter implementation.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from omym2.domain.models.library import Library
    from omym2.domain.models.plan import Plan
    from omym2.domain.models.plan_action import PlanAction


@dataclass(frozen=True, slots=True)
class CreateOrganizePlanRequest:
    """Request to organize or register a Library root."""

    library_root: str | None = None


@dataclass(frozen=True, slots=True)
class OrganizeLibraryResult:
    """Result of scanning a Library for organize registration."""

    library: Library
    plan: Plan | None
    actions: tuple[PlanAction, ...]
    track_count: int
