"""
Summary: Converts raw TOML config tables into AppConfig values.
Why: Keeps adapter-level schema validation outside domain models and usecases.
"""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass
from typing import cast

from omym2.config import (
    ALLOWED_ALBUM_YEAR_RESOLUTION_METHODS,
    ALLOWED_COLLISION_DUPLICATE_HASH_POLICIES,
    ALLOWED_COLLISION_MISSING_METADATA_POLICIES,
    ALLOWED_COLLISION_TARGET_EXISTS_POLICIES,
    ALLOWED_COMMAND_MODES,
    ALLOWED_PATH_POLICY_DISC_NUMBER_CONDITIONS,
    ALLOWED_PATH_POLICY_DISC_NUMBER_STYLES,
    ALLOWED_UI_THEMES,
    CONFIG_VERSION,
    DEFAULT_ADD_AUTO_APPLY,
    DEFAULT_ALBUM_YEAR_RESOLUTION,
    DEFAULT_ARTIST_ID_FALLBACK,
    DEFAULT_ARTIST_ID_MAX_LENGTH,
    DEFAULT_COLLISION_ON_DUPLICATE_HASH,
    DEFAULT_COLLISION_ON_MISSING_METADATA,
    DEFAULT_COLLISION_ON_TARGET_EXISTS,
    DEFAULT_COMMAND_MODE,
    DEFAULT_MAX_FILENAME_LENGTH,
    DEFAULT_METADATA_PREFER_ALBUM_ARTIST,
    DEFAULT_METADATA_REQUIRE_ALBUM,
    DEFAULT_METADATA_REQUIRE_ARTIST,
    DEFAULT_METADATA_REQUIRE_TITLE,
    DEFAULT_ORGANIZE_AUTO_APPLY,
    DEFAULT_ORGANIZE_ONLY_MISPLACED,
    DEFAULT_PATH_POLICY_DISC_NUMBER_CONDITION,
    DEFAULT_PATH_POLICY_DISC_NUMBER_STYLE,
    DEFAULT_PATH_POLICY_SANITIZE,
    DEFAULT_PATH_POLICY_TEMPLATE,
    DEFAULT_REFRESH_AUTO_APPLY,
    DEFAULT_UI_SHOW_ADVANCED_SETTINGS,
    DEFAULT_UI_THEME,
    DEFAULT_UNKNOWN_ALBUM,
    DEFAULT_UNKNOWN_ARTIST,
)
from omym2.domain.models.app_config import (
    AppConfig,
    ArtistIdConfig,
    CollisionConfig,
    CommandConfig,
    MetadataConfig,
    OrganizeConfig,
    PathPolicyConfig,
    PathsConfig,
    UiConfig,
)
from omym2.features.common_ports import ConfigStoreValidationError

type ConfigTable = Mapping[str, object]


@dataclass(frozen=True, slots=True)
class ChoiceRule:
    """Schema rule for a string value limited to known choices."""

    key: str
    section: str
    default: str
    allowed_values: frozenset[str]


ADD_SECTION = "add"
ALBUM_YEAR_RESOLUTION_KEY = "album_year_resolution"
ARTIST_IDS_SECTION = "artist_ids"
AUTO_APPLY_KEY = "auto_apply"
COLLISION_SECTION = "collision"
DEFAULT_MODE_KEY = "default_mode"
DISC_NUMBER_CONDITION_KEY = "disc_number_condition"
DISC_NUMBER_STYLE_KEY = "disc_number_style"
INCOMING_KEY = "incoming"
ENTRIES_KEY = "entries"
FALLBACK_ID_KEY = "fallback_id"
LIBRARY_KEY = "library"
MAX_LENGTH_KEY = "max_length"
MAX_FILENAME_LENGTH_KEY = "max_filename_length"
METADATA_SECTION = "metadata"
ON_DUPLICATE_HASH_KEY = "on_duplicate_hash"
ON_MISSING_METADATA_KEY = "on_missing_metadata"
ON_TARGET_EXISTS_KEY = "on_target_exists"
ORGANIZE_SECTION = "organize"
PATH_POLICY_SECTION = "path_policy"
PATHS_SECTION = "paths"
PREFER_ALBUM_ARTIST_KEY = "prefer_album_artist"
REFRESH_SECTION = "refresh"
REQUIRE_ALBUM_KEY = "require_album"
REQUIRE_ARTIST_KEY = "require_artist"
REQUIRE_TITLE_KEY = "require_title"
SANITIZE_KEY = "sanitize"
SHOW_ADVANCED_SETTINGS_KEY = "show_advanced_settings"
TEMPLATE_KEY = "template"
THEME_KEY = "theme"
UI_SECTION = "ui"
UNKNOWN_ALBUM_KEY = "unknown_album"
UNKNOWN_ARTIST_KEY = "unknown_artist"
VERSION_KEY = "version"
ONLY_MISPLACED_KEY = "only_misplaced"

