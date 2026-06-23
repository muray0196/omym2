"""
Summary: Groups add feature port dependencies.
Why: Keeps add usecases wired through contracts, not concrete adapters.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from omym2.features.common_ports import (
        Clock,
        ConfigStore,
        FilePresence,
        FileScanner,
        FileSnapshotReader,
        IdGenerator,
        PathResolver,
        UnitOfWork,
    )


@dataclass(frozen=True, slots=True)
class CreateAddPlanPorts:
    """Ports required when add plan creation is implemented."""

    uow: UnitOfWork
    file_scanner: FileScanner
    file_snapshot_reader: FileSnapshotReader
    file_presence: FilePresence
    config_store: ConfigStore
    path_resolver: PathResolver
    clock: Clock
    id_generator: IdGenerator
