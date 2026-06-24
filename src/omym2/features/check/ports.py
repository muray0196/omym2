"""
Summary: Groups check feature port dependencies.
Why: Keeps check read-only and adapter-independent.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from omym2.features.common_ports import ConfigStore, FileScanner, FileSnapshotReader, PathResolver, UnitOfWork


@dataclass(frozen=True, slots=True)
class CheckLibraryPorts:
    """Ports required when check inspection is implemented."""

    uow: UnitOfWork
    file_scanner: FileScanner
    file_snapshot_reader: FileSnapshotReader
    config_store: ConfigStore
    path_resolver: PathResolver
