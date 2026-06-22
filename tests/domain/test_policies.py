"""
Summary: Tests pure domain policy services.
Why: Protects canonical paths, fingerprints, collisions, and duplicates.
"""

from __future__ import annotations

import pytest

from omym2.domain.models.app_config import PathPolicyConfig
from omym2.domain.models.plan_action import PlanActionReason
from omym2.domain.models.track_metadata import TrackMetadata
from omym2.domain.services.collision_policy import CollisionDecisionKind, CollisionPolicy
from omym2.domain.services.content_fingerprint import calculate_content_fingerprint
from omym2.domain.services.duplicate_policy import DuplicateDecisionKind, DuplicatePolicy
from omym2.domain.services.metadata_fingerprint import calculate_metadata_fingerprint
from omym2.domain.services.path_policy import MISSING_TITLE_MESSAGE, PathPolicy

ALBUM = "Example Album"
ALBUM_ARTIST = "Aimer"
CONTENT = b"content"
DIFFERENT_CONTENT = b"different content"
DISC_NUMBER = 1
EXPECTED_CANONICAL_PATH = "Aimer/2024_Example Album/1-03_Example Song.flac"
EXPECTED_STEM_TEMPLATE_PATH = "Aimer/Example Album/1-03 - Example Song.flac"
FILE_EXTENSION = ".FLAC"
GENRE = "J-Pop"
OCCUPIED_PATH = "Aimer/2024_Example Album/1-03_Example Song.flac"
SANITIZED_ARTIST = "Artist_Name"
SANITIZED_PATH = "Artist_Name/2024_Example Album/1-03_Example Song.flac"
TITLE = "Example Song"
TRACK_NUMBER = 3
TRUNCATED_FILENAME_LENGTH = 12
UNSANITIZED_ARTIST = "Artist:Name"
UNSANITIZED_PATH = "Artist:Name/2024_Example Album/1-03_Example Song.flac"
YEAR = 2024
STEM_TEMPLATE = "{album_artist}/{album}/{disc}-{track} - {title}"


def test_path_policy_generates_relative_path_without_hash_suffix() -> None:
    """PathPolicy uses metadata and extension to create a canonical relative path."""
    metadata = _track_metadata()

    canonical_path = PathPolicy(PathPolicyConfig()).canonical_path(metadata, FILE_EXTENSION)

    assert canonical_path == EXPECTED_CANONICAL_PATH


def test_path_policy_appends_source_extension_to_rendered_stem() -> None:
    """PathPolicy renders a stem template and appends the lowercase source suffix."""
    canonical_path = PathPolicy(PathPolicyConfig(template=STEM_TEMPLATE)).canonical_path(
        _track_metadata(), FILE_EXTENSION
    )

    assert canonical_path == EXPECTED_STEM_TEMPLATE_PATH
    assert canonical_path.endswith(".flac")
    assert ".flac.flac" not in canonical_path


def test_path_policy_sanitizes_metadata_path_components() -> None:
    """Metadata path separators are sanitized so they cannot create extra directories."""
    metadata = TrackMetadata(
        title=TITLE,
        artist="Artist/Name",
        album=ALBUM,
        year=YEAR,
        track_number=TRACK_NUMBER,
        disc_number=DISC_NUMBER,
    )

    canonical_path = PathPolicy(PathPolicyConfig()).canonical_path(metadata, FILE_EXTENSION)

    assert canonical_path == SANITIZED_PATH
    assert canonical_path.startswith(SANITIZED_ARTIST)


def test_path_policy_can_leave_metadata_components_unsanitized() -> None:
    """PathPolicy respects the sanitize config flag for metadata text."""
    metadata = TrackMetadata(
        title=TITLE,
        artist=UNSANITIZED_ARTIST,
        album=ALBUM,
        year=YEAR,
        track_number=TRACK_NUMBER,
        disc_number=DISC_NUMBER,
    )

    canonical_path = PathPolicy(PathPolicyConfig(sanitize=False)).canonical_path(metadata, FILE_EXTENSION)

    assert canonical_path == UNSANITIZED_PATH


def test_path_policy_preserves_extension_when_limiting_long_filename() -> None:
    """PathPolicy shortens long final components without dropping the source extension."""
    metadata = TrackMetadata(
        title="A" * 200,
        artist=ALBUM_ARTIST,
        album=ALBUM,
        year=YEAR,
        track_number=TRACK_NUMBER,
        disc_number=DISC_NUMBER,
    )

    canonical_path = PathPolicy(PathPolicyConfig(max_filename_length=TRUNCATED_FILENAME_LENGTH)).canonical_path(
        metadata, FILE_EXTENSION
    )

    final_component = canonical_path.rsplit("/", maxsplit=1)[-1]
    assert final_component == "1-03_AA.flac"
    assert len(final_component) == TRUNCATED_FILENAME_LENGTH


def test_path_policy_blocks_missing_title() -> None:
    """PathPolicy rejects metadata that cannot fill the title placeholder."""
    metadata = TrackMetadata(artist=ALBUM_ARTIST, album=ALBUM)

    with pytest.raises(ValueError, match=MISSING_TITLE_MESSAGE):
        PathPolicy(PathPolicyConfig()).canonical_path(metadata, FILE_EXTENSION)


def test_metadata_fingerprint_changes_when_metadata_changes() -> None:
    """Metadata fingerprints are stable for equal metadata and change for tag changes."""
    metadata = TrackMetadata(title=TITLE, artist=ALBUM_ARTIST, album=ALBUM)
    changed_metadata = TrackMetadata(title=f"{TITLE} Remix", artist=ALBUM_ARTIST, album=ALBUM)

    assert calculate_metadata_fingerprint(metadata) == calculate_metadata_fingerprint(metadata)
    assert calculate_metadata_fingerprint(metadata) != calculate_metadata_fingerprint(changed_metadata)


def test_content_fingerprint_changes_when_content_changes() -> None:
    """Content fingerprints are stable for equal bytes and change for different bytes."""
    assert calculate_content_fingerprint(CONTENT) == calculate_content_fingerprint(CONTENT)
    assert calculate_content_fingerprint(CONTENT) != calculate_content_fingerprint(DIFFERENT_CONTENT)


def test_collision_policy_blocks_existing_target() -> None:
    """CollisionPolicy blocks the extension-included canonical target."""
    target_path = PathPolicy(PathPolicyConfig()).canonical_path(_track_metadata(), FILE_EXTENSION)

    decision = CollisionPolicy().decide(target_path, [OCCUPIED_PATH])

    assert decision.kind == CollisionDecisionKind.BLOCKED
    assert decision.reason == PlanActionReason.TARGET_EXISTS


def test_duplicate_policy_skips_duplicate_hash() -> None:
    """DuplicatePolicy returns a skip decision for an already known content hash."""
    content_hash = calculate_content_fingerprint(CONTENT)

    decision = DuplicatePolicy().decide(content_hash, [content_hash])

    assert decision.kind == DuplicateDecisionKind.SKIP
    assert decision.reason == PlanActionReason.DUPLICATE_HASH


def _track_metadata() -> TrackMetadata:
    return TrackMetadata(
        title=TITLE,
        artist=ALBUM_ARTIST,
        album=ALBUM,
        album_artist=ALBUM_ARTIST,
        genre=GENRE,
        year=YEAR,
        track_number=TRACK_NUMBER,
        disc_number=DISC_NUMBER,
    )
