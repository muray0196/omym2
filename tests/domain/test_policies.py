"""
Summary: Tests pure domain policy services.
Why: Protects canonical paths, fingerprints, collisions, and duplicates.
"""

from __future__ import annotations

import pytest

from omym2.config import DEFAULT_ARTIST_ID_FALLBACK, DEFAULT_ARTIST_ID_MAX_LENGTH
from omym2.domain.models.app_config import ArtistIdConfig, PathPolicyConfig
from omym2.domain.models.plan_action import PlanActionReason
from omym2.domain.models.track_metadata import TrackMetadata
from omym2.domain.services.artist_id import generate_artist_id
from omym2.domain.services.collision_policy import CollisionDecisionKind, CollisionPolicy
from omym2.domain.services.content_fingerprint import calculate_content_fingerprint
from omym2.domain.services.duplicate_policy import DuplicateDecisionKind, DuplicatePolicy
from omym2.domain.services.metadata_fingerprint import calculate_metadata_fingerprint
from omym2.domain.services.path_policy import MISSING_TITLE_MESSAGE, PathPolicy
from omym2.shared.paths import ESCAPING_LIBRARY_PATH_MESSAGE

ALBUM = "Example Album"
ALBUM_ARTIST = "Aimer"
CONTENT = b"content"
DIFFERENT_CONTENT = b"different content"
DISC_NUMBER = 1
EDGE_BUDGET_FINAL_COMPONENT = "S.flac"
EXPECTED_CANONICAL_PATH = "Aimer/2024_Example-Album/1-03_Example-Song.flac"
EXTENSION_BYTES_FILENAME_LENGTH = 5
EXPECTED_STEM_TEMPLATE_PATH = "Aimer/Example-Album/1-03-Example-Song.flac"
EXPECTED_ARTIST_ID_PATH = "AIMR/Example-Song.flac"
FILE_EXTENSION = ".FLAC"
GENRE = "J-Pop"
OCCUPIED_PATH = "Aimer/2024_Example-Album/1-03_Example-Song.flac"
SANITIZED_ARTIST = "Artist-Name"
SANITIZED_UNICODE_PATH = "こんにちは/2024_你好/1-03_Café-Song.flac"
SANITIZED_PATH = "Artist-Name/2024_Example-Album/1-03_Example-Song.flac"
SHORT_BUDGET_FILENAME_LENGTH = 5
SHORT_BUDGET_FINAL_COMPONENT = "SomeT.flac"
SHORT_BUDGET_TITLE = "SomeTitle"
SHORT_FILENAME_LENGTH = 3
TITLE = "Example Song"
TITLE_ONLY_TEMPLATE = "{title}"
TRACK_NUMBER = 3
TRUNCATED_FILENAME_LENGTH = 12
TRUNCATED_FINAL_COMPONENT = "1-03_AAAAAAA.flac"
UNSANITIZED_ARTIST = "Artist:Name"
UNSANITIZED_PATH = "Artist:Name/2024_Example Album/1-03_Example Song.flac"
YEAR = 2024
STEM_TEMPLATE = "{album_artist}/{album}/{disc}-{track} - {title}"
ARTIST_ID_TEMPLATE = "{artist_id}/{title}"
ALBUM_ARTIST_ID_TEMPLATE = "{album}/{artist_id}/{title}"
ALBUM_ARTIST_ID_TEMPLATE_PART_COUNT = 3
UNSAFE_ARTIST_ID_ENTRY = "../../../etc/passwd"


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


def test_path_policy_renders_artist_id_from_saved_config() -> None:
    """PathPolicy resolves artist_id from already-loaded config without I/O."""
    canonical_path = PathPolicy(
        PathPolicyConfig(template=ARTIST_ID_TEMPLATE),
        ArtistIdConfig(entries={ALBUM_ARTIST: "AIMR"}),
    ).canonical_path(_track_metadata(), FILE_EXTENSION)

    assert canonical_path == EXPECTED_ARTIST_ID_PATH


def test_path_policy_generates_artist_id_when_no_saved_entry_exists() -> None:
    """PathPolicy uses the deterministic generator when no artist_id entry is saved."""
    canonical_path = PathPolicy(
        PathPolicyConfig(template=ARTIST_ID_TEMPLATE),
        ArtistIdConfig(entries={}),
    ).canonical_path(_track_metadata(), FILE_EXTENSION)

    expected_artist_id = generate_artist_id(
        ALBUM_ARTIST,
        max_length=DEFAULT_ARTIST_ID_MAX_LENGTH,
        fallback_id=DEFAULT_ARTIST_ID_FALLBACK,
    )
    assert canonical_path == f"{expected_artist_id}/Example-Song.flac"


