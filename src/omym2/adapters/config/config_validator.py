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
    ALLOWED_LOGGING_LEVELS,
    ALLOWED_MUSICBRAINZ_CACHE_POLICIES,
    ALLOWED_PATH_POLICY_DISC_NUMBER_CONDITIONS,
    ALLOWED_PATH_POLICY_DISC_NUMBER_STYLES,
    CONFIG_VERSION,
    DEFAULT_ADD_AUTO_APPLY,
    DEFAULT_ALBUM_YEAR_RESOLUTION,
    DEFAULT_ARTIST_ID_FALLBACK,
    DEFAULT_ARTIST_ID_MAX_LENGTH,
    DEFAULT_COLLISION_ON_DUPLICATE_HASH,
    DEFAULT_COLLISION_ON_MISSING_METADATA,
    DEFAULT_COLLISION_ON_TARGET_EXISTS,
    DEFAULT_COMMAND_MODE,
    DEFAULT_COMPANIONS_ENABLED,
    DEFAULT_FASTTEXT_MINIMUM_CONFIDENCE,
    DEFAULT_HASHING_READ_CHUNK_SIZE_BYTES,
    DEFAULT_LOGGING_LEVEL,
    DEFAULT_LOGGING_RETENTION_FILES,
    DEFAULT_LOGGING_ROTATION_MAX_BYTES,
    DEFAULT_MAX_FILENAME_LENGTH,
    DEFAULT_METADATA_PREFER_ALBUM_ARTIST,
    DEFAULT_METADATA_REQUIRE_ALBUM,
    DEFAULT_METADATA_REQUIRE_ARTIST,
    DEFAULT_METADATA_REQUIRE_TITLE,
    DEFAULT_MUSICBRAINZ_APPLICATION_NAME,
    DEFAULT_MUSICBRAINZ_CACHE_POLICY,
    DEFAULT_MUSICBRAINZ_CONTACT,
    DEFAULT_MUSICBRAINZ_ENABLED,
    DEFAULT_MUSICBRAINZ_RATE_LIMIT_SECONDS,
    DEFAULT_MUSICBRAINZ_RETRY_LIMIT,
    DEFAULT_MUSICBRAINZ_TIMEOUT_SECONDS,
    DEFAULT_ORGANIZE_AUTO_APPLY,
    DEFAULT_PATH_POLICY_DISC_NUMBER_CONDITION,
    DEFAULT_PATH_POLICY_DISC_NUMBER_STYLE,
    DEFAULT_PATH_POLICY_SANITIZE,
    DEFAULT_PATH_POLICY_TEMPLATE,
    DEFAULT_REFRESH_AUTO_APPLY,
    DEFAULT_UNKNOWN_ALBUM,
    DEFAULT_UNKNOWN_ARTIST,
    DEFAULT_UNPROCESSED_DIRECTORY,
    DEFAULT_UNPROCESSED_ENABLED,
    DEFAULT_UNPROCESSED_RESULT_PREVIEW_LIMIT,
)
from omym2.domain.models.app_config import (
    AppConfig,
    ArtistIdConfig,
    ArtistNameConfig,
    CollisionConfig,
    CommandConfig,
    CompanionsConfig,
    FastTextConfig,
    HashingConfig,
    LoggingConfig,
    MetadataConfig,
    MusicBrainzConfig,
    OrganizeConfig,
    PathPolicyConfig,
    PathsConfig,
    UnprocessedConfig,
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
APPLICATION_NAME_KEY = "application_name"
ARTIST_IDS_SECTION = "artist_ids"
ARTIST_NAMES_SECTION = "artist_names"
AUTO_APPLY_KEY = "auto_apply"
CACHE_POLICY_KEY = "cache_policy"
COLLISION_SECTION = "collision"
COMPANIONS_SECTION = "companions"
CONTACT_KEY = "contact"
DEFAULT_MODE_KEY = "default_mode"
DESTINATION_KEY = "destination"
DISC_NUMBER_CONDITION_KEY = "disc_number_condition"
DISC_NUMBER_STYLE_KEY = "disc_number_style"
DIRECTORY_KEY = "directory"
ENABLED_KEY = "enabled"
FASTTEXT_SECTION = "fasttext"
HASHING_SECTION = "hashing"
INCOMING_KEY = "incoming"
ENTRIES_KEY = "entries"
FALLBACK_ID_KEY = "fallback_id"
LIBRARY_KEY = "library"
LEVEL_KEY = "level"
LOGGING_SECTION = "logging"
MAX_LENGTH_KEY = "max_length"
MAX_FILENAME_LENGTH_KEY = "max_filename_length"
METADATA_SECTION = "metadata"
MINIMUM_CONFIDENCE_KEY = "minimum_confidence"
MODEL_PATH_KEY = "model_path"
MUSICBRAINZ_SECTION = "musicbrainz"
ON_DUPLICATE_HASH_KEY = "on_duplicate_hash"
ON_MISSING_METADATA_KEY = "on_missing_metadata"
ON_TARGET_EXISTS_KEY = "on_target_exists"
ORGANIZE_SECTION = "organize"
PATH_POLICY_SECTION = "path_policy"
PATHS_SECTION = "paths"
PREFER_ALBUM_ARTIST_KEY = "prefer_album_artist"
PREFERENCES_KEY = "preferences"
RATE_LIMIT_SECONDS_KEY = "rate_limit_seconds"
READ_CHUNK_SIZE_BYTES_KEY = "read_chunk_size_bytes"
REFRESH_SECTION = "refresh"
REQUIRE_ALBUM_KEY = "require_album"
REQUIRE_ARTIST_KEY = "require_artist"
REQUIRE_TITLE_KEY = "require_title"
RETENTION_FILES_KEY = "retention_files"
RETRY_LIMIT_KEY = "retry_limit"
ROTATION_MAX_BYTES_KEY = "rotation_max_bytes"
RESULT_PREVIEW_LIMIT_KEY = "result_preview_limit"
SANITIZE_KEY = "sanitize"
TEMPLATE_KEY = "template"
TIMEOUT_SECONDS_KEY = "timeout_seconds"
UNKNOWN_ALBUM_KEY = "unknown_album"
UNKNOWN_ARTIST_KEY = "unknown_artist"
UNPROCESSED_SECTION = "unprocessed"
VERSION_KEY = "version"

ROOT_KEYS = frozenset(
    {
        VERSION_KEY,
        PATHS_SECTION,
        ADD_SECTION,
        ORGANIZE_SECTION,
        REFRESH_SECTION,
        PATH_POLICY_SECTION,
        ARTIST_IDS_SECTION,
        ARTIST_NAMES_SECTION,
        METADATA_SECTION,
        COLLISION_SECTION,
        MUSICBRAINZ_SECTION,
        FASTTEXT_SECTION,
        HASHING_SECTION,
        LOGGING_SECTION,
        COMPANIONS_SECTION,
        UNPROCESSED_SECTION,
    }
)
PATHS_KEYS = frozenset({LIBRARY_KEY, INCOMING_KEY})
ARTIST_IDS_KEYS = frozenset({MAX_LENGTH_KEY, FALLBACK_ID_KEY, ENTRIES_KEY})
ARTIST_NAMES_KEYS = frozenset({PREFERENCES_KEY})
COMMAND_KEYS = frozenset({DEFAULT_MODE_KEY, AUTO_APPLY_KEY})
ORGANIZE_KEYS = frozenset({DEFAULT_MODE_KEY, AUTO_APPLY_KEY})
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
MUSICBRAINZ_KEYS = frozenset(
    {
        ENABLED_KEY,
        APPLICATION_NAME_KEY,
        CONTACT_KEY,
        TIMEOUT_SECONDS_KEY,
        RETRY_LIMIT_KEY,
        RATE_LIMIT_SECONDS_KEY,
        CACHE_POLICY_KEY,
    }
)
FASTTEXT_KEYS = frozenset({MODEL_PATH_KEY, MINIMUM_CONFIDENCE_KEY})
HASHING_KEYS = frozenset({READ_CHUNK_SIZE_BYTES_KEY})
LOGGING_KEYS = frozenset({DESTINATION_KEY, LEVEL_KEY, ROTATION_MAX_BYTES_KEY, RETENTION_FILES_KEY})
COMPANIONS_KEYS = frozenset({ENABLED_KEY})
UNPROCESSED_KEYS = frozenset({ENABLED_KEY, DIRECTORY_KEY, RESULT_PREVIEW_LIMIT_KEY})

BOOL_TYPE_NAME = "a boolean"
FLOAT_TYPE_NAME = "a number"
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
    try:
        artist_name_config = _artist_name_config(_section(raw_config, ARTIST_NAMES_SECTION, errors), errors)
    except ValueError as exc:
        errors.append(str(exc))
        artist_name_config = ArtistNameConfig()
    metadata_config = _metadata_config(_section(raw_config, METADATA_SECTION, errors), errors)
    collision_config = _collision_config(_section(raw_config, COLLISION_SECTION, errors), errors)
    try:
        musicbrainz_config = _musicbrainz_config(_section(raw_config, MUSICBRAINZ_SECTION, errors), errors)
    except ValueError as exc:
        errors.append(str(exc))
        musicbrainz_config = MusicBrainzConfig()
    try:
        fasttext_config = _fasttext_config(_section(raw_config, FASTTEXT_SECTION, errors), errors)
    except ValueError as exc:
        errors.append(str(exc))
        fasttext_config = FastTextConfig()
    try:
        hashing_config = _hashing_config(_section(raw_config, HASHING_SECTION, errors), errors)
    except ValueError as exc:
        errors.append(str(exc))
        hashing_config = HashingConfig()
    logging_config, companions_config, unprocessed_config = _operational_configs(raw_config, errors)

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
            artist_names=artist_name_config,
            metadata=metadata_config,
            collision=collision_config,
            musicbrainz=musicbrainz_config,
            fasttext=fasttext_config,
            hashing=hashing_config,
            logging=logging_config,
            companions=companions_config,
            unprocessed=unprocessed_config,
        )
    except ValueError as exc:
        raise ConfigStoreValidationError((str(exc),)) from exc


