"""
Summary: Defines local Web UI settings routes.
Why: Exposes settings display, editing, validation, diff, and preview in one screen.
"""

from __future__ import annotations

from dataclasses import dataclass
from secrets import compare_digest
from typing import TYPE_CHECKING
from urllib.parse import parse_qs

from fastapi import APIRouter, Request
from fastapi.responses import HTMLResponse

from omym2.adapters.web.schemas.settings_form import (
    FIELD_ADD_AUTO_APPLY,
    FIELD_ADD_DEFAULT_MODE,
    FIELD_COLLISION_ON_DUPLICATE_HASH,
    FIELD_COLLISION_ON_MISSING_METADATA,
    FIELD_COLLISION_ON_TARGET_EXISTS,
    FIELD_INCOMING,
    FIELD_LIBRARY,
    FIELD_METADATA_PREFER_ALBUM_ARTIST,
    FIELD_METADATA_REQUIRE_ALBUM,
    FIELD_METADATA_REQUIRE_ARTIST,
    FIELD_METADATA_REQUIRE_TITLE,
    FIELD_ORGANIZE_AUTO_APPLY,
    FIELD_ORGANIZE_DEFAULT_MODE,
    FIELD_ORGANIZE_ONLY_MISPLACED,
    FIELD_PATH_POLICY_MAX_FILENAME_LENGTH,
    FIELD_PATH_POLICY_SANITIZE,
    FIELD_PATH_POLICY_TEMPLATE,
    FIELD_PATH_POLICY_UNKNOWN_ALBUM,
    FIELD_PATH_POLICY_UNKNOWN_ARTIST,
    FIELD_REFRESH_AUTO_APPLY,
    FIELD_REFRESH_DEFAULT_MODE,
    FIELD_UI_SHOW_ADVANCED_SETTINGS,
    FIELD_UI_THEME,
    FORM_ACTION_FIELD,
    FORM_ACTION_SAVE,
    FORM_ACTION_VALIDATE,
    FORM_CSRF_FIELD,
    SettingsChange,
    describe_config_changes,
    parse_settings_form,
)
from omym2.config import (
    ALLOWED_COLLISION_DUPLICATE_HASH_POLICIES,
    ALLOWED_COLLISION_MISSING_METADATA_POLICIES,
    ALLOWED_COLLISION_TARGET_EXISTS_POLICIES,
    ALLOWED_COMMAND_MODES,
    ALLOWED_UI_THEMES,
    CONFIG_FILE_ENCODING,
    PATH_POLICY_PREVIEW_ALBUM,
    PATH_POLICY_PREVIEW_ALBUM_ARTIST,
    PATH_POLICY_PREVIEW_ARTIST,
    PATH_POLICY_PREVIEW_DISC_NUMBER,
    PATH_POLICY_PREVIEW_FILE_EXTENSION,
    PATH_POLICY_PREVIEW_TITLE,
    PATH_POLICY_PREVIEW_TRACK_NUMBER,
    PATH_POLICY_PREVIEW_YEAR,
    WEB_SETTINGS_ROUTE,
    WEB_SETTINGS_TEMPLATE_NAME,
)
from omym2.domain.models.app_config import AppConfig
from omym2.domain.models.track_metadata import TrackMetadata
from omym2.features.common_ports import ConfigStoreValidationError
from omym2.features.settings.dto import PathPolicyPreviewRequest, SaveSettingsRequest, ValidateSettingsResult
from omym2.features.settings.usecases.load_settings import LoadSettingsUseCase
from omym2.features.settings.usecases.preview_path_policy import PreviewPathPolicyUseCase
from omym2.features.settings.usecases.save_settings import SaveSettingsUseCase
from omym2.features.settings.usecases.validate_settings import ValidateSettingsUseCase

if TYPE_CHECKING:
    from fastapi.templating import Jinja2Templates
    from starlette.responses import Response

    from omym2.features.settings.ports import SettingsPorts

ERROR_STATUS_CODE = 400
FORBIDDEN_STATUS_CODE = 403
SUCCESS_STATUS_CODE = 200
SAVE_CSRF_ERROR_MESSAGE = "Settings save request failed CSRF validation."
SETTINGS_SAVED_MESSAGE = "Settings saved."
SETTINGS_VALID_MESSAGE = "Settings are valid."


@dataclass(frozen=True, slots=True)
class SettingsRouteContext:
    """Concrete dependencies for settings routes."""

    csrf_token: str
    ports: SettingsPorts
    templates: Jinja2Templates


