"""
Summary: Tests pure domain policy services.
Why: Protects canonical paths, fingerprints, collisions, and duplicates.
"""

from __future__ import annotations

import pytest

from omym2.config import (
    DEFAULT_ARTIST_ID_FALLBACK,
    DEFAULT_ARTIST_ID_MAX_LENGTH,
    PATH_POLICY_DISC_NUMBER_CONDITION_MULTIPLE_DISCS,
    PATH_POLICY_DISC_NUMBER_STYLE_D_PREFIXED,
)
from omym2.domain.models.app_config import ArtistIdConfig, PathPolicyConfig
from omym2.domain.models.plan_action import PlanActionReason
from omym2.domain.models.track_metadata import TrackMetadata
from omym2.domain.services.artist_id import generate_artist_id
from omym2.domain.services.artist_name import ArtistNameProjection
from omym2.domain.services.collision_policy import CollisionDecisionKind, CollisionPolicy, OccupiedPaths
from omym2.domain.services.metadata_fingerprint import calculate_metadata_fingerprint
from omym2.domain.services.path_policy import MISSING_TITLE_MESSAGE, PathPolicy

ALBUM = "Example Album"
ALBUM_ARTIST = "Aimer"
DISC_NUMBER = 1
EDGE_BUDGET_FINAL_COMPONENT = "S.flac"
EXPECTED_CANONICAL_PATH = "Aimer/2024_Example-Album/1-03_Example-Song.flac"
EXPECTED_D_PREFIXED_PATH = "Aimer/2024_Example-Album/D1-03_Example-Song.flac"
EXPECTED_MULTI_DISC_SUPPRESSED_PATH = "Aimer/2024_Example-Album/03_Example-Song.flac"
EXTENSION_BYTES_FILENAME_LENGTH = 5
EXPECTED_STEM_TEMPLATE_PATH = "Aimer/Example-Album/1-03-Example-Song.flac"
EXPECTED_ARTIST_ID_PATH = "AIMR/Example-Song.flac"
FILE_EXTENSION = ".FLAC"
GENRE = "J-Pop"
NON_CANONICAL_OCCUPIED_PATH = "./Aimer/2024_Example-Album/1-03_Example-Song.flac"
OCCUPIED_PATH = "Aimer/2024_Example-Album/1-03_Example-Song.flac"
SANITIZED_ARTIST = "Artist-Name"
SANITIZED_UNICODE_PATH = "こんにちは/2024_你好/1-03_Café-Song.flac"
SANITIZED_PATH = "Artist-Name/2024_Example-Album/1-03_Example-Song.flac"
SHORT_BUDGET_FILENAME_LENGTH = 5
SHORT_BUDGET_FINAL_COMPONENT = "S.flac"
SHORT_BUDGET_TITLE = "SomeTitle"
SHORT_FILENAME_LENGTH = 3
TITLE = "Example Song"
TITLE_ONLY_TEMPLATE = "{title}"
TRACK_NUMBER = 3
TRUNCATED_FILENAME_LENGTH = 12
TRUNCATED_FINAL_COMPONENT = "1-03_AA.flac"
UNOCCUPIED_TARGET_PATH = "Other/2024_Other-Album/1-01_Other-Song.flac"
UNSANITIZED_ARTIST = "Artist:Name"
UNSANITIZED_PATH = "Artist:Name/2024_Example Album/1-03_Example Song.flac"
YEAR = 2024
STEM_TEMPLATE = "{album_artist}/{album}/{disc}-{track} - {title}"
ARTIST_ID_TEMPLATE = "{artist_id}/{title}"
ARTIST_ONLY_TEMPLATE = "{artist}"
ALBUM_ARTIST_ID_TEMPLATE = "{album}/{artist_id}/{title}"
ALBUM_ARTIST_ID_TEMPLATE_PART_COUNT = 3
DISPLAY_ARTIST_ID_TEMPLATE = "{album_artist}/{artist_id}/{title}"
UNUSED_ARTIST_ID_GENERATOR_MESSAGE = "unused artist ID generator was called"


