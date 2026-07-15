"""
Summary: Defines in-memory application configuration models.
Why: Gives usecases typed settings without depending on TOML adapters.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from string import Formatter
from types import MappingProxyType
from typing import TYPE_CHECKING

from omym2.config import (
    ALLOWED_ALBUM_YEAR_RESOLUTION_METHODS,
    ALLOWED_PATH_POLICY_DISC_NUMBER_CONDITIONS,
    ALLOWED_PATH_POLICY_DISC_NUMBER_STYLES,
    ARTIST_ID_ENTRY_VALUE_PATTERN,
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
    DEFAULT_PATH_POLICY_DISC_NUMBER_CONDITION,
    DEFAULT_PATH_POLICY_DISC_NUMBER_STYLE,
    DEFAULT_PATH_POLICY_SANITIZE,
    DEFAULT_PATH_POLICY_TEMPLATE,
    DEFAULT_REFRESH_AUTO_APPLY,
    DEFAULT_UNKNOWN_ALBUM,
    DEFAULT_UNKNOWN_ARTIST,
    LOGICAL_PATH_SEPARATOR,
    PATH_EXTENSION_PREFIX,
    PATH_POLICY_ALLOWED_PLACEHOLDERS,
)

if TYPE_CHECKING:
    from collections.abc import Mapping

INVALID_CONFIG_VERSION_MESSAGE = "Unsupported config version."
INVALID_ARTIST_ID_ENTRY_VALUE_MESSAGE = (
    "ArtistIdConfig entries values must be non-empty ASCII letters, digits, or underscores "
    "with optional single internal hyphens."
)
INVALID_ARTIST_ID_FALLBACK_MESSAGE = (
    "ArtistIdConfig fallback_id must be non-empty ASCII letters, digits, or underscores "
    "with optional single internal hyphens."
)
INVALID_ARTIST_ID_MAX_LENGTH_MESSAGE = "ArtistIdConfig max_length must be positive."
INVALID_ARTIST_NAME_PREFERENCE_MESSAGE = "ArtistNameConfig preference keys and values must not be empty."
INVALID_MAX_FILENAME_LENGTH_MESSAGE = "PathPolicy max_filename_length must be positive."
INVALID_PATH_POLICY_DISC_NUMBER_CONDITION_MESSAGE = "PathPolicy disc_number_condition is not supported."
INVALID_PATH_POLICY_DISC_NUMBER_STYLE_MESSAGE = "PathPolicy disc_number_style is not supported."
INVALID_PATH_POLICY_TEMPLATE_EXTENSION_MESSAGE = "PathPolicy template must not include a file extension."
INVALID_PATH_POLICY_TEMPLATE_PLACEHOLDER_MESSAGE = "PathPolicy template contains unsupported placeholder."
INVALID_PATH_POLICY_TEMPLATE_SYNTAX_MESSAGE = "PathPolicy template contains unsupported placeholder syntax."
INVALID_PATH_POLICY_UNKNOWN_ALBUM_MESSAGE = "PathPolicy unknown_album must not be empty."
INVALID_PATH_POLICY_UNKNOWN_ARTIST_MESSAGE = "PathPolicy unknown_artist must not be empty."
INVALID_METADATA_ALBUM_YEAR_RESOLUTION_MESSAGE = "Metadata album_year_resolution must be a supported method."

_ARTIST_ID_ENTRY_VALUE_PATTERN = re.compile(ARTIST_ID_ENTRY_VALUE_PATTERN)


@dataclass(frozen=True, slots=True)
class PathsConfig:
    """User-facing default paths from application config."""

    library: str | None = None
    incoming: str | None = None


@dataclass(frozen=True, slots=True)
class CommandConfig:
    """Default execution behavior for one command family."""

    default_mode: str = DEFAULT_COMMAND_MODE
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
    """Editable artist ID settings stored in TOML config."""

    max_length: int = DEFAULT_ARTIST_ID_MAX_LENGTH
    fallback_id: str = DEFAULT_ARTIST_ID_FALLBACK
    entries: Mapping[str, str] | None = None

    def __post_init__(self) -> None:
        """Validate artist ID tunables and freeze user-editable entries."""
        if self.max_length <= 0:
            raise ValueError(INVALID_ARTIST_ID_MAX_LENGTH_MESSAGE)
        # fallback_id can flow into generated IDs and saved entries (see
        # generate_artist_id's no-usable-characters branch), so it must be
        # sanitizer-stable by the same rule as entries values, not merely
        # non-empty.
        if _ARTIST_ID_ENTRY_VALUE_PATTERN.fullmatch(self.fallback_id) is None:
            raise ValueError(INVALID_ARTIST_ID_FALLBACK_MESSAGE)
        normalized_entries = dict(self.entries or {})
        _validate_artist_id_entries(normalized_entries)
        # Read-only entries keep cached AppConfig instances safe to reuse.
        object.__setattr__(self, "entries", MappingProxyType(normalized_entries))


@dataclass(frozen=True, slots=True)
class ArtistNameConfig:
    """Editable full artist display-name preferences stored in TOML config."""

    preferences: Mapping[str, str] | None = None

    def __post_init__(self) -> None:
        """Validate and freeze exact source-to-display-name preferences."""
        normalized_preferences = dict(self.preferences or {})
        _validate_artist_name_preferences(normalized_preferences)
        object.__setattr__(self, "preferences", MappingProxyType(normalized_preferences))


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


def _validate_artist_id_entries(entries: dict[str, str]) -> None:
    # Entry keys are free-form source artist text; only saved ID values feed
    # PathPolicy path rendering, so only values must be sanitizer-stable.
    for value in entries.values():
        if _ARTIST_ID_ENTRY_VALUE_PATTERN.fullmatch(value) is None:
            raise ValueError(INVALID_ARTIST_ID_ENTRY_VALUE_MESSAGE)


def _validate_artist_name_preferences(preferences: dict[str, str]) -> None:
    for source_name, display_name in preferences.items():
        if source_name.strip() == "" or display_name.strip() == "":
            raise ValueError(INVALID_ARTIST_NAME_PREFERENCE_MESSAGE)


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
    artist_names: ArtistNameConfig = field(default_factory=ArtistNameConfig)
    metadata: MetadataConfig = MetadataConfig()
    collision: CollisionConfig = CollisionConfig()

    def __post_init__(self) -> None:
        """Reject config versions that this domain model cannot interpret."""
        if self.version != CONFIG_VERSION:
            raise ValueError(INVALID_CONFIG_VERSION_MESSAGE)
