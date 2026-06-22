"""
Summary: Groups history feature port dependencies.
Why: Keeps history queries independent from concrete persistence.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from omym2.features.common_ports import UnitOfWork


@dataclass(frozen=True, slots=True)
class HistoryPorts:
    """Ports required when history queries are implemented."""

    uow: UnitOfWork
