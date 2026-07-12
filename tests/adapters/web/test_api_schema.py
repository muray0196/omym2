"""
Summary: Tests the no-I/O Web API schema application.
Why: Prevents production routes and the committed generated client contract from drifting.
"""

from __future__ import annotations

import json
from typing import TYPE_CHECKING, cast

import pytest
from pydantic import ValidationError

from omym2.adapters.web.app import create_web_app
from omym2.adapters.web.routes.api_context import ApiRouteContext
from omym2.adapters.web.schema_app import create_api_schema_app
from omym2.adapters.web.schemas.api_envelopes import ApiEnvelope
from omym2.adapters.web.schemas.api_errors import ApiError, ApiErrorCode
from omym2.config import WEB_API_BOOTSTRAP_ROUTE, WEB_CORRELATION_HEADER_NAME

SCHEMA_EXECUTION_MESSAGE = "Schema generation must not execute route dependencies."

if TYPE_CHECKING:
    from pathlib import Path


def test_schema_app_exports_only_the_production_bootstrap_route(tmp_path: Path) -> None:
    """Schema generation registers no legacy or future route and performs no I/O."""
    schema_app = create_api_schema_app()
    production_app = create_web_app(
        ApiRouteContext(csrf_token="unused", get_bootstrap=_must_not_execute),  # noqa: S106  # Non-secret test value.
        tmp_path / "missing-static",
    )

    schema = cast("dict[str, object]", schema_app.openapi())
    production_schema = cast("dict[str, object]", production_app.openapi())
    paths = _mapping(schema, "paths")
    production_paths = _mapping(production_schema, "paths")
    schemas = _mapping(_mapping(schema, "components"), "schemas")

    assert set(paths) == {WEB_API_BOOTSTRAP_ROUTE}
    assert production_paths == paths
    assert "HTTPValidationError" not in schemas
    assert not tuple(tmp_path.iterdir())


def test_openapi_output_is_deterministic_and_declares_typed_responses() -> None:
    """Repeated exports are byte-identical and contain success and error schemas."""
    first = cast("dict[str, object]", create_api_schema_app().openapi())
    second = cast("dict[str, object]", create_api_schema_app().openapi())
    operation = _mapping(_mapping(_mapping(first, "paths"), WEB_API_BOOTSTRAP_ROUTE), "get")
    responses = _mapping(operation, "responses")
    success = _mapping(responses, "200")
    failure = _mapping(responses, "500")
    schemas = _mapping(_mapping(first, "components"), "schemas")
    failure_envelope = _mapping(schemas, "ApiFailureEnvelope")
    api_error_properties = _mapping(_mapping(schemas, "ApiError"), "properties")
    remediation_properties = _mapping(_mapping(schemas, "ApiRemediation"), "properties")

    assert json.dumps(first, indent=2, sort_keys=True) == json.dumps(second, indent=2, sort_keys=True)
    assert operation["operationId"] == "getBootstrap"
    assert set(responses) == {"200", "500"}
    assert _mapping(_mapping(_mapping(success, "content"), "application/json"), "schema")
    assert _mapping(_mapping(_mapping(failure, "content"), "application/json"), "schema")
    assert set(cast("list[str]", failure_envelope["required"])) == {"data", "errors"}
    assert _mapping(api_error_properties, "field")["type"] == "string"
    assert "field" not in cast("list[str]", _mapping(schemas, "ApiError")["required"])
    assert _mapping(remediation_properties, "route")["type"] == "string"
    assert _mapping(remediation_properties, "command")["type"] == "string"
    assert WEB_CORRELATION_HEADER_NAME in _mapping(success, "headers")
    assert WEB_CORRELATION_HEADER_NAME in _mapping(failure, "headers")


def test_generic_envelope_enforces_failure_and_bootstrap_exception_boundaries() -> None:
    """Empty envelopes and non-Bootstrap data/error mixtures are invalid."""
    error = ApiError(code=ApiErrorCode.INTERNAL_ERROR, message="Request failed.", retryable=True)

    with pytest.raises(ValidationError):
        _ = ApiEnvelope[str](data=None, errors=())
    with pytest.raises(ValidationError):
        _ = ApiEnvelope[str](data="normal data", errors=(error,))

    failure = ApiEnvelope[str](data=None, errors=(error,))
    assert failure.errors == (error,)


def _must_not_execute():
    raise AssertionError(SCHEMA_EXECUTION_MESSAGE)


def _mapping(value: dict[str, object], key: str) -> dict[str, object]:
    nested = value[key]
    assert isinstance(nested, dict)
    return cast("dict[str, object]", nested)