@dataclass(frozen=True, slots=True)
class SettingsTemplateState:
    """Values rendered by the settings template."""

    current_config: AppConfig
    form_config: AppConfig
    errors: tuple[str, ...]
    status_message: str
    changes: tuple[SettingsChange, ...]
    status_code: int


def create_settings_router(context: SettingsRouteContext) -> APIRouter:
    """Create settings routes bound to concrete route dependencies."""
    router = APIRouter()

    def show_settings(request: Request) -> Response:
        """Render the current settings screen."""
        current_config, load_errors = _load_current_config(context.ports)
        return _render_settings(
            context,
            request,
            SettingsTemplateState(
                current_config=current_config,
                form_config=current_config,
                errors=load_errors,
                status_message="",
                changes=(),
                status_code=SUCCESS_STATUS_CODE,
            ),
        )

    async def update_settings(request: Request) -> Response:
        """Validate or save settings posted by the local form."""
        current_config, load_errors = _load_current_config(context.ports)
        form_data = await _read_urlencoded_form(request)
        form_result = parse_settings_form(form_data)
        if form_result.config is None:
            return _render_settings(
                context,
                request,
                SettingsTemplateState(
                    current_config=current_config,
                    form_config=current_config,
                    errors=load_errors + form_result.errors,
                    status_message="",
                    changes=(),
                    status_code=ERROR_STATUS_CODE,
                ),
            )

        proposed_config = form_result.config
        changes = describe_config_changes(current_config, proposed_config)
        action = form_data.get(FORM_ACTION_FIELD, FORM_ACTION_VALIDATE)
        if action == FORM_ACTION_SAVE:
            if not _has_valid_csrf_token(context, form_data):
                return _render_settings(
                    context,
                    request,
                    SettingsTemplateState(
                        current_config=current_config,
                        form_config=proposed_config,
                        errors=(SAVE_CSRF_ERROR_MESSAGE,),
                        status_message="",
                        changes=changes,
                        status_code=FORBIDDEN_STATUS_CODE,
                    ),
                )
            try:
                SaveSettingsUseCase(context.ports).execute(SaveSettingsRequest(config=proposed_config))
            except OSError as exc:
                return _render_settings(
                    context,
                    request,
                    SettingsTemplateState(
                        current_config=current_config,
                        form_config=proposed_config,
                        errors=(f"Config I/O error: {exc}",),
                        status_message="",
                        changes=changes,
                        status_code=ERROR_STATUS_CODE,
                    ),
                )

        return _render_settings(
            context,
            request,
            SettingsTemplateState(
                current_config=proposed_config if action == FORM_ACTION_SAVE else current_config,
                form_config=proposed_config,
                errors=(),
                status_message=SETTINGS_SAVED_MESSAGE if action == FORM_ACTION_SAVE else SETTINGS_VALID_MESSAGE,
                changes=changes,
                status_code=SUCCESS_STATUS_CODE,
            ),
        )

    router.add_api_route(WEB_SETTINGS_ROUTE, show_settings, methods=["GET"], response_class=HTMLResponse)
    router.add_api_route(WEB_SETTINGS_ROUTE, update_settings, methods=["POST"], response_class=HTMLResponse)
    return router


def _render_settings(
    context: SettingsRouteContext,
    request: Request,
    state: SettingsTemplateState,
) -> Response:
    validation_result = _validate_persisted_settings(context.ports)
    preview_result = PreviewPathPolicyUseCase().execute(
        PathPolicyPreviewRequest(
            path_policy=state.form_config.path_policy,
            metadata=_preview_metadata(),
            file_extension=PATH_POLICY_PREVIEW_FILE_EXTENSION,
        )
    )
    return context.templates.TemplateResponse(
        request,
        WEB_SETTINGS_TEMPLATE_NAME,
        {
            "active_nav": "settings",
            "choices": _template_choices(),
            "csrf_token": context.csrf_token,
            "current_config": state.current_config,
            "errors": state.errors,
            "fields": _template_fields(),
            "form_action_save": FORM_ACTION_SAVE,
            "form_action_validate": FORM_ACTION_VALIDATE,
            "form_config": state.form_config,
            "preview": preview_result,
            "settings_changes": state.changes,
            "status_message": state.status_message,
            "validation": validation_result,
        },
        status_code=state.status_code,
    )