ROOT_KEYS = frozenset(
    {
        VERSION_KEY,
        PATHS_SECTION,
        ADD_SECTION,
        ORGANIZE_SECTION,
        REFRESH_SECTION,
        PATH_POLICY_SECTION,
        ARTIST_IDS_SECTION,
        METADATA_SECTION,
        COLLISION_SECTION,
        UI_SECTION,
    }
)
PATHS_KEYS = frozenset({LIBRARY_KEY, INCOMING_KEY})
ARTIST_IDS_KEYS = frozenset({MAX_LENGTH_KEY, FALLBACK_ID_KEY, ENTRIES_KEY})
COMMAND_KEYS = frozenset({DEFAULT_MODE_KEY, AUTO_APPLY_KEY})
ORGANIZE_KEYS = frozenset({DEFAULT_MODE_KEY, AUTO_APPLY_KEY, ONLY_MISPLACED_KEY})
PATH_POLICY_KEYS = frozenset(
    {
        TEMPLATE_KEY,
        UNKNOWN_ARTIST_KEY,
        UNKNOWN_ALBUM_KEY,
        SANITIZE_KEY,
        MAX_FILENAME_LENGTH_KEY,
        DISC_NUMBER_STYLE_KEY,
        DISC_NUMBER_CONDITION_KEY,
    }
)
METADATA_KEYS = frozenset(
    {PREFER_ALBUM_ARTIST_KEY, REQUIRE_TITLE_KEY, REQUIRE_ARTIST_KEY, REQUIRE_ALBUM_KEY, ALBUM_YEAR_RESOLUTION_KEY}
)
COLLISION_KEYS = frozenset({ON_TARGET_EXISTS_KEY, ON_DUPLICATE_HASH_KEY, ON_MISSING_METADATA_KEY})
UI_KEYS = frozenset({THEME_KEY, SHOW_ADVANCED_SETTINGS_KEY})

BOOL_TYPE_NAME = "a boolean"
INT_TYPE_NAME = "an integer"
STRING_TYPE_NAME = "a string"
TABLE_TYPE_NAME = "a table"


def validate_config_data(raw_config: ConfigTable) -> AppConfig:
    """Return AppConfig or raise validation errors for a raw TOML table."""
    errors: list[str] = []
    _reject_unknown_keys(raw_config, ROOT_KEYS, "", errors)

    version = _required_int(raw_config, VERSION_KEY, CONFIG_VERSION, errors)
    paths_config = _paths_config(_section(raw_config, PATHS_SECTION, errors), errors)
    add_config = _command_config(
        _section(raw_config, ADD_SECTION, errors),
        ADD_SECTION,
        default_auto_apply=DEFAULT_ADD_AUTO_APPLY,
        errors=errors,
    )
    organize_config = _organize_config(_section(raw_config, ORGANIZE_SECTION, errors), errors)
    refresh_config = _command_config(
        _section(raw_config, REFRESH_SECTION, errors),
        REFRESH_SECTION,
        default_auto_apply=DEFAULT_REFRESH_AUTO_APPLY,
        errors=errors,
    )
    try:
        path_policy_config = _path_policy_config(_section(raw_config, PATH_POLICY_SECTION, errors), errors)
    except ValueError as exc:
        # PathPolicyConfig owns domain-level path template invariants; the
        # adapter reports those through the ConfigStore validation contract.
        errors.append(str(exc))
        path_policy_config = PathPolicyConfig()
    try:
        artist_id_config = _artist_id_config(_section(raw_config, ARTIST_IDS_SECTION, errors), errors)
    except ValueError as exc:
        errors.append(str(exc))
        artist_id_config = ArtistIdConfig()
    metadata_config = _metadata_config(_section(raw_config, METADATA_SECTION, errors), errors)
    collision_config = _collision_config(_section(raw_config, COLLISION_SECTION, errors), errors)
    ui_config = _ui_config(_section(raw_config, UI_SECTION, errors), errors)

    if errors:
        raise ConfigStoreValidationError(errors)

    try:
        return AppConfig(
            version=version,
            paths=paths_config,
            add=add_config,
            organize=organize_config,
            refresh=refresh_config,
            path_policy=path_policy_config,
            artist_ids=artist_id_config,
            metadata=metadata_config,
            collision=collision_config,
            ui=ui_config,
        )
    except ValueError as exc:
        raise ConfigStoreValidationError((str(exc),)) from exc


