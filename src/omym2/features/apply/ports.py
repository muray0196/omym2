"""
Summary: Groups apply feature port dependencies.
Why: Keeps apply wired through durable log and filesystem contracts.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from omym2.features.common_ports import Clock, FileMover, FileSnapshotReader, IdGenerator, PathResolver, UnitOfWork


@dataclass(frozen=True, slots=True)
class ApplyPlanPorts:
    """Ports required when apply execution is implemented."""

    uow: UnitOfWork
    file_mover: FileMover
    file_snapshot_reader: FileSnapshotReader
    path_resolver: PathResolver
    clock: Clock
    id_generator: IdGenerator
