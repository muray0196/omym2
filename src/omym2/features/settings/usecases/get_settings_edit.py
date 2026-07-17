"""
Summary: Builds the current recovery-capable Settings edit projection.
Why: Gives Web one backend-owned Config draft, choices, validation, and preview.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING

from omym2.features.common_ports import ConfigSnapshotState
from omym2.features.settings.dto import SettingsEditResult, SettingsValidationIssue
from omym2.features.settings.settings_projection import (
    default_settings_preview,
    settings_choices,
    validate_settings_config,
)

if TYPE_CHECKING:
    from omym2.features.settings.ports import SettingsPorts


@dataclass(frozen=True, slots=True)
class GetSettingsEditUseCase:
    """Return one complete Settings edit snapshot without exposing raw TOML."""

    ports: SettingsPorts

    def execute(self) -> SettingsEditResult:
        """Project recovery state while preserving its opaque raw revision."""
        snapshot = self.ports.config_store.read_snapshot()
        if snapshot.state is ConfigSnapshotState.INVALID:
            issues = tuple(SettingsValidationIssue(field="config", message=message) for message in snapshot.errors)
        else:
            issues = validate_settings_config(snapshot.config)
        return SettingsEditResult(
            config=snapshot.config,
            config_revision=snapshot.config_revision,
            choices=settings_choices(),
            valid=not issues,
            validation_issues=issues,
            preview=default_settings_preview(snapshot.config, self.ports.artist_name_resolver),
        )