def test_path_policy_generates_relative_path_without_hash_suffix() -> None:
    """PathPolicy uses metadata and extension to create a canonical relative path."""
    metadata = _track_metadata()

    canonical_path = PathPolicy(PathPolicyConfig()).canonical_path(metadata, FILE_EXTENSION)

    assert canonical_path == EXPECTED_CANONICAL_PATH


def test_path_policy_renders_d_prefixed_disc_number() -> None:
    """PathPolicy can render {disc} with a D prefix."""
    metadata = _track_metadata()

    canonical_path = PathPolicy(
        PathPolicyConfig(disc_number_style=PATH_POLICY_DISC_NUMBER_STYLE_D_PREFIXED)
    ).canonical_path(metadata, FILE_EXTENSION)

    assert canonical_path == EXPECTED_D_PREFIXED_PATH


def test_path_policy_suppresses_single_disc_album_disc_number() -> None:
    """PathPolicy can suppress {disc} when context does not infer multi-disc."""
    metadata = _track_metadata()

    canonical_path = PathPolicy(
        PathPolicyConfig(disc_number_condition=PATH_POLICY_DISC_NUMBER_CONDITION_MULTIPLE_DISCS)
    ).canonical_path(metadata, FILE_EXTENSION, album_disc_total=1)

    assert canonical_path == EXPECTED_MULTI_DISC_SUPPRESSED_PATH


def test_path_policy_renders_disc_number_for_multi_disc_album_context() -> None:
    """PathPolicy keeps {disc} when context infers a multi-disc album."""
    metadata = _track_metadata()

    canonical_path = PathPolicy(
        PathPolicyConfig(
            disc_number_style=PATH_POLICY_DISC_NUMBER_STYLE_D_PREFIXED,
            disc_number_condition=PATH_POLICY_DISC_NUMBER_CONDITION_MULTIPLE_DISCS,
        )
    ).canonical_path(metadata, FILE_EXTENSION, album_disc_total=2)

    assert canonical_path == EXPECTED_D_PREFIXED_PATH


def test_path_policy_renders_disc_number_from_metadata_disc_total_without_album_context() -> None:
    """PathPolicy treats a single file's disc_total tag as multi-disc context."""
    metadata = _track_metadata_with_disc_total(2)

    canonical_path = PathPolicy(
        PathPolicyConfig(
            disc_number_style=PATH_POLICY_DISC_NUMBER_STYLE_D_PREFIXED,
            disc_number_condition=PATH_POLICY_DISC_NUMBER_CONDITION_MULTIPLE_DISCS,
        )
    ).canonical_path(metadata, FILE_EXTENSION)

    assert canonical_path == EXPECTED_D_PREFIXED_PATH


def test_path_policy_appends_source_extension_to_rendered_stem() -> None:
    """PathPolicy renders a stem template and appends the lowercase source suffix."""
    canonical_path = PathPolicy(PathPolicyConfig(template=STEM_TEMPLATE)).canonical_path(
        _track_metadata(), FILE_EXTENSION
    )

    assert canonical_path == EXPECTED_STEM_TEMPLATE_PATH
    assert canonical_path.endswith(".flac")
    assert ".flac.flac" not in canonical_path


def test_path_policy_generates_artist_id_automatically() -> None:
    """PathPolicy uses the deterministic internal generator when the placeholder is needed."""
    canonical_path = PathPolicy(
        PathPolicyConfig(template=ARTIST_ID_TEMPLATE),
        ArtistIdConfig(),
    ).canonical_path(_track_metadata(), FILE_EXTENSION)

    expected_artist_id = generate_artist_id(
        ALBUM_ARTIST,
        max_length=DEFAULT_ARTIST_ID_MAX_LENGTH,
        fallback_id=DEFAULT_ARTIST_ID_FALLBACK,
    )
    assert canonical_path == f"{expected_artist_id}/Example-Song.flac"


