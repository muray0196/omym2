"""
Summary: Validates and projects a complete revision-bound Settings candidate.
Why: Returns deterministic field changes and preview without persisting Config.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING

from omym2.features.common_ports import ConfigRevisionMismatchError
from omym2.features.settings.dto import SettingsCandidateResult
from omym2.features.settings.settings_projection import (
    default_settings_preview,
    settings_field_changes,
    validate_settings_config,
)

if TYPE_CHECKING:
    from omym2.features.settings.dto import ValidateSettingsRequest
    from omym2.features.settings.ports import SettingsPorts


@dataclass(frozen=True, slots=True)
class ValidateSettingsCandidateUseCase:
    """Validate one complete Config candidate against its current edit base."""

    ports: SettingsPorts

    def execute(self, request: ValidateSettingsRequest) -> SettingsCandidateResult:
        """Return validation, changes, and preview without writing Config."""
        snapshot = self.ports.config_store.read_snapshot()
        if snapshot.config_revision != request.expected_config_revision:
            raise ConfigRevisionMismatchError(request.expected_config_revision, snapshot.config_revision)
        issues = validate_settings_config(request.config)
        return SettingsCandidateResult(
            config=request.config,
            config_revision=snapshot.config_revision,
            changes=settings_field_changes(snapshot.config, request.config),
            valid=not issues,
            validation_issues=issues,
            preview=default_settings_preview(request.config, self.ports.artist_name_resolver),
        )
