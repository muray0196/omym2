"""
Summary: Implements reviewed Plan listing as one keyset page.
Why: Lets users browse created Plans at scale before apply exists.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from omym2.domain.models.plan import Plan
    from omym2.features.plans.dto import ListPlansRequest
    from omym2.features.plans.ports import PlanQueryPorts
    from omym2.shared.pagination import Page


@dataclass(frozen=True, slots=True)
class ListPlansUseCase:
    """List reviewed Plan headers as one keyset page, newest first."""

    ports: PlanQueryPorts

    def execute(self, request: ListPlansRequest) -> Page[Plan]:
        """Return one page of Plans for the requested scope, status, and plan_type filters.

        Ordered (created_at DESC, plan_id DESC). Fetch is per-Library when
        request.library_id is set, otherwise scoped across every known
        Library.
        """
        with self.ports.uow as uow:
            return uow.plans.query_page(
                request.library_id,
                search=request.search,
                status=request.status,
                plan_type=request.plan_type,
                blocked_only=request.blocked_only,
                page=request.page,
            )
