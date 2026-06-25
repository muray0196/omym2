"""
Summary: Groups track inspection feature port dependencies.
Why: Keeps Track listing independent from concrete persistence.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from omym2.features.common_ports import UnitOfWork


@dataclass(frozen=True, slots=True)
class TracksPorts:
    """Ports required for read-only Track inspection."""

    uow: UnitOfWork
