"""
Summary: Groups settings feature port dependencies.
Why: Keeps settings usecases independent from concrete config adapters.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from omym2.features.common_ports import ConfigStore


@dataclass(frozen=True, slots=True)
class SettingsPorts:
    """Ports required for settings load, save, and validation usecases."""

    config_store: ConfigStore