def test_canonical_path_artist_id_entry_cannot_escape_library_root() -> None:
    """A saved artist_id entry cannot introduce parent-directory path components.

    ArtistIdConfig normally rejects unsafe entry values at construction, so
    this bypasses validation with object.__setattr__ to simulate a future code
    path handing PathPolicy unvalidated config (e.g. a legacy persisted value
    written before entry validation existed).
    """
    metadata = _track_metadata()

    sanitized_artist_ids = ArtistIdConfig(entries={ALBUM_ARTIST: "SAFE"})
    object.__setattr__(sanitized_artist_ids, "entries", {ALBUM_ARTIST: UNSAFE_ARTIST_ID_ENTRY})
    canonical_path = PathPolicy(
        PathPolicyConfig(template=ARTIST_ID_TEMPLATE),
        sanitized_artist_ids,
    ).canonical_path(metadata, FILE_EXTENSION)
    assert ".." not in canonical_path.split("/")

    unsanitized_artist_ids = ArtistIdConfig(entries={ALBUM_ARTIST: "SAFE"})
    object.__setattr__(unsanitized_artist_ids, "entries", {ALBUM_ARTIST: UNSAFE_ARTIST_ID_ENTRY})
    with pytest.raises(ValueError, match=ESCAPING_LIBRARY_PATH_MESSAGE):
        _ = PathPolicy(
            PathPolicyConfig(template=ARTIST_ID_TEMPLATE, sanitize=False),
            unsanitized_artist_ids,
        ).canonical_path(metadata, FILE_EXTENSION)


def test_canonical_path_empty_artist_id_entry_does_not_silently_drop_directory_level() -> None:
    """An empty saved artist_id entry falls back to the generated ID instead of
    collapsing a path directory level.

    Bypasses ArtistIdConfig validation with object.__setattr__ to simulate a
    future code path handing PathPolicy unvalidated config.
    """
    metadata = _track_metadata()
    bypassed_artist_ids = ArtistIdConfig(entries={ALBUM_ARTIST: "SAFE"})
    object.__setattr__(bypassed_artist_ids, "entries", {ALBUM_ARTIST: ""})

    canonical_path = PathPolicy(
        PathPolicyConfig(template=ALBUM_ARTIST_ID_TEMPLATE),
        bypassed_artist_ids,
    ).canonical_path(metadata, FILE_EXTENSION)

    parts = canonical_path.split("/")
    assert len(parts) == ALBUM_ARTIST_ID_TEMPLATE_PART_COUNT
    expected_artist_id = generate_artist_id(
        ALBUM_ARTIST,
        max_length=DEFAULT_ARTIST_ID_MAX_LENGTH,
        fallback_id=DEFAULT_ARTIST_ID_FALLBACK,
    )
    assert parts[1] == expected_artist_id


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


def test_path_policy_sanitizer_preserves_unicode_letters() -> None:
    """Sanitizing path text preserves Japanese, Chinese, and Latin-1 letters."""
    metadata = TrackMetadata(
        title="Café Song",
        artist="こんにちは",
        album="你好",
        year=YEAR,
        track_number=TRACK_NUMBER,
        disc_number=DISC_NUMBER,
    )

    canonical_path = PathPolicy(PathPolicyConfig()).canonical_path(metadata, FILE_EXTENSION)

    assert canonical_path == SANITIZED_UNICODE_PATH


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
    assert final_component == TRUNCATED_FINAL_COMPONENT
    assert len(final_component.removesuffix(".flac")) == TRUNCATED_FILENAME_LENGTH


def test_path_policy_preserves_extension_when_stem_budget_is_shorter_than_extension() -> None:
    """PathPolicy applies max_filename_length to the stem before appending the suffix."""
    metadata = _track_metadata()

    canonical_path = PathPolicy(PathPolicyConfig(max_filename_length=SHORT_FILENAME_LENGTH)).canonical_path(
        metadata,
        FILE_EXTENSION,
    )

    final_component = canonical_path.rsplit("/", maxsplit=1)[-1]
    assert final_component == "1-0.flac"
    assert final_component.endswith(".flac")
    assert final_component.removesuffix(".flac") != ""


