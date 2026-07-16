"""
Summary: Implements Plan inspection and ready-Plan cancellation Web API routes.
Why: Gives Plan Review typed evidence and a lock-protected synchronous Cancel action.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from typing import TYPE_CHECKING, Annotated, cast
from uuid import UUID

from fastapi import APIRouter, Depends, Header, Query
from fastapi.responses import JSONResponse  # noqa: TC002  # FastAPI resolves response annotations at registration.

from omym2.adapters.web.routes.api_context import (
    ApiContext,  # noqa: TC001  # FastAPI resolves dependency annotations at registration.
)
from omym2.adapters.web.routes.api_responses import api_failure_response
from omym2.adapters.web.routes.operations import operation_in_progress_failure
from omym2.adapters.web.schemas.api_envelopes import ApiEnvelope, ApiFailureEnvelope
from omym2.adapters.web.schemas.api_errors import ApiError, ApiErrorCode, ApiRemediation
from omym2.adapters.web.schemas.browsing import FacetValueResource, PageInfo, PaginatedData
from omym2.adapters.web.schemas.plans import (
    ArtistNameDiagnosticsResource,
    ArtistNameResolutionDiagnosticResource,
    PlanActionFacetsData,
    PlanActionFacetSets,
    PlanActionGroupResource,
    PlanActionGroupsData,
    PlanActionResource,
    PlanActionSummary,
    PlanActionSummaryCounts,
    PlanActionTypeCounts,
    PlanCapabilities,
    PlanDetailData,
    PlanHeader,
    PlanSummary,
)
from omym2.config import (
    HTTP_CONFLICT_STATUS,
    HTTP_FORBIDDEN_STATUS,
    HTTP_INTERNAL_ERROR_STATUS,
    HTTP_NOT_FOUND_STATUS,
    HTTP_OK_STATUS,
    HTTP_UNPROCESSABLE_CONTENT_STATUS,
    WEB_API_CANCEL_PLAN_ROUTE,
    WEB_API_PLAN_ACTIONS_ROUTE,
    WEB_API_PLAN_DETAIL_ROUTE,
    WEB_API_PLAN_FACETS_ROUTE,
    WEB_API_PLAN_GROUPS_ROUTE,
    WEB_API_PLANS_ROUTE,
    WEB_CORRELATION_HEADER_NAME,
    WEB_CSRF_HEADER_NAME,
)
from omym2.domain.models.plan import PlanStatus, PlanType
from omym2.domain.models.plan_action import (
    ActionStatus,
    ActionType,
    PlanActionReason,
)
from omym2.features.common_ports import ExclusiveOperationBusyError
from omym2.features.plans.dto import (
    CancelPlanRequest,
    GetPlanActionDependenciesRequest,
    GetPlanActionSummariesRequest,
    GetPlanHeaderRequest,
    GroupPlanActionsRequest,
    ListPlanActionsRequest,
    ListPlansRequest,
    PlanActionFacetsRequest,
    PlanActionGrouping,
    plan_action_summary_from_counts,
)
from omym2.features.plans.usecases.cancel_plan import (
    PLAN_NOT_READY_MESSAGE,
    PlanCannotBeCancelledError,
)
from omym2.features.plans.usecases.get_plan_capabilities import (
    GetPlanCapabilitiesRequest,
    PlanCapabilitiesResult,
    PlanCapability,
    PlanCapabilityReason,
)
from omym2.features.plans.usecases.get_plan_header import PlanNotFoundError
from omym2.shared.ids import OperationId, PlanId
from omym2.shared.pagination import (
    DEFAULT_PAGE_LIMIT,
    CursorDecodeError,
    PageRequest,
    clamp_limit,
    decode_cursor,
    encode_cursor,
)

if TYPE_CHECKING:
    from collections.abc import Callable, Mapping

    from omym2.domain.models.artist_name_resolution import (
        ArtistNameDiagnostics,
        ArtistNameResolutionDiagnostic,
    )
    from omym2.domain.models.plan import Plan
    from omym2.domain.models.plan_action import PlanAction
    from omym2.features.plans.dto import PlanActionFacetsResult, PlanActionGroup
    from omym2.features.plans.dto import PlanActionSummary as PlanActionSummaryDto
    from omym2.features.plans.dto import PlanActionTypeCounts as PlanActionTypeCountsDto
    from omym2.shared.ids import ActionId
    from omym2.shared.pagination import Page

PLAN_NOT_FOUND_MESSAGE = "Plan was not found."
INVALID_PLAN_QUERY_MESSAGE = "Plan browse query is invalid."
PLAN_HANDLERS_UNAVAILABLE_MESSAGE = "Plan route handlers are unavailable."
PLAN_CURSOR_KEY_LENGTH = 2  # Plan list cursors carry created_at and plan_id.
PLAN_ACTION_CURSOR_KEY_LENGTH = 2  # PlanAction cursors carry sort_order and action_id.
PLAN_GROUP_CURSOR_KEY_LENGTH = 2  # PlanAction group cursors carry count and group key.
CORRELATION_HEADER_SCHEMA = {
    "description": "Request correlation identifier written to server logs.",
    "schema": {"type": "string"},
}


@dataclass(frozen=True, slots=True)
class PlanRouteHandlers:
    """Read-only Plan handlers supplied by the composition root."""

    list_plans: Callable[[ListPlansRequest], Page[Plan]]
    get_plan_header: Callable[[GetPlanHeaderRequest], Plan]
    get_plan_action_summaries: Callable[[GetPlanActionSummariesRequest], dict[PlanId, PlanActionSummaryDto]]
    get_plan_capabilities: Callable[[GetPlanCapabilitiesRequest], PlanCapabilitiesResult]
    list_plan_actions: Callable[[ListPlanActionsRequest], Page[PlanAction]]
    get_plan_action_dependencies: Callable[
        [GetPlanActionDependenciesRequest],
        Mapping[ActionId, tuple[ActionId, ...]],
    ]
    get_plan_action_facets: Callable[[PlanActionFacetsRequest], PlanActionFacetsResult]
    group_plan_actions: Callable[[GroupPlanActionsRequest], Page[PlanActionGroup]]
    cancel_plan: Callable[[CancelPlanRequest], Plan]
    active_operation_id: Callable[[PlanId], OperationId | None]
    conflicting_operation_id: Callable[[], OperationId | None]


def get_plan_route_handlers(context: ApiContext) -> PlanRouteHandlers:
    """Resolve the Plan-specific collaborators from the shared route context."""
    handlers = context.plans
    if handlers is None:
        raise RuntimeError(PLAN_HANDLERS_UNAVAILABLE_MESSAGE)
    return cast("PlanRouteHandlers", cast("object", handlers))


type PlansContext = Annotated[PlanRouteHandlers, Depends(get_plan_route_handlers)]
type CsrfToken = Annotated[str, Header(alias=WEB_CSRF_HEADER_NAME, min_length=1)]


def create_plans_router() -> APIRouter:  # noqa: C901  # One factory registers the fixed Plan route set.
    """Create the read-only Plan list, detail, action, facet, and group routes."""
    router = APIRouter()
    response_headers = {WEB_CORRELATION_HEADER_NAME: CORRELATION_HEADER_SCHEMA}
    error_responses = {
        HTTP_NOT_FOUND_STATUS: {"model": ApiFailureEnvelope, "headers": response_headers},
        HTTP_UNPROCESSABLE_CONTENT_STATUS: {"model": ApiFailureEnvelope, "headers": response_headers},
        HTTP_INTERNAL_ERROR_STATUS: {"model": ApiFailureEnvelope, "headers": response_headers},
    }

    @router.get(
        WEB_API_PLANS_ROUTE,
        operation_id="listPlans",
        response_model=ApiEnvelope[PaginatedData[PlanSummary]],
        responses={HTTP_OK_STATUS: {"headers": response_headers}, **error_responses},
    )
    def list_plans(  # noqa: PLR0913  # pyright: ignore[reportUnusedFunction]  # FastAPI route contract.
        context: PlansContext,
        query_text: Annotated[str | None, Query(alias="query")] = None,
        status: PlanStatus | None = None,
        plan_type: Annotated[PlanType | None, Query(alias="type")] = None,
        blocked: bool = False,  # noqa: FBT001, FBT002  # FastAPI binds this public boolean query parameter.
        limit: Annotated[int, Query(ge=1)] = DEFAULT_PAGE_LIMIT,
        cursor: str | None = None,
    ) -> ApiEnvelope[PaginatedData[PlanSummary]] | JSONResponse:
        try:
            page_request = _page_request(limit, cursor, _is_plan_cursor)
            page = context.list_plans(
                ListPlansRequest(
                    search=query_text,
                    status=status,
                    plan_type=plan_type,
                    blocked_only=blocked,
                    page=page_request,
                )
            )
        except CursorDecodeError, ValueError:
            return _invalid_plan_query("query.cursor" if cursor is not None else "query.limit")

        plan_ids = tuple(plan.plan_id for plan in page.items)
        summaries = context.get_plan_action_summaries(GetPlanActionSummariesRequest(plan_ids))
        items = tuple(_plan_summary(plan, summaries[plan.plan_id]) for plan in page.items)
        return ApiEnvelope(data=PaginatedData(items=items, page=_page_info(page, page_request)), errors=())

    @router.get(
        WEB_API_PLAN_DETAIL_ROUTE,
        operation_id="getPlan",
        response_model=ApiEnvelope[PlanDetailData],
        responses={HTTP_OK_STATUS: {"headers": response_headers}, **error_responses},
    )
    def get_plan(  # pyright: ignore[reportUnusedFunction]  # FastAPI calls decorator-registered routes.
        plan_id: UUID,
        context: PlansContext,
    ) -> ApiEnvelope[PlanDetailData] | JSONResponse:
        typed_plan_id = PlanId(plan_id)
        try:
            plan = context.get_plan_header(GetPlanHeaderRequest(typed_plan_id))
            summaries = context.get_plan_action_summaries(GetPlanActionSummariesRequest((typed_plan_id,)))
            capabilities = context.get_plan_capabilities(GetPlanCapabilitiesRequest(typed_plan_id))
        except PlanNotFoundError:
            return _plan_not_found()

        return ApiEnvelope(
            data=_plan_detail_data(
                context,
                plan,
                summaries[typed_plan_id],
                capabilities,
            ),
            errors=(),
        )

    @router.get(
        WEB_API_PLAN_ACTIONS_ROUTE,
        operation_id="listPlanActions",
        response_model=ApiEnvelope[PaginatedData[PlanActionResource]],
        responses={HTTP_OK_STATUS: {"headers": response_headers}, **error_responses},
    )
    def list_plan_actions(  # noqa: PLR0913  # pyright: ignore[reportUnusedFunction]  # FastAPI route contract.
        plan_id: UUID,
        context: PlansContext,
        query_text: Annotated[str | None, Query(alias="query")] = None,
        status: ActionStatus | None = None,
        action_type: ActionType | None = None,
        reason: PlanActionReason | None = None,
        group_by: PlanActionGrouping | None = None,
        group_key: str | None = None,
        limit: Annotated[int, Query(ge=1)] = DEFAULT_PAGE_LIMIT,
        cursor: str | None = None,
    ) -> ApiEnvelope[PaginatedData[PlanActionResource]] | JSONResponse:
        try:
            if (group_by is None) != (group_key is None):
                field = "query.group_by" if group_by is None else "query.group_key"
                return _invalid_plan_query(field)
            page_request = _page_request(limit, cursor, _is_plan_action_cursor)
            page = context.list_plan_actions(
                ListPlanActionsRequest(
                    plan_id=PlanId(plan_id),
                    search=query_text,
                    status=status,
                    action_type=action_type,
                    reason=reason,
                    grouping=group_by,
                    group_key=group_key,
                    page=page_request,
                )
            )
        except PlanNotFoundError:
            return _plan_not_found()
        except CursorDecodeError, ValueError:
            return _invalid_plan_query("query.cursor" if cursor is not None else "query.group_by")

        dependencies = context.get_plan_action_dependencies(
            GetPlanActionDependenciesRequest(tuple(action.action_id for action in page.items))
        )
        items = tuple(_plan_action_resource(action, dependencies.get(action.action_id, ())) for action in page.items)
        return ApiEnvelope(data=PaginatedData(items=items, page=_page_info(page, page_request)), errors=())

    @router.get(
        WEB_API_PLAN_FACETS_ROUTE,
        operation_id="getPlanActionFacets",
        response_model=ApiEnvelope[PlanActionFacetsData],
        responses={HTTP_OK_STATUS: {"headers": response_headers}, **error_responses},
    )
    def get_plan_action_facets(  # noqa: PLR0913  # pyright: ignore[reportUnusedFunction]  # FastAPI route contract.
        plan_id: UUID,
        context: PlansContext,
        query_text: Annotated[str | None, Query(alias="query")] = None,
        status: ActionStatus | None = None,
        action_type: ActionType | None = None,
        reason: PlanActionReason | None = None,
    ) -> ApiEnvelope[PlanActionFacetsData] | JSONResponse:
        try:
            result = context.get_plan_action_facets(
                PlanActionFacetsRequest(
                    plan_id=PlanId(plan_id),
                    search=query_text,
                    status=status,
                    action_type=action_type,
                    reason=reason,
                )
            )
        except PlanNotFoundError:
            return _plan_not_found()
        return ApiEnvelope(data=_plan_action_facets(result), errors=())

    @router.get(
        WEB_API_PLAN_GROUPS_ROUTE,
        operation_id="groupPlanActions",
        response_model=ApiEnvelope[PlanActionGroupsData],
        responses={HTTP_OK_STATUS: {"headers": response_headers}, **error_responses},
    )
    def get_plan_action_groups(  # noqa: PLR0913  # pyright: ignore[reportUnusedFunction]  # FastAPI route contract.
        plan_id: UUID,
        context: PlansContext,
        group_by: PlanActionGrouping,
        query_text: Annotated[str | None, Query(alias="query")] = None,
        status: ActionStatus | None = None,
        action_type: ActionType | None = None,
        reason: PlanActionReason | None = None,
        limit: Annotated[int, Query(ge=1)] = DEFAULT_PAGE_LIMIT,
        cursor: str | None = None,
    ) -> ApiEnvelope[PlanActionGroupsData] | JSONResponse:
        try:
            page_request = _page_request(limit, cursor, _is_plan_group_cursor)
            page = context.group_plan_actions(
                GroupPlanActionsRequest(
                    plan_id=PlanId(plan_id),
                    search=query_text,
                    status=status,
                    action_type=action_type,
                    reason=reason,
                    grouping=group_by,
                    page=page_request,
                )
            )
        except PlanNotFoundError:
            return _plan_not_found()
        except CursorDecodeError, ValueError:
            return _invalid_plan_query("query.cursor" if cursor is not None else "query.group_by")

        data = PlanActionGroupsData(
            group_by=group_by,
            items=tuple(
                PlanActionGroupResource(
                    key=group.key,
                    label=group.label,
                    count=group.count,
                    blocked_count=group.blocked_count,
                    top_reason=None if group.top_reason is None else PlanActionReason(group.top_reason),
                )
                for group in page.items
            ),
            page=_page_info(page, page_request),
        )
        return ApiEnvelope(data=data, errors=())

    return router


def create_plan_mutation_router() -> APIRouter:
    """Create the synchronous ready-Plan cancellation route without application I/O."""
    router = APIRouter()
    response_headers = {WEB_CORRELATION_HEADER_NAME: CORRELATION_HEADER_SCHEMA}

    @router.post(
        WEB_API_CANCEL_PLAN_ROUTE,
        operation_id="cancelPlan",
        response_model=ApiEnvelope[PlanDetailData],
        responses={
            HTTP_OK_STATUS: {"headers": response_headers},
            HTTP_FORBIDDEN_STATUS: {"model": ApiFailureEnvelope, "headers": response_headers},
            HTTP_NOT_FOUND_STATUS: {"model": ApiFailureEnvelope, "headers": response_headers},
            HTTP_CONFLICT_STATUS: {"model": ApiFailureEnvelope, "headers": response_headers},
            HTTP_UNPROCESSABLE_CONTENT_STATUS: {"model": ApiFailureEnvelope, "headers": response_headers},
            HTTP_INTERNAL_ERROR_STATUS: {"model": ApiFailureEnvelope, "headers": response_headers},
        },
    )
    def cancel_plan(  # pyright: ignore[reportUnusedFunction]  # FastAPI calls decorator-registered routes.
        plan_id: UUID,
        context: PlansContext,
        csrf_token: CsrfToken,
    ) -> ApiEnvelope[PlanDetailData] | JSONResponse:
        _ = csrf_token
        typed_plan_id = PlanId(plan_id)
        try:
            plan = context.cancel_plan(CancelPlanRequest(typed_plan_id))
            summaries = context.get_plan_action_summaries(GetPlanActionSummariesRequest((typed_plan_id,)))
            capabilities = context.get_plan_capabilities(GetPlanCapabilitiesRequest(typed_plan_id))
        except PlanNotFoundError:
            return _plan_not_found()
        except PlanCannotBeCancelledError:
            return _plan_not_ready()
        except ExclusiveOperationBusyError:
            return operation_in_progress_failure(context.conflicting_operation_id())
        return ApiEnvelope(
            data=_plan_detail_data(context, plan, summaries[typed_plan_id], capabilities),
            errors=(),
        )

    return router


def _page_request(
    limit: int,
    cursor: str | None,
    cursor_is_valid: Callable[[tuple[str, ...]], bool],
) -> PageRequest:
    """Build one validated page request from the endpoint's opaque cursor shape."""
    cursor_key = None if cursor is None else decode_cursor(cursor)
    if cursor_key is not None and not cursor_is_valid(cursor_key):
        raise CursorDecodeError(INVALID_PLAN_QUERY_MESSAGE)
    return PageRequest(
        limit=clamp_limit(limit),
        cursor_key=cursor_key,
    )


