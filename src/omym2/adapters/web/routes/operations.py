"""
Summary: Implements durable Operation polling and mutation acceptance routes.
Why: Exposes idempotent planning, Apply, Check, and Undo work without blocking Web requests.
"""

from __future__ import annotations

import secrets
from typing import TYPE_CHECKING, Annotated
from uuid import UUID  # noqa: TC003  # FastAPI resolves UUID request annotations at registration.

from fastapi import APIRouter, Header
from fastapi.responses import JSONResponse

from omym2.adapters.web.routes.api_context import (
    ApiContext,  # noqa: TC001  # FastAPI resolves dependency annotations at registration.
)
from omym2.adapters.web.routes.api_responses import api_failure_response
from omym2.adapters.web.routes.read_query import CORRELATION_HEADER_SCHEMA
from omym2.adapters.web.schemas.api_envelopes import ApiEnvelope, ApiFailureEnvelope
from omym2.adapters.web.schemas.api_errors import ApiError, ApiErrorCode, ApiRemediation
from omym2.adapters.web.schemas.operations import (
    AddPlanRequest,
    CheckCompletedResultResource,
    CheckRunRequest,
    OperationRef,
    OperationResource,
    OrganizePlanRequest,
    PlanCreatedResultResource,
    RefreshPlanRequest,
    RegisteredWithoutPlanResultResource,
    RunCompletedResultResource,
)
from omym2.config import (
    HTTP_ACCEPTED_STATUS,
    HTTP_CONFLICT_STATUS,
    HTTP_FORBIDDEN_STATUS,
    HTTP_GONE_STATUS,
    HTTP_INTERNAL_ERROR_STATUS,
    HTTP_NOT_FOUND_STATUS,
    HTTP_OK_STATUS,
    HTTP_UNPROCESSABLE_CONTENT_STATUS,
    MILLISECONDS_PER_SECOND,
    OPERATION_POLL_INITIAL_SECONDS,
    WEB_API_ADD_PLAN_ROUTE,
    WEB_API_APPLY_PLAN_ROUTE,
    WEB_API_CHECK_RUN_ROUTE,
    WEB_API_OPERATION_ROUTE,
    WEB_API_ORGANIZE_PLAN_ROUTE,
    WEB_API_REFRESH_PLAN_ROUTE,
    WEB_API_UNDO_PLAN_ROUTE,
    WEB_CORRELATION_HEADER_NAME,
    WEB_CSRF_HEADER_NAME,
    WEB_IDEMPOTENCY_HEADER_NAME,
)
from omym2.domain.models.operation import (
    CheckCompletedResult,
    Operation,
    OperationError,
    OperationStatus,
    OperationTombstone,
    PlanCreatedResult,
    RegisteredWithoutPlanResult,
    RunCompletedResult,
)
from omym2.features.add.dto import CreateAddPlanRequest
from omym2.features.apply.usecases.apply_plan import (
    LIBRARY_NOT_FOUND_MESSAGE,
    LIBRARY_ROOT_CHANGED_SUMMARY,
    PLAN_NOT_FOUND_MESSAGE,
    PLAN_NOT_READY_MESSAGE,
    ApplyPlanError,
    PlanCannotBeAppliedError,
)
from omym2.features.apply.usecases.apply_plan import (
    PlanNotFoundError as ApplyPlanNotFoundError,
)
from omym2.features.apply.usecases.claim_apply import LibraryRootChangedError
from omym2.features.check.dto import CheckLibraryRequest
from omym2.features.common_ports import ExclusiveOperationBusyError, IdempotencyKeyReusedError, OperationInProgressError
from omym2.features.operations.dto import (
    OperationExpiredError,
    OperationNotFoundError,
)
from omym2.features.organize.dto import CreateOrganizePlanRequest
from omym2.features.refresh.dto import CreateRefreshPlanRequest, RefreshTargetKind
from omym2.features.undo.dto import CreateUndoPlanRequest
from omym2.features.undo.usecases.create_undo_plan import (
    ALREADY_UNDONE_OR_IN_PROGRESS_MESSAGE,
    NOTHING_TO_UNDO_MESSAGE,
    PENDING_FILE_EVENT_REQUIRES_REVIEW_MESSAGE,
    RUN_LIBRARY_NOT_FOUND_MESSAGE,
    RUN_NOT_FOUND_MESSAGE,
    RUN_NOT_TERMINAL_MESSAGE,
    RUN_PLAN_NOT_FOUND_MESSAGE,
    RUN_REFRESH_METADATA_UNSUPPORTED_MESSAGE,
    UndoPlanError,
)
from omym2.shared.ids import LibraryId, OperationId, PlanId, RunId

