"""
Summary: Groups check feature port dependencies.
Why: Separates the recompute-and-persist write path from read-only browsing ports.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING, Protocol

if TYPE_CHECKING:
    from omym2.features.common_ports import (
        BatchFileSnapshotReader,
        Clock,
        ConfigReader,
        FileContentSnapshotReader,
        FileScanner,
        FileSystemPath,
        IdGenerator,
        PathResolver,
        SourceInventoryReader,
        UnitOfWork,
    )


class FileContentHasher(Protocol):
    """Hash-only filesystem observation required by unmanaged-file checks."""

    def calculate(self, path: FileSystemPath) -> str:
        """Return the configured content hash without reading metadata."""
        ...


@dataclass(frozen=True, slots=True)
class CheckLibraryPorts:
    """Ports required to recompute and persist check findings."""

    uow: UnitOfWork
    file_scanner: FileScanner
    file_snapshot_reader: BatchFileSnapshotReader
    file_content_snapshot_reader: FileContentSnapshotReader
    source_inventory_reader: SourceInventoryReader
    file_content_hasher: FileContentHasher
    config_store: ConfigReader
    path_resolver: PathResolver
    clock: Clock
    id_generator: IdGenerator


@dataclass(frozen=True, slots=True)
class CheckQueryPorts:
    """Ports required for read-only browsing of persisted check findings."""

    uow: UnitOfWork