def _paths_config(table: ConfigTable, errors: list[str]) -> PathsConfig:
    _reject_unknown_keys(table, PATHS_KEYS, PATHS_SECTION, errors)
    return PathsConfig(
        library=_optional_path(table, LIBRARY_KEY, PATHS_SECTION, errors),
        incoming=_optional_path(table, INCOMING_KEY, PATHS_SECTION, errors),
    )


def _command_config(
    table: ConfigTable,
    section: str,
    *,
    default_auto_apply: bool,
    errors: list[str],
) -> CommandConfig:
    _reject_unknown_keys(table, COMMAND_KEYS, section, errors)
    return CommandConfig(
        default_mode=_choice(
            table,
            ChoiceRule(
                key=DEFAULT_MODE_KEY,
                section=section,
                default=DEFAULT_COMMAND_MODE,
                allowed_values=ALLOWED_COMMAND_MODES,
            ),
            errors,
        ),
        auto_apply=_bool(table, AUTO_APPLY_KEY, section, default=default_auto_apply, errors=errors),
    )


def _organize_config(table: ConfigTable, errors: list[str]) -> OrganizeConfig:
    _reject_unknown_keys(table, ORGANIZE_KEYS, ORGANIZE_SECTION, errors)
    return OrganizeConfig(
        default_mode=_choice(
            table,
            ChoiceRule(
                key=DEFAULT_MODE_KEY,
                section=ORGANIZE_SECTION,
                default=DEFAULT_COMMAND_MODE,
                allowed_values=ALLOWED_COMMAND_MODES,
            ),
            errors,
        ),
        auto_apply=_bool(table, AUTO_APPLY_KEY, ORGANIZE_SECTION, default=DEFAULT_ORGANIZE_AUTO_APPLY, errors=errors),
        only_misplaced=_bool(
            table,
            ONLY_MISPLACED_KEY,
            ORGANIZE_SECTION,
            default=DEFAULT_ORGANIZE_ONLY_MISPLACED,
            errors=errors,
        ),
    )


def _path_policy_config(table: ConfigTable, errors: list[str]) -> PathPolicyConfig:
    _reject_unknown_keys(table, PATH_POLICY_KEYS, PATH_POLICY_SECTION, errors)
    return PathPolicyConfig(
        template=_required_string(table, TEMPLATE_KEY, PATH_POLICY_SECTION, DEFAULT_PATH_POLICY_TEMPLATE, errors),
        unknown_artist=_required_string(
            table,
            UNKNOWN_ARTIST_KEY,
            PATH_POLICY_SECTION,
            DEFAULT_UNKNOWN_ARTIST,
            errors,
        ),
        unknown_album=_required_string(
            table,
            UNKNOWN_ALBUM_KEY,
            PATH_POLICY_SECTION,
            DEFAULT_UNKNOWN_ALBUM,
            errors,
        ),
        sanitize=_bool(table, SANITIZE_KEY, PATH_POLICY_SECTION, default=DEFAULT_PATH_POLICY_SANITIZE, errors=errors),
        max_filename_length=_int(
            table,
            MAX_FILENAME_LENGTH_KEY,
            PATH_POLICY_SECTION,
            DEFAULT_MAX_FILENAME_LENGTH,
            errors,
        ),
        disc_number_style=_choice(
            table,
            ChoiceRule(
                key=DISC_NUMBER_STYLE_KEY,
                section=PATH_POLICY_SECTION,
                default=DEFAULT_PATH_POLICY_DISC_NUMBER_STYLE,
                allowed_values=ALLOWED_PATH_POLICY_DISC_NUMBER_STYLES,
            ),
            errors,
        ),
        disc_number_condition=_choice(
            table,
            ChoiceRule(
                key=DISC_NUMBER_CONDITION_KEY,
                section=PATH_POLICY_SECTION,
                default=DEFAULT_PATH_POLICY_DISC_NUMBER_CONDITION,
                allowed_values=ALLOWED_PATH_POLICY_DISC_NUMBER_CONDITIONS,
            ),
            errors,
        ),
    )