def _load_current_config(ports: SettingsPorts) -> tuple[AppConfig, tuple[str, ...]]:
    try:
        return LoadSettingsUseCase(ports).execute(), ()
    except ConfigStoreValidationError as exc:
        return AppConfig(), exc.errors
    except OSError as exc:
        return AppConfig(), (f"Config I/O error: {exc}",)


def _validate_persisted_settings(ports: SettingsPorts) -> ValidateSettingsResult:
    try:
        return ValidateSettingsUseCase(ports).execute()
    except OSError as exc:
        return ValidateSettingsResult(valid=False, errors=(f"Config I/O error: {exc}",))


def _has_valid_csrf_token(context: SettingsRouteContext, form_data: dict[str, str]) -> bool:
    supplied_token = form_data.get(FORM_CSRF_FIELD, "")
    return compare_digest(supplied_token, context.csrf_token)


async def _read_urlencoded_form(request: Request) -> dict[str, str]:
    body = (await request.body()).decode(CONFIG_FILE_ENCODING)
    parsed_body = parse_qs(body, keep_blank_values=True)
    # The settings form posts one value per field; taking the last value keeps
    # handling deterministic if a browser sends duplicate keys.
    return {key: values[-1] for key, values in parsed_body.items()}


def _preview_metadata() -> TrackMetadata:
    return TrackMetadata(
        title=PATH_POLICY_PREVIEW_TITLE,
        artist=PATH_POLICY_PREVIEW_ARTIST,
        album=PATH_POLICY_PREVIEW_ALBUM,
        album_artist=PATH_POLICY_PREVIEW_ALBUM_ARTIST,
        year=PATH_POLICY_PREVIEW_YEAR,
        disc_number=PATH_POLICY_PREVIEW_DISC_NUMBER,
        track_number=PATH_POLICY_PREVIEW_TRACK_NUMBER,
    )


def _template_fields() -> dict[str, str]:
    return {
        "action": FORM_ACTION_FIELD,
        "library": FIELD_LIBRARY,
        "incoming": FIELD_INCOMING,
        "add_default_mode": FIELD_ADD_DEFAULT_MODE,
        "add_auto_apply": FIELD_ADD_AUTO_APPLY,
        "organize_default_mode": FIELD_ORGANIZE_DEFAULT_MODE,
        "organize_auto_apply": FIELD_ORGANIZE_AUTO_APPLY,
        "organize_only_misplaced": FIELD_ORGANIZE_ONLY_MISPLACED,
        "refresh_default_mode": FIELD_REFRESH_DEFAULT_MODE,
        "refresh_auto_apply": FIELD_REFRESH_AUTO_APPLY,
        "path_policy_template": FIELD_PATH_POLICY_TEMPLATE,
        "path_policy_unknown_artist": FIELD_PATH_POLICY_UNKNOWN_ARTIST,
        "path_policy_unknown_album": FIELD_PATH_POLICY_UNKNOWN_ALBUM,
        "path_policy_sanitize": FIELD_PATH_POLICY_SANITIZE,
        "path_policy_max_filename_length": FIELD_PATH_POLICY_MAX_FILENAME_LENGTH,
        "metadata_prefer_album_artist": FIELD_METADATA_PREFER_ALBUM_ARTIST,
        "metadata_require_title": FIELD_METADATA_REQUIRE_TITLE,
        "metadata_require_artist": FIELD_METADATA_REQUIRE_ARTIST,
        "metadata_require_album": FIELD_METADATA_REQUIRE_ALBUM,
        "collision_on_target_exists": FIELD_COLLISION_ON_TARGET_EXISTS,
        "collision_on_duplicate_hash": FIELD_COLLISION_ON_DUPLICATE_HASH,
        "collision_on_missing_metadata": FIELD_COLLISION_ON_MISSING_METADATA,
        "ui_theme": FIELD_UI_THEME,
        "ui_show_advanced_settings": FIELD_UI_SHOW_ADVANCED_SETTINGS,
    }


def _template_choices() -> dict[str, tuple[str, ...]]:
    return {
        "command_modes": tuple(sorted(ALLOWED_COMMAND_MODES)),
        "duplicate_hash_policies": tuple(sorted(ALLOWED_COLLISION_DUPLICATE_HASH_POLICIES)),
        "missing_metadata_policies": tuple(sorted(ALLOWED_COLLISION_MISSING_METADATA_POLICIES)),
        "target_exists_policies": tuple(sorted(ALLOWED_COLLISION_TARGET_EXISTS_POLICIES)),
        "ui_themes": tuple(sorted(ALLOWED_UI_THEMES)),
    }
