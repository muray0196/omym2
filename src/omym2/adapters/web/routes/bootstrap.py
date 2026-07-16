"""
Summary: Implements the typed Bootstrap Web API route.
Why: Gives the renewed SPA a degraded-capable initial readiness snapshot.
"""

from __future__ import annotations

from fastapi import APIRouter

from omym2.adapters.web.routes.api_context import (
    ApiContext,  # noqa: TC001  # FastAPI resolves dependency annotations at registration.
)
from omym2.adapters.web.schemas.api_envelopes import ApiEnvelope, ApiFailureEnvelope
from omym2.adapters.web.schemas.api_errors import ApiError, ApiErrorCode, ApiRemediation
from omym2.adapters.web.schemas.bootstrap import (
    BootstrapData,
    ConfigValidationResource,
    OperationPollingPolicy,
    RuntimeCapabilities,
)
from omym2.adapters.web.schemas.libraries import LibraryResource
from omym2.config import (
    MILLISECONDS_PER_SECOND,
    OPERATION_POLL_BACKOFF_FACTOR,
    OPERATION_POLL_INITIAL_SECONDS,
    OPERATION_POLL_MAX_SECONDS,
    WEB_API_BOOTSTRAP_ROUTE,
    WEB_CORRELATION_HEADER_NAME,
    WEB_SETTINGS_ROUTE,
)
from omym2.features.bootstrap.dto import BootstrapCapabilities, BootstrapReason, BootstrapResult

BOOTSTRAP_OPERATION_ID = "getBootstrap"
CORRELATION_HEADER_SCHEMA = {
    "description": "Request correlation identifier written to server logs.",
    "schema": {"type": "string"},
}


def create_bootstrap_router() -> APIRouter:
    """Create the Bootstrap router without resolving application state."""
    router = APIRouter()

    @router.get(
        WEB_API_BOOTSTRAP_ROUTE,
        operation_id=BOOTSTRAP_OPERATION_ID,
        response_model=ApiEnvelope[BootstrapData],
        responses={
            200: {"headers": {WEB_CORRELATION_HEADER_NAME: CORRELATION_HEADER_SCHEMA}},
            500: {
                "model": ApiFailureEnvelope,
                "headers": {WEB_CORRELATION_HEADER_NAME: CORRELATION_HEADER_SCHEMA},
            },
        },
    )
    def get_bootstrap(  # pyright: ignore[reportUnusedFunction]  # FastAPI calls decorator-registered routes.
        context: ApiContext,
    ) -> ApiEnvelope[BootstrapData]:
        return _bootstrap_envelope(context.get_bootstrap(), context.csrf_token)

    return router


def _bootstrap_envelope(result: BootstrapResult, csrf_token: str) -> ApiEnvelope[BootstrapData]:
    config_errors = _config_errors(result)
    library_errors = tuple(_error_for_reason(reason) for reason in result.library_reasons)
    top_errors = config_errors + tuple(
        error for error in library_errors if error.code is ApiErrorCode.STORAGE_UNAVAILABLE
    )
    capabilities = result.runtime_capabilities
    disabled_reasons = _capability_disabled_reasons(capabilities)
    snapshot = result.config_snapshot
    return ApiEnvelope[BootstrapData](
        data=BootstrapData(
            csrf_token=csrf_token,
            active_library=_library_resource(result),
            library_diagnostics=library_errors,
            config_validation=ConfigValidationResource(
                valid=result.config_valid,
                config_revision=None if snapshot is None else snapshot.config_revision,
                errors=config_errors,
            ),
            runtime_capabilities=RuntimeCapabilities(
                can_read_state=capabilities.can_read_state,
                can_change_settings=capabilities.can_change_settings,
                can_start_operations=capabilities.can_start_operations,
                can_start_organize=capabilities.can_start_organize,
                disabled_reasons=disabled_reasons,
            ),
            operation_polling=OperationPollingPolicy(
                initial_ms=int(OPERATION_POLL_INITIAL_SECONDS * MILLISECONDS_PER_SECOND),
                backoff_factor=OPERATION_POLL_BACKOFF_FACTOR,
                max_ms=int(OPERATION_POLL_MAX_SECONDS * MILLISECONDS_PER_SECOND),
            ),
            active_operation_id=result.active_operation_id,
        ),
        errors=top_errors,
    )


