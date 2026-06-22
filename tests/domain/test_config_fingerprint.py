"""
Summary: Tests config fingerprint policy.
Why: Ensures reviewed Plans can preserve the settings identity used.
"""

from __future__ import annotations

from omym2.domain.models.app_config import AppConfig, UiConfig
from omym2.domain.services.config_fingerprint import calculate_config_fingerprint

UI_THEME_DARK = "dark"


def test_config_fingerprint_is_stable_for_equal_configs() -> None:
    """Equal AppConfig values produce the same fingerprint."""
    config = AppConfig()

    assert calculate_config_fingerprint(config) == calculate_config_fingerprint(AppConfig())


def test_config_fingerprint_changes_when_config_changes() -> None:
    """Different AppConfig values produce different fingerprints."""
    default_hash = calculate_config_fingerprint(AppConfig())
    changed_hash = calculate_config_fingerprint(AppConfig(ui=UiConfig(theme=UI_THEME_DARK)))

    assert changed_hash != default_hash