def _artist_id_config(table: ConfigTable, errors: list[str]) -> ArtistIdConfig:
    _reject_unknown_keys(table, ARTIST_IDS_KEYS, ARTIST_IDS_SECTION, errors)
    return ArtistIdConfig(
        max_length=_int(table, MAX_LENGTH_KEY, ARTIST_IDS_SECTION, DEFAULT_ARTIST_ID_MAX_LENGTH, errors),
        fallback_id=_required_string(
            table,
            FALLBACK_ID_KEY,
            ARTIST_IDS_SECTION,
            DEFAULT_ARTIST_ID_FALLBACK,
            errors,
        ),
        entries=_string_mapping(_section(table, ENTRIES_KEY, errors, parent_section=ARTIST_IDS_SECTION), errors),
    )


def _metadata_config(table: ConfigTable, errors: list[str]) -> MetadataConfig:
    _reject_unknown_keys(table, METADATA_KEYS, METADATA_SECTION, errors)
    return MetadataConfig(
        prefer_album_artist=_bool(
            table,
            PREFER_ALBUM_ARTIST_KEY,
            METADATA_SECTION,
            default=DEFAULT_METADATA_PREFER_ALBUM_ARTIST,
            errors=errors,
        ),
        require_title=_bool(
            table, REQUIRE_TITLE_KEY, METADATA_SECTION, default=DEFAULT_METADATA_REQUIRE_TITLE, errors=errors
        ),
        require_artist=_bool(
            table,
            REQUIRE_ARTIST_KEY,
            METADATA_SECTION,
            default=DEFAULT_METADATA_REQUIRE_ARTIST,
            errors=errors,
        ),
        require_album=_bool(
            table, REQUIRE_ALBUM_KEY, METADATA_SECTION, default=DEFAULT_METADATA_REQUIRE_ALBUM, errors=errors
        ),
        album_year_resolution=_choice(
            table,
            ChoiceRule(
                key=ALBUM_YEAR_RESOLUTION_KEY,
                section=METADATA_SECTION,
                default=DEFAULT_ALBUM_YEAR_RESOLUTION,
                allowed_values=ALLOWED_ALBUM_YEAR_RESOLUTION_METHODS,
            ),
            errors,
        ),
    )


def _collision_config(table: ConfigTable, errors: list[str]) -> CollisionConfig:
    _reject_unknown_keys(table, COLLISION_KEYS, COLLISION_SECTION, errors)
    return CollisionConfig(
        on_target_exists=_choice(
            table,
            ChoiceRule(
                key=ON_TARGET_EXISTS_KEY,
                section=COLLISION_SECTION,
                default=DEFAULT_COLLISION_ON_TARGET_EXISTS,
                allowed_values=ALLOWED_COLLISION_TARGET_EXISTS_POLICIES,
            ),
            errors,
        ),
        on_duplicate_hash=_choice(
            table,
            ChoiceRule(
                key=ON_DUPLICATE_HASH_KEY,
                section=COLLISION_SECTION,
                default=DEFAULT_COLLISION_ON_DUPLICATE_HASH,
                allowed_values=ALLOWED_COLLISION_DUPLICATE_HASH_POLICIES,
            ),
            errors,
        ),
        on_missing_metadata=_choice(
            table,
            ChoiceRule(
                key=ON_MISSING_METADATA_KEY,
                section=COLLISION_SECTION,
                default=DEFAULT_COLLISION_ON_MISSING_METADATA,
                allowed_values=ALLOWED_COLLISION_MISSING_METADATA_POLICIES,
            ),
            errors,
        ),
    )