def test_unsanitized_final_component_keeps_extension_and_stem_when_budget_is_below_extension() -> None:
    """sanitize=False: a max_filename_length smaller than the extension keeps both intact.

    Extension preservation dominates the length budget: the suffix is never
    truncated or dropped, and the stem keeps at least its first character even
    though the total then necessarily exceeds max_filename_length. Previously
    this edge ate the extension and left an empty component.
    """
    metadata = TrackMetadata(title=SHORT_BUDGET_TITLE)

    canonical_path = PathPolicy(
        PathPolicyConfig(template=TITLE_ONLY_TEMPLATE, sanitize=False, max_filename_length=SHORT_FILENAME_LENGTH)
    ).canonical_path(metadata, FILE_EXTENSION)

    assert canonical_path == EDGE_BUDGET_FINAL_COMPONENT


def test_unsanitized_final_component_keeps_stem_when_budget_equals_extension_bytes() -> None:
    """sanitize=False: a max_filename_length equal to the extension bytes keeps a 1-char stem.

    Previously this boundary returned the bare extension with an empty stem.
    """
    metadata = TrackMetadata(title=SHORT_BUDGET_TITLE)

    canonical_path = PathPolicy(
        PathPolicyConfig(
            template=TITLE_ONLY_TEMPLATE,
            sanitize=False,
            max_filename_length=EXTENSION_BYTES_FILENAME_LENGTH,
        )
    ).canonical_path(metadata, FILE_EXTENSION)

    assert canonical_path == EDGE_BUDGET_FINAL_COMPONENT


def test_canonical_path_currently_budgets_max_length_against_stem_only_when_sanitized() -> None:
    """Characterizes current behavior: max_filename_length is applied to the
    sanitized stem before the extension suffix is appended back on, so the
    final component's total length can exceed max_filename_length. This is
    the current contract; it is not validated against the full byte budget.
    """
    metadata = TrackMetadata(title=SHORT_BUDGET_TITLE)

    canonical_path = PathPolicy(
        PathPolicyConfig(template=TITLE_ONLY_TEMPLATE, max_filename_length=SHORT_BUDGET_FILENAME_LENGTH)
    ).canonical_path(metadata, FILE_EXTENSION)

    assert canonical_path == SHORT_BUDGET_FINAL_COMPONENT
    assert len(SHORT_BUDGET_FINAL_COMPONENT) > SHORT_BUDGET_FILENAME_LENGTH


def test_path_policy_falls_back_when_metadata_component_sanitizes_empty() -> None:
    """Non-empty metadata components that sanitize away still produce relative paths."""
    metadata = TrackMetadata(
        title=TITLE,
        artist="!!!",
        album="!!!",
        year=YEAR,
        track_number=TRACK_NUMBER,
        disc_number=DISC_NUMBER,
    )

    canonical_path = PathPolicy(PathPolicyConfig()).canonical_path(metadata, FILE_EXTENSION)

    assert canonical_path == "_/2024__/1-03_Example-Song.flac"


def test_path_policy_blocks_missing_title() -> None:
    """PathPolicy rejects metadata that cannot fill the title placeholder."""
    metadata = TrackMetadata(artist=ALBUM_ARTIST, album=ALBUM)

    with pytest.raises(ValueError, match=MISSING_TITLE_MESSAGE):
        _ = PathPolicy(PathPolicyConfig()).canonical_path(metadata, FILE_EXTENSION)


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


def test_collision_policy_blocks_intra_batch_duplicate_target() -> None:
    """CollisionPolicy blocks a target claimed by more than one batch source,
    even when no occupied path matches it yet."""
    target_path = PathPolicy(PathPolicyConfig()).canonical_path(_track_metadata(), FILE_EXTENSION)

    decision = CollisionPolicy().decide(target_path, [], batch_target_count=2)

    assert decision.kind == CollisionDecisionKind.BLOCKED
    assert decision.reason == PlanActionReason.TARGET_EXISTS


def test_collision_policy_allows_single_batch_source_target() -> None:
    """CollisionPolicy does not block a target with exactly one batch source
    that is not otherwise occupied."""
    target_path = PathPolicy(PathPolicyConfig()).canonical_path(_track_metadata(), FILE_EXTENSION)

    decision = CollisionPolicy().decide(target_path, [], batch_target_count=1)

    assert decision.kind == CollisionDecisionKind.AVAILABLE


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