def _is_plan_cursor(cursor_key: tuple[str, ...]) -> bool:
    """Return whether a Plan cursor has an aware timestamp and UUID tie-breaker."""
    if len(cursor_key) != PLAN_CURSOR_KEY_LENGTH:
        return False
    timestamp, plan_id = cursor_key
    try:
        parsed = datetime.fromisoformat(timestamp)
        _ = UUID(plan_id)
    except ValueError:
        return False
    return parsed.tzinfo is not None and parsed.utcoffset() is not None


def _is_plan_action_cursor(cursor_key: tuple[str, ...]) -> bool:
    """Return whether a PlanAction cursor has an integer order and UUID tie-breaker."""
    if len(cursor_key) != PLAN_ACTION_CURSOR_KEY_LENGTH:
        return False
    sort_order, action_id = cursor_key
    try:
        _ = int(sort_order)
        _ = UUID(action_id)
    except ValueError:
        return False
    return True


def _is_plan_group_cursor(cursor_key: tuple[str, ...]) -> bool:
    """Return whether a PlanAction group cursor has a non-negative count and key."""
    if len(cursor_key) != PLAN_GROUP_CURSOR_KEY_LENGTH:
        return False
    count, _key = cursor_key
    try:
        return int(count) >= 0
    except ValueError:
        return False


