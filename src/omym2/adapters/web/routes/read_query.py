"""
Summary: Translates shared read-query pagination and failures for Web routes.
Why: Keeps opaque cursor and typed error handling consistent across M2 slices.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from omym2.adapters.web.routes.api_responses import api_failure_response
from omym2.adapters.web.schemas.api_errors import ApiErrorCode
from omym2.config import HTTP_NOT_FOUND_STATUS, HTTP_UNPROCESSABLE_CONTENT_STATUS
from omym2.shared.pagination import PageRequest, clamp_limit, decode_cursor

if TYPE_CHECKING:
    from fastapi.responses import JSONResponse

CORRELATION_HEADER_SCHEMA = {
    "description": "Request correlation identifier written to server logs.",
    "schema": {"type": "string"},
}
INVALID_CURSOR_MESSAGE = "Cursor is invalid for this endpoint."
INVALID_LIMIT_MESSAGE = "Page limit must be at least 1."


def page_request(limit: int | None, cursor: str | None) -> PageRequest:
    """Build a clamped PageRequest while preserving the cursor as opaque input."""
    return PageRequest(
        limit=clamp_limit(limit),
        cursor_key=None if cursor is None else decode_cursor(cursor),
    )


def validation_failure(*, field: str, message: str) -> JSONResponse:
    """Return one typed 422 read-query failure."""
    return api_failure_response(
        HTTP_UNPROCESSABLE_CONTENT_STATUS,
        ApiErrorCode.VALIDATION_FAILED,
        message,
        field=field,
    )


def not_found_failure(code: ApiErrorCode, message: str, *, field: str) -> JSONResponse:
    """Return one typed 404 identity failure."""
    return api_failure_response(HTTP_NOT_FOUND_STATUS, code, message, field=field)
