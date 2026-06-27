"""
Summary: Tests settings preview usecase.
Why: Protects Web UI path preview behavior at the feature boundary.
"""

from __future__ import annotations

from omym2.domain.models.app_config import AppConfig
from omym2.domain.models.track_metadata import TrackMetadata
from omym2.features.settings.dto import PathPolicyPreviewRequest
from omym2.features.settings.usecases.preview_path_policy import PreviewPathPolicyUseCase

EXPECTED_PREVIEW_PATH = "Aimer/2024_Example Album/1-03_Example Song.flac"
SOURCE_EXTENSION = ".FLAC"


def test_path_policy_preview_renders_sample_path() -> None:
    """Preview uses PathPolicy and normalizes the source extension."""
    result = PreviewPathPolicyUseCase().execute(
        PathPolicyPreviewRequest(
            path_policy=AppConfig().path_policy,
            metadata=TrackMetadata(
                title="Example Song",
                artist="Aimer",
                album="Example Album",
                album_artist="Aimer",
                year=2024,
                disc_number=1,
                track_number=3,
            ),
            file_extension=SOURCE_EXTENSION,
        )
    )

    assert result.path == EXPECTED_PREVIEW_PATH
    assert result.errors == ()