def _page_info[Item](page: Page[Item], request: PageRequest) -> PageInfo:
    next_cursor = None if page.next_cursor_key is None else encode_cursor(page.next_cursor_key)
    return PageInfo(limit=request.limit, next_cursor=next_cursor, total=page.total)


def _plan_summary(plan: Plan, summary: PlanActionSummaryDto | None) -> PlanSummary:
    return PlanSummary(
        plan_id=plan.plan_id,
        library_id=plan.library_id,
        plan_type=plan.plan_type,
        status=plan.status,
        created_at=plan.created_at,
        summary=_plan_action_summary(summary),
    )


def _plan_header(plan: Plan) -> PlanHeader:
    return PlanHeader(
        plan_id=plan.plan_id,
        library_id=plan.library_id,
        plan_type=plan.plan_type,
        status=plan.status,
        created_at=plan.created_at,
        config_hash=plan.config_hash,
        library_root_at_plan=plan.library_root_at_plan,
    )


def _plan_detail_data(
    context: PlanRouteHandlers,
    plan: Plan,
    summary: PlanActionSummaryDto | None,
    capabilities: PlanCapabilitiesResult,
) -> PlanDetailData:
    """Project one current Plan detail after a read or synchronous transition."""
    return PlanDetailData(
        plan=_plan_header(plan),
        summary=_plan_action_summary(summary),
        capabilities=_plan_capabilities(plan, capabilities),
        active_operation_id=context.active_operation_id(plan.plan_id),
    )