def _config_errors(result: BootstrapResult) -> tuple[ApiError, ...]:
    snapshot = result.config_snapshot
    if result.config_reason is BootstrapReason.CONFIG_IO_FAILED:
        return (_error_for_reason(BootstrapReason.CONFIG_IO_FAILED),)
    if result.config_reason is not BootstrapReason.CONFIG_INVALID or snapshot is None:
        return ()
    return tuple(
        ApiError(
            code=ApiErrorCode.CONFIG_INVALID,
            message=message,
            field="config",
            retryable=False,
            remediation=ApiRemediation(label="Review Settings", route=WEB_SETTINGS_ROUTE),
        )
        for message in snapshot.errors
    ) or (_error_for_reason(BootstrapReason.CONFIG_INVALID),)


def _library_resource(result: BootstrapResult) -> LibraryResource | None:
    library = result.active_library
    if library is None:
        return None
    effective_status = result.effective_library_status
    if effective_status is None:
        return None
    return LibraryResource(
        library_id=library.library_id,
        root_path=library.root_path,
        status=effective_status,
        is_registered=result.is_library_registered,
        registered_at=library.registered_at,
        path_policy_fingerprint=library.path_policy_hash,
        is_path_policy_current=result.is_path_policy_current,
    )


def _error_for_reason(reason: BootstrapReason) -> ApiError:
    definitions = {
        BootstrapReason.CONFIG_INVALID: (
            ApiErrorCode.CONFIG_INVALID,
            "Configuration is invalid.",
            "Review Settings",
            WEB_SETTINGS_ROUTE,
            False,
        ),
        BootstrapReason.CONFIG_IO_FAILED: (
            ApiErrorCode.CONFIG_IO_FAILED,
            "Configuration storage could not be read.",
            "Retry",
            None,
            True,
        ),
        BootstrapReason.LIBRARY_SELECTION_AMBIGUOUS: (
            ApiErrorCode.LIBRARY_SELECTION_AMBIGUOUS,
            "More than one Library is registered; selection is ambiguous.",
            "Review Settings",
            WEB_SETTINGS_ROUTE,
            False,
        ),
        BootstrapReason.LIBRARY_UNREGISTERED: (
            ApiErrorCode.LIBRARY_UNREGISTERED,
            "No registered Library is available.",
            "Create an Organize Plan",
            "/plans/new/organize",
            False,
        ),
        BootstrapReason.LIBRARY_STALE: (
            ApiErrorCode.LIBRARY_STALE,
            "The Library PathPolicy fingerprint is stale.",
            "Create an Organize Plan",
            "/plans/new/organize",
            False,
        ),
        BootstrapReason.LIBRARY_BLOCKED: (
            ApiErrorCode.LIBRARY_BLOCKED,
            "The Library is blocked.",
            "Open Health",
            "/health",
            False,
        ),
        BootstrapReason.STORAGE_UNAVAILABLE: (
            ApiErrorCode.STORAGE_UNAVAILABLE,
            "Application state storage could not be read.",
            "Retry",
            None,
            True,
        ),
    }
    code, message, label, route, retryable = definitions[reason]
    remediation = ApiRemediation(label=label) if route is None else ApiRemediation(label=label, route=route)
    return ApiError(
        code=code,
        message=message,
        retryable=retryable,
        remediation=remediation,
    )


def _capability_disabled_reasons(capabilities: BootstrapCapabilities) -> tuple[ApiError, ...]:
    definitions = (
        (capabilities.read_state_disabled_reasons, "runtime_capabilities.can_read_state"),
        (capabilities.change_settings_disabled_reasons, "runtime_capabilities.can_change_settings"),
        (capabilities.start_operations_disabled_reasons, "runtime_capabilities.can_start_operations"),
        (capabilities.start_organize_disabled_reasons, "runtime_capabilities.can_start_organize"),
    )
    return tuple(_with_field(_error_for_reason(reason), field) for reasons, field in definitions for reason in reasons)


def _with_field(error: ApiError, field: str) -> ApiError:
    return error.model_copy(update={"field": field})
