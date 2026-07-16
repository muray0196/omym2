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
from omym2.config import (
    WEB_API_ADD_PLAN_ROUTE,
    WEB_API_APPLY_PLAN_ROUTE,
    WEB_API_BOOTSTRAP_ROUTE,
    WEB_API_CANCEL_PLAN_ROUTE,
    WEB_API_CHECK_FACETS_ROUTE,
    WEB_API_CHECK_GROUPS_ROUTE,
    WEB_API_CHECK_ROUTE,
    WEB_API_CHECK_RUN_ROUTE,
    WEB_API_HISTORY_FACETS_ROUTE,
    WEB_API_HISTORY_ROUTE,
    WEB_API_LIBRARIES_ROUTE,
    WEB_API_LIBRARY_DETAIL_ROUTE,
    WEB_API_OPERATION_ROUTE,
    WEB_API_ORGANIZE_PLAN_ROUTE,
    WEB_API_PLAN_ACTIONS_ROUTE,
    WEB_API_PLAN_DETAIL_ROUTE,
    WEB_API_PLAN_FACETS_ROUTE,
    WEB_API_PLAN_GROUPS_ROUTE,
    WEB_API_PLANS_ROUTE,
    WEB_API_REFRESH_PLAN_ROUTE,
    WEB_API_RUN_DETAIL_ROUTE,
    WEB_API_RUN_EVENT_FACETS_ROUTE,
    WEB_API_RUN_EVENT_GROUPS_ROUTE,
    WEB_API_RUN_EVENTS_ROUTE,
    WEB_API_SETTINGS_ARTIST_IDS_ROUTE,
    WEB_API_SETTINGS_PREVIEW_ROUTE,
    WEB_API_SETTINGS_ROUTE,
    WEB_API_SETTINGS_VALIDATE_ROUTE,
    WEB_API_TRACK_DETAIL_ROUTE,
    WEB_API_TRACK_FACETS_ROUTE,
    WEB_API_TRACK_GROUPS_ROUTE,
    WEB_API_TRACKS_ROUTE,
    WEB_API_UNDO_PLAN_ROUTE,
    WEB_CORRELATION_HEADER_NAME,
    WEB_CSRF_HEADER_NAME,
)

SCHEMA_EXECUTION_MESSAGE = "Schema generation must not execute route dependencies."

if TYPE_CHECKING:
    from pathlib import Path


def test_schema_app_exports_the_production_routes_without_io(tmp_path: Path) -> None:
    """Schema generation registers the exact production routes and performs no application I/O."""
    schema_app = create_api_schema_app()
    production_app = create_web_app(
        ApiRouteContext(csrf_token="unused", get_bootstrap=_must_not_execute),  # noqa: S106  # Non-secret test value.
        tmp_path / "missing-static",
    )

    schema = cast("dict[str, object]", schema_app.openapi())
    production_schema = cast("dict[str, object]", production_app.openapi())
    paths = _mapping(schema, "paths")
    production_paths = _mapping(production_schema, "paths")

    assert set(paths) == {
        WEB_API_BOOTSTRAP_ROUTE,
        WEB_API_OPERATION_ROUTE,
        WEB_API_ADD_PLAN_ROUTE,
        WEB_API_ORGANIZE_PLAN_ROUTE,
        WEB_API_REFRESH_PLAN_ROUTE,
        WEB_API_APPLY_PLAN_ROUTE,
        WEB_API_CANCEL_PLAN_ROUTE,
        WEB_API_CHECK_RUN_ROUTE,
        WEB_API_SETTINGS_ROUTE,
        WEB_API_SETTINGS_VALIDATE_ROUTE,
        WEB_API_SETTINGS_PREVIEW_ROUTE,
        WEB_API_SETTINGS_ARTIST_IDS_ROUTE,
        WEB_API_LIBRARIES_ROUTE,
        WEB_API_LIBRARY_DETAIL_ROUTE,
        WEB_API_PLANS_ROUTE,
        WEB_API_PLAN_DETAIL_ROUTE,
        WEB_API_PLAN_ACTIONS_ROUTE,
        WEB_API_PLAN_FACETS_ROUTE,
        WEB_API_PLAN_GROUPS_ROUTE,
        WEB_API_TRACKS_ROUTE,
        WEB_API_TRACK_DETAIL_ROUTE,
        WEB_API_TRACK_FACETS_ROUTE,
        WEB_API_TRACK_GROUPS_ROUTE,
        WEB_API_CHECK_ROUTE,
        WEB_API_CHECK_FACETS_ROUTE,
        WEB_API_CHECK_GROUPS_ROUTE,
        WEB_API_HISTORY_ROUTE,
        WEB_API_HISTORY_FACETS_ROUTE,
        WEB_API_RUN_DETAIL_ROUTE,
        WEB_API_RUN_EVENTS_ROUTE,
        WEB_API_RUN_EVENT_FACETS_ROUTE,
        WEB_API_RUN_EVENT_GROUPS_ROUTE,
        WEB_API_UNDO_PLAN_ROUTE,
    }
    assert production_paths == paths
    schemas = _mapping(_mapping(schema, "components"), "schemas")
    assert "HTTPValidationError" not in schemas
    assert not tuple(tmp_path.iterdir())