def test_path_policy_generates_artist_id_from_projected_name() -> None:
    """Resolved Latin text changes generator input while the raw source remains the cache key."""
    source_artist = "エメ"
    display_artist = "Aimer"
    metadata = TrackMetadata(title=TITLE, artist=source_artist, album_artist=source_artist)
    artist_names = ArtistNameProjection(artist=display_artist, album_artist=display_artist)

    canonical_path = PathPolicy(
        PathPolicyConfig(template=DISPLAY_ARTIST_ID_TEMPLATE),
        ArtistIdConfig(),
    ).canonical_path(metadata, FILE_EXTENSION, artist_names=artist_names)

    assert canonical_path == "Aimer/AIMER/Example-Song.flac"


def test_path_policy_does_not_generate_artist_id_when_template_does_not_use_it(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Templates without artist_id avoid work that cannot affect the rendered path."""

    def fail_if_called(source_artist: str, *, max_length: int, fallback_id: str) -> str:
        del source_artist, max_length, fallback_id
        raise AssertionError(UNUSED_ARTIST_ID_GENERATOR_MESSAGE)

    monkeypatch.setattr("omym2.domain.services.path_policy.generate_artist_id", fail_if_called)

    canonical_path = PathPolicy(PathPolicyConfig()).canonical_path(_track_metadata(), FILE_EXTENSION)

    assert canonical_path == EXPECTED_CANONICAL_PATH


def test_path_policy_memoizes_generated_artist_id_per_instance(monkeypatch: pytest.MonkeyPatch) -> None:
    """Repeated tracks by one artist reuse its generated ID within one planning policy."""
    generated_artists: list[str] = []

    def record_generation(source_artist: str, *, max_length: int, fallback_id: str) -> str:
        del max_length, fallback_id
        generated_artists.append(source_artist)
        return "AIMR"

    monkeypatch.setattr("omym2.domain.services.path_policy.generate_artist_id", record_generation)
    policy = PathPolicy(PathPolicyConfig(template=ARTIST_ID_TEMPLATE), ArtistIdConfig())

    first_path = policy.canonical_path(_track_metadata(), FILE_EXTENSION)
    second_path = policy.canonical_path(
        TrackMetadata(title="Second Song", artist=ALBUM_ARTIST),
        FILE_EXTENSION,
    )

    assert first_path == EXPECTED_ARTIST_ID_PATH
    assert second_path == "AIMR/Second-Song.flac"
    assert generated_artists == [ALBUM_ARTIST]


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
    assert len(final_component) == TRUNCATED_FILENAME_LENGTH


def test_path_policy_preserves_extension_when_stem_budget_is_shorter_than_extension() -> None:
    """PathPolicy budgets max_filename_length against the total component, extension included.

    Extension preservation dominates the budget: the suffix is never truncated
    or dropped, and the stem keeps at least its first character even when
    max_filename_length is smaller than the extension bytes, so the total then
    necessarily exceeds max_filename_length.
    """
    metadata = _track_metadata()

    canonical_path = PathPolicy(PathPolicyConfig(max_filename_length=SHORT_FILENAME_LENGTH)).canonical_path(
        metadata,
        FILE_EXTENSION,
    )

    final_component = canonical_path.rsplit("/", maxsplit=1)[-1]
    assert final_component == "1.flac"
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


def test_canonical_path_budgets_max_length_including_extension() -> None:
    """max_filename_length budgets the sanitized final component's TOTAL length,
    stem and extension together, matching the sanitize=False branch. With a
    budget of 5 and a 5-byte extension the stem keeps its 1-char floor, so the
    result is "S.flac" rather than the old stem-only-budget "SomeT.flac".
    """
    metadata = TrackMetadata(title=SHORT_BUDGET_TITLE)

    canonical_path = PathPolicy(
        PathPolicyConfig(template=TITLE_ONLY_TEMPLATE, max_filename_length=SHORT_BUDGET_FILENAME_LENGTH)
    ).canonical_path(metadata, FILE_EXTENSION)

    assert canonical_path == SHORT_BUDGET_FINAL_COMPONENT


def test_sanitized_final_component_keeps_extension_and_stem_when_budget_is_below_extension() -> None:
    """sanitize=True: a max_filename_length smaller than the extension keeps both intact.

    Mirrors the sanitize=False edge: the suffix is never truncated or dropped
    and the stem keeps at least its first character, so the total necessarily
    exceeds max_filename_length for such degenerate budgets.
    """
    metadata = TrackMetadata(title=SHORT_BUDGET_TITLE)

    canonical_path = PathPolicy(
        PathPolicyConfig(template=TITLE_ONLY_TEMPLATE, max_filename_length=SHORT_FILENAME_LENGTH)
    ).canonical_path(metadata, FILE_EXTENSION)

    assert canonical_path == EDGE_BUDGET_FINAL_COMPONENT


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


def test_path_policy_keeps_missing_title_invariant_when_template_omits_title() -> None:
    """Template-aware rendering does not weaken the existing title requirement."""
    metadata = TrackMetadata(artist=ALBUM_ARTIST, album=ALBUM)

    with pytest.raises(ValueError, match=MISSING_TITLE_MESSAGE):
        _ = PathPolicy(PathPolicyConfig(template=ARTIST_ONLY_TEMPLATE)).canonical_path(metadata, FILE_EXTENSION)


def test_metadata_fingerprint_changes_when_metadata_changes() -> None:
    """Metadata fingerprints are stable for equal metadata and change for tag changes."""
    metadata = TrackMetadata(title=TITLE, artist=ALBUM_ARTIST, album=ALBUM)
    changed_metadata = TrackMetadata(title=f"{TITLE} Remix", artist=ALBUM_ARTIST, album=ALBUM)

    assert calculate_metadata_fingerprint(metadata) == calculate_metadata_fingerprint(metadata)
    assert calculate_metadata_fingerprint(metadata) != calculate_metadata_fingerprint(changed_metadata)


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


def test_collision_policy_occupied_paths_matches_raw_iterable_decisions() -> None:
    """OccupiedPaths.from_paths normalizes non-canonical inputs at construction
    and yields the same block and allow decisions as the raw iterable."""
    target_path = PathPolicy(PathPolicyConfig()).canonical_path(_track_metadata(), FILE_EXTENSION)
    raw_occupied = [NON_CANONICAL_OCCUPIED_PATH]
    occupied_paths = OccupiedPaths.from_paths(raw_occupied)

    blocked_decision = CollisionPolicy().decide(target_path, occupied_paths)
    available_decision = CollisionPolicy().decide(UNOCCUPIED_TARGET_PATH, occupied_paths)

    assert occupied_paths.normalized_paths == frozenset({OCCUPIED_PATH})
    assert blocked_decision == CollisionPolicy().decide(target_path, raw_occupied)
    assert blocked_decision.kind == CollisionDecisionKind.BLOCKED
    assert blocked_decision.reason == PlanActionReason.TARGET_EXISTS
    assert available_decision == CollisionPolicy().decide(UNOCCUPIED_TARGET_PATH, raw_occupied)
    assert available_decision.kind == CollisionDecisionKind.AVAILABLE


def _track_metadata() -> TrackMetadata:
    return _track_metadata_with_disc_total(None)


def _track_metadata_with_disc_total(disc_total: int | None) -> TrackMetadata:
    return TrackMetadata(
        title=TITLE,
        artist=ALBUM_ARTIST,
        album=ALBUM,
        album_artist=ALBUM_ARTIST,
        genre=GENRE,
        year=YEAR,
        track_number=TRACK_NUMBER,
        disc_number=DISC_NUMBER,
        disc_total=disc_total,
    )
