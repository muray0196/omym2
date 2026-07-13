"""
Summary: Implements typed read-only Run and FileEvent inspection routes.
Why: Exposes durable execution evidence without mutating managed state.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING, Annotated, Literal, cast
from uuid import UUID  # noqa: TC003  # FastAPI resolves path and query annotations.

from fastapi import APIRouter, Depends
from fastapi.responses import JSONResponse  # noqa: TC002  # FastAPI resolves route return annotations.

from omym2.adapters.web.routes.api_context import ApiContext  # noqa: TC001  # FastAPI resolves dependencies.
from omym2.adapters.web.routes.read_query import (
    CORRELATION_HEADER_SCHEMA,
    INVALID_CURSOR_MESSAGE,
    INVALID_LIMIT_MESSAGE,
    not_found_failure,
    page_request,
    validation_failure,
)
from omym2.adapters.web.schemas.api_envelopes import ApiEnvelope, ApiFailureEnvelope
from omym2.adapters.web.schemas.api_errors import ApiError, ApiErrorCode, ApiRemediation
from omym2.adapters.web.schemas.browsing import (
    FacetValueResource,
    GroupResource,
    PageInfo,
    PaginatedData,
)
from omym2.adapters.web.schemas.history import (
    FileEventFacetsData,
    FileEventFacetSets,
    FileEventGroupsData,
    FileEventResource,
    RunCapabilities,
    RunDetailData,
    RunFacetsData,
    RunFacetSets,
    RunHeader,
)
from omym2.config import (
    HTTP_INTERNAL_ERROR_STATUS,
    HTTP_NOT_FOUND_STATUS,
    HTTP_OK_STATUS,
    HTTP_UNPROCESSABLE_CONTENT_STATUS,
    WEB_API_HISTORY_FACETS_ROUTE,
    WEB_API_HISTORY_ROUTE,
    WEB_API_RUN_DETAIL_ROUTE,
    WEB_API_RUN_EVENT_FACETS_ROUTE,
    WEB_API_RUN_EVENT_GROUPS_ROUTE,
    WEB_API_RUN_EVENTS_ROUTE,
    WEB_CORRELATION_HEADER_NAME,
)
from omym2.domain.models.file_event import (  # FastAPI resolves query enums.
    FileEventStatus,
)
from omym2.domain.models.run import RunStatus  # FastAPI resolves query enums.
from omym2.features.history.dto import (
    FileEventStatusFacetsRequest,
    GetRunHeaderRequest,
    GroupRunEventsRequest,
    ListRunEventsRequest,
    ListRunsRequest,
    RunCapabilityReason,
    RunStatusFacetsRequest,
)
from omym2.features.history.usecases.get_run_header import RUN_NOT_FOUND_MESSAGE, RunNotFoundError
from omym2.shared.ids import LibraryId, PlanId, RunId
from omym2.shared.pagination import CursorDecodeError, encode_cursor

if TYPE_CHECKING:
    from collections.abc import Callable

    from omym2.domain.models.file_event import FileEvent
    from omym2.domain.models.run import Run
    from omym2.features.history.dto import (
        FileEventStatusFacetsResult,
        RunDetailResult,
        RunStatusFacetsResult,
    )
    from omym2.shared.ids import OperationId
    from omym2.shared.pagination import GroupCount, Page

HISTORY_HANDLERS_UNAVAILABLE_MESSAGE = "History route handlers are unavailable."


@dataclass(frozen=True, slots=True)
class HistoryRouteHandlers:
    """Read-only History handlers supplied by the composition root."""

    list_runs: Callable[[ListRunsRequest], Page[Run]]
    get_run_detail: Callable[[GetRunHeaderRequest], RunDetailResult]
    get_run_status_facets: Callable[[RunStatusFacetsRequest], RunStatusFacetsResult]
    list_run_events: Callable[[ListRunEventsRequest], Page[FileEvent]]
    get_file_event_status_facets: Callable[[FileEventStatusFacetsRequest], FileEventStatusFacetsResult]
    group_run_events: Callable[[GroupRunEventsRequest], Page[GroupCount]]
    active_operation_id: Callable[[RunId], OperationId | None]


def get_history_route_handlers(context: ApiContext) -> HistoryRouteHandlers:
    """Resolve History-specific collaborators from the shared route context."""
    handlers = getattr(context, "history", None)
    if handlers is None:
        raise RuntimeError(HISTORY_HANDLERS_UNAVAILABLE_MESSAGE)
    return cast("HistoryRouteHandlers", cast("object", handlers))


type HistoryContext = Annotated[HistoryRouteHandlers, Depends(get_history_route_handlers)]


def create_history_router() -> APIRouter:  # noqa: C901  # One factory keeps the route family together.
    """Create History routes without resolving application state."""
    router = APIRouter()
    common_responses: dict[int | str, dict[str, object]] = {
        HTTP_OK_STATUS: {"headers": {WEB_CORRELATION_HEADER_NAME: CORRELATION_HEADER_SCHEMA}},
        HTTP_UNPROCESSABLE_CONTENT_STATUS: {"model": ApiFailureEnvelope},
        HTTP_INTERNAL_ERROR_STATUS: {"model": ApiFailureEnvelope},
    }

    @router.get(
        WEB_API_HISTORY_ROUTE,
        operation_id="getHistory",
        response_model=ApiEnvelope[PaginatedData[RunHeader]],
        responses=common_responses,
    )
    def get_history(  # noqa: PLR0913  # pyright: ignore[reportUnusedFunction]  # FastAPI route contract.
        context: HistoryContext,
        query: str | None = None,
        status: RunStatus | None = None,
        plan_id: UUID | None = None,
        library_id: UUID | None = None,
        limit: int | None = None,
        cursor: str | None = None,
    ) -> ApiEnvelope[PaginatedData[RunHeader]] | JSONResponse:
        try:
            page = page_request(limit, cursor)
            result = context.list_runs(
                ListRunsRequest(
                    library_id=None if library_id is None else LibraryId(library_id),
                    search=query,
                    plan_id=None if plan_id is None else PlanId(plan_id),
                    status=status,
                    page=page,
                )
            )
        except CursorDecodeError:
            return validation_failure(field="query.cursor", message=INVALID_CURSOR_MESSAGE)
        except ValueError:
            return validation_failure(field="query.limit", message=INVALID_LIMIT_MESSAGE)
        return ApiEnvelope(data=_run_page(result, page.limit), errors=())

    @router.get(
        WEB_API_HISTORY_FACETS_ROUTE,
        operation_id="getHistoryFacets",
        response_model=ApiEnvelope[RunFacetsData],
        responses=common_responses,
    )
    def get_history_facets(  # pyright: ignore[reportUnusedFunction]  # FastAPI calls decorator-registered routes.
        context: HistoryContext,
        library_id: UUID | None = None,
    ) -> ApiEnvelope[RunFacetsData]:
        result = context.get_run_status_facets(
            RunStatusFacetsRequest(library_id=None if library_id is None else LibraryId(library_id))
        )
        return ApiEnvelope(
            data=RunFacetsData(
                facets=RunFacetSets(
                    status=tuple(
                        FacetValueResource(value=RunStatus(item.value), count=item.count) for item in result.facets
                    )
                ),
                total=result.total,
            ),
            errors=(),
        )

    @router.get(
        WEB_API_RUN_DETAIL_ROUTE,
        operation_id="getRun",
        response_model=ApiEnvelope[RunDetailData],
        responses={**common_responses, HTTP_NOT_FOUND_STATUS: {"model": ApiFailureEnvelope}},
    )
    def get_run(  # pyright: ignore[reportUnusedFunction]  # FastAPI calls decorator-registered routes.
        run_id: UUID,
        context: HistoryContext,
    ) -> ApiEnvelope[RunDetailData] | JSONResponse:
        try:
            result = context.get_run_detail(GetRunHeaderRequest(run_id=RunId(run_id)))
        except RunNotFoundError:
            return not_found_failure(ApiErrorCode.RUN_NOT_FOUND, RUN_NOT_FOUND_MESSAGE, field="path.run_id")
        return ApiEnvelope(
            data=RunDetailData(
                run=_run_resource(result.run),
                capabilities=RunCapabilities(
                    can_create_undo=result.capabilities.can_create_undo,
                    disabled_reasons=tuple(
                        _run_capability_error(reason) for reason in result.capabilities.disabled_reasons
                    ),
                ),
                active_operation_id=context.active_operation_id(result.run.run_id),
            ),
            errors=(),
        )

    @router.get(
        WEB_API_RUN_EVENTS_ROUTE,
        operation_id="getRunEvents",
        response_model=ApiEnvelope[PaginatedData[FileEventResource]],
        responses={**common_responses, HTTP_NOT_FOUND_STATUS: {"model": ApiFailureEnvelope}},
    )
    def get_run_events(  # pyright: ignore[reportUnusedFunction]  # FastAPI calls decorator-registered routes.
        run_id: UUID,
        context: HistoryContext,
        status: FileEventStatus | None = None,
        limit: int | None = None,
        cursor: str | None = None,
    ) -> ApiEnvelope[PaginatedData[FileEventResource]] | JSONResponse:
        try:
            page = page_request(limit, cursor)
            result = context.list_run_events(ListRunEventsRequest(run_id=RunId(run_id), status=status, page=page))
        except RunNotFoundError:
            return not_found_failure(ApiErrorCode.RUN_NOT_FOUND, RUN_NOT_FOUND_MESSAGE, field="path.run_id")
        except CursorDecodeError:
            return validation_failure(field="query.cursor", message=INVALID_CURSOR_MESSAGE)
        except ValueError:
            return validation_failure(field="query.limit", message=INVALID_LIMIT_MESSAGE)
        return ApiEnvelope(data=_event_page(result, page.limit), errors=())

    @router.get(
        WEB_API_RUN_EVENT_FACETS_ROUTE,
        operation_id="getRunEventFacets",
        response_model=ApiEnvelope[FileEventFacetsData],
        responses={**common_responses, HTTP_NOT_FOUND_STATUS: {"model": ApiFailureEnvelope}},
    )
    def get_run_event_facets(  # pyright: ignore[reportUnusedFunction]  # FastAPI calls decorator-registered routes.
        run_id: UUID,
        context: HistoryContext,
    ) -> ApiEnvelope[FileEventFacetsData] | JSONResponse:
        try:
            result = context.get_file_event_status_facets(FileEventStatusFacetsRequest(run_id=RunId(run_id)))
        except RunNotFoundError:
            return not_found_failure(ApiErrorCode.RUN_NOT_FOUND, RUN_NOT_FOUND_MESSAGE, field="path.run_id")
        return ApiEnvelope(
            data=FileEventFacetsData(
                facets=FileEventFacetSets(
                    status=tuple(
                        FacetValueResource(value=FileEventStatus(item.value), count=item.count)
                        for item in result.facets
                    )
                ),
                total=result.total,
            ),
            errors=(),
        )

    @router.get(
        WEB_API_RUN_EVENT_GROUPS_ROUTE,
        operation_id="getRunEventGroups",
        response_model=ApiEnvelope[FileEventGroupsData],
        responses={**common_responses, HTTP_NOT_FOUND_STATUS: {"model": ApiFailureEnvelope}},
    )
    def get_run_event_groups(  # pyright: ignore[reportUnusedFunction]  # FastAPI calls decorator-registered routes.
        run_id: UUID,
        context: HistoryContext,
        group_by: Literal["target_directory"],
        limit: int | None = None,
        cursor: str | None = None,
    ) -> ApiEnvelope[FileEventGroupsData] | JSONResponse:
        try:
            page = page_request(limit, cursor)
            result = context.group_run_events(GroupRunEventsRequest(run_id=RunId(run_id), page=page))
        except RunNotFoundError:
            return not_found_failure(ApiErrorCode.RUN_NOT_FOUND, RUN_NOT_FOUND_MESSAGE, field="path.run_id")
        except CursorDecodeError:
            return validation_failure(field="query.cursor", message=INVALID_CURSOR_MESSAGE)
        except ValueError:
            return validation_failure(field="query.limit", message=INVALID_LIMIT_MESSAGE)
        return ApiEnvelope(
            data=FileEventGroupsData(
                group_by=group_by,
                items=tuple(GroupResource(key=item.key, label=item.label, count=item.count) for item in result.items),
                page=_page_info(result, page.limit),
            ),
            errors=(),
        )

    return router


def _run_page(page: Page[Run], limit: int) -> PaginatedData[RunHeader]:
    return PaginatedData(items=tuple(_run_resource(item) for item in page.items), page=_page_info(page, limit))


def _event_page(page: Page[FileEvent], limit: int) -> PaginatedData[FileEventResource]:
    return PaginatedData(items=tuple(_event_resource(item) for item in page.items), page=_page_info(page, limit))


def _page_info[Item](page: Page[Item], limit: int) -> PageInfo:
    return PageInfo(
        limit=limit,
        next_cursor=None if page.next_cursor_key is None else encode_cursor(page.next_cursor_key),
        total=page.total,
    )


def _run_resource(run: Run) -> RunHeader:
    return RunHeader(
        run_id=run.run_id,
        plan_id=run.plan_id,
        library_id=run.library_id,
        status=run.status,
        started_at=run.started_at,
        completed_at=run.completed_at,
        error_summary=run.error_summary,
    )


def _event_resource(event: FileEvent) -> FileEventResource:
    return FileEventResource(
        event_id=event.event_id,
        library_id=event.library_id,
        run_id=event.run_id,
        plan_action_id=event.plan_action_id,
        event_type=event.event_type,
        source_path=event.source_path,
        target_path=event.target_path,
        status=event.status,
        started_at=event.started_at,
        completed_at=event.completed_at,
        error_code=event.error_code,
        error_message=event.error_message,
        sequence_no=event.sequence_no,
    )


def _run_capability_error(reason: RunCapabilityReason) -> ApiError:
    definitions = {
        RunCapabilityReason.RUN_NOT_TERMINAL: ("The Run has not finished.", None),
        RunCapabilityReason.NOTHING_TO_UNDO: ("The Run has no confirmed file mutation to undo.", None),
        RunCapabilityReason.UNDO_REFRESH_METADATA_UNSUPPORTED: (
            "Runs containing refresh metadata work cannot be undone.",
            None,
        ),
        RunCapabilityReason.PENDING_FILE_EVENT_REQUIRES_REVIEW: (
            "A pending FileEvent requires manual review before Undo planning.",
            ApiRemediation(label="Open Health", route="/health"),
        ),
        RunCapabilityReason.ALREADY_UNDONE_OR_IN_PROGRESS: (
            "Undo has already been applied or is in progress for this Run.",
            None,
        ),
    }
    message, remediation = definitions[reason]
    if remediation is None:
        return ApiError(
            code=ApiErrorCode(reason.value),
            message=message,
            field="capabilities.can_create_undo",
            retryable=False,
        )
    return ApiError(
        code=ApiErrorCode(reason.value),
        message=message,
        field="capabilities.can_create_undo",
        retryable=False,
        remediation=remediation,
    )