def test_settings_operations_have_stable_ids_and_declared_typed_errors() -> None:
    """Generated Settings clients receive all synchronous and draft-only operations."""
    schema = cast("dict[str, object]", create_api_schema_app().openapi())
    paths = _mapping(schema, "paths")
    settings = _mapping(paths, WEB_API_SETTINGS_ROUTE)

    assert _mapping(settings, "get")["operationId"] == "getSettings"
    assert _mapping(settings, "put")["operationId"] == "saveSettings"
    assert _mapping(_mapping(paths, WEB_API_SETTINGS_VALIDATE_ROUTE), "post")["operationId"] == "validateSettings"
    assert _mapping(_mapping(paths, WEB_API_SETTINGS_PREVIEW_ROUTE), "post")["operationId"] == "previewSettingsPath"
    assert _mapping(_mapping(paths, WEB_API_SETTINGS_ARTIST_IDS_ROUTE), "post")["operationId"] == (
        "generateArtistIdDraft"
    )
    put_responses = _mapping(_mapping(settings, "put"), "responses")
    assert {"200", "403", "409", "422", "500"} <= set(put_responses)
    schemas = _mapping(_mapping(schema, "components"), "schemas")
    assert "SettingsData" in schemas
    assert "SettingsCandidateData" in schemas
    assert "ArtistIdDraftData" in schemas
    assert "ArtistNameConfigResource" in schemas
    app_config_properties = _mapping(_mapping(schemas, "AppConfigResource"), "properties")
    settings_choices_properties = _mapping(_mapping(schemas, "SettingsChoices"), "properties")
    preview_properties = _mapping(_mapping(schemas, "PathPreviewRequest"), "properties")
    assert {
        "artist_names",
        "musicbrainz",
        "fasttext",
        "hashing",
        "logging",
        "companions",
        "unprocessed",
    } <= set(app_config_properties)
    assert {
        "musicbrainz_cache_policies",
        "logging_levels",
        "unprocessed_result_preview_limit_min",
        "unprocessed_result_preview_limit_max",
    } <= set(settings_choices_properties)
    assert "artist_names" in preview_properties


def test_plan_read_operations_have_stable_ids_and_declared_typed_errors() -> None:
    """Generated clients receive stable operation names and envelope-only error models."""
    schema = cast("dict[str, object]", create_api_schema_app().openapi())
    paths = _mapping(schema, "paths")

    assert _operation(paths, WEB_API_PLANS_ROUTE)["operationId"] == "listPlans"
    assert _operation(paths, WEB_API_PLAN_ACTIONS_ROUTE)["operationId"] == "listPlanActions"
    assert _operation(paths, WEB_API_PLAN_FACETS_ROUTE)["operationId"] == "getPlanActionFacets"
    assert _operation(paths, WEB_API_PLAN_GROUPS_ROUTE)["operationId"] == "groupPlanActions"
    for path in (
        WEB_API_PLANS_ROUTE,
        WEB_API_PLAN_ACTIONS_ROUTE,
        WEB_API_PLAN_FACETS_ROUTE,
        WEB_API_PLAN_GROUPS_ROUTE,
    ):
        responses = _mapping(_operation(paths, path), "responses")
        assert "422" in responses
        assert "500" in responses
    schemas = _mapping(_mapping(schema, "components"), "schemas")
    for path in (
        WEB_API_PLANS_ROUTE,
        WEB_API_PLAN_ACTIONS_ROUTE,
        WEB_API_PLAN_FACETS_ROUTE,
        WEB_API_PLAN_GROUPS_ROUTE,
    ):
        failure_schema = _response_schema(_mapping(_operation(paths, path), "responses"), "422")
        assert failure_schema != {"$ref": "#/components/schemas/HTTPValidationError"}
    assert "ApiFailureEnvelope" in schemas


