"""
Summary: Defines pure config fingerprint calculation.
Why: Lets Plans preserve the settings identity used during creation.
"""

from __future__ import annotations

import json
from dataclasses import asdict
from hashlib import new
from string import Formatter
from typing import TYPE_CHECKING

from omym2.config import (
    CONFIG_FINGERPRINT_ALGORITHM,
    CONFIG_FINGERPRINT_ENCODING,
    CONFIG_FINGERPRINT_JSON_ITEM_SEPARATOR,
    CONFIG_FINGERPRINT_JSON_KEY_SEPARATOR,
    CONFIG_FINGERPRINT_PATH_POLICY_BEHAVIOR_KEY,
    CONFIG_FINGERPRINT_PATH_POLICY_CONFIG_KEY,
    DEFAULT_ALBUM_YEAR_RESOLUTION,
    PATH_POLICY_ARTIST_ID_PLACEHOLDER,
    PATH_POLICY_BEHAVIOR_VERSION,
    PATH_POLICY_DISC_NUMBER_PLACEHOLDER,
    PATH_POLICY_YEAR_PLACEHOLDER,
)

if TYPE_CHECKING:
    from omym2.domain.models.app_config import AppConfig, ArtistIdConfig, PathPolicyConfig

JSON_SEPARATORS = (CONFIG_FINGERPRINT_JSON_ITEM_SEPARATOR, CONFIG_FINGERPRINT_JSON_KEY_SEPARATOR)

# Shared by add and refresh, which both refuse to operate on a registered
# Library whose stored PathPolicy fingerprint no longer matches current
# config. Organize does not use this message because it re-registers the
# Library under the current PathPolicy instead of rejecting it.
STALE_LIBRARY_MESSAGE = "Registered Library uses a stale PathPolicy. Run organize --library PATH."


def calculate_config_fingerprint(config: AppConfig, algorithm: str = CONFIG_FINGERPRINT_ALGORITHM) -> str:
    """Return a stable fingerprint for the complete AppConfig value."""
    # Canonical JSON keeps the hash independent from TOML formatting, comments,
    # and table ordering while still reflecting every AppConfig field.
    config_payload = _app_config_payload(config)
    config_payload[CONFIG_FINGERPRINT_PATH_POLICY_BEHAVIOR_KEY] = PATH_POLICY_BEHAVIOR_VERSION
    payload = json.dumps(config_payload, sort_keys=True, separators=JSON_SEPARATORS)
    return _fingerprint_payload(payload, algorithm)


def calculate_path_policy_fingerprint(
    path_policy_config: PathPolicyConfig,
    artist_id_config: ArtistIdConfig | None = None,
    album_year_resolution: str = DEFAULT_ALBUM_YEAR_RESOLUTION,
    algorithm: str = CONFIG_FINGERPRINT_ALGORITHM,
) -> str:
    """Return a stable fingerprint for Library registration path policy."""
    # Library registration depends on canonical path rules, not unrelated
    # settings such as UI display choices or command defaults.
    path_policy_payload: dict[str, object] = {
        CONFIG_FINGERPRINT_PATH_POLICY_BEHAVIOR_KEY: PATH_POLICY_BEHAVIOR_VERSION,
        CONFIG_FINGERPRINT_PATH_POLICY_CONFIG_KEY: _path_policy_payload(path_policy_config),
    }
    if artist_id_config is not None and _template_uses_placeholder(
        path_policy_config.template,
        PATH_POLICY_ARTIST_ID_PLACEHOLDER,
    ):
        path_policy_payload["artist_ids"] = _artist_id_payload(artist_id_config)
    if _template_uses_placeholder(path_policy_config.template, PATH_POLICY_YEAR_PLACEHOLDER):
        path_policy_payload["album_year_resolution"] = album_year_resolution
    payload = json.dumps(path_policy_payload, sort_keys=True, separators=JSON_SEPARATORS)
    return _fingerprint_payload(payload, algorithm)


def is_path_policy_stale(library_path_policy_hash: str, current_path_policy_hash: str) -> bool:
    """Return whether a Library's stored PathPolicy hash no longer matches current config."""
    return library_path_policy_hash != current_path_policy_hash


def _template_uses_placeholder(template: str, placeholder: str) -> bool:
    """Return whether a format template contains a renderable field."""
    return any(field_name == placeholder for _, field_name, _, _ in Formatter().parse(template))


def _app_config_payload(config: AppConfig) -> dict[str, object]:
    """Return a JSON-safe config payload without copying immutable mappings through asdict."""
    return {
        "version": config.version,
        "paths": asdict(config.paths),
        "add": asdict(config.add),
        "organize": asdict(config.organize),
        "refresh": asdict(config.refresh),
        "path_policy": asdict(config.path_policy),
        "artist_ids": _artist_id_payload(config.artist_ids),
        "metadata": asdict(config.metadata),
        "collision": asdict(config.collision),
        "ui": asdict(config.ui),
    }


def _path_policy_payload(config: PathPolicyConfig) -> dict[str, object]:
    """Return path policy settings that can affect Library registration paths."""
    payload: dict[str, object] = {
        "template": config.template,
        "unknown_artist": config.unknown_artist,
        "unknown_album": config.unknown_album,
        "sanitize": config.sanitize,
        "max_filename_length": config.max_filename_length,
    }
    if _template_uses_placeholder(config.template, PATH_POLICY_DISC_NUMBER_PLACEHOLDER):
        payload["disc_number_style"] = config.disc_number_style
        payload["disc_number_condition"] = config.disc_number_condition
    return payload


def _artist_id_payload(config: ArtistIdConfig) -> dict[str, object]:
    """Return artist ID settings as plain JSON data for stable hashing."""
    return {
        "max_length": config.max_length,
        "fallback_id": config.fallback_id,
        "entries": dict(config.entries or {}),
    }


def _fingerprint_payload(payload: str, algorithm: str) -> str:
    digest = new(algorithm)
    digest.update(payload.encode(CONFIG_FINGERPRINT_ENCODING))
    return digest.hexdigest()
