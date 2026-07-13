"""
Summary: Implements settings validation through the ConfigStore port.
Why: Validates an edit only against the raw Config revision it was based on.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING

from omym2.domain.services.config_fingerprint import calculate_config_fingerprint
from omym2.features.common_ports import ConfigRevisionMismatchError
from omym2.features.settings.dto import ValidateSettingsResult
from omym2.features.settings.settings_projection import validate_settings_config

if TYPE_CHECKING:
    from omym2.features.settings.dto import ValidateSettingsRequest
    from omym2.features.settings.ports import SettingsPorts


@dataclass(frozen=True, slots=True)
class ValidateSettingsUseCase:
    """Validate a revision-bound application settings candidate."""

    ports: SettingsPorts

    def execute(self, request: ValidateSettingsRequest) -> ValidateSettingsResult:
        """Validate a candidate only while its raw Config edit base remains current."""
        snapshot = self.ports.config_store.read_snapshot()
        if snapshot.config_revision != request.expected_config_revision:
            raise ConfigRevisionMismatchError(request.expected_config_revision, snapshot.config_revision)
        issues = validate_settings_config(request.config)
        return ValidateSettingsResult(
            valid=not issues,
            errors=tuple(f"{issue.field}: {issue.message}" for issue in issues),
            config_revision=snapshot.config_revision,
            config_hash=None if issues else calculate_config_fingerprint(request.config),
        )