def _plan_action_summary(summary: PlanActionSummaryDto | None) -> PlanActionSummary:
    resolved = summary if summary is not None else plan_action_summary_from_counts({})
    return PlanActionSummary(
        total=resolved.total,
        counts=PlanActionSummaryCounts(
            planned=_plan_action_type_counts(resolved.planned),
            blocked=_plan_action_type_counts(resolved.blocked),
            applied=_plan_action_type_counts(resolved.applied),
            failed=_plan_action_type_counts(resolved.failed),
        ),
    )


def _plan_action_type_counts(counts: PlanActionTypeCountsDto) -> PlanActionTypeCounts:
    return PlanActionTypeCounts(
        move=counts.move,
        move_lyrics=counts.move_lyrics,
        move_artwork=counts.move_artwork,
        move_unprocessed=counts.move_unprocessed,
        skip=counts.skip,
        refresh_metadata=counts.refresh_metadata,
    )


def _plan_action_resource(
    action: PlanAction,
    depends_on_action_ids: tuple[ActionId, ...],
) -> PlanActionResource:
    return PlanActionResource(
        action_id=action.action_id,
        plan_id=action.plan_id,
        library_id=action.library_id,
        track_id=action.track_id,
        action_type=action.action_type,
        source_path=action.source_path,
        target_path=action.target_path,
        content_hash_at_plan=action.content_hash_at_plan,
        metadata_hash_at_plan=action.metadata_hash_at_plan,
        status=action.status,
        reason=action.reason,
        sort_order=action.sort_order,
        companion_asset_id=action.companion_asset_id,
        owner_action_id=action.owner_action_id,
        depends_on_action_ids=depends_on_action_ids,
        artist_name_diagnostics=_artist_name_diagnostics_resource(action.artist_name_diagnostics),
    )


