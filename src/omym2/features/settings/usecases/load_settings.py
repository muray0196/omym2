"""
Summary: Implements settings loading through the ConfigStore port.
Why: Lets CLI and future UI read settings without importing TOML adapters.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from omym2.domain.models.app_config import AppConfig
    from omym2.features.settings.ports import SettingsPorts


@dataclass(frozen=True, slots=True)
class LoadSettingsUseCase:
    """Load application settings from the configured store."""

    ports: SettingsPorts

    def execute(self) -> AppConfig:
        """Return the current application settings."""
        return self.ports.config_store.load()
