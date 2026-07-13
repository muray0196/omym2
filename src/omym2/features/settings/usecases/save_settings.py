"""
Summary: Implements settings persistence through the ConfigStore port.
Why: Keeps TOML save behavior behind a feature usecase boundary.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING

from omym2.features.common_ports import ConfigRevisionMismatchError, ConfigStoreValidationError
from omym2.features.settings.dto import SaveSettingsResult
from omym2.features.settings.settings_projection import validate_settings_config

if TYPE_CHECKING:
    from omym2.features.settings.dto import SaveSettingsRequest
    from omym2.features.settings.ports import SettingsPorts


@dataclass(frozen=True, slots=True)
class SaveSettingsUseCase:
    """Persist application settings."""

    ports: SettingsPorts

    def execute(self, request: SaveSettingsRequest) -> SaveSettingsResult:
        """Save the supplied settings only if raw Config still matches the edit base."""
        current = self.ports.config_store.read_snapshot()
        if current.config_revision != request.expected_config_revision:
            raise ConfigRevisionMismatchError(request.expected_config_revision, current.config_revision)
        issues = validate_settings_config(request.config)
        if issues:
            raise ConfigStoreValidationError(tuple(f"{issue.field}: {issue.message}" for issue in issues))
        snapshot = self.ports.config_store.save(
            request.config,
            expected_config_revision=request.expected_config_revision,
        )
        return SaveSettingsResult(config=snapshot.config, config_revision=snapshot.config_revision)
