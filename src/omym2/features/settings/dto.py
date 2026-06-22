"""
Summary: Defines settings feature request and response data.
Why: Gives config-facing usecases stable contracts for adapters.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from omym2.domain.models.app_config import AppConfig


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
