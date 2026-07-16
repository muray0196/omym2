"""
Summary: Groups organize feature port dependencies.
Why: Keeps organize usecases wired through contracts, not concrete adapters.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from omym2.features.common_ports import (
        ArtistNameResolutionReader,
        BatchFileSnapshotReader,
        Clock,
        ConfigReader,
        FileContentSnapshotReader,
        FilePresence,
        FileScanner,
        IdGenerator,
        PathResolver,
        SourceInventoryReader,
        UnitOfWork,
    )


@dataclass(frozen=True, slots=True)
class CreateOrganizePlanPorts:
    """Ports required when organize planning is implemented."""

    uow: UnitOfWork
    file_scanner: FileScanner
    file_snapshot_reader: BatchFileSnapshotReader
    file_content_snapshot_reader: FileContentSnapshotReader
    source_inventory_reader: SourceInventoryReader
    file_presence: FilePresence
    config_store: ConfigReader
    artist_name_resolver: ArtistNameResolutionReader
    path_resolver: PathResolver
    clock: Clock
    id_generator: IdGenerator
