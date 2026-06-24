"""
Summary: Implements settings persistence through the ConfigStore port.
Why: Keeps TOML save behavior behind a feature usecase boundary.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from omym2.features.settings.dto import SaveSettingsRequest
    from omym2.features.settings.ports import SettingsPorts


@dataclass(frozen=True, slots=True)
class SaveSettingsUseCase:
    """Persist application settings."""

    ports: SettingsPorts

    def execute(self, request: SaveSettingsRequest) -> None:
        """Save the supplied application settings."""
        self.ports.config_store.save(request.config)
