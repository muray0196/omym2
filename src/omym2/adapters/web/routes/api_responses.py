"""
Summary: Builds typed Web API failure responses for route-known errors.
Why: Preserves the common envelope when a usecase rejects a request.
"""

from __future__ import annotations

from fastapi.responses import JSONResponse

from omym2.adapters.web.schemas.api_envelopes import ApiFailureEnvelope
from omym2.adapters.web.schemas.api_errors import ApiError, ApiErrorCode


def api_failure_response(
    status_code: int,
    code: ApiErrorCode,
    message: str,
    *,
    field: str | None = None,
) -> JSONResponse:
    """Return one typed failure envelope for an expected route error."""
    error_values: dict[str, object] = {
        "code": code,
        "message": message,
        "retryable": False,
    }
    if field is not None:
        error_values["field"] = field
    envelope = ApiFailureEnvelope(
        data=None,
        errors=(ApiError.model_validate(error_values),),
    )
    return JSONResponse(envelope.model_dump(mode="json"), status_code=status_code)