if TYPE_CHECKING:
    from collections.abc import Callable

    from pydantic import BaseModel

    from omym2.domain.models.operation import OperationResult
    from omym2.features.operations.dto import ReserveOperationResult

GET_OPERATION_OPERATION_ID = "getOperation"
START_ADD_PLAN_OPERATION_ID = "startAddPlan"
START_ORGANIZE_PLAN_OPERATION_ID = "startOrganizePlan"
START_REFRESH_PLAN_OPERATION_ID = "startRefreshPlan"
START_CHECK_OPERATION_ID = "startCheck"
APPLY_PLAN_OPERATION_ID = "applyPlan"
CREATE_UNDO_PLAN_OPERATION_ID = "createUndoPlan"
CSRF_INVALID_MESSAGE = "The Web mutation token is missing or invalid."
IDEMPOTENCY_REUSED_MESSAGE = "The idempotency key was already used for different work."
OPERATION_IN_PROGRESS_MESSAGE = "Another state-changing Operation is already in progress."
OPERATION_NOT_FOUND_MESSAGE = "The Operation was not found."
OPERATION_EXPIRED_MESSAGE = "The Operation result has expired."
OPERATIONS_CONTEXT_MISSING_MESSAGE = "Operation routes are not configured."
LOCATION_HEADER_SCHEMA = {
    "description": "Relative durable Operation polling URL.",
    "schema": {"type": "string"},
}
type RequiredCsrfToken = Annotated[str, Header(alias=WEB_CSRF_HEADER_NAME, min_length=1)]


