"""
Summary: Tests settings preview usecase.
Why: Protects Web UI path preview behavior at the feature boundary.
"""

from __future__ import annotations

from omym2.domain.models.app_config import AppConfig, PathPolicyConfig
from omym2.domain.models.track_metadata import TrackMetadata
from omym2.features.settings.dto import PathPolicyPreviewRequest
from omym2.features.settings.usecases.preview_path_policy import PreviewPathPolicyUseCase
from tests.fakes.runtime import MappingArtistNameResolver

EXPECTED_PREVIEW_PATH = "Aimer/2024_Example-Album/1-03_Example-Song.flac"
PREFERRED_PREVIEW_PATH = "Hikaru-Utada/Example-Song.flac"
SOURCE_EXTENSION = ".FLAC"


def test_path_policy_preview_renders_sample_path() -> None:
    """Preview uses PathPolicy and normalizes the source extension."""
    result = PreviewPathPolicyUseCase(MappingArtistNameResolver()).execute(
        PathPolicyPreviewRequest(
            path_policy=AppConfig().path_policy,
            artist_ids=AppConfig().artist_ids,
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


def test_path_policy_preview_applies_saved_english_artist_mapping() -> None:
    """Preview projects the saved mapping through the same PathPolicy input as Plans."""
    result = PreviewPathPolicyUseCase(MappingArtistNameResolver({"宇多田ヒカル": "Hikaru Utada"})).execute(
        PathPolicyPreviewRequest(
            path_policy=PathPolicyConfig(template="{artist}/{title}"),
            artist_ids=AppConfig().artist_ids,
            metadata=TrackMetadata(title="Example Song", artist="宇多田ヒカル"),
            file_extension=SOURCE_EXTENSION,
        )
    )

    assert result.path == PREFERRED_PREVIEW_PATH
    assert result.errors == ()
