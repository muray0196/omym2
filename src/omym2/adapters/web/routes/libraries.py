"""
Summary: Implements typed read-only Library inspection routes.
Why: Exposes stable identity and effective readiness without adapter-side inference.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING, Annotated, cast
from uuid import UUID  # noqa: TC003  # FastAPI resolves path annotations at registration.

from fastapi import APIRouter, Depends
from fastapi.responses import JSONResponse  # noqa: TC002  # FastAPI resolves route return annotations.

from omym2.adapters.web.routes.api_context import ApiContext  # noqa: TC001  # FastAPI resolves dependencies.
from omym2.adapters.web.routes.read_query import CORRELATION_HEADER_SCHEMA, not_found_failure
from omym2.adapters.web.schemas.api_envelopes import ApiEnvelope, ApiFailureEnvelope
from omym2.adapters.web.schemas.api_errors import ApiErrorCode
from omym2.adapters.web.schemas.libraries import LibrariesData, LibraryResource
from omym2.config import (
    HTTP_INTERNAL_ERROR_STATUS,
    HTTP_NOT_FOUND_STATUS,
    HTTP_OK_STATUS,
    HTTP_UNPROCESSABLE_CONTENT_STATUS,
    WEB_API_LIBRARIES_ROUTE,
    WEB_API_LIBRARY_DETAIL_ROUTE,
    WEB_CORRELATION_HEADER_NAME,
)
from omym2.features.libraries.dto import InspectLibrariesRequest
from omym2.features.libraries.usecases.inspect_libraries import (
    LIBRARY_NOT_FOUND_MESSAGE,
    LibraryNotFoundError,
)
from omym2.shared.ids import LibraryId

if TYPE_CHECKING:
    from collections.abc import Callable

    from omym2.features.libraries.dto import LibraryInspection

LIBRARY_HANDLERS_UNAVAILABLE_MESSAGE = "Library route handlers are unavailable."


@dataclass(frozen=True, slots=True)
class LibraryRouteHandlers:
    """Read-only Library handlers supplied by the composition root."""

    inspect_libraries: Callable[[InspectLibrariesRequest], tuple[LibraryInspection, ...]]


def get_library_route_handlers(context: ApiContext) -> LibraryRouteHandlers:
    """Resolve Library-specific collaborators from the shared route context."""
    handlers = getattr(context, "libraries", None)
    if handlers is None:
        raise RuntimeError(LIBRARY_HANDLERS_UNAVAILABLE_MESSAGE)
    return cast("LibraryRouteHandlers", cast("object", handlers))


type LibrariesContext = Annotated[LibraryRouteHandlers, Depends(get_library_route_handlers)]


def create_libraries_router() -> APIRouter:
    """Create Library list/detail routes without resolving application state."""
    router = APIRouter()

    @router.get(
        WEB_API_LIBRARIES_ROUTE,
        operation_id="getLibraries",
        response_model=ApiEnvelope[LibrariesData],
        responses={
            HTTP_OK_STATUS: {"headers": {WEB_CORRELATION_HEADER_NAME: CORRELATION_HEADER_SCHEMA}},
            HTTP_INTERNAL_ERROR_STATUS: {"model": ApiFailureEnvelope},
        },
    )
    def get_libraries(  # pyright: ignore[reportUnusedFunction]  # FastAPI calls decorator-registered routes.
        context: LibrariesContext,
    ) -> ApiEnvelope[LibrariesData]:
        inspections = context.inspect_libraries(InspectLibrariesRequest())
        return ApiEnvelope(
            data=LibrariesData(items=tuple(_library_resource(item) for item in inspections)),
            errors=(),
        )

    @router.get(
        WEB_API_LIBRARY_DETAIL_ROUTE,
        operation_id="getLibrary",
        response_model=ApiEnvelope[LibraryResource],
        responses={
            HTTP_OK_STATUS: {"headers": {WEB_CORRELATION_HEADER_NAME: CORRELATION_HEADER_SCHEMA}},
            HTTP_NOT_FOUND_STATUS: {"model": ApiFailureEnvelope},
            HTTP_UNPROCESSABLE_CONTENT_STATUS: {"model": ApiFailureEnvelope},
            HTTP_INTERNAL_ERROR_STATUS: {"model": ApiFailureEnvelope},
        },
    )
    def get_library(  # pyright: ignore[reportUnusedFunction]  # FastAPI calls decorator-registered routes.
        library_id: UUID,
        context: LibrariesContext,
    ) -> ApiEnvelope[LibraryResource] | JSONResponse:
        try:
            inspection = context.inspect_libraries(InspectLibrariesRequest(library_id=LibraryId(library_id)))[0]
        except LibraryNotFoundError:
            return not_found_failure(
                ApiErrorCode.LIBRARY_NOT_FOUND,
                LIBRARY_NOT_FOUND_MESSAGE,
                field="path.library_id",
            )
        return ApiEnvelope(data=_library_resource(inspection), errors=())

    return router


def _library_resource(inspection: LibraryInspection) -> LibraryResource:
    library = inspection.library
    return LibraryResource(
        library_id=library.library_id,
        root_path=library.root_path,
        status=inspection.effective_status,
        is_registered=inspection.is_registered,
        registered_at=library.registered_at,
        path_policy_fingerprint=library.path_policy_hash,
        is_path_policy_current=inspection.is_path_policy_current,
    )
