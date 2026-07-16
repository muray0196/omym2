"""
Summary: Defines settings feature request and response data.
Why: Gives config-facing usecases stable contracts for adapters.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from omym2.domain.models.app_config import AppConfig, ArtistIdConfig, ArtistNameConfig, PathPolicyConfig
    from omym2.domain.models.track_metadata import TrackMetadata
    from omym2.features.common_ports import ConfigSnapshotState


@dataclass(frozen=True, slots=True)
class LoadSettingsResult:
    """Current Config recovery draft and its opaque raw-storage identity."""

    state: ConfigSnapshotState
    config: AppConfig
    config_revision: str
    errors: tuple[str, ...]


@dataclass(frozen=True, slots=True)
class SaveSettingsRequest:
    """Request to persist application settings."""

    config: AppConfig
    expected_config_revision: str


@dataclass(frozen=True, slots=True)
class ValidateSettingsRequest:
    """Candidate application settings tied to the raw state the caller edited."""

    config: AppConfig
    expected_config_revision: str


@dataclass(frozen=True, slots=True)
class PathPolicyPreviewRequest:
    """Request to render a sample path policy result."""

    path_policy: PathPolicyConfig
    artist_ids: ArtistIdConfig
    artist_names: ArtistNameConfig
    metadata: TrackMetadata
    file_extension: str


@dataclass(frozen=True, slots=True)
class PathPolicyPreviewResult:
    """Result of rendering a path policy preview."""

    path: str | None
    errors: tuple[str, ...]


@dataclass(frozen=True, slots=True)
class SettingsChoicesResult:
    """Backend-owned closed values presented by Settings controls."""

    command_modes: tuple[str, ...]
    disc_number_styles: tuple[str, ...]
    disc_number_conditions: tuple[str, ...]
    album_year_resolutions: tuple[str, ...]
    target_exists_policies: tuple[str, ...]
    duplicate_hash_policies: tuple[str, ...]
    missing_metadata_policies: tuple[str, ...]
    musicbrainz_cache_policies: tuple[str, ...]
    logging_levels: tuple[str, ...]
    unprocessed_result_preview_limit_min: int
    unprocessed_result_preview_limit_max: int
    path_placeholders: tuple[str, ...]


@dataclass(frozen=True, slots=True)
class SettingsValidationIssue:
    """One deterministic field-level candidate or recovery error."""

    field: str
    message: str


type SettingsChangeValue = str | int | float | bool | None


@dataclass(frozen=True, slots=True)
class SettingsFieldChange:
    """One deterministic field-level difference from the current Config."""

    field: str
    before: SettingsChangeValue
    after: SettingsChangeValue


@dataclass(frozen=True, slots=True)
class SettingsEditResult:
    """Recovery-capable current Settings edit projection."""

    config: AppConfig
    config_revision: str
    choices: SettingsChoicesResult
    valid: bool
    validation_issues: tuple[SettingsValidationIssue, ...]
    preview: PathPolicyPreviewResult


@dataclass(frozen=True, slots=True)
class SettingsCandidateResult:
    """Validated Settings candidate or completed save projection."""

    config: AppConfig
    config_revision: str
    changes: tuple[SettingsFieldChange, ...]
    valid: bool
    validation_issues: tuple[SettingsValidationIssue, ...]
    preview: PathPolicyPreviewResult
