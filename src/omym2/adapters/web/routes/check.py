"""
Summary: Implements typed read-only persisted Check inspection routes.
Why: Keeps Health browsing available without filesystem I/O or recomputation.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING, Annotated, cast
from uuid import UUID  # noqa: TC003  # FastAPI resolves query annotations at registration.

from fastapi import APIRouter, Depends
from fastapi.responses import JSONResponse  # noqa: TC002  # FastAPI resolves route return annotations.

from omym2.adapters.web.routes.api_context import ApiContext  # noqa: TC001  # FastAPI resolves dependencies.
from omym2.adapters.web.routes.read_query import (
    CORRELATION_HEADER_SCHEMA,
    INVALID_CURSOR_MESSAGE,
    INVALID_LIMIT_MESSAGE,
    page_request,
    validation_failure,
)
from omym2.adapters.web.schemas.api_envelopes import ApiEnvelope, ApiFailureEnvelope
from omym2.adapters.web.schemas.browsing import FacetValueResource, PageInfo
from omym2.adapters.web.schemas.check import (
    CheckIssueFacetsData,
    CheckIssueFacetSets,
    CheckIssueGroupResource,
    CheckIssueGroupsData,
    CheckIssueResource,
    CheckIssuesData,
)
from omym2.config import (
    HTTP_INTERNAL_ERROR_STATUS,
    HTTP_OK_STATUS,
    HTTP_UNPROCESSABLE_CONTENT_STATUS,
    WEB_API_CHECK_FACETS_ROUTE,
    WEB_API_CHECK_GROUPS_ROUTE,
    WEB_API_CHECK_ROUTE,
    WEB_CORRELATION_HEADER_NAME,
)
from omym2.domain.models.check_issue import (  # FastAPI resolves query enums.
    CheckIssueGrouping,
    CheckIssueType,
)
from omym2.features.check.dto import (
    CheckIssueFacetsRequest,
    GroupCheckIssuesRequest,
    ListCheckIssuesRequest,
)
from omym2.features.check.usecases.list_check_issues import GROUP_FILTER_PAIRING_MESSAGE
from omym2.shared.ids import LibraryId
from omym2.shared.pagination import CursorDecodeError, encode_cursor

if TYPE_CHECKING:
    from collections.abc import Callable

    from omym2.domain.models.check_issue import CheckIssue
    from omym2.features.check.dto import (
        CheckIssueFacetsResult,
        ListCheckIssuesResult,
    )
    from omym2.features.common_ports import CheckIssueGroup
    from omym2.shared.pagination import Page

CHECK_HANDLERS_UNAVAILABLE_MESSAGE = "Check route handlers are unavailable."


@dataclass(frozen=True, slots=True)
class CheckRouteHandlers:
    """Read-only persisted Check handlers supplied by the composition root."""

    list_check_issues: Callable[[ListCheckIssuesRequest], ListCheckIssuesResult]
    get_check_issue_facets: Callable[[CheckIssueFacetsRequest], CheckIssueFacetsResult]
    group_check_issues: Callable[[GroupCheckIssuesRequest], Page[CheckIssueGroup]]


def get_check_route_handlers(context: ApiContext) -> CheckRouteHandlers:
    """Resolve Check-specific collaborators from the shared route context."""
    handlers = getattr(context, "check", None)
    if handlers is None:
        raise RuntimeError(CHECK_HANDLERS_UNAVAILABLE_MESSAGE)
    return cast("CheckRouteHandlers", cast("object", handlers))


type CheckContext = Annotated[CheckRouteHandlers, Depends(get_check_route_handlers)]


def create_check_router() -> APIRouter:
    """Create persisted Check routes without resolving application state."""
    router = APIRouter()
    common_responses: dict[int | str, dict[str, object]] = {
        HTTP_OK_STATUS: {"headers": {WEB_CORRELATION_HEADER_NAME: CORRELATION_HEADER_SCHEMA}},
        HTTP_UNPROCESSABLE_CONTENT_STATUS: {"model": ApiFailureEnvelope},
        HTTP_INTERNAL_ERROR_STATUS: {"model": ApiFailureEnvelope},
    }

    @router.get(
        WEB_API_CHECK_ROUTE,
        operation_id="getCheckIssues",
        response_model=ApiEnvelope[CheckIssuesData],
        responses=common_responses,
    )
    def get_check_issues(  # noqa: PLR0913  # pyright: ignore[reportUnusedFunction]  # FastAPI route contract.
        context: CheckContext,
        query: str | None = None,
        issue_type: CheckIssueType | None = None,
        group_by: CheckIssueGrouping | None = None,
        group_key: str | None = None,
        library_id: UUID | None = None,
        limit: int | None = None,
        cursor: str | None = None,
    ) -> ApiEnvelope[CheckIssuesData] | JSONResponse:
        if (group_by is None) != (group_key is None):
            return validation_failure(field="query.group_by", message=GROUP_FILTER_PAIRING_MESSAGE)
        try:
            page = page_request(limit, cursor)
            result = context.list_check_issues(
                ListCheckIssuesRequest(
                    library_id=None if library_id is None else LibraryId(library_id),
                    search=query,
                    issue_type=issue_type,
                    grouping=group_by,
                    group_key=group_key,
                    page=page,
                )
            )
        except CursorDecodeError:
            return validation_failure(field="query.cursor", message=INVALID_CURSOR_MESSAGE)
        except ValueError:
            return validation_failure(field="query.limit", message=INVALID_LIMIT_MESSAGE)

        return ApiEnvelope(
            data=CheckIssuesData(
                items=tuple(_check_issue_resource(issue) for issue in result.page.items),
                page=_page_info(result.page, page.limit),
                checked_at=result.checked_at,
            ),
            errors=(),
        )

    @router.get(
        WEB_API_CHECK_FACETS_ROUTE,
        operation_id="getCheckIssueFacets",
        response_model=ApiEnvelope[CheckIssueFacetsData],
        responses=common_responses,
    )
    def get_check_issue_facets(  # pyright: ignore[reportUnusedFunction]  # FastAPI calls decorator-registered routes.
        context: CheckContext,
        query: str | None = None,
        library_id: UUID | None = None,
    ) -> ApiEnvelope[CheckIssueFacetsData]:
        result = context.get_check_issue_facets(
            CheckIssueFacetsRequest(
                library_id=None if library_id is None else LibraryId(library_id),
                search=query,
            )
        )
        return ApiEnvelope(
            data=CheckIssueFacetsData(
                facets=CheckIssueFacetSets(
                    issue_type=tuple(
                        FacetValueResource(value=CheckIssueType(item.value), count=item.count) for item in result.facets
                    )
                ),
                total=result.total,
                checked_at=result.checked_at,
            ),
            errors=(),
        )

    @router.get(
        WEB_API_CHECK_GROUPS_ROUTE,
        operation_id="getCheckIssueGroups",
        response_model=ApiEnvelope[CheckIssueGroupsData],
        responses=common_responses,
    )
    def get_check_issue_groups(  # noqa: PLR0913  # pyright: ignore[reportUnusedFunction]  # FastAPI route contract.
        context: CheckContext,
        group_by: CheckIssueGrouping,
        query: str | None = None,
        issue_type: CheckIssueType | None = None,
        library_id: UUID | None = None,
        limit: int | None = None,
        cursor: str | None = None,
    ) -> ApiEnvelope[CheckIssueGroupsData] | JSONResponse:
        try:
            page = page_request(limit, cursor)
            result = context.group_check_issues(
                GroupCheckIssuesRequest(
                    library_id=None if library_id is None else LibraryId(library_id),
                    search=query,
                    issue_type=issue_type,
                    grouping=group_by,
                    page=page,
                )
            )
        except CursorDecodeError:
            return validation_failure(field="query.cursor", message=INVALID_CURSOR_MESSAGE)
        except ValueError:
            return validation_failure(field="query.limit", message=INVALID_LIMIT_MESSAGE)
        return ApiEnvelope(
            data=CheckIssueGroupsData(
                group_by=group_by,
                items=tuple(
                    CheckIssueGroupResource(
                        key=item.key,
                        label=item.label,
                        count=item.count,
                        common_path_root=item.common_path_root,
                    )
                    for item in result.items
                ),
                page=_page_info(result, page.limit),
            ),
            errors=(),
        )

    return router


def _check_issue_resource(issue: CheckIssue) -> CheckIssueResource:
    return CheckIssueResource(
        issue_type=issue.issue_type,
        library_id=issue.library_id,
        path=issue.path,
        track_id=issue.track_id,
        plan_id=issue.plan_id,
        detail=issue.detail,
    )


def _page_info[Item](page: Page[Item], limit: int) -> PageInfo:
    return PageInfo(
        limit=limit,
        next_cursor=None if page.next_cursor_key is None else encode_cursor(page.next_cursor_key),
        total=page.total,
    )
