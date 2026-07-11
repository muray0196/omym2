"""
Summary: Captures complete read-only file snapshots.
Why: Combines stat, metadata, and hashes for inspect and later planning.
"""

from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass, field
from datetime import UTC, datetime
from pathlib import Path
from typing import TYPE_CHECKING

from omym2.adapters.fs.hash_calculator import FileContentHasher
from omym2.config import FILE_SNAPSHOT_CAPTURE_MIN_WORKER_COUNT, FILE_SNAPSHOT_CAPTURE_WORKER_COUNT
from omym2.domain.models.file_snapshot import FileSnapshot
from omym2.domain.services.metadata_fingerprint import calculate_metadata_fingerprint
from omym2.features.common_ports import (
    Clock,
    FileSnapshotCaptureRequest,
    FileSystemPath,
    MetadataReader,
    SystemClock,
)

if TYPE_CHECKING:
    from collections.abc import Sequence

INVALID_SNAPSHOT_CAPTURE_WORKER_COUNT_MESSAGE = "Snapshot capture worker count must be positive."


@dataclass(frozen=True, slots=True)
class FilesystemFileSnapshotReader:
    """Capture metadata and hash state for one filesystem file."""

    metadata_reader: MetadataReader
    clock: Clock = field(default_factory=SystemClock)
    hasher: FileContentHasher = field(default_factory=FileContentHasher)
    worker_count: int = FILE_SNAPSHOT_CAPTURE_WORKER_COUNT

    def __post_init__(self) -> None:
        """Validate the configured batch concurrency bound eagerly."""
        if self.worker_count < FILE_SNAPSHOT_CAPTURE_MIN_WORKER_COUNT:
            raise ValueError(INVALID_SNAPSHOT_CAPTURE_WORKER_COUNT_MESSAGE)

    def capture_many(self, requests: Sequence[FileSnapshotCaptureRequest]) -> tuple[FileSnapshot | None, ...]:
        """Capture snapshots concurrently while returning results in request order."""
        if len(requests) == 0:
            return ()
        with ThreadPoolExecutor(max_workers=self.worker_count) as executor:
            return tuple(
                executor.map(
                    self._capture_or_missing,
                    requests,
                    buffersize=self.worker_count,
                )
            )

    def capture(self, path: FileSystemPath) -> FileSnapshot:
        """Capture a fresh stat plus metadata and hashes for one file."""
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

    def _capture_or_missing(self, request: FileSnapshotCaptureRequest) -> FileSnapshot | None:
        try:
            return self.capture(request.path)
        except FileNotFoundError:
            return None