def create_operations_router() -> APIRouter:  # noqa: C901  # One factory keeps schema and production routes identical.
    """Create durable Operation and planning routes without application I/O."""
    router = APIRouter()
    error_responses = _error_responses()

    @router.get(
        WEB_API_OPERATION_ROUTE,
        operation_id=GET_OPERATION_OPERATION_ID,
        response_model=ApiEnvelope[OperationResource],
        responses=error_responses,
    )
    def get_operation(  # pyright: ignore[reportUnusedFunction]  # FastAPI calls decorator-registered routes.
        operation_id: UUID,
        context: ApiContext,
    ) -> ApiEnvelope[OperationResource] | JSONResponse:
        operations = _operations_context(context)
        try:
            operation = operations.get_operation(OperationId(operation_id))
        except OperationExpiredError:
            return _failure(HTTP_GONE_STATUS, ApiErrorCode.OPERATION_EXPIRED, OPERATION_EXPIRED_MESSAGE)
        except OperationNotFoundError:
            return _failure(HTTP_NOT_FOUND_STATUS, ApiErrorCode.OPERATION_NOT_FOUND, OPERATION_NOT_FOUND_MESSAGE)
        return ApiEnvelope(data=_operation_resource(operation), errors=())

    @router.post(
        WEB_API_ADD_PLAN_ROUTE,
        operation_id=START_ADD_PLAN_OPERATION_ID,
        status_code=HTTP_ACCEPTED_STATUS,
        response_model=ApiEnvelope[OperationRef],
        responses=_acceptance_responses(),
    )
    def start_add_plan(  # pyright: ignore[reportUnusedFunction]  # FastAPI calls decorator-registered routes.
        request: AddPlanRequest,
        context: ApiContext,
        idempotency_key: Annotated[UUID, Header(alias=WEB_IDEMPOTENCY_HEADER_NAME)],
        csrf_token: RequiredCsrfToken,
    ) -> JSONResponse:
        csrf_failure = _csrf_failure(context, csrf_token)
        if csrf_failure is not None:
            return csrf_failure
        feature_request = CreateAddPlanRequest(
            source_path=request.source_path,
            library_id=None if request.library_id is None else LibraryId(request.library_id),
        )
        operations = _operations_context(context)
        return _acceptance_response(
            lambda: operations.start_add_plan(feature_request, idempotency_key),
            operations.active_operation_id,
        )

    @router.post(
        WEB_API_ORGANIZE_PLAN_ROUTE,
        operation_id=START_ORGANIZE_PLAN_OPERATION_ID,
        status_code=HTTP_ACCEPTED_STATUS,
        response_model=ApiEnvelope[OperationRef],
        responses=_acceptance_responses(),
    )
    def start_organize_plan(  # pyright: ignore[reportUnusedFunction]  # FastAPI calls decorator-registered routes.
        request: OrganizePlanRequest,
        context: ApiContext,
        idempotency_key: Annotated[UUID, Header(alias=WEB_IDEMPOTENCY_HEADER_NAME)],
        csrf_token: RequiredCsrfToken,
    ) -> JSONResponse:
        csrf_failure = _csrf_failure(context, csrf_token)
        if csrf_failure is not None:
            return csrf_failure
        feature_request = CreateOrganizePlanRequest(trust_stat=False, library_root=request.library_root)
        operations = _operations_context(context)
        return _acceptance_response(
            lambda: operations.start_organize_plan(feature_request, idempotency_key),
            operations.active_operation_id,
        )

    @router.post(
        WEB_API_REFRESH_PLAN_ROUTE,
        operation_id=START_REFRESH_PLAN_OPERATION_ID,
        status_code=HTTP_ACCEPTED_STATUS,
        response_model=ApiEnvelope[OperationRef],
        responses=_acceptance_responses(),
    )
    def start_refresh_plan(  # pyright: ignore[reportUnusedFunction]  # FastAPI calls decorator-registered routes.
        request: RefreshPlanRequest,
        context: ApiContext,
        idempotency_key: Annotated[UUID, Header(alias=WEB_IDEMPOTENCY_HEADER_NAME)],
        csrf_token: RequiredCsrfToken,
    ) -> JSONResponse:
        csrf_failure = _csrf_failure(context, csrf_token)
        if csrf_failure is not None:
            return csrf_failure
        feature_request = CreateRefreshPlanRequest(
            trust_stat=False,
            library_id=LibraryId(request.library_id),
            target_path=request.target_path,
            target_kind=None if request.target_kind == "all" else RefreshTargetKind(request.target_kind),
            include_all=request.target_kind == "all",
        )
        operations = _operations_context(context)
        return _acceptance_response(
            lambda: operations.start_refresh_plan(feature_request, idempotency_key),
            operations.active_operation_id,
        )

    @router.post(
        WEB_API_CHECK_RUN_ROUTE,
        operation_id=START_CHECK_OPERATION_ID,
        status_code=HTTP_ACCEPTED_STATUS,
        response_model=ApiEnvelope[OperationRef],
        responses=_acceptance_responses(),
    )
    def start_check(  # pyright: ignore[reportUnusedFunction]  # FastAPI calls decorator-registered routes.
        request: CheckRunRequest,
        context: ApiContext,
        idempotency_key: Annotated[UUID, Header(alias=WEB_IDEMPOTENCY_HEADER_NAME)],
        csrf_token: RequiredCsrfToken,
    ) -> JSONResponse:
        csrf_failure = _csrf_failure(context, csrf_token)
        if csrf_failure is not None:
            return csrf_failure
        feature_request = CheckLibraryRequest(
            trust_stat=False,
            library_id=None if request.library_id is None else LibraryId(request.library_id),
        )
        operations = _operations_context(context)
        return _acceptance_response(
            lambda: operations.start_check(feature_request, idempotency_key),
            operations.active_operation_id,
        )

    @router.post(
        WEB_API_APPLY_PLAN_ROUTE,
        operation_id=APPLY_PLAN_OPERATION_ID,
        status_code=HTTP_ACCEPTED_STATUS,
        response_model=ApiEnvelope[OperationRef],
        responses=_acceptance_responses(),
    )
    def apply_plan(  # pyright: ignore[reportUnusedFunction]  # FastAPI calls decorator-registered routes.
        plan_id: UUID,
        context: ApiContext,
        idempotency_key: Annotated[UUID, Header(alias=WEB_IDEMPOTENCY_HEADER_NAME)],
        csrf_token: RequiredCsrfToken,
    ) -> JSONResponse:
        csrf_failure = _csrf_failure(context, csrf_token)
        if csrf_failure is not None:
            return csrf_failure
        operations = _operations_context(context)
        try:
            return _acceptance_response(
                lambda: operations.start_apply_plan(PlanId(plan_id), idempotency_key),
                operations.active_operation_id,
            )
        except ApplyPlanNotFoundError:
            return _failure(
                HTTP_NOT_FOUND_STATUS,
                ApiErrorCode.PLAN_NOT_FOUND,
                PLAN_NOT_FOUND_MESSAGE,
                field="path.plan_id",
            )
        except PlanCannotBeAppliedError:
            return _failure(
                HTTP_CONFLICT_STATUS,
                ApiErrorCode.PLAN_NOT_READY,
                PLAN_NOT_READY_MESSAGE,
                field="path.plan_id",
            )
        except LibraryRootChangedError:
            return _failure(
                HTTP_CONFLICT_STATUS,
                ApiErrorCode.LIBRARY_ROOT_CHANGED,
                LIBRARY_ROOT_CHANGED_SUMMARY,
                field="path.plan_id",
            )
        except ApplyPlanError:
            return _failure(
                HTTP_NOT_FOUND_STATUS,
                ApiErrorCode.LIBRARY_NOT_FOUND,
                LIBRARY_NOT_FOUND_MESSAGE,
                field="path.plan_id",
            )

    @router.post(
        WEB_API_UNDO_PLAN_ROUTE,
        operation_id=CREATE_UNDO_PLAN_OPERATION_ID,
        status_code=HTTP_ACCEPTED_STATUS,
        response_model=ApiEnvelope[OperationRef],
        responses=_acceptance_responses(),
    )
    def create_undo_plan(  # pyright: ignore[reportUnusedFunction]  # FastAPI calls decorator-registered routes.
        run_id: UUID,
        context: ApiContext,
        idempotency_key: Annotated[UUID, Header(alias=WEB_IDEMPOTENCY_HEADER_NAME)],
        csrf_token: RequiredCsrfToken,
    ) -> JSONResponse:
        csrf_failure = _csrf_failure(context, csrf_token)
        if csrf_failure is not None:
            return csrf_failure
        operations = _operations_context(context)
        try:
            return _acceptance_response(
                lambda: operations.start_undo_plan(CreateUndoPlanRequest(RunId(run_id)), idempotency_key),
                operations.active_operation_id,
            )
        except UndoPlanError as exc:
            response = _undo_plan_failure(str(exc))
            if response is None:
                raise
            return response

    return router


