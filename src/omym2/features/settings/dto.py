"""
Summary: Defines settings feature request and response data.
Why: Gives config-facing usecases stable contracts for adapters.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from omym2.domain.models.app_config import AppConfig, PathPolicyConfig
    from omym2.domain.models.track_metadata import TrackMetadata


@dataclass(frozen=True, slots=True)
class SaveSettingsRequest:
    """Request to persist application settings."""

    config: AppConfig


@dataclass(frozen=True, slots=True)
class ValidateSettingsResult:
    """Result of validating persisted application settings."""

    valid: bool
    errors: tuple[str, ...]
    config_hash: str | None = None


@dataclass(frozen=True, slots=True)
class PathPolicyPreviewRequest:
    """Request to render a sample path policy result."""

    path_policy: PathPolicyConfig
    metadata: TrackMetadata
    file_extension: str


@dataclass(frozen=True, slots=True)
class PathPolicyPreviewResult:
    """Result of rendering a path policy preview."""

    path: str | None
    errors: tuple[str, ...]
