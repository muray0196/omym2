"""
Summary: Converts settings form fields into AppConfig values.
Why: Keeps HTTP field parsing out of settings route orchestration.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING

from omym2.adapters.config.config_validator import (
    ADD_SECTION,
    AUTO_APPLY_KEY,
    COLLISION_SECTION,
    DEFAULT_MODE_KEY,
    INCOMING_KEY,
    LIBRARY_KEY,
    MAX_FILENAME_LENGTH_KEY,
    METADATA_SECTION,
    ON_DUPLICATE_HASH_KEY,
    ON_MISSING_METADATA_KEY,
    ON_TARGET_EXISTS_KEY,
    ONLY_MISPLACED_KEY,
    ORGANIZE_SECTION,
    PATH_POLICY_SECTION,
    PATHS_SECTION,
    PREFER_ALBUM_ARTIST_KEY,
    REFRESH_SECTION,
    REQUIRE_ALBUM_KEY,
    REQUIRE_ARTIST_KEY,
    REQUIRE_TITLE_KEY,
    SANITIZE_KEY,
    SHOW_ADVANCED_SETTINGS_KEY,
    TEMPLATE_KEY,
    THEME_KEY,
    UI_SECTION,
    UNKNOWN_ALBUM_KEY,
    UNKNOWN_ARTIST_KEY,
    VERSION_KEY,
    validate_config_data,
)
from omym2.config import CONFIG_VERSION
from omym2.features.common_ports import ConfigStoreValidationError

if TYPE_CHECKING:
    from collections.abc import Mapping

    from omym2.domain.models.app_config import AppConfig

FORM_ACTION_FIELD = "form_action"
FORM_ACTION_SAVE = "save"
FORM_ACTION_VALIDATE = "validate"
FORM_CSRF_FIELD = "csrf_token"
HTML_CHECKED_VALUE = "on"

FIELD_LIBRARY = f"{PATHS_SECTION}.{LIBRARY_KEY}"
FIELD_INCOMING = f"{PATHS_SECTION}.{INCOMING_KEY}"
FIELD_ADD_DEFAULT_MODE = f"{ADD_SECTION}.{DEFAULT_MODE_KEY}"
FIELD_ADD_AUTO_APPLY = f"{ADD_SECTION}.{AUTO_APPLY_KEY}"
FIELD_ORGANIZE_DEFAULT_MODE = f"{ORGANIZE_SECTION}.{DEFAULT_MODE_KEY}"
FIELD_ORGANIZE_AUTO_APPLY = f"{ORGANIZE_SECTION}.{AUTO_APPLY_KEY}"
FIELD_ORGANIZE_ONLY_MISPLACED = f"{ORGANIZE_SECTION}.{ONLY_MISPLACED_KEY}"
FIELD_REFRESH_DEFAULT_MODE = f"{REFRESH_SECTION}.{DEFAULT_MODE_KEY}"
FIELD_REFRESH_AUTO_APPLY = f"{REFRESH_SECTION}.{AUTO_APPLY_KEY}"
FIELD_PATH_POLICY_TEMPLATE = f"{PATH_POLICY_SECTION}.{TEMPLATE_KEY}"
FIELD_PATH_POLICY_UNKNOWN_ARTIST = f"{PATH_POLICY_SECTION}.{UNKNOWN_ARTIST_KEY}"
FIELD_PATH_POLICY_UNKNOWN_ALBUM = f"{PATH_POLICY_SECTION}.{UNKNOWN_ALBUM_KEY}"
FIELD_PATH_POLICY_SANITIZE = f"{PATH_POLICY_SECTION}.{SANITIZE_KEY}"
FIELD_PATH_POLICY_MAX_FILENAME_LENGTH = f"{PATH_POLICY_SECTION}.{MAX_FILENAME_LENGTH_KEY}"
FIELD_METADATA_PREFER_ALBUM_ARTIST = f"{METADATA_SECTION}.{PREFER_ALBUM_ARTIST_KEY}"
FIELD_METADATA_REQUIRE_TITLE = f"{METADATA_SECTION}.{REQUIRE_TITLE_KEY}"
FIELD_METADATA_REQUIRE_ARTIST = f"{METADATA_SECTION}.{REQUIRE_ARTIST_KEY}"
FIELD_METADATA_REQUIRE_ALBUM = f"{METADATA_SECTION}.{REQUIRE_ALBUM_KEY}"
FIELD_COLLISION_ON_TARGET_EXISTS = f"{COLLISION_SECTION}.{ON_TARGET_EXISTS_KEY}"
FIELD_COLLISION_ON_DUPLICATE_HASH = f"{COLLISION_SECTION}.{ON_DUPLICATE_HASH_KEY}"
FIELD_COLLISION_ON_MISSING_METADATA = f"{COLLISION_SECTION}.{ON_MISSING_METADATA_KEY}"
FIELD_UI_THEME = f"{UI_SECTION}.{THEME_KEY}"
FIELD_UI_SHOW_ADVANCED_SETTINGS = f"{UI_SECTION}.{SHOW_ADVANCED_SETTINGS_KEY}"

INTEGER_FIELD_ERROR = "Field path_policy.max_filename_length must be an integer."


@dataclass(frozen=True, slots=True)
class SettingsFormResult:
    """Parsed settings form result."""

    config: AppConfig | None
    errors: tuple[str, ...]


@dataclass(frozen=True, slots=True)
class SettingsChange:
    """One displayable settings difference."""

    label: str
    before: str
    after: str


def parse_settings_form(form_data: Mapping[str, str]) -> SettingsFormResult:
    """Convert URL form fields into a validated AppConfig."""
    errors: list[str] = []
    raw_config = _raw_config_from_form(form_data, errors)
    if errors:
        return SettingsFormResult(config=None, errors=tuple(errors))

    try:
        config = validate_config_data(raw_config)
    except ConfigStoreValidationError as exc:
        return SettingsFormResult(config=None, errors=exc.errors)
    return SettingsFormResult(config=config, errors=())


def describe_config_changes(before: AppConfig, after: AppConfig) -> tuple[SettingsChange, ...]:
    """Return field-level changes between two AppConfig values."""
    field_values = (
        ("Library path", before.paths.library, after.paths.library),
        ("Incoming path", before.paths.incoming, after.paths.incoming),
        ("Add mode", before.add.default_mode, after.add.default_mode),
        ("Add auto apply", before.add.auto_apply, after.add.auto_apply),
        ("Organize mode", before.organize.default_mode, after.organize.default_mode),
        ("Organize auto apply", before.organize.auto_apply, after.organize.auto_apply),
        ("Organize only misplaced", before.organize.only_misplaced, after.organize.only_misplaced),
        ("Refresh mode", before.refresh.default_mode, after.refresh.default_mode),
        ("Refresh auto apply", before.refresh.auto_apply, after.refresh.auto_apply),
        ("Path template", before.path_policy.template, after.path_policy.template),
        ("Unknown artist", before.path_policy.unknown_artist, after.path_policy.unknown_artist),
        ("Unknown album", before.path_policy.unknown_album, after.path_policy.unknown_album),
        ("Sanitize path text", before.path_policy.sanitize, after.path_policy.sanitize),
        ("Max filename length", before.path_policy.max_filename_length, after.path_policy.max_filename_length),
        ("Prefer album artist", before.metadata.prefer_album_artist, after.metadata.prefer_album_artist),
        ("Require title", before.metadata.require_title, after.metadata.require_title),
        ("Require artist", before.metadata.require_artist, after.metadata.require_artist),
        ("Require album", before.metadata.require_album, after.metadata.require_album),
        ("Target exists policy", before.collision.on_target_exists, after.collision.on_target_exists),
        ("Duplicate hash policy", before.collision.on_duplicate_hash, after.collision.on_duplicate_hash),
        ("Missing metadata policy", before.collision.on_missing_metadata, after.collision.on_missing_metadata),
        ("UI theme", before.ui.theme, after.ui.theme),
        ("Show advanced settings", before.ui.show_advanced_settings, after.ui.show_advanced_settings),
    )
    return tuple(
        SettingsChange(label=label, before=_display_value(before_value), after=_display_value(after_value))
        for label, before_value, after_value in field_values
        if before_value != after_value
    )


def _raw_config_from_form(form_data: Mapping[str, str], errors: list[str]) -> dict[str, object]:
    path_values: dict[str, object] = {}
    _set_optional_text(path_values, LIBRARY_KEY, form_data, FIELD_LIBRARY)
    _set_optional_text(path_values, INCOMING_KEY, form_data, FIELD_INCOMING)

    return {
        VERSION_KEY: CONFIG_VERSION,
        PATHS_SECTION: path_values,
        ADD_SECTION: {
            DEFAULT_MODE_KEY: _text(form_data, FIELD_ADD_DEFAULT_MODE),
            AUTO_APPLY_KEY: _checkbox(form_data, FIELD_ADD_AUTO_APPLY),
        },
        ORGANIZE_SECTION: {
            DEFAULT_MODE_KEY: _text(form_data, FIELD_ORGANIZE_DEFAULT_MODE),
            AUTO_APPLY_KEY: _checkbox(form_data, FIELD_ORGANIZE_AUTO_APPLY),
            ONLY_MISPLACED_KEY: _checkbox(form_data, FIELD_ORGANIZE_ONLY_MISPLACED),
        },
        REFRESH_SECTION: {
            DEFAULT_MODE_KEY: _text(form_data, FIELD_REFRESH_DEFAULT_MODE),
            AUTO_APPLY_KEY: _checkbox(form_data, FIELD_REFRESH_AUTO_APPLY),
        },
        PATH_POLICY_SECTION: {
            TEMPLATE_KEY: _text(form_data, FIELD_PATH_POLICY_TEMPLATE),
            UNKNOWN_ARTIST_KEY: _text(form_data, FIELD_PATH_POLICY_UNKNOWN_ARTIST),
            UNKNOWN_ALBUM_KEY: _text(form_data, FIELD_PATH_POLICY_UNKNOWN_ALBUM),
            SANITIZE_KEY: _checkbox(form_data, FIELD_PATH_POLICY_SANITIZE),
            MAX_FILENAME_LENGTH_KEY: _int(form_data, FIELD_PATH_POLICY_MAX_FILENAME_LENGTH, errors),
        },
        METADATA_SECTION: {
            PREFER_ALBUM_ARTIST_KEY: _checkbox(form_data, FIELD_METADATA_PREFER_ALBUM_ARTIST),
            REQUIRE_TITLE_KEY: _checkbox(form_data, FIELD_METADATA_REQUIRE_TITLE),
            REQUIRE_ARTIST_KEY: _checkbox(form_data, FIELD_METADATA_REQUIRE_ARTIST),
            REQUIRE_ALBUM_KEY: _checkbox(form_data, FIELD_METADATA_REQUIRE_ALBUM),
        },
        COLLISION_SECTION: {
            ON_TARGET_EXISTS_KEY: _text(form_data, FIELD_COLLISION_ON_TARGET_EXISTS),
            ON_DUPLICATE_HASH_KEY: _text(form_data, FIELD_COLLISION_ON_DUPLICATE_HASH),
            ON_MISSING_METADATA_KEY: _text(form_data, FIELD_COLLISION_ON_MISSING_METADATA),
        },
        UI_SECTION: {
            THEME_KEY: _text(form_data, FIELD_UI_THEME),
            SHOW_ADVANCED_SETTINGS_KEY: _checkbox(form_data, FIELD_UI_SHOW_ADVANCED_SETTINGS),
        },
    }


def _set_optional_text(target: dict[str, object], key: str, form_data: Mapping[str, str], field_name: str) -> None:
    value = _text(form_data, field_name)
    if value != "":
        target[key] = value


def _text(form_data: Mapping[str, str], field_name: str) -> str:
    return form_data.get(field_name, "").strip()


def _checkbox(form_data: Mapping[str, str], field_name: str) -> bool:
    return form_data.get(field_name) == HTML_CHECKED_VALUE


def _int(form_data: Mapping[str, str], field_name: str, errors: list[str]) -> int:
    try:
        return int(_text(form_data, field_name))
    except ValueError:
        errors.append(INTEGER_FIELD_ERROR)
        return 0


def _display_value(value: object) -> str:
    if value is None:
        return "Not set"
    if isinstance(value, bool):
        return "On" if value else "Off"
    return str(value)
