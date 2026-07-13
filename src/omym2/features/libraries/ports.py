"""
Summary: Groups dependencies for read-only Library inspection.
Why: Keeps readiness queries behind feature-owned ports.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from omym2.features.common_ports import ConfigSnapshotReader, UnitOfWork


@dataclass(frozen=True, slots=True)
class LibraryInspectionPorts:
    """Ports needed to project persisted Libraries against current Config."""

    uow: UnitOfWork
    config_snapshot_reader: ConfigSnapshotReader
