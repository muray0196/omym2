"""
Summary: Reconstructs snapshots from explicitly trusted Track stat baselines.
Why: Lets opted-in read workflows skip unchanged file hashing without weakening apply.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from omym2.domain.models.file_snapshot import FileSnapshot
from omym2.domain.models.track import TrackStatus

if TYPE_CHECKING:
    from datetime import datetime

    from omym2.domain.models.file_scan_entry import FileScanEntry
    from omym2.domain.models.track import Track


def snapshot_from_trusted_stat(
    track: Track,
    source_path: str,
    expected_path: str,
    observation: FileScanEntry,
    captured_at: datetime,
) -> FileSnapshot | None:
    """Reuse persisted Track state only when the complete stat baseline matches."""
    if track.status != TrackStatus.ACTIVE or track.current_path != source_path:
        return None
    if observation.path != expected_path:
        return None
    if track.size is None or track.mtime is None:
        return None
    if track.size != observation.size or track.mtime != observation.mtime:
        return None

    return FileSnapshot(
        path=observation.path,
        size=observation.size,
        mtime=observation.mtime,
        file_extension=observation.file_extension,
        content_hash=track.content_hash,
        metadata_hash=track.metadata_hash,
        metadata=track.metadata,
        filesystem_identity=None,
        captured_at=captured_at,
    )
