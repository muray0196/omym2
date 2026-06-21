"""
Summary: Defines in-memory application configuration models.
Why: Gives usecases typed settings without depending on TOML adapters.
"""

from __future__ import annotations

from dataclasses import dataclass

from omym2.config import (
    CONFIG_VERSION,
    DEFAULT_ADD_AUTO_APPLY,
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
    DEFAULT_PATH_POLICY_SANITIZE,
    DEFAULT_PATH_POLICY_TEMPLATE,
    DEFAULT_REFRESH_AUTO_APPLY,
    DEFAULT_UI_SHOW_ADVANCED_SETTINGS,
    DEFAULT_UI_THEME,
    DEFAULT_UNKNOWN_ALBUM,
    DEFAULT_UNKNOWN_ARTIST,
    PATH_EXTENSION_PREFIX,
    PATH_POLICY_EXTENSION_PLACEHOLDER,
)

INVALID_CONFIG_VERSION_MESSAGE = "Unsupported config version."
INVALID_MAX_FILENAME_LENGTH_MESSAGE = "PathPolicy max_filename_length must be positive."
INVALID_PATH_POLICY_TEMPLATE_EXTENSION_MESSAGE = "PathPolicy template must end with .{ext}."


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
    only_misplaced: bool = DEFAULT_ORGANIZE_ONLY_MISPLACED


@dataclass(frozen=True, slots=True)
class PathPolicyConfig:
    """Settings used by PathPolicy canonical path generation."""

    template: str = DEFAULT_PATH_POLICY_TEMPLATE
    unknown_artist: str = DEFAULT_UNKNOWN_ARTIST
    unknown_album: str = DEFAULT_UNKNOWN_ALBUM
    sanitize: bool = DEFAULT_PATH_POLICY_SANITIZE
    max_filename_length: int = DEFAULT_MAX_FILENAME_LENGTH

    def __post_init__(self) -> None:
        """Validate path policy tunables that affect generated paths."""
        if self.max_filename_length <= 0:
            raise ValueError(INVALID_MAX_FILENAME_LENGTH_MESSAGE)
        # Keep the source file extension as the final suffix; otherwise a custom
        # template could silently drop it or replace it with a literal suffix.
        required_suffix = f"{PATH_EXTENSION_PREFIX}{PATH_POLICY_EXTENSION_PLACEHOLDER}"
        if not self.template.strip().endswith(required_suffix):
            raise ValueError(INVALID_PATH_POLICY_TEMPLATE_EXTENSION_MESSAGE)


@dataclass(frozen=True, slots=True)
class MetadataConfig:
    """Settings that define required metadata during plan creation."""

    prefer_album_artist: bool = DEFAULT_METADATA_PREFER_ALBUM_ARTIST
    require_title: bool = DEFAULT_METADATA_REQUIRE_TITLE
    require_artist: bool = DEFAULT_METADATA_REQUIRE_ARTIST
    require_album: bool = DEFAULT_METADATA_REQUIRE_ALBUM


@dataclass(frozen=True, slots=True)
class CollisionConfig:
    """Settings that define plan-time conflict and duplicate behavior."""

    on_target_exists: str = DEFAULT_COLLISION_ON_TARGET_EXISTS
    on_duplicate_hash: str = DEFAULT_COLLISION_ON_DUPLICATE_HASH
    on_missing_metadata: str = DEFAULT_COLLISION_ON_MISSING_METADATA


@dataclass(frozen=True, slots=True)
class UiConfig:
    """Settings for local UI display preferences."""

    theme: str = DEFAULT_UI_THEME
    show_advanced_settings: bool = DEFAULT_UI_SHOW_ADVANCED_SETTINGS


@dataclass(frozen=True, slots=True)
class AppConfig:
    """In-memory representation of user settings."""

    version: int = CONFIG_VERSION
    paths: PathsConfig = PathsConfig()
    add: CommandConfig = CommandConfig(auto_apply=DEFAULT_ADD_AUTO_APPLY)
    organize: OrganizeConfig = OrganizeConfig()
    refresh: CommandConfig = CommandConfig(auto_apply=DEFAULT_REFRESH_AUTO_APPLY)
    path_policy: PathPolicyConfig = PathPolicyConfig()
    metadata: MetadataConfig = MetadataConfig()
    collision: CollisionConfig = CollisionConfig()
    ui: UiConfig = UiConfig()

    def __post_init__(self) -> None:
        """Reject config versions that this domain model cannot interpret."""
        if self.version != CONFIG_VERSION:
            raise ValueError(INVALID_CONFIG_VERSION_MESSAGE)