def _artist_name_diagnostics_resource(
    diagnostics: ArtistNameDiagnostics | None,
) -> ArtistNameDiagnosticsResource | None:
    if diagnostics is None:
        return None
    return ArtistNameDiagnosticsResource(
        artist=_artist_name_resolution_diagnostic_resource(diagnostics.artist),
        album_artist=_artist_name_resolution_diagnostic_resource(diagnostics.album_artist),
    )


def _artist_name_resolution_diagnostic_resource(
    diagnostic: ArtistNameResolutionDiagnostic,
) -> ArtistNameResolutionDiagnosticResource:
    return ArtistNameResolutionDiagnosticResource(
        source_name=diagnostic.source_name,
        resolved_name=diagnostic.resolved_name,
        provenance=diagnostic.provenance,
        issue=diagnostic.issue,
    )


def _plan_action_facets(result: PlanActionFacetsResult) -> PlanActionFacetsData:
    return PlanActionFacetsData(
        facets=PlanActionFacetSets(
            status=tuple(
                FacetValueResource(value=ActionStatus(facet.value), count=facet.count) for facet in result.status_facets
            ),
            action_type=tuple(
                FacetValueResource(value=ActionType(facet.value), count=facet.count)
                for facet in result.action_type_facets
            ),
            reason=tuple(
                FacetValueResource(value=PlanActionReason(facet.value), count=facet.count)
                for facet in result.reason_facets
            ),
        ),
        total=result.total,
        target_collisions=result.target_collisions,
    )