def _acceptance_response(
    start: Callable[[], ReserveOperationResult],
    active_operation_id: Callable[[], OperationId | None],
) -> JSONResponse:
    try:
        accepted = start()
    except IdempotencyKeyReusedError:
        return _failure(HTTP_CONFLICT_STATUS, ApiErrorCode.IDEMPOTENCY_KEY_REUSED, IDEMPOTENCY_REUSED_MESSAGE)
    except (ExclusiveOperationBusyError, OperationInProgressError) as exc:
        operation_id = exc.active_operation.operation_id if isinstance(exc, OperationInProgressError) else None
        if operation_id is None:
            operation_id = active_operation_id()
        return operation_in_progress_failure(operation_id)

    lookup = accepted.lookup
    location = _operation_status_url(lookup.operation_id)
    if isinstance(lookup, OperationTombstone):
        response = _failure(HTTP_GONE_STATUS, ApiErrorCode.OPERATION_EXPIRED, OPERATION_EXPIRED_MESSAGE)
        response.headers["Location"] = location
        return response
    if lookup.status in {OperationStatus.SUCCEEDED, OperationStatus.FAILED, OperationStatus.INTERRUPTED}:
        envelope = ApiEnvelope(data=_operation_resource(lookup), errors=())
        return _json_response(envelope, HTTP_OK_STATUS, location=location)
    envelope = ApiEnvelope(data=_operation_ref(lookup), errors=())
    return _json_response(envelope, HTTP_ACCEPTED_STATUS, location=location)


