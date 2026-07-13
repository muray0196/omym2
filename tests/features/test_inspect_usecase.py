"""
Summary: Tests inspect usecase behavior.
Why: Protects read-only snapshot and canonical-path projection.
"""

from __future__ import annotations

from datetime import UTC, datetime
from typing import TYPE_CHECKING

from omym2.adapters.config.default_config import default_app_config
from omym2.config import (
    PATH_POLICY_DISC_NUMBER_CONDITION_MULTIPLE_DISCS,
    PATH_POLICY_DISC_NUMBER_STYLE_D_PREFIXED,
)
from omym2.domain.models.app_config import AppConfig, PathPolicyConfig
from omym2.domain.models.file_snapshot import FileSnapshot
from omym2.domain.models.track_metadata import TrackMetadata
from omym2.domain.services.content_fingerprint import calculate_content_fingerprint
from omym2.domain.services.metadata_fingerprint import calculate_metadata_fingerprint
from omym2.domain.services.path_policy import MISSING_TITLE_MESSAGE
from omym2.features.inspect.dto import InspectFileRequest
from omym2.features.inspect.ports import InspectFilePorts
from omym2.features.inspect.usecases.inspect_file import InspectFileUseCase

if TYPE_CHECKING:
    from omym2.domain.models.file_scan_entry import FileScanEntry
    from omym2.features.common_ports import FileSystemPath

CAPTURED_AT = datetime(2026, 1, 1, tzinfo=UTC)
CONTENT = b"audio"
CONTENT_HASH = calculate_content_fingerprint(CONTENT)
EXPECTED_CANONICAL_PATH = "Artist/2026_Album/1-02_Title.flac"
EXPECTED_D_PREFIXED_CANONICAL_PATH = "Artist/2026_Album/D1-02_Title.flac"
FILE_EXTENSION = ".flac"
FILE_PATH = "/incoming/title.flac"
FILE_SIZE = 5
METADATA = TrackMetadata(
    title="Title",
    artist="Artist",
    album="Album",
    year=2026,
    track_number=2,
    disc_number=1,
)
MULTI_DISC_METADATA = TrackMetadata(
    title="Title",
    artist="Artist",
    album="Album",
    year=2026,
    track_number=2,
    disc_number=1,
    disc_total=2,
)
METADATA_HASH = calculate_metadata_fingerprint(METADATA)
MISSING_TITLE_METADATA = TrackMetadata(artist="Artist", album="Album")


def test_inspect_file_usecase_returns_snapshot_and_canonical_path() -> None:
    """Inspect returns the captured file snapshot and current canonical path."""
    snapshot = _snapshot(METADATA)
    snapshot_reader = StaticSnapshotReader(snapshot)

    result = InspectFileUseCase(InspectFilePorts(snapshot_reader, StaticConfigStore())).execute(
        InspectFileRequest(FILE_PATH)
    )

    assert snapshot_reader.captured_path == FILE_PATH
    assert result.snapshot == snapshot
    assert result.canonical_path == EXPECTED_CANONICAL_PATH
    assert result.canonical_path_error is None


def test_inspect_file_usecase_uses_metadata_disc_total_for_multiple_disc_paths() -> None:
    """Inspect renders the disc when the single file's tags identify a multi-disc album."""
    snapshot = _snapshot(MULTI_DISC_METADATA)
    config = default_app_config()
    config = AppConfig(
        paths=config.paths,
        add=config.add,
        organize=config.organize,
        refresh=config.refresh,
        path_policy=PathPolicyConfig(
            disc_number_style=PATH_POLICY_DISC_NUMBER_STYLE_D_PREFIXED,
            disc_number_condition=PATH_POLICY_DISC_NUMBER_CONDITION_MULTIPLE_DISCS,
        ),
        artist_ids=config.artist_ids,
        metadata=config.metadata,
        collision=config.collision,
        ui=config.ui,
    )

    result = InspectFileUseCase(InspectFilePorts(StaticSnapshotReader(snapshot), StaticConfigStore(config))).execute(
        InspectFileRequest(FILE_PATH)
    )

    assert result.canonical_path == EXPECTED_D_PREFIXED_CANONICAL_PATH
    assert result.canonical_path_error is None


def test_inspect_file_usecase_reports_canonical_path_errors() -> None:
    """Inspect keeps the snapshot when metadata cannot produce a canonical path."""
    snapshot = _snapshot(MISSING_TITLE_METADATA)

    result = InspectFileUseCase(InspectFilePorts(StaticSnapshotReader(snapshot), StaticConfigStore())).execute(
        InspectFileRequest(FILE_PATH)
    )

    assert result.snapshot == snapshot
    assert result.canonical_path is None
    assert result.canonical_path_error == MISSING_TITLE_MESSAGE


class StaticConfigStore:
    """ConfigStore fake returning an AppConfig."""

    def __init__(self, config: AppConfig | None = None) -> None:
        """Store the config returned by load."""
        self._config: AppConfig = config or default_app_config()

    def load(self) -> AppConfig:
        """Return valid settings."""
        return self._config

    def save(self, config: AppConfig) -> None:
        """Accept saves to satisfy the ConfigStore protocol."""
        del config


class StaticSnapshotReader:
    """FileSnapshotReader fake that records the requested path."""

    def __init__(self, snapshot: FileSnapshot) -> None:
        """Store the snapshot returned by capture."""
        self._snapshot: FileSnapshot = snapshot
        self.captured_path: FileSystemPath | None = None

    def capture(
        self,
        path: FileSystemPath,
        *,
        observation: FileScanEntry | None = None,
    ) -> FileSnapshot:
        """Return the configured snapshot."""
        del observation
        self.captured_path = path
        return self._snapshot


def _snapshot(metadata: TrackMetadata) -> FileSnapshot:
    return FileSnapshot(
        path=FILE_PATH,
        size=FILE_SIZE,
        mtime=CAPTURED_AT,
        file_extension=FILE_EXTENSION,
        content_hash=CONTENT_HASH,
        metadata_hash=calculate_metadata_fingerprint(metadata),
        metadata=metadata,
        filesystem_identity=None,
        captured_at=CAPTURED_AT,
    )
