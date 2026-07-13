"""
Summary: Tests config fingerprint policy.
Why: Ensures reviewed Plans can preserve the settings identity used.
"""

from __future__ import annotations

import json
from dataclasses import asdict
from hashlib import new

from omym2.config import (
    ALBUM_YEAR_RESOLUTION_OLDEST,
    CONFIG_FINGERPRINT_ALGORITHM,
    CONFIG_FINGERPRINT_ENCODING,
    CONFIG_FINGERPRINT_JSON_ITEM_SEPARATOR,
    CONFIG_FINGERPRINT_JSON_KEY_SEPARATOR,
    PATH_POLICY_DISC_NUMBER_CONDITION_MULTIPLE_DISCS,
    PATH_POLICY_DISC_NUMBER_STYLE_D_PREFIXED,
)
from omym2.domain.models.app_config import AppConfig, ArtistIdConfig, PathPolicyConfig, PathsConfig
from omym2.domain.services.config_fingerprint import calculate_config_fingerprint, calculate_path_policy_fingerprint

LIBRARY_PATH = "/music/library"
JSON_SEPARATORS = (CONFIG_FINGERPRINT_JSON_ITEM_SEPARATOR, CONFIG_FINGERPRINT_JSON_KEY_SEPARATOR)


def test_config_fingerprint_is_stable_for_equal_configs() -> None:
    """Equal AppConfig values produce the same fingerprint."""
    config = AppConfig()

    assert calculate_config_fingerprint(config) == calculate_config_fingerprint(AppConfig())


def test_config_fingerprint_changes_when_config_changes() -> None:
    """Different AppConfig values produce different fingerprints."""
    default_hash = calculate_config_fingerprint(AppConfig())
    changed_hash = calculate_config_fingerprint(AppConfig(paths=PathsConfig(library=LIBRARY_PATH)))

    assert changed_hash != default_hash


def test_path_policy_fingerprint_includes_behavior_version() -> None:
    """PathPolicy behavior changes invalidate legacy Library registrations."""
    config = AppConfig()
    legacy_payload = json.dumps(asdict(config.path_policy), sort_keys=True, separators=JSON_SEPARATORS)
    legacy_digest = new(CONFIG_FINGERPRINT_ALGORITHM)
    legacy_digest.update(legacy_payload.encode(CONFIG_FINGERPRINT_ENCODING))

    assert calculate_path_policy_fingerprint(config.path_policy) != legacy_digest.hexdigest()


def test_path_policy_fingerprint_ignores_artist_ids_when_template_cannot_use_them() -> None:
    """Artist ID settings do not stale Library registration for unrelated templates."""
    default_hash = calculate_path_policy_fingerprint(AppConfig().path_policy, AppConfig().artist_ids)
    changed_hash = calculate_path_policy_fingerprint(
        AppConfig().path_policy,
        ArtistIdConfig(entries={"Aimer": "AIMR"}),
    )

    assert changed_hash == default_hash


def test_path_policy_fingerprint_changes_when_used_artist_ids_change() -> None:
    """Artist ID settings affect Library registration when {artist_id} can render paths."""
    path_policy = PathPolicyConfig(template="{artist_id}/{title}")
    default_hash = calculate_path_policy_fingerprint(path_policy, AppConfig().artist_ids)
    changed_hash = calculate_path_policy_fingerprint(
        path_policy,
        ArtistIdConfig(entries={"Aimer": "AIMR"}),
    )

    assert changed_hash != default_hash


def test_path_policy_fingerprint_changes_when_used_album_year_resolution_changes() -> None:
    """Album-year settings affect Library registration when {year} can render paths."""
    path_policy = AppConfig().path_policy
    default_hash = calculate_path_policy_fingerprint(path_policy, AppConfig().artist_ids)
    changed_hash = calculate_path_policy_fingerprint(
        path_policy,
        AppConfig().artist_ids,
        ALBUM_YEAR_RESOLUTION_OLDEST,
    )

    assert changed_hash != default_hash


def test_path_policy_fingerprint_ignores_album_year_resolution_when_template_cannot_use_it() -> None:
    """Album-year settings do not stale Library registration for unrelated templates."""
    path_policy = PathPolicyConfig(template="{artist}/{title}")
    default_hash = calculate_path_policy_fingerprint(path_policy, AppConfig().artist_ids)
    changed_hash = calculate_path_policy_fingerprint(
        path_policy,
        AppConfig().artist_ids,
        ALBUM_YEAR_RESOLUTION_OLDEST,
    )

    assert changed_hash == default_hash


def test_path_policy_fingerprint_ignores_disc_settings_when_template_cannot_use_them() -> None:
    """Disc rendering settings do not stale registration for templates without {disc}."""
    default_hash = calculate_path_policy_fingerprint(PathPolicyConfig(template="{artist}/{title}"))
    changed_hash = calculate_path_policy_fingerprint(
        PathPolicyConfig(
            template="{artist}/{title}",
            disc_number_style=PATH_POLICY_DISC_NUMBER_STYLE_D_PREFIXED,
            disc_number_condition=PATH_POLICY_DISC_NUMBER_CONDITION_MULTIPLE_DISCS,
        )
    )

    assert changed_hash == default_hash


def test_path_policy_fingerprint_changes_when_disc_settings_can_affect_template() -> None:
    """Disc rendering settings stale registration when {disc} can render paths."""
    default_hash = calculate_path_policy_fingerprint(PathPolicyConfig(template="{artist}/{disc}-{title}"))
    changed_hash = calculate_path_policy_fingerprint(
        PathPolicyConfig(
            template="{artist}/{disc}-{title}",
            disc_number_style=PATH_POLICY_DISC_NUMBER_STYLE_D_PREFIXED,
            disc_number_condition=PATH_POLICY_DISC_NUMBER_CONDITION_MULTIPLE_DISCS,
        )
    )

    assert changed_hash != default_hash
