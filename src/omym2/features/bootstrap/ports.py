"""
Summary: Defines ports required for read-only Bootstrap readiness.
Why: Keeps Bootstrap independent of TOML and SQLite implementations.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING, Protocol

if TYPE_CHECKING:
    from collections.abc import Sequence

    from omym2.domain.models.library import Library
    from omym2.features.common_ports import ConfigSnapshotReader
    from omym2.shared.ids import OperationId


class LibrarySnapshotUnavailableError(RuntimeError):
    """Raised when persisted Library state cannot be read safely."""


class LibrarySnapshotReader(Protocol):
    """Read-only Library snapshot boundary for Bootstrap."""

    def list_libraries(self) -> Sequence[Library]:
        """Return all persisted Libraries without applying selection policy."""
        ...


class OperationSnapshotReader(Protocol):
    """Read-only active Operation boundary for Bootstrap recovery."""

    def active_operation_id(self) -> OperationId | None:
        """Return the single queued/running Operation identity, if present."""
        ...


@dataclass(frozen=True, slots=True)
class BootstrapPorts:
    """Ports required to inspect Config and Library readiness."""

    config_snapshot_reader: ConfigSnapshotReader
    library_snapshot_reader: LibrarySnapshotReader
    operation_snapshot_reader: OperationSnapshotReader
