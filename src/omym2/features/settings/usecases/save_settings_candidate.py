"""
Summary: Validates and atomically saves a complete Settings candidate.
Why: Prevents unsupported choices from reaching revision-aware Config persistence.
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
    from omym2.features.settings.dto import SaveSettingsRequest, SettingsValidationIssue
    from omym2.features.settings.ports import SettingsPorts


class SettingsCandidateValidationError(ValueError):
    """Raised when a Settings candidate violates complete Config rules."""

    def __init__(self, issues: tuple[SettingsValidationIssue, ...]) -> None:
        """Retain typed field errors for an inbound adapter's 422 response."""
        self.issues: tuple[SettingsValidationIssue, ...] = issues
        super().__init__("Settings candidate validation failed.")


@dataclass(frozen=True, slots=True)
class SaveSettingsCandidateUseCase:
    """Persist one valid Config candidate with raw-revision compare-and-set."""

    ports: SettingsPorts

    def execute(self, request: SaveSettingsRequest) -> SettingsCandidateResult:
        """Reject invalid/stale candidates before returning the saved projection."""
        snapshot = self.ports.config_store.read_snapshot()
        if snapshot.config_revision != request.expected_config_revision:
            raise ConfigRevisionMismatchError(request.expected_config_revision, snapshot.config_revision)
        issues = validate_settings_config(request.config)
        if issues:
            raise SettingsCandidateValidationError(issues)
        changes = settings_field_changes(snapshot.config, request.config)
        saved = self.ports.config_store.save(
            request.config,
            expected_config_revision=request.expected_config_revision,
        )
        return SettingsCandidateResult(
            config=saved.config,
            config_revision=saved.config_revision,
            changes=changes,
            valid=True,
            validation_issues=(),
            preview=default_settings_preview(saved.config),
        )
