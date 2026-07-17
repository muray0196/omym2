"""
Summary: Groups inspect feature port dependencies.
Why: Keeps inspect read-only and adapter-independent.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from omym2.features.common_ports import ArtistNameResolutionReader, ConfigReader, FileSnapshotReader


@dataclass(frozen=True, slots=True)
class InspectFilePorts:
    """Ports required when single-file inspection is implemented."""

    file_snapshot_reader: FileSnapshotReader
    config_store: ConfigReader
    artist_name_resolver: ArtistNameResolutionReader
