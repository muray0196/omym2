"""
Summary: Captures complete read-only file snapshots.
Why: Combines stat, metadata, and hashes for inspect and later planning.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import UTC, datetime
from pathlib import Path

from omym2.adapters.fs.hash_calculator import FileContentHasher
from omym2.domain.models.file_snapshot import FileSnapshot
from omym2.domain.services.metadata_fingerprint import calculate_metadata_fingerprint
from omym2.features.common_ports import Clock, FileSystemPath, MetadataReader, SystemClock


@dataclass(frozen=True, slots=True)
class FilesystemFileSnapshotReader:
    """Capture metadata and hash state for one filesystem file."""

    metadata_reader: MetadataReader
    clock: Clock = field(default_factory=SystemClock)
    hasher: FileContentHasher = field(default_factory=FileContentHasher)

    def capture(self, path: FileSystemPath) -> FileSnapshot:
        """Capture stat, content hash, metadata hash, and metadata."""
        file_path = Path(path)
        stat_result = file_path.stat()
        metadata = self.metadata_reader.read(file_path)
        content_hash = self.hasher.calculate(file_path)

        # The snapshot is an observation, not an atomic filesystem lock. Later
        # Plan and apply workflows re-check hashes before mutating Library files.
        return FileSnapshot(
            path=str(file_path),
            size=stat_result.st_size,
            mtime=datetime.fromtimestamp(stat_result.st_mtime, UTC),
            file_extension=file_path.suffix.lower(),
            content_hash=content_hash,
            metadata_hash=calculate_metadata_fingerprint(metadata),
            metadata=metadata,
            captured_at=self.clock.now(),
        )
