"""
Summary: Groups undo feature port dependencies.
Why: Keeps undo planning wired through Run history and Plan contracts.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from omym2.features.common_ports import (
        Clock,
        FileContentSnapshotReader,
        FilePresence,
        FileSnapshotReader,
        IdGenerator,
        PathResolver,
        UnitOfWork,
    )


@dataclass(frozen=True, slots=True)
class CreateUndoPlanPorts:
    """Ports required when undo planning is implemented."""

    uow: UnitOfWork
    file_snapshot_reader: FileSnapshotReader
    file_content_snapshot_reader: FileContentSnapshotReader
    file_presence: FilePresence
    path_resolver: PathResolver
    clock: Clock
    id_generator: IdGenerator