def test_extended_file_catalogs_and_resource_identity_fields_are_explicit() -> None:
    """Generated schemas expose companion identity and every extended file catalog value."""
    schema = cast("dict[str, object]", create_api_schema_app().openapi())
    schemas = _mapping(_mapping(schema, "components"), "schemas")

    plan_action_properties = _mapping(_mapping(schemas, "PlanActionResource"), "properties")
    file_event_properties = _mapping(_mapping(schemas, "FileEventResource"), "properties")
    check_issue_properties = _mapping(_mapping(schemas, "CheckIssueResource"), "properties")
    count_properties = _mapping(_mapping(schemas, "PlanActionTypeCounts"), "properties")

    assert {"companion_asset_id", "owner_action_id", "depends_on_action_ids"} <= set(plan_action_properties)
    assert "companion_asset_id" in file_event_properties
    assert "companion_asset_id" in check_issue_properties
    assert {"move_lyrics", "move_artwork", "move_unprocessed"} <= set(count_properties)
    assert {"move_lyrics", "move_artwork", "move_unprocessed"} <= set(
        cast("list[str]", _mapping(schemas, "ActionType")["enum"])
    )
    assert {
        "companion_owner_blocked",
        "companion_association_ambiguous",
        "companion_dependency_failed",
    } <= set(cast("list[str]", _mapping(schemas, "PlanActionReason")["enum"]))
    assert {"move_lyrics_file", "move_artwork_file", "move_unprocessed_file"} <= set(
        cast("list[str]", _mapping(schemas, "FileEventType")["enum"])
    )
    assert {
        "companion_file_missing",
        "companion_content_hash_changed",
        "companion_current_path_differs_from_canonical_path",
        "companion_owner_missing",
        "unmanaged_companion_exists",
        "failed_companion_source_exists",
        "unprocessed_file_missing",
        "unprocessed_content_hash_changed",
    } <= set(cast("list[str]", _mapping(schemas, "CheckIssueType")["enum"]))


def test_m4_execution_operations_have_stable_ids_and_typed_errors() -> None:
    """Generated clients receive stable names, errors, and required mutation headers."""
    schema = cast("dict[str, object]", create_api_schema_app().openapi())
    paths = _mapping(schema, "paths")

    assert _mapping(_mapping(paths, WEB_API_APPLY_PLAN_ROUTE), "post")["operationId"] == "applyPlan"
    assert _mapping(_mapping(paths, WEB_API_CANCEL_PLAN_ROUTE), "post")["operationId"] == "cancelPlan"
    assert _mapping(_mapping(paths, WEB_API_UNDO_PLAN_ROUTE), "post")["operationId"] == "createUndoPlan"
    for path in (WEB_API_APPLY_PLAN_ROUTE, WEB_API_CANCEL_PLAN_ROUTE, WEB_API_UNDO_PLAN_ROUTE):
        responses = _mapping(_mapping(_mapping(paths, path), "post"), "responses")
        assert {"200", "403", "409", "422", "500"} <= set(responses)
        assert _response_schema(responses, "422") == {"$ref": "#/components/schemas/ApiFailureEnvelope"}
    for path in (
        WEB_API_ADD_PLAN_ROUTE,
        WEB_API_ORGANIZE_PLAN_ROUTE,
        WEB_API_REFRESH_PLAN_ROUTE,
        WEB_API_CHECK_RUN_ROUTE,
        WEB_API_APPLY_PLAN_ROUTE,
        WEB_API_UNDO_PLAN_ROUTE,
    ):
        operation = _mapping(_mapping(paths, path), "post")
        csrf_parameter = _header_parameter(operation, WEB_CSRF_HEADER_NAME)
        assert csrf_parameter["required"] is True


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


def _operation(paths: dict[str, object], path: str) -> dict[str, object]:
    """Return one GET operation object from the generated schema."""
    return _mapping(_mapping(paths, path), "get")


def _response_schema(responses: dict[str, object], status_code: str) -> dict[str, object]:
    """Return one declared JSON response schema."""
    response = _mapping(responses, status_code)
    content = _mapping(response, "content")
    media_type = _mapping(content, "application/json")
    return _mapping(media_type, "schema")


def _header_parameter(operation: dict[str, object], name: str) -> dict[str, object]:
    """Return one named header parameter from an OpenAPI operation."""
    raw_parameters = operation["parameters"]
    assert isinstance(raw_parameters, list)
    parameters = cast("list[object]", raw_parameters)
    for parameter in parameters:
        assert isinstance(parameter, dict)
        typed_parameter = cast("dict[str, object]", parameter)
        if typed_parameter.get("in") == "header" and typed_parameter.get("name") == name:
            return typed_parameter
    raise AssertionError(name)