def _operational_configs(
    raw_config: ConfigTable,
    errors: list[str],
) -> tuple[LoggingConfig, CompanionsConfig, UnprocessedConfig]:
    try:
        logging_config = _logging_config(_section(raw_config, LOGGING_SECTION, errors), errors)
    except ValueError as exc:
        errors.append(str(exc))
        logging_config = LoggingConfig()
    try:
        companions_config = _companions_config(_section(raw_config, COMPANIONS_SECTION, errors), errors)
    except ValueError as exc:
        errors.append(str(exc))
        companions_config = CompanionsConfig()
    try:
        unprocessed_config = _unprocessed_config(_section(raw_config, UNPROCESSED_SECTION, errors), errors)
    except ValueError as exc:
        errors.append(str(exc))
        unprocessed_config = UnprocessedConfig()
    return logging_config, companions_config, unprocessed_config


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
        entries=_string_mapping(
            _section(table, ENTRIES_KEY, errors, parent_section=ARTIST_IDS_SECTION),
            _path(ARTIST_IDS_SECTION, ENTRIES_KEY),
            errors,
        ),
    )


def _artist_name_config(table: ConfigTable, errors: list[str]) -> ArtistNameConfig:
    _reject_unknown_keys(table, ARTIST_NAMES_KEYS, ARTIST_NAMES_SECTION, errors)
    return ArtistNameConfig(
        preferences=_string_mapping(
            _section(table, PREFERENCES_KEY, errors, parent_section=ARTIST_NAMES_SECTION),
            _path(ARTIST_NAMES_SECTION, PREFERENCES_KEY),
            errors,
        )
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


def _musicbrainz_config(table: ConfigTable, errors: list[str]) -> MusicBrainzConfig:
    _reject_unknown_keys(table, MUSICBRAINZ_KEYS, MUSICBRAINZ_SECTION, errors)
    return MusicBrainzConfig(
        enabled=_bool(
            table,
            ENABLED_KEY,
            MUSICBRAINZ_SECTION,
            default=DEFAULT_MUSICBRAINZ_ENABLED,
            errors=errors,
        ),
        application_name=_required_string(
            table,
            APPLICATION_NAME_KEY,
            MUSICBRAINZ_SECTION,
            DEFAULT_MUSICBRAINZ_APPLICATION_NAME,
            errors,
        ),
        contact=_required_string(
            table,
            CONTACT_KEY,
            MUSICBRAINZ_SECTION,
            DEFAULT_MUSICBRAINZ_CONTACT,
            errors,
        ),
        timeout_seconds=_float(
            table,
            TIMEOUT_SECONDS_KEY,
            MUSICBRAINZ_SECTION,
            DEFAULT_MUSICBRAINZ_TIMEOUT_SECONDS,
            errors,
        ),
        retry_limit=_int(
            table,
            RETRY_LIMIT_KEY,
            MUSICBRAINZ_SECTION,
            DEFAULT_MUSICBRAINZ_RETRY_LIMIT,
            errors,
        ),
        rate_limit_seconds=_float(
            table,
            RATE_LIMIT_SECONDS_KEY,
            MUSICBRAINZ_SECTION,
            DEFAULT_MUSICBRAINZ_RATE_LIMIT_SECONDS,
            errors,
        ),
        cache_policy=_choice(
            table,
            ChoiceRule(
                key=CACHE_POLICY_KEY,
                section=MUSICBRAINZ_SECTION,
                default=DEFAULT_MUSICBRAINZ_CACHE_POLICY,
                allowed_values=ALLOWED_MUSICBRAINZ_CACHE_POLICIES,
            ),
            errors,
        ),
    )


def _fasttext_config(table: ConfigTable, errors: list[str]) -> FastTextConfig:
    _reject_unknown_keys(table, FASTTEXT_KEYS, FASTTEXT_SECTION, errors)
    return FastTextConfig(
        model_path=_optional_string(table, MODEL_PATH_KEY, FASTTEXT_SECTION, errors),
        minimum_confidence=_float(
            table,
            MINIMUM_CONFIDENCE_KEY,
            FASTTEXT_SECTION,
            DEFAULT_FASTTEXT_MINIMUM_CONFIDENCE,
            errors,
        ),
    )


def _hashing_config(table: ConfigTable, errors: list[str]) -> HashingConfig:
    _reject_unknown_keys(table, HASHING_KEYS, HASHING_SECTION, errors)
    return HashingConfig(
        read_chunk_size_bytes=_int(
            table,
            READ_CHUNK_SIZE_BYTES_KEY,
            HASHING_SECTION,
            DEFAULT_HASHING_READ_CHUNK_SIZE_BYTES,
            errors,
        )
    )


def _logging_config(table: ConfigTable, errors: list[str]) -> LoggingConfig:
    _reject_unknown_keys(table, LOGGING_KEYS, LOGGING_SECTION, errors)
    return LoggingConfig(
        destination=_optional_string(table, DESTINATION_KEY, LOGGING_SECTION, errors),
        level=_choice(
            table,
            ChoiceRule(
                key=LEVEL_KEY,
                section=LOGGING_SECTION,
                default=DEFAULT_LOGGING_LEVEL,
                allowed_values=ALLOWED_LOGGING_LEVELS,
            ),
            errors,
        ),
        rotation_max_bytes=_int(
            table,
            ROTATION_MAX_BYTES_KEY,
            LOGGING_SECTION,
            DEFAULT_LOGGING_ROTATION_MAX_BYTES,
            errors,
        ),
        retention_files=_int(
            table,
            RETENTION_FILES_KEY,
            LOGGING_SECTION,
            DEFAULT_LOGGING_RETENTION_FILES,
            errors,
        ),
    )


def _companions_config(table: ConfigTable, errors: list[str]) -> CompanionsConfig:
    _reject_unknown_keys(table, COMPANIONS_KEYS, COMPANIONS_SECTION, errors)
    return CompanionsConfig(
        enabled=_bool(
            table,
            ENABLED_KEY,
            COMPANIONS_SECTION,
            default=DEFAULT_COMPANIONS_ENABLED,
            errors=errors,
        )
    )


def _unprocessed_config(table: ConfigTable, errors: list[str]) -> UnprocessedConfig:
    _reject_unknown_keys(table, UNPROCESSED_KEYS, UNPROCESSED_SECTION, errors)
    return UnprocessedConfig(
        enabled=_bool(
            table,
            ENABLED_KEY,
            UNPROCESSED_SECTION,
            default=DEFAULT_UNPROCESSED_ENABLED,
            errors=errors,
        ),
        directory=_required_string(
            table,
            DIRECTORY_KEY,
            UNPROCESSED_SECTION,
            DEFAULT_UNPROCESSED_DIRECTORY,
            errors,
        ),
        result_preview_limit=_int(
            table,
            RESULT_PREVIEW_LIMIT_KEY,
            UNPROCESSED_SECTION,
            DEFAULT_UNPROCESSED_RESULT_PREVIEW_LIMIT,
            errors,
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


def _string_mapping(table: ConfigTable, mapping_path: str, errors: list[str]) -> dict[str, str]:
    values: dict[str, str] = {}
    for key, value in table.items():
        path = _path(mapping_path, key)
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


def _float(table: ConfigTable, key: str, section: str, default: float, errors: list[str]) -> float:
    if key not in table:
        return default
    value = table[key]
    if isinstance(value, bool) or not isinstance(value, int | float):
        errors.append(_type_error(_path(section, key), FLOAT_TYPE_NAME))
        return default
    return float(value)


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


def _optional_string(table: ConfigTable, key: str, section: str, errors: list[str]) -> str | None:
    return _optional_path(table, key, section, errors)


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