def _operation_ref(operation: Operation) -> OperationRef:
    return OperationRef(
        operation_id=operation.operation_id,
        kind=operation.kind,
        status=operation.status,
        status_url=_operation_status_url(operation.operation_id),
        poll_after_ms=int(OPERATION_POLL_INITIAL_SECONDS * MILLISECONDS_PER_SECOND),
    )


def _operation_resource(operation: Operation) -> OperationResource:
    return OperationResource(
        operation_id=operation.operation_id,
        kind=operation.kind,
        status=operation.status,
        library_id=operation.library_id,
        plan_id=operation.plan_id,
        run_id=operation.run_id,
        result=_operation_result_resource(operation.result),
        error=None if operation.error is None else _operation_error_resource(operation.error),
        requested_at=operation.requested_at,
        started_at=operation.started_at,
        completed_at=operation.completed_at,
    )


def _operation_result_resource(result: OperationResult | None):
    if isinstance(result, PlanCreatedResult):
        return PlanCreatedResultResource(plan_id=result.plan_id)
    if isinstance(result, RegisteredWithoutPlanResult):
        return RegisteredWithoutPlanResultResource(library_id=result.library_id, track_count=result.track_count)
    if isinstance(result, CheckCompletedResult):
        return CheckCompletedResultResource(check_run_ids=result.check_run_ids, issue_count=result.issue_count)
    if isinstance(result, RunCompletedResult):
        return RunCompletedResultResource(run_id=result.run_id)
    return None


def _operation_error_resource(error: OperationError) -> ApiError:
    remediation = error.remediation
    api_remediation = None
    if remediation is not None:
        if remediation.route is not None:
            api_remediation = ApiRemediation(label=remediation.label, route=remediation.route)
        elif remediation.command is not None:
            api_remediation = ApiRemediation(label=remediation.label, command=remediation.command)
        else:
            api_remediation = ApiRemediation(label=remediation.label)
    values: dict[str, object] = {
        "code": ApiErrorCode(error.code.value),
        "message": error.message,
        "retryable": error.retryable,
    }
    if error.field is not None:
        values["field"] = error.field
    if api_remediation is not None:
        values["remediation"] = api_remediation
    return ApiError.model_validate(values)


def _operations_context(context: ApiContext):
    if context.operations is None:
        raise RuntimeError(OPERATIONS_CONTEXT_MISSING_MESSAGE)
    return context.operations


def _csrf_failure(context: ApiContext, token: str | None) -> JSONResponse | None:
    if token is not None and secrets.compare_digest(token, context.csrf_token):
        return None
    return _failure(HTTP_FORBIDDEN_STATUS, ApiErrorCode.CSRF_INVALID, CSRF_INVALID_MESSAGE)


def operation_in_progress_failure(operation_id: OperationId | None) -> JSONResponse:
    """Return the shared typed conflict with optional active-Operation remediation."""
    remediation = (
        ApiRemediation(label="View active Operation")
        if operation_id is None
        else ApiRemediation(label="View active Operation", route=_operation_status_url(operation_id))
    )
    envelope = ApiFailureEnvelope(
        data=None,
        errors=(
            ApiError(
                code=ApiErrorCode.OPERATION_IN_PROGRESS,
                message=OPERATION_IN_PROGRESS_MESSAGE,
                retryable=True,
                remediation=remediation,
            ),
        ),
    )
    return _json_response(envelope, HTTP_CONFLICT_STATUS)


