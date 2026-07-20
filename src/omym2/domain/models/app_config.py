"""
Summary: Defines in-memory application configuration models.
Why: Gives usecases typed settings without depending on TOML adapters.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from math import isfinite
from pathlib import PurePosixPath, PureWindowsPath
from string import Formatter

from omym2.config import (
    ALLOWED_ALBUM_YEAR_RESOLUTION_METHODS,
    ALLOWED_LOGGING_LEVELS,
    ALLOWED_PATH_POLICY_DISC_NUMBER_CONDITIONS,
    ALLOWED_PATH_POLICY_DISC_NUMBER_STYLES,
    ARTIST_ID_VALUE_PATTERN,
    CONFIG_VERSION,
    CURRENT_DIRECTORY_REFERENCE,
    DEFAULT_ADD_AUTO_APPLY,
    DEFAULT_ALBUM_YEAR_RESOLUTION,
    DEFAULT_ARTIST_ID_FALLBACK,
    DEFAULT_ARTIST_ID_MAX_LENGTH,
    DEFAULT_COLLISION_ON_DUPLICATE_HASH,
    DEFAULT_COLLISION_ON_MISSING_METADATA,
    DEFAULT_COLLISION_ON_TARGET_EXISTS,
    DEFAULT_COMPANIONS_ENABLED,
    DEFAULT_HASHING_READ_CHUNK_SIZE_BYTES,
    DEFAULT_LOGGING_DESTINATION,
    DEFAULT_LOGGING_LEVEL,
    DEFAULT_LOGGING_RETENTION_FILES,
    DEFAULT_LOGGING_ROTATION_MAX_BYTES,
    DEFAULT_MAX_FILENAME_LENGTH,
    DEFAULT_METADATA_PREFER_ALBUM_ARTIST,
    DEFAULT_METADATA_REQUIRE_ALBUM,
    DEFAULT_METADATA_REQUIRE_ARTIST,
    DEFAULT_METADATA_REQUIRE_TITLE,
    DEFAULT_MUSICBRAINZ_APPLICATION_NAME,
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
    LOGICAL_PATH_SEPARATOR,
    PARENT_DIRECTORY_REFERENCE,
    PATH_EXTENSION_PREFIX,
    PATH_POLICY_ALLOWED_PLACEHOLDERS,
    PATH_POLICY_RESERVED_WINDOWS_DEVICE_NAMES,
    PORTABLE_PATH_CONTROL_CHARACTER_LIMIT,
    PORTABLE_PATH_FORBIDDEN_CHARACTERS,
    UNPROCESSED_RESULT_PREVIEW_LIMIT_MAX,
    UNPROCESSED_RESULT_PREVIEW_LIMIT_MIN,
)

INVALID_CONFIG_VERSION_MESSAGE = (
    "Unsupported pre-release config version. Reset .config/config.toml and recreate Settings."
)
INVALID_ARTIST_ID_FALLBACK_MESSAGE = (
    "ArtistIdConfig fallback_id must be non-empty ASCII letters, digits, or underscores "
    "with optional single internal hyphens."
)
INVALID_ARTIST_ID_MAX_LENGTH_MESSAGE = "ArtistIdConfig max_length must be positive."
INVALID_MAX_FILENAME_LENGTH_MESSAGE = "PathPolicy max_filename_length must be positive."
INVALID_PATH_POLICY_DISC_NUMBER_CONDITION_MESSAGE = "PathPolicy disc_number_condition is not supported."
INVALID_PATH_POLICY_DISC_NUMBER_STYLE_MESSAGE = "PathPolicy disc_number_style is not supported."
INVALID_PATH_POLICY_TEMPLATE_EXTENSION_MESSAGE = "PathPolicy template must not include a file extension."
INVALID_PATH_POLICY_TEMPLATE_PLACEHOLDER_MESSAGE = "PathPolicy template contains unsupported placeholder."
INVALID_PATH_POLICY_TEMPLATE_SYNTAX_MESSAGE = "PathPolicy template contains unsupported placeholder syntax."
INVALID_PATH_POLICY_UNKNOWN_ALBUM_MESSAGE = "PathPolicy unknown_album must not be empty."
INVALID_PATH_POLICY_UNKNOWN_ARTIST_MESSAGE = "PathPolicy unknown_artist must not be empty."
INVALID_METADATA_ALBUM_YEAR_RESOLUTION_MESSAGE = "Metadata album_year_resolution must be a supported method."
INVALID_MUSICBRAINZ_APPLICATION_NAME_MESSAGE = "MusicBrainzConfig application_name must not be blank."
INVALID_MUSICBRAINZ_CONTACT_MESSAGE = "MusicBrainzConfig contact must not be blank."
INVALID_MUSICBRAINZ_TIMEOUT_MESSAGE = "MusicBrainzConfig timeout_seconds must be finite and positive."
INVALID_MUSICBRAINZ_RETRY_LIMIT_MESSAGE = "MusicBrainzConfig retry_limit must not be negative."
INVALID_MUSICBRAINZ_RATE_LIMIT_MESSAGE = "MusicBrainzConfig rate_limit_seconds must be finite and at least 1.0."
INVALID_HASHING_READ_CHUNK_SIZE_MESSAGE = "HashingConfig read_chunk_size_bytes must be positive."
INVALID_LOGGING_DESTINATION_MESSAGE = (
    "LoggingConfig destination must be a normalized application-root-relative logical path."
)
INVALID_LOGGING_LEVEL_MESSAGE = "LoggingConfig level is not supported."
INVALID_LOGGING_ROTATION_MAX_BYTES_MESSAGE = "LoggingConfig rotation_max_bytes must be positive."
INVALID_LOGGING_RETENTION_FILES_MESSAGE = "LoggingConfig retention_files must be positive."
INVALID_UNPROCESSED_DIRECTORY_MESSAGE = (
    "UnprocessedConfig directory must be exactly one portable relative path component."
)
INVALID_UNPROCESSED_RESULT_PREVIEW_LIMIT_MESSAGE = (
    "UnprocessedConfig result_preview_limit must be an integer between "
    f"{UNPROCESSED_RESULT_PREVIEW_LIMIT_MIN} and {UNPROCESSED_RESULT_PREVIEW_LIMIT_MAX}."
)

_ARTIST_ID_VALUE_PATTERN = re.compile(ARTIST_ID_VALUE_PATTERN)


@dataclass(frozen=True, slots=True)
class PathsConfig:
    """User-facing default paths from application config."""

    library: str | None = None
    incoming: str | None = None


@dataclass(frozen=True, slots=True)
class CommandConfig:
    """Default execution behavior for one command family."""

    auto_apply: bool = False


@dataclass(frozen=True, slots=True)
class OrganizeConfig(CommandConfig):
    """Default execution behavior for organize."""

    auto_apply: bool = DEFAULT_ORGANIZE_AUTO_APPLY


@dataclass(frozen=True, slots=True)
class PathPolicyConfig:
    """Settings used by PathPolicy canonical path generation."""

    template: str = DEFAULT_PATH_POLICY_TEMPLATE
    unknown_artist: str = DEFAULT_UNKNOWN_ARTIST
    unknown_album: str = DEFAULT_UNKNOWN_ALBUM
    sanitize: bool = DEFAULT_PATH_POLICY_SANITIZE
    max_filename_length: int = DEFAULT_MAX_FILENAME_LENGTH
    disc_number_style: str = DEFAULT_PATH_POLICY_DISC_NUMBER_STYLE
    disc_number_condition: str = DEFAULT_PATH_POLICY_DISC_NUMBER_CONDITION

    def __post_init__(self) -> None:
        """Validate path policy tunables that affect generated paths."""
        if self.max_filename_length <= 0:
            raise ValueError(INVALID_MAX_FILENAME_LENGTH_MESSAGE)
        if self.disc_number_style not in ALLOWED_PATH_POLICY_DISC_NUMBER_STYLES:
            raise ValueError(INVALID_PATH_POLICY_DISC_NUMBER_STYLE_MESSAGE)
        if self.disc_number_condition not in ALLOWED_PATH_POLICY_DISC_NUMBER_CONDITIONS:
            raise ValueError(INVALID_PATH_POLICY_DISC_NUMBER_CONDITION_MESSAGE)
        if self.unknown_artist.strip() == "":
            raise ValueError(INVALID_PATH_POLICY_UNKNOWN_ARTIST_MESSAGE)
        if self.unknown_album.strip() == "":
            raise ValueError(INVALID_PATH_POLICY_UNKNOWN_ALBUM_MESSAGE)
        _validate_template_placeholders(self.template)
        # Templates are path stems. A literal dot in the final component is
        # treated as an extension-like suffix and is rejected before planning.
        if _final_component_contains_literal_extension(self.template):
            raise ValueError(INVALID_PATH_POLICY_TEMPLATE_EXTENSION_MESSAGE)


@dataclass(frozen=True, slots=True)
class ArtistIdConfig:
    """Tunables for automatic internal artist-ID generation."""

    max_length: int = DEFAULT_ARTIST_ID_MAX_LENGTH
    fallback_id: str = DEFAULT_ARTIST_ID_FALLBACK

    def __post_init__(self) -> None:
        """Validate automatic artist-ID generation tunables."""
        if self.max_length <= 0:
            raise ValueError(INVALID_ARTIST_ID_MAX_LENGTH_MESSAGE)
        if _ARTIST_ID_VALUE_PATTERN.fullmatch(self.fallback_id) is None:
            raise ValueError(INVALID_ARTIST_ID_FALLBACK_MESSAGE)


@dataclass(frozen=True, slots=True)
class MetadataConfig:
    """Settings that define required metadata during plan creation."""

    prefer_album_artist: bool = DEFAULT_METADATA_PREFER_ALBUM_ARTIST
    require_title: bool = DEFAULT_METADATA_REQUIRE_TITLE
    require_artist: bool = DEFAULT_METADATA_REQUIRE_ARTIST
    require_album: bool = DEFAULT_METADATA_REQUIRE_ALBUM
    album_year_resolution: str = DEFAULT_ALBUM_YEAR_RESOLUTION

    def __post_init__(self) -> None:
        """Validate metadata handling choices used during plan creation."""
        if self.album_year_resolution not in ALLOWED_ALBUM_YEAR_RESOLUTION_METHODS:
            raise ValueError(INVALID_METADATA_ALBUM_YEAR_RESOLUTION_MESSAGE)


@dataclass(frozen=True, slots=True)
class CollisionConfig:
    """Settings that define plan-time conflict and duplicate behavior."""

    on_target_exists: str = DEFAULT_COLLISION_ON_TARGET_EXISTS
    on_duplicate_hash: str = DEFAULT_COLLISION_ON_DUPLICATE_HASH
    on_missing_metadata: str = DEFAULT_COLLISION_ON_MISSING_METADATA


@dataclass(frozen=True, slots=True)
class MusicBrainzConfig:
    """Persisted operational controls for MusicBrainz artist-name lookup."""

    enabled: bool = DEFAULT_MUSICBRAINZ_ENABLED
    application_name: str = DEFAULT_MUSICBRAINZ_APPLICATION_NAME
    contact: str = DEFAULT_MUSICBRAINZ_CONTACT
    timeout_seconds: float = DEFAULT_MUSICBRAINZ_TIMEOUT_SECONDS
    retry_limit: int = DEFAULT_MUSICBRAINZ_RETRY_LIMIT
    rate_limit_seconds: float = DEFAULT_MUSICBRAINZ_RATE_LIMIT_SECONDS

    def __post_init__(self) -> None:
        """Validate bounded provider identity and request controls."""
        if self.application_name.strip() == "":
            raise ValueError(INVALID_MUSICBRAINZ_APPLICATION_NAME_MESSAGE)
        if self.contact.strip() == "":
            raise ValueError(INVALID_MUSICBRAINZ_CONTACT_MESSAGE)
        if not isfinite(self.timeout_seconds) or not self.timeout_seconds > 0:
            raise ValueError(INVALID_MUSICBRAINZ_TIMEOUT_MESSAGE)
        if self.retry_limit < 0:
            raise ValueError(INVALID_MUSICBRAINZ_RETRY_LIMIT_MESSAGE)
        if not isfinite(self.rate_limit_seconds) or not (
            self.rate_limit_seconds >= DEFAULT_MUSICBRAINZ_RATE_LIMIT_SECONDS
        ):
            raise ValueError(INVALID_MUSICBRAINZ_RATE_LIMIT_MESSAGE)


@dataclass(frozen=True, slots=True)
class HashingConfig:
    """Persisted operational controls for streaming content hashes."""

    read_chunk_size_bytes: int = DEFAULT_HASHING_READ_CHUNK_SIZE_BYTES

    def __post_init__(self) -> None:
        """Reject chunk sizes that cannot advance a streaming hash."""
        if self.read_chunk_size_bytes <= 0:
            raise ValueError(INVALID_HASHING_READ_CHUNK_SIZE_MESSAGE)


@dataclass(frozen=True, slots=True)
class LoggingConfig:
    """Persisted destination, severity, rotation, and retention controls."""

    destination: str | None = DEFAULT_LOGGING_DESTINATION
    level: str = DEFAULT_LOGGING_LEVEL
    rotation_max_bytes: int = DEFAULT_LOGGING_ROTATION_MAX_BYTES
    retention_files: int = DEFAULT_LOGGING_RETENTION_FILES

    def __post_init__(self) -> None:
        """Validate one safe application-root-relative log policy."""
        if self.destination is not None and not _is_normalized_application_relative_path(self.destination):
            raise ValueError(INVALID_LOGGING_DESTINATION_MESSAGE)
        if self.level not in ALLOWED_LOGGING_LEVELS:
            raise ValueError(INVALID_LOGGING_LEVEL_MESSAGE)
        if self.rotation_max_bytes <= 0:
            raise ValueError(INVALID_LOGGING_ROTATION_MAX_BYTES_MESSAGE)
        if self.retention_files <= 0:
            raise ValueError(INVALID_LOGGING_RETENTION_FILES_MESSAGE)


@dataclass(frozen=True, slots=True)
class CompanionsConfig:
    """Persisted opt-in control for companion lyrics and artwork."""

    enabled: bool = DEFAULT_COMPANIONS_ENABLED


@dataclass(frozen=True, slots=True)
class UnprocessedConfig:
    """Persisted controls for reviewed unprocessed-file collection."""

    enabled: bool = DEFAULT_UNPROCESSED_ENABLED
    directory: str = DEFAULT_UNPROCESSED_DIRECTORY
    result_preview_limit: int = DEFAULT_UNPROCESSED_RESULT_PREVIEW_LIMIT

    def __post_init__(self) -> None:
        """Validate one portable destination component and bounded preview size."""
        if not _is_portable_relative_component(self.directory):
            raise ValueError(INVALID_UNPROCESSED_DIRECTORY_MESSAGE)
        if not _is_valid_unprocessed_result_preview_limit(self.result_preview_limit):
            raise ValueError(INVALID_UNPROCESSED_RESULT_PREVIEW_LIMIT_MESSAGE)


def _is_normalized_application_relative_path(value: str) -> bool:
    if value.strip() == "" or value == "." or "\\" in value:
        return False
    logical_path = PurePosixPath(value)
    windows_path = PureWindowsPath(value)
    return (
        not logical_path.is_absolute()
        and windows_path.drive == ""
        and ".." not in logical_path.parts
        and value == logical_path.as_posix()
    )


def _is_portable_relative_component(value: object) -> bool:
    if not isinstance(value, str):
        return False
    if (
        value == ""
        or value in {CURRENT_DIRECTORY_REFERENCE, PARENT_DIRECTORY_REFERENCE}
        or value.endswith((CURRENT_DIRECTORY_REFERENCE, " "))
        or any(character in PORTABLE_PATH_FORBIDDEN_CHARACTERS for character in value)
        or any(ord(character) < PORTABLE_PATH_CONTROL_CHARACTER_LIMIT for character in value)
    ):
        return False
    windows_stem = value.split(CURRENT_DIRECTORY_REFERENCE, maxsplit=1)[0].upper()
    return windows_stem not in PATH_POLICY_RESERVED_WINDOWS_DEVICE_NAMES


def _is_valid_unprocessed_result_preview_limit(value: object) -> bool:
    return (
        not isinstance(value, bool)
        and isinstance(value, int)
        and UNPROCESSED_RESULT_PREVIEW_LIMIT_MIN <= value <= UNPROCESSED_RESULT_PREVIEW_LIMIT_MAX
    )


def _validate_template_placeholders(template: str) -> None:
    allowed_placeholders = set(PATH_POLICY_ALLOWED_PLACEHOLDERS)
    for _, field_name, format_spec, conversion in Formatter().parse(template):
        if field_name is None:
            continue
        # Keep the template language intentionally small and deterministic.
        if field_name == "" or format_spec != "" or conversion is not None or not field_name.isidentifier():
            raise ValueError(INVALID_PATH_POLICY_TEMPLATE_SYNTAX_MESSAGE)
        if field_name not in allowed_placeholders:
            raise ValueError(INVALID_PATH_POLICY_TEMPLATE_PLACEHOLDER_MESSAGE)


def _final_component_contains_literal_extension(template: str) -> bool:
    final_component = template.strip().rsplit(LOGICAL_PATH_SEPARATOR, maxsplit=1)[-1]
    return any(PATH_EXTENSION_PREFIX in literal_text for literal_text, _, _, _ in Formatter().parse(final_component))


@dataclass(frozen=True, slots=True)
class AppConfig:
    """In-memory representation of user settings."""

    version: int = CONFIG_VERSION
    paths: PathsConfig = PathsConfig()
    add: CommandConfig = CommandConfig(auto_apply=DEFAULT_ADD_AUTO_APPLY)
    organize: OrganizeConfig = OrganizeConfig()
    refresh: CommandConfig = CommandConfig(auto_apply=DEFAULT_REFRESH_AUTO_APPLY)
    path_policy: PathPolicyConfig = PathPolicyConfig()
    artist_ids: ArtistIdConfig = field(default_factory=ArtistIdConfig)
    metadata: MetadataConfig = MetadataConfig()
    collision: CollisionConfig = CollisionConfig()
    musicbrainz: MusicBrainzConfig = MusicBrainzConfig()
    hashing: HashingConfig = HashingConfig()
    logging: LoggingConfig = LoggingConfig()
    companions: CompanionsConfig = CompanionsConfig()
    unprocessed: UnprocessedConfig = UnprocessedConfig()

    def __post_init__(self) -> None:
        """Reject config versions that this domain model cannot interpret."""
        if self.version != CONFIG_VERSION:
            raise ValueError(INVALID_CONFIG_VERSION_MESSAGE)
