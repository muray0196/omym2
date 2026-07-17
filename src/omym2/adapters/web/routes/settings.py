"""
Summary: Implements typed Settings edit, validation, preview, save, and draft routes.
Why: Exposes revision-safe Config workflows without TOML or filesystem access.
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Annotated

from fastapi import APIRouter, Depends, Header
from fastapi.responses import JSONResponse  # FastAPI resolves route return annotations.

from omym2.adapters.web.routes.api_context import (
    ApiContext,  # FastAPI resolves dependency annotations.
    SettingsRouteContext,
)
from omym2.adapters.web.routes.read_query import CORRELATION_HEADER_SCHEMA
from omym2.adapters.web.schemas.api_envelopes import ApiEnvelope, ApiFailureEnvelope
from omym2.adapters.web.schemas.api_errors import ApiError, ApiErrorCode
from omym2.adapters.web.schemas.settings import (
    AppConfigResource,
    ArtistNameMappingEntry,
    ArtistNameMappingsData,
    PathPreview,
    PathPreviewRequest,
    SaveArtistNameMappingsRequestResource,
    SettingsCandidateData,
    SettingsCandidateRequest,
    SettingsChange,
    SettingsChoices,
    SettingsData,
    SettingsValidation,
)
from omym2.config import (
    HTTP_CONFLICT_STATUS,
    HTTP_FORBIDDEN_STATUS,
    HTTP_INTERNAL_ERROR_STATUS,
    HTTP_OK_STATUS,
    HTTP_UNPROCESSABLE_CONTENT_STATUS,
    WEB_API_SETTINGS_ARTIST_NAMES_ROUTE,
    WEB_API_SETTINGS_PREVIEW_ROUTE,
    WEB_API_SETTINGS_ROUTE,
    WEB_API_SETTINGS_VALIDATE_ROUTE,
    WEB_CORRELATION_HEADER_NAME,
    WEB_CSRF_HEADER_NAME,
)
from omym2.features.artist_names.dto import SaveArtistNameMappingsRequest
from omym2.features.artist_names.usecases.save_artist_name_mappings import (
    ArtistNameMappingsRevisionMismatchError,
)
from omym2.features.common_ports import (
    ConfigRevisionMismatchError,
    ConfigStoreIoError,
    ConfigStoreValidationError,
    ExclusiveOperationBusyError,
)
from omym2.features.settings.dto import (
    PathPolicyPreviewRequest,
    PathPolicyPreviewResult,
    SaveSettingsRequest,
    SettingsValidationIssue,
    ValidateSettingsRequest,
)
from omym2.features.settings.usecases.save_settings_candidate import SettingsCandidateValidationError

if TYPE_CHECKING:
    from omym2.features.artist_names.dto import ArtistNameMappingsResult
    from omym2.features.settings.dto import (
        SettingsCandidateResult,
        SettingsChoicesResult,
        SettingsEditResult,
        SettingsFieldChange,
    )

SETTINGS_HANDLERS_UNAVAILABLE_MESSAGE = "Settings route handlers are unavailable."
CONFIG_CHANGED_MESSAGE = "Configuration changed after this edit began."
ARTIST_NAME_MAPPINGS_CHANGED_MESSAGE = "Artist-name mappings changed after this edit began."
CONFIG_IO_FAILED_MESSAGE = "Configuration storage could not complete the request."
OPERATION_IN_PROGRESS_MESSAGE = "Another state-changing operation is already in progress."
SETTINGS_VALIDATION_FAILED_MESSAGE = "Settings candidate validation failed."
GET_SETTINGS_OPERATION_ID = "getSettings"
VALIDATE_SETTINGS_OPERATION_ID = "validateSettings"
PREVIEW_SETTINGS_OPERATION_ID = "previewSettingsPath"
SAVE_SETTINGS_OPERATION_ID = "saveSettings"
SAVE_ARTIST_NAME_MAPPINGS_OPERATION_ID = "saveArtistNameMappings"


def get_settings_route_context(context: ApiContext) -> SettingsRouteContext:
    """Resolve Settings-specific collaborators from the shared route context."""
    if context.settings is None:
        raise RuntimeError(SETTINGS_HANDLERS_UNAVAILABLE_MESSAGE)
    return context.settings


type SettingsContext = Annotated[SettingsRouteContext, Depends(get_settings_route_context)]
type CsrfToken = Annotated[str, Header(alias=WEB_CSRF_HEADER_NAME, min_length=1)]


def create_settings_router() -> APIRouter:  # noqa: C901  # One schema router registers the Settings endpoints.
    """Create Settings routes without resolving Config or draft collaborators."""
    router = APIRouter()

    @router.get(
        WEB_API_SETTINGS_ROUTE,
        operation_id=GET_SETTINGS_OPERATION_ID,
        response_model=ApiEnvelope[SettingsData],
        responses={
            HTTP_OK_STATUS: {"headers": {WEB_CORRELATION_HEADER_NAME: CORRELATION_HEADER_SCHEMA}},
            HTTP_INTERNAL_ERROR_STATUS: {"model": ApiFailureEnvelope},
        },
    )
    def get_settings(  # pyright: ignore[reportUnusedFunction]  # FastAPI calls decorator-registered routes.
        context: SettingsContext,
    ) -> ApiEnvelope[SettingsData] | JSONResponse:
        try:
            result, artist_name_mappings = context.get_settings()
        except ConfigStoreIoError:
            return _config_io_failure()
        return ApiEnvelope(data=_settings_data(result, artist_name_mappings), errors=())

    @router.post(
        WEB_API_SETTINGS_VALIDATE_ROUTE,
        operation_id=VALIDATE_SETTINGS_OPERATION_ID,
        response_model=ApiEnvelope[SettingsCandidateData],
        responses={
            HTTP_OK_STATUS: {"headers": {WEB_CORRELATION_HEADER_NAME: CORRELATION_HEADER_SCHEMA}},
            HTTP_CONFLICT_STATUS: {"model": ApiFailureEnvelope},
            HTTP_UNPROCESSABLE_CONTENT_STATUS: {"model": ApiFailureEnvelope},
            HTTP_INTERNAL_ERROR_STATUS: {"model": ApiFailureEnvelope},
        },
    )
    def validate_settings(  # pyright: ignore[reportUnusedFunction]  # FastAPI calls decorator-registered routes.
        body: SettingsCandidateRequest,
        context: SettingsContext,
    ) -> ApiEnvelope[SettingsCandidateData] | JSONResponse:
        try:
            config = body.config.to_domain()
        except ValueError as exc:
            return _invalid_candidate_validation(body, context, str(exc))
        try:
            result = context.validate_settings(
                ValidateSettingsRequest(
                    config=config,
                    expected_config_revision=body.expected_config_revision,
                )
            )
        except ConfigRevisionMismatchError:
            return _config_changed_failure()
        except ConfigStoreIoError:
            return _config_io_failure()
        return ApiEnvelope(data=_candidate_data(result), errors=())

    @router.post(
        WEB_API_SETTINGS_PREVIEW_ROUTE,
        operation_id=PREVIEW_SETTINGS_OPERATION_ID,
        response_model=ApiEnvelope[PathPreview],
        responses={
            HTTP_OK_STATUS: {"headers": {WEB_CORRELATION_HEADER_NAME: CORRELATION_HEADER_SCHEMA}},
            HTTP_UNPROCESSABLE_CONTENT_STATUS: {"model": ApiFailureEnvelope},
            HTTP_INTERNAL_ERROR_STATUS: {"model": ApiFailureEnvelope},
        },
    )
    def preview_settings_path(  # pyright: ignore[reportUnusedFunction]  # FastAPI calls decorator-registered routes.
        body: PathPreviewRequest,
        context: SettingsContext,
    ) -> ApiEnvelope[PathPreview]:
        try:
            result = context.preview_path_policy(_preview_request(body))
        except ValueError as exc:
            result = _invalid_preview(str(exc))
        return ApiEnvelope(data=_path_preview(result), errors=())

    @router.put(
        WEB_API_SETTINGS_ROUTE,
        operation_id=SAVE_SETTINGS_OPERATION_ID,
        response_model=ApiEnvelope[SettingsCandidateData],
        responses={
            HTTP_OK_STATUS: {"headers": {WEB_CORRELATION_HEADER_NAME: CORRELATION_HEADER_SCHEMA}},
            HTTP_FORBIDDEN_STATUS: {"model": ApiFailureEnvelope},
            HTTP_CONFLICT_STATUS: {"model": ApiFailureEnvelope},
            HTTP_UNPROCESSABLE_CONTENT_STATUS: {"model": ApiFailureEnvelope},
            HTTP_INTERNAL_ERROR_STATUS: {"model": ApiFailureEnvelope},
        },
    )
    def save_settings(  # pyright: ignore[reportUnusedFunction]  # FastAPI calls decorator-registered routes.
        body: SettingsCandidateRequest,
        context: SettingsContext,
        csrf_token: CsrfToken,
    ) -> ApiEnvelope[SettingsCandidateData] | JSONResponse:
        _ = csrf_token
        try:
            config = body.config.to_domain()
        except ValueError as exc:
            return _settings_validation_failure((SettingsValidationIssue(field="config", message=str(exc)),))
        try:
            result = context.save_settings(
                SaveSettingsRequest(
                    config=config,
                    expected_config_revision=body.expected_config_revision,
                )
            )
        except (
            ConfigRevisionMismatchError,
            ConfigStoreIoError,
            ConfigStoreValidationError,
            ExclusiveOperationBusyError,
            SettingsCandidateValidationError,
        ) as exc:
            return _save_exception_response(exc)
        return ApiEnvelope(data=_candidate_data(result), errors=())

    @router.put(
        WEB_API_SETTINGS_ARTIST_NAMES_ROUTE,
        operation_id=SAVE_ARTIST_NAME_MAPPINGS_OPERATION_ID,
        response_model=ApiEnvelope[ArtistNameMappingsData],
        responses={
            HTTP_OK_STATUS: {"headers": {WEB_CORRELATION_HEADER_NAME: CORRELATION_HEADER_SCHEMA}},
            HTTP_FORBIDDEN_STATUS: {"model": ApiFailureEnvelope},
            HTTP_CONFLICT_STATUS: {"model": ApiFailureEnvelope},
            HTTP_UNPROCESSABLE_CONTENT_STATUS: {"model": ApiFailureEnvelope},
            HTTP_INTERNAL_ERROR_STATUS: {"model": ApiFailureEnvelope},
        },
    )
    def save_artist_name_mappings(  # pyright: ignore[reportUnusedFunction]  # FastAPI calls decorator-registered routes.
        body: SaveArtistNameMappingsRequestResource,
        context: SettingsContext,
        csrf_token: CsrfToken,
    ) -> ApiEnvelope[ArtistNameMappingsData] | JSONResponse:
        _ = csrf_token
        try:
            result = context.save_artist_name_mappings(
                SaveArtistNameMappingsRequest(
                    entries=body.entries,
                    expected_revision=body.expected_revision,
                )
            )
        except ArtistNameMappingsRevisionMismatchError:
            return _artist_name_mappings_changed_failure()
        except ExclusiveOperationBusyError:
            return _operation_in_progress_failure()
        except ValueError as exc:
            return _settings_validation_failure(
                (SettingsValidationIssue(field="artist_name_mappings", message=str(exc)),)
            )
        return ApiEnvelope(data=_artist_name_mappings_data(result), errors=())

    return router


def _settings_data(
    result: SettingsEditResult,
    artist_name_mappings: ArtistNameMappingsResult,
) -> SettingsData:
    return SettingsData(
        config=AppConfigResource.from_domain(result.config),
        config_revision=result.config_revision,
        choices=_settings_choices(result.choices),
        validation=_settings_validation(
            valid=result.valid,
            issues=result.validation_issues,
            code=ApiErrorCode.CONFIG_INVALID,
        ),
        preview=_path_preview(result.preview),
        artist_name_mappings=_artist_name_mappings_data(artist_name_mappings),
    )


def _candidate_data(result: SettingsCandidateResult) -> SettingsCandidateData:
    return SettingsCandidateData(
        config=AppConfigResource.from_domain(result.config),
        config_revision=result.config_revision,
        changes=tuple(_settings_change(change) for change in result.changes),
        validation=_settings_validation(
            valid=result.valid,
            issues=result.validation_issues,
            code=ApiErrorCode.VALIDATION_FAILED,
        ),
        preview=_path_preview(result.preview),
    )


def _settings_choices(choices: SettingsChoicesResult) -> SettingsChoices:
    return SettingsChoices(
        command_modes=choices.command_modes,
        disc_number_styles=choices.disc_number_styles,
        disc_number_conditions=choices.disc_number_conditions,
        album_year_resolutions=choices.album_year_resolutions,
        target_exists_policies=choices.target_exists_policies,
        duplicate_hash_policies=choices.duplicate_hash_policies,
        missing_metadata_policies=choices.missing_metadata_policies,
        musicbrainz_cache_policies=choices.musicbrainz_cache_policies,
        logging_levels=choices.logging_levels,
        unprocessed_result_preview_limit_min=choices.unprocessed_result_preview_limit_min,
        unprocessed_result_preview_limit_max=choices.unprocessed_result_preview_limit_max,
        path_placeholders=choices.path_placeholders,
    )


def _settings_validation(
    *,
    valid: bool,
    issues: tuple[SettingsValidationIssue, ...],
    code: ApiErrorCode,
) -> SettingsValidation:
    return SettingsValidation(valid=valid, errors=tuple(_issue_error(issue, code) for issue in issues))


def _settings_change(change: SettingsFieldChange) -> SettingsChange:
    return SettingsChange(field=change.field, before=change.before, after=change.after)


def _path_preview(result: PathPolicyPreviewResult) -> PathPreview:
    errors = tuple(
        ApiError(
            code=ApiErrorCode.VALIDATION_FAILED,
            message=message,
            field="path_policy",
            retryable=False,
        )
        for message in result.errors
    )
    return PathPreview(path=result.path, errors=errors)


def _preview_request(body: PathPreviewRequest) -> PathPolicyPreviewRequest:
    return PathPolicyPreviewRequest(
        path_policy=body.path_policy.to_domain(),
        artist_ids=body.artist_ids.to_domain(),
        metadata=body.metadata.to_domain(),
        file_extension=body.file_extension,
    )


def _invalid_preview(message: str) -> PathPolicyPreviewResult:
    return PathPolicyPreviewResult(path=None, errors=(message,))


def _invalid_candidate_validation(
    body: SettingsCandidateRequest,
    context: SettingsRouteContext,
    message: str,
) -> ApiEnvelope[SettingsCandidateData] | JSONResponse:
    try:
        current, _ = context.get_settings()
    except ConfigStoreIoError:
        return _config_io_failure()
    if current.config_revision != body.expected_config_revision:
        return _config_changed_failure()
    issue = SettingsValidationIssue(field="config", message=message)
    return ApiEnvelope(
        data=SettingsCandidateData(
            config=body.config,
            config_revision=current.config_revision,
            changes=(),
            validation=_settings_validation(
                valid=False,
                issues=(issue,),
                code=ApiErrorCode.VALIDATION_FAILED,
            ),
            preview=_path_preview(_invalid_preview(message)),
        ),
        errors=(),
    )


def _artist_name_mappings_data(result: ArtistNameMappingsResult) -> ArtistNameMappingsData:
    return ArtistNameMappingsData(
        entries=tuple(
            ArtistNameMappingEntry(
                source_name=mapping.source_name,
                english_name=mapping.resolved_name,
                source=mapping.provider,
                selected_name_kind=mapping.selected_name_kind,
                selected_locale=mapping.selected_locale,
            )
            for mapping in result.mappings
        ),
        revision=result.revision,
    )


def _issue_error(issue: SettingsValidationIssue, code: ApiErrorCode) -> ApiError:
    return ApiError(
        code=code,
        message=issue.message,
        field=issue.field,
        retryable=False,
    )


def _config_changed_failure() -> JSONResponse:
    return _failure_response(
        HTTP_CONFLICT_STATUS,
        (ApiError(code=ApiErrorCode.CONFIG_CHANGED, message=CONFIG_CHANGED_MESSAGE, retryable=False),),
    )


def _artist_name_mappings_changed_failure() -> JSONResponse:
    return _failure_response(
        HTTP_CONFLICT_STATUS,
        (
            ApiError(
                code=ApiErrorCode.ARTIST_NAME_MAPPINGS_CHANGED,
                message=ARTIST_NAME_MAPPINGS_CHANGED_MESSAGE,
                retryable=False,
            ),
        ),
    )


def _operation_in_progress_failure() -> JSONResponse:
    return _failure_response(
        HTTP_CONFLICT_STATUS,
        (
            ApiError(
                code=ApiErrorCode.OPERATION_IN_PROGRESS,
                message=OPERATION_IN_PROGRESS_MESSAGE,
                retryable=False,
            ),
        ),
    )


def _save_exception_response(
    exc: ConfigRevisionMismatchError
    | ConfigStoreIoError
    | ConfigStoreValidationError
    | ExclusiveOperationBusyError
    | SettingsCandidateValidationError,
) -> JSONResponse:
    if isinstance(exc, ConfigRevisionMismatchError):
        return _config_changed_failure()
    if isinstance(exc, ExclusiveOperationBusyError):
        return _operation_in_progress_failure()
    if isinstance(exc, SettingsCandidateValidationError):
        return _settings_validation_failure(exc.issues)
    if isinstance(exc, ConfigStoreValidationError):
        issues = tuple(SettingsValidationIssue(field="config", message=message) for message in exc.errors)
        return _settings_validation_failure(issues)
    return _config_io_failure()


def _settings_validation_failure(issues: tuple[SettingsValidationIssue, ...]) -> JSONResponse:
    errors = tuple(_issue_error(issue, ApiErrorCode.VALIDATION_FAILED) for issue in issues)
    if not errors:
        errors = (
            ApiError(
                code=ApiErrorCode.VALIDATION_FAILED,
                message=SETTINGS_VALIDATION_FAILED_MESSAGE,
                retryable=False,
            ),
        )
    return _failure_response(HTTP_UNPROCESSABLE_CONTENT_STATUS, errors)


def _config_io_failure() -> JSONResponse:
    return _failure_response(
        HTTP_INTERNAL_ERROR_STATUS,
        (ApiError(code=ApiErrorCode.CONFIG_IO_FAILED, message=CONFIG_IO_FAILED_MESSAGE, retryable=True),),
    )


def _failure_response(status_code: int, errors: tuple[ApiError, ...]) -> JSONResponse:
    envelope = ApiFailureEnvelope(data=None, errors=errors)
    return JSONResponse(envelope.model_dump(mode="json"), status_code=status_code)
