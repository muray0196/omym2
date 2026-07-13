"""
Summary: Implements settings loading through the ConfigStore port.
Why: Lets CLI and future UI read settings without importing TOML adapters.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING

from omym2.features.settings.dto import LoadSettingsResult

if TYPE_CHECKING:
    from omym2.features.settings.ports import SettingsPorts


@dataclass(frozen=True, slots=True)
class LoadSettingsUseCase:
    """Load application settings from the configured store."""

    ports: SettingsPorts

    def execute(self) -> LoadSettingsResult:
        """Return the current settings recovery draft and raw-storage revision."""
        snapshot = self.ports.config_store.read_snapshot()
        return LoadSettingsResult(
            state=snapshot.state,
            config=snapshot.config,
            config_revision=snapshot.config_revision,
            errors=snapshot.errors,
        )
