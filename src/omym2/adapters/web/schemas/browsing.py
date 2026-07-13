"""
Summary: Defines shared typed Web browsing page and facet resources.
Why: Keeps cursor list envelopes consistent across read-only API slices.
"""

from __future__ import annotations

from typing import Annotated

from pydantic import Field

from omym2.adapters.web.schemas.api_errors import ApiModel
from omym2.shared.pagination import MAX_PAGE_LIMIT

type NonNegativeCount = Annotated[int, Field(ge=0)]


class PageInfo(ApiModel):
    """One effective keyset page with an opaque next cursor."""

    limit: Annotated[int, Field(ge=1, le=MAX_PAGE_LIMIT)]
    next_cursor: str | None
    total: NonNegativeCount


class PaginatedData[Item](ApiModel):
    """One typed list page."""

    items: tuple[Item, ...]
    page: PageInfo


class FacetValueResource[Value](ApiModel):
    """One stable facet value and matching row count."""

    value: Value
    count: NonNegativeCount


class GroupResource(ApiModel):
    """One stable group key, display label, and matching row count."""

    key: str
    label: str
    count: NonNegativeCount
