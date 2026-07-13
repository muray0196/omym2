"""
Summary: Groups durable Operation feature dependencies.
Why: Keeps lifecycle policy independent from clocks, IDs, and SQLite adapters.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from omym2.features.common_ports import Clock, IdGenerator, UnitOfWork


@dataclass(frozen=True, slots=True)
class OperationPorts:
    """Ports required for durable lifecycle usecases."""

    uow: UnitOfWork
    clock: Clock
    id_generator: IdGenerator
