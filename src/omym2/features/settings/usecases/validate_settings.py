"""
Summary: Implements settings validation through the ConfigStore port.
Why: Gives CLI and future UI a non-throwing validation result.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING

from omym2.domain.services.config_fingerprint import calculate_config_fingerprint
from omym2.features.common_ports import ConfigStoreValidationError
from omym2.features.settings.dto import ValidateSettingsResult

if TYPE_CHECKING:
    from omym2.features.settings.ports import SettingsPorts


@dataclass(frozen=True, slots=True)
class ValidateSettingsUseCase:
    """Validate persisted application settings."""

    ports: SettingsPorts

    def execute(self) -> ValidateSettingsResult:
        """Return validation errors instead of raising config validation exceptions."""
        try:
            config = self.ports.config_store.load()
        except ConfigStoreValidationError as exc:
            return ValidateSettingsResult(valid=False, errors=exc.errors)
        return ValidateSettingsResult(
            valid=True,
            errors=(),
            config_hash=calculate_config_fingerprint(config),
        )
