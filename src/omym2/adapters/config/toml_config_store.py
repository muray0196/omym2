"""
Summary: Implements TOML-backed AppConfig persistence.
Why: Stores editable user settings outside SQLite in the documented location.
"""

from __future__ import annotations

import json
import tomllib
from dataclasses import dataclass, field
from typing import TYPE_CHECKING

from omym2.adapters.config.config_validator import (
    ADD_SECTION,
    ARTIST_IDS_SECTION,
    AUTO_APPLY_KEY,
    COLLISION_SECTION,
    DEFAULT_MODE_KEY,
    ENTRIES_KEY,
    FALLBACK_ID_KEY,
    INCOMING_KEY,
    LIBRARY_KEY,
    MAX_FILENAME_LENGTH_KEY,
    MAX_LENGTH_KEY,
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
from omym2.adapters.config.default_config import default_app_config
from omym2.config import CONFIG_FILE_ENCODING
from omym2.features.common_ports import ConfigStoreValidationError

if TYPE_CHECKING:
    from pathlib import Path

    from omym2.domain.models.app_config import AppConfig

INVALID_TOML_MESSAGE_PREFIX = "Invalid TOML"
UNSUPPORTED_TOML_VALUE_MESSAGE = "Unsupported TOML value type."


@dataclass(frozen=True, slots=True)
class TomlConfigStore:
    """ConfigStore implementation backed by one TOML file."""

    config_path: Path
    # Single-entry parse cache keyed by exact TOML text, so metadata-preserving
    # external rewrites cannot reuse stale config.
    _load_cache: dict[str, AppConfig] = field(default_factory=dict, init=False, repr=False, compare=False)

    def load(self) -> AppConfig:
        """Load settings, returning defaults when the file is not created yet."""
        if not self.config_path.exists():
            return default_app_config()
        config_text = self.config_path.read_text(encoding=CONFIG_FILE_ENCODING)
        cached_config = self._load_cache.get(config_text)
        if cached_config is not None:
            return cached_config
        config = load_config_text(config_text)
        self._load_cache.clear()
        self._load_cache[config_text] = config
        return config

    def save(self, config: AppConfig) -> None:
        """Persist settings, creating the config directory lazily."""
        self.config_path.parent.mkdir(parents=True, exist_ok=True)
        _ = self.config_path.write_text(dump_config_toml(config), encoding=CONFIG_FILE_ENCODING)
        # A successful save changes the source text behind any cached parse.
        self._load_cache.clear()


def load_config_text(config_text: str) -> AppConfig:
    """Parse and validate TOML config text."""
    try:
        raw_config = tomllib.loads(config_text)
    except tomllib.TOMLDecodeError as exc:
        raise ConfigStoreValidationError((f"{INVALID_TOML_MESSAGE_PREFIX}: {exc}",)) from exc
    return validate_config_data(raw_config)


def dump_config_toml(config: AppConfig) -> str:
    """Return deterministic TOML text for an AppConfig value."""
    lines = [f"{VERSION_KEY} = {config.version}", ""]
    _append_section(
        lines,
        PATHS_SECTION,
        (
            (LIBRARY_KEY, config.paths.library),
            (INCOMING_KEY, config.paths.incoming),
        ),
    )
    _append_section(
        lines,
        ADD_SECTION,
        (
            (DEFAULT_MODE_KEY, config.add.default_mode),
            (AUTO_APPLY_KEY, config.add.auto_apply),
        ),
    )
    _append_section(
        lines,
        ORGANIZE_SECTION,
        (
            (DEFAULT_MODE_KEY, config.organize.default_mode),
            (AUTO_APPLY_KEY, config.organize.auto_apply),
            (ONLY_MISPLACED_KEY, config.organize.only_misplaced),
        ),
    )
    _append_section(
        lines,
        REFRESH_SECTION,
        (
            (DEFAULT_MODE_KEY, config.refresh.default_mode),
            (AUTO_APPLY_KEY, config.refresh.auto_apply),
        ),
    )
    _append_section(
        lines,
        PATH_POLICY_SECTION,
        (
            (TEMPLATE_KEY, config.path_policy.template),
            (UNKNOWN_ARTIST_KEY, config.path_policy.unknown_artist),
            (UNKNOWN_ALBUM_KEY, config.path_policy.unknown_album),
            (SANITIZE_KEY, config.path_policy.sanitize),
            (MAX_FILENAME_LENGTH_KEY, config.path_policy.max_filename_length),
        ),
    )
    _append_section(
        lines,
        ARTIST_IDS_SECTION,
        (
            (MAX_LENGTH_KEY, config.artist_ids.max_length),
            (FALLBACK_ID_KEY, config.artist_ids.fallback_id),
        ),
    )
    _append_section(
        lines,
        f"{ARTIST_IDS_SECTION}.{ENTRIES_KEY}",
        tuple((key, value) for key, value in sorted((config.artist_ids.entries or {}).items())),
    )
    _append_section(
        lines,
        METADATA_SECTION,
        (
            (PREFER_ALBUM_ARTIST_KEY, config.metadata.prefer_album_artist),
            (REQUIRE_TITLE_KEY, config.metadata.require_title),
            (REQUIRE_ARTIST_KEY, config.metadata.require_artist),
            (REQUIRE_ALBUM_KEY, config.metadata.require_album),
        ),
    )
    _append_section(
        lines,
        COLLISION_SECTION,
        (
            (ON_TARGET_EXISTS_KEY, config.collision.on_target_exists),
            (ON_DUPLICATE_HASH_KEY, config.collision.on_duplicate_hash),
            (ON_MISSING_METADATA_KEY, config.collision.on_missing_metadata),
        ),
    )
    _append_section(
        lines,
        UI_SECTION,
        (
            (THEME_KEY, config.ui.theme),
            (SHOW_ADVANCED_SETTINGS_KEY, config.ui.show_advanced_settings),
        ),
    )
    return "\n".join(lines).rstrip() + "\n"


def _append_section(lines: list[str], section: str, values: tuple[tuple[str, object | None], ...]) -> None:
    lines.append(f"[{section}]")
    for key, value in values:
        if value is None:
            continue
        lines.append(f"{_format_toml_key(key)} = {_format_toml_value(value)}")
    lines.append("")


def _format_toml_key(key: str) -> str:
    if key != "" and key.isascii() and all(char.isalnum() or char in ("_", "-") for char in key):
        return key
    return json.dumps(key)


def _format_toml_value(value: object) -> str:
    if isinstance(value, bool):
        return "true" if value else "false"
    if isinstance(value, int):
        return str(value)
    if isinstance(value, str):
        return json.dumps(value)
    raise TypeError(UNSUPPORTED_TOML_VALUE_MESSAGE)