def _failure(status: int, code: ApiErrorCode, message: str, *, field: str | None = None) -> JSONResponse:
    return api_failure_response(status, code, message, field=field)


def _undo_plan_failure(message: str) -> JSONResponse | None:
    definitions = {
        RUN_NOT_FOUND_MESSAGE: (HTTP_NOT_FOUND_STATUS, ApiErrorCode.RUN_NOT_FOUND),
        RUN_LIBRARY_NOT_FOUND_MESSAGE: (HTTP_NOT_FOUND_STATUS, ApiErrorCode.LIBRARY_NOT_FOUND),
        RUN_PLAN_NOT_FOUND_MESSAGE: (HTTP_NOT_FOUND_STATUS, ApiErrorCode.PLAN_NOT_FOUND),
        RUN_NOT_TERMINAL_MESSAGE: (HTTP_CONFLICT_STATUS, ApiErrorCode.RUN_NOT_TERMINAL),
        NOTHING_TO_UNDO_MESSAGE: (HTTP_CONFLICT_STATUS, ApiErrorCode.NOTHING_TO_UNDO),
        RUN_REFRESH_METADATA_UNSUPPORTED_MESSAGE: (
            HTTP_CONFLICT_STATUS,
            ApiErrorCode.UNDO_REFRESH_METADATA_UNSUPPORTED,
        ),
        ALREADY_UNDONE_OR_IN_PROGRESS_MESSAGE: (
            HTTP_CONFLICT_STATUS,
            ApiErrorCode.ALREADY_UNDONE_OR_IN_PROGRESS,
        ),
        PENDING_FILE_EVENT_REQUIRES_REVIEW_MESSAGE: (
            HTTP_CONFLICT_STATUS,
            ApiErrorCode.PENDING_FILE_EVENT_REQUIRES_REVIEW,
        ),
    }
    definition = definitions.get(message)
    if definition is None:
        return None
    status, code = definition
    return _failure(status, code, message, field="path.run_id")


def _json_response(
    envelope: BaseModel,
    status: int,
    *,
    location: str | None = None,
) -> JSONResponse:
    response = JSONResponse(envelope.model_dump(mode="json"), status_code=status)
    if location is not None:
        response.headers["Location"] = location
    return response


def _operation_status_url(operation_id: object) -> str:
    return WEB_API_OPERATION_ROUTE.format(operation_id=operation_id)


def _error_responses() -> dict[int | str, dict[str, object]]:
    return {
        HTTP_NOT_FOUND_STATUS: _response(ApiFailureEnvelope),
        HTTP_GONE_STATUS: _response(ApiFailureEnvelope),
        HTTP_UNPROCESSABLE_CONTENT_STATUS: _response(ApiFailureEnvelope),
        HTTP_INTERNAL_ERROR_STATUS: _response(ApiFailureEnvelope),
    }


def _acceptance_responses() -> dict[int | str, dict[str, object]]:
    responses = _error_responses()
    responses.update(
        {
            HTTP_OK_STATUS: _response(ApiEnvelope[OperationResource], include_location=True),
            HTTP_ACCEPTED_STATUS: _response(ApiEnvelope[OperationRef], include_location=True),
            HTTP_FORBIDDEN_STATUS: _response(ApiFailureEnvelope),
            HTTP_CONFLICT_STATUS: _response(ApiFailureEnvelope),
            HTTP_GONE_STATUS: _response(ApiFailureEnvelope, include_location=True),
            HTTP_UNPROCESSABLE_CONTENT_STATUS: _response(ApiFailureEnvelope),
        }
    )
    return responses


def _response(model: object, *, include_location: bool = False) -> dict[str, object]:
    headers = {WEB_CORRELATION_HEADER_NAME: CORRELATION_HEADER_SCHEMA}
    if include_location:
        headers["Location"] = LOCATION_HEADER_SCHEMA
    return {
        "model": model,
        "headers": headers,
    }