def _plan_capabilities(plan: Plan, result: PlanCapabilitiesResult) -> PlanCapabilities:
    return PlanCapabilities(
        can_apply=result.can_apply,
        can_cancel=result.can_cancel,
        can_recreate=result.can_recreate,
        disabled_reasons=tuple(
            _plan_capability_error(plan, reason.capability, reason.reason) for reason in result.disabled_reasons
        ),
    )


def _plan_capability_error(
    plan: Plan,
    capability: PlanCapability,
    reason: PlanCapabilityReason,
) -> ApiError:
    creation_routes = {
        PlanType.ADD: "/plans/new/add",
        PlanType.ORGANIZE: "/plans/new/organize",
        PlanType.REFRESH: "/plans/new/refresh",
        PlanType.UNDO: "/history",
    }
    if reason is PlanCapabilityReason.PLAN_NOT_READY:
        return ApiError(
            code=ApiErrorCode.PLAN_NOT_READY,
            message="The Plan is not ready.",
            field=f"capabilities.{capability.value}",
            retryable=False,
            remediation=ApiRemediation(label="Create a new Plan", route=creation_routes[plan.plan_type]),
        )
    if reason is PlanCapabilityReason.LIBRARY_NOT_FOUND:
        return ApiError(
            code=ApiErrorCode.LIBRARY_NOT_FOUND,
            message="The Plan's Library is unavailable.",
            field=f"capabilities.{capability.value}",
            retryable=False,
            remediation=ApiRemediation(label="Open Health", route="/health"),
        )
    if reason is PlanCapabilityReason.LIBRARY_ROOT_CHANGED:
        return ApiError(
            code=ApiErrorCode.LIBRARY_ROOT_CHANGED,
            message="The Library root changed after this Plan was created.",
            field=f"capabilities.{capability.value}",
            retryable=False,
            remediation=ApiRemediation(label="Create a new Plan", route=creation_routes[plan.plan_type]),
        )
    return ApiError(
        code=ApiErrorCode.VALIDATION_FAILED,
        message="Undo Plans are recreated from their source Run in History.",
        field=f"capabilities.{capability.value}",
        retryable=False,
        remediation=ApiRemediation(label="Open History", route="/history"),
    )


def _plan_not_found() -> JSONResponse:
    return api_failure_response(
        HTTP_NOT_FOUND_STATUS,
        ApiErrorCode.PLAN_NOT_FOUND,
        PLAN_NOT_FOUND_MESSAGE,
        field="path.plan_id",
    )


def _invalid_plan_query(field: str) -> JSONResponse:
    return api_failure_response(
        HTTP_UNPROCESSABLE_CONTENT_STATUS,
        ApiErrorCode.VALIDATION_FAILED,
        INVALID_PLAN_QUERY_MESSAGE,
        field=field,
    )


def _plan_not_ready() -> JSONResponse:
    return api_failure_response(
        HTTP_CONFLICT_STATUS,
        ApiErrorCode.PLAN_NOT_READY,
        PLAN_NOT_READY_MESSAGE,
        field="path.plan_id",
    )
