"""
Summary: Groups refresh feature port dependencies.
Why: Keeps refresh usecases wired through contracts, not concrete adapters.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from omym2.features.common_ports import Clock, FileSnapshotReader, IdGenerator, UnitOfWork


@dataclass(frozen=True, slots=True)
class CreateRefreshPlanPorts:
    """Ports required when refresh planning is implemented."""

    uow: UnitOfWork
    file_snapshot_reader: FileSnapshotReader
    clock: Clock
    id_generator: IdGenerator