def _ui_config(table: ConfigTable, errors: list[str]) -> UiConfig:
    _reject_unknown_keys(table, UI_KEYS, UI_SECTION, errors)
    return UiConfig(
        theme=_choice(
            table,
            ChoiceRule(key=THEME_KEY, section=UI_SECTION, default=DEFAULT_UI_THEME, allowed_values=ALLOWED_UI_THEMES),
            errors,
        ),
        show_advanced_settings=_bool(
            table,
            SHOW_ADVANCED_SETTINGS_KEY,
            UI_SECTION,
            default=DEFAULT_UI_SHOW_ADVANCED_SETTINGS,
            errors=errors,
        ),
    )


def _section(
    raw_config: ConfigTable,
    section: str,
    errors: list[str],
    *,
    parent_section: str = "",
) -> ConfigTable:
    if section not in raw_config:
        return {}
    value = raw_config[section]
    if isinstance(value, Mapping):
        return cast("ConfigTable", value)
    errors.append(_type_error(_path(parent_section, section), TABLE_TYPE_NAME))
    return {}


def _string_mapping(table: ConfigTable, errors: list[str]) -> dict[str, str]:
    values: dict[str, str] = {}
    for key, value in table.items():
        path = _path(_path(ARTIST_IDS_SECTION, ENTRIES_KEY), key)
        if not isinstance(value, str):
            errors.append(_type_error(path, STRING_TYPE_NAME))
            continue
        if key.strip() == "" or value.strip() == "":
            errors.append(f"Config key {path} must not be empty.")
            continue
        values[key] = value
    return values


def _required_int(table: ConfigTable, key: str, default: int, errors: list[str]) -> int:
    if key not in table:
        errors.append(f"Missing config key: {key}.")
        return default
    return _int(table, key, "", default, errors)


def _int(table: ConfigTable, key: str, section: str, default: int, errors: list[str]) -> int:
    if key not in table:
        return default
    value = table[key]
    if isinstance(value, bool) or not isinstance(value, int):
        errors.append(_type_error(_path(section, key), INT_TYPE_NAME))
        return default
    return value


def _bool(table: ConfigTable, key: str, section: str, *, default: bool, errors: list[str]) -> bool:
    if key not in table:
        return default
    value = table[key]
    if not isinstance(value, bool):
        errors.append(_type_error(_path(section, key), BOOL_TYPE_NAME))
        return default
    return value


def _required_string(table: ConfigTable, key: str, section: str, default: str, errors: list[str]) -> str:
    if key not in table:
        return default
    value = table[key]
    if not isinstance(value, str):
        errors.append(_type_error(_path(section, key), STRING_TYPE_NAME))
        return default
    if value.strip() == "":
        errors.append(f"Config key {_path(section, key)} must not be empty.")
        return default
    return value


def _optional_path(table: ConfigTable, key: str, section: str, errors: list[str]) -> str | None:
    if key not in table:
        return None
    value = table[key]
    if not isinstance(value, str):
        errors.append(_type_error(_path(section, key), STRING_TYPE_NAME))
        return None
    if value.strip() == "":
        errors.append(f"Config key {_path(section, key)} must not be empty.")
        return None
    return value


def _choice(
    table: ConfigTable,
    rule: ChoiceRule,
    errors: list[str],
) -> str:
    value = _required_string(table, rule.key, rule.section, rule.default, errors)
    if value not in rule.allowed_values:
        allowed = ", ".join(sorted(rule.allowed_values))
        errors.append(f"Config key {_path(rule.section, rule.key)} must be one of: {allowed}.")
        return rule.default
    return value


def _reject_unknown_keys(
    table: ConfigTable,
    allowed_keys: frozenset[str],
    section: str,
    errors: list[str],
) -> None:
    errors.extend(f"Unknown config key: {_path(section, key)}." for key in sorted(set(table) - allowed_keys))


def _type_error(path: str, expected_type: str) -> str:
    return f"Config key {path} must be {expected_type}."


def _path(section: str, key: str) -> str:
    if section == "":
        return key
    return f"{section}.{key}"
