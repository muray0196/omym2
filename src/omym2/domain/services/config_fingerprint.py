"""
Summary: Defines pure config fingerprint calculation.
Why: Lets Plans preserve the settings identity used during creation.
"""

from __future__ import annotations

import json
from dataclasses import asdict
from hashlib import new
from typing import TYPE_CHECKING

from omym2.config import (
    CONFIG_FINGERPRINT_ALGORITHM,
    CONFIG_FINGERPRINT_ENCODING,
    CONFIG_FINGERPRINT_JSON_ITEM_SEPARATOR,
    CONFIG_FINGERPRINT_JSON_KEY_SEPARATOR,
    CONFIG_FINGERPRINT_PATH_POLICY_BEHAVIOR_KEY,
    CONFIG_FINGERPRINT_PATH_POLICY_CONFIG_KEY,
    PATH_POLICY_BEHAVIOR_VERSION,
)

if TYPE_CHECKING:
    from omym2.domain.models.app_config import AppConfig, ArtistIdConfig, PathPolicyConfig

JSON_SEPARATORS = (CONFIG_FINGERPRINT_JSON_ITEM_SEPARATOR, CONFIG_FINGERPRINT_JSON_KEY_SEPARATOR)


def calculate_config_fingerprint(config: AppConfig, algorithm: str = CONFIG_FINGERPRINT_ALGORITHM) -> str:
    """Return a stable fingerprint for the complete AppConfig value."""
    # Canonical JSON keeps the hash independent from TOML formatting, comments,
    # and table ordering while still reflecting every AppConfig field.
    config_payload = asdict(config)
    config_payload[CONFIG_FINGERPRINT_PATH_POLICY_BEHAVIOR_KEY] = PATH_POLICY_BEHAVIOR_VERSION
    payload = json.dumps(config_payload, sort_keys=True, separators=JSON_SEPARATORS)
    return _fingerprint_payload(payload, algorithm)


def calculate_path_policy_fingerprint(
    path_policy_config: PathPolicyConfig,
    artist_id_config: ArtistIdConfig | None = None,
    algorithm: str = CONFIG_FINGERPRINT_ALGORITHM,
) -> str:
    """Return a stable fingerprint for Library registration path policy."""
    # Library registration depends on canonical path rules, not unrelated
    # settings such as UI display choices or command defaults.
    path_policy_payload = {
        CONFIG_FINGERPRINT_PATH_POLICY_BEHAVIOR_KEY: PATH_POLICY_BEHAVIOR_VERSION,
        CONFIG_FINGERPRINT_PATH_POLICY_CONFIG_KEY: asdict(path_policy_config),
    }
    if artist_id_config is not None:
        path_policy_payload["artist_ids"] = asdict(artist_id_config)
    payload = json.dumps(path_policy_payload, sort_keys=True, separators=JSON_SEPARATORS)
    return _fingerprint_payload(payload, algorithm)


def _fingerprint_payload(payload: str, algorithm: str) -> str:
    digest = new(algorithm)
    digest.update(payload.encode(CONFIG_FINGERPRINT_ENCODING))
    return digest.hexdigest()
