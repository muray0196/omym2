"""
Summary: Tests config fingerprint policy.
Why: Ensures reviewed Plans can preserve the settings identity used.
"""

from __future__ import annotations

import json
from dataclasses import asdict
from hashlib import new

from omym2.config import (
    CONFIG_FINGERPRINT_ALGORITHM,
    CONFIG_FINGERPRINT_ENCODING,
    CONFIG_FINGERPRINT_JSON_ITEM_SEPARATOR,
    CONFIG_FINGERPRINT_JSON_KEY_SEPARATOR,
)
from omym2.domain.models.app_config import AppConfig, ArtistIdConfig, ArtistIdEntry, UiConfig
from omym2.domain.services.config_fingerprint import calculate_config_fingerprint, calculate_path_policy_fingerprint

UI_THEME_DARK = "dark"
ARTIST_ID_SOURCE = "Aimer"
JSON_SEPARATORS = (CONFIG_FINGERPRINT_JSON_ITEM_SEPARATOR, CONFIG_FINGERPRINT_JSON_KEY_SEPARATOR)


def test_config_fingerprint_is_stable_for_equal_configs() -> None:
    """Equal AppConfig values produce the same fingerprint."""
    config = AppConfig()

    assert calculate_config_fingerprint(config) == calculate_config_fingerprint(AppConfig())


def test_config_fingerprint_changes_when_config_changes() -> None:
    """Different AppConfig values produce different fingerprints."""
    default_hash = calculate_config_fingerprint(AppConfig())
    changed_hash = calculate_config_fingerprint(AppConfig(ui=UiConfig(theme=UI_THEME_DARK)))

    assert changed_hash != default_hash


def test_path_policy_fingerprint_includes_behavior_version() -> None:
    """PathPolicy behavior changes invalidate legacy Library registrations."""
    config = AppConfig()
    legacy_payload = json.dumps(asdict(config.path_policy), sort_keys=True, separators=JSON_SEPARATORS)
    legacy_digest = new(CONFIG_FINGERPRINT_ALGORITHM)
    legacy_digest.update(legacy_payload.encode(CONFIG_FINGERPRINT_ENCODING))

    assert calculate_path_policy_fingerprint(config.path_policy) != legacy_digest.hexdigest()


def test_path_policy_fingerprint_changes_when_artist_ids_change() -> None:
    """Artist ID settings affect canonical paths and Library freshness."""
    config = AppConfig()
    changed_artist_ids = ArtistIdConfig(entries=(ArtistIdEntry(source_artist=ARTIST_ID_SOURCE, artist_id="AMR"),))

    assert calculate_path_policy_fingerprint(
        config.path_policy, config.artist_ids
    ) != calculate_path_policy_fingerprint(
        config.path_policy,
        changed_artist_ids,
    )
