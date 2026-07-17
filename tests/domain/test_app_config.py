"""
Summary: Tests application config domain models.
Why: Ensures defaults match the documented initial configuration shape.
"""

from __future__ import annotations

import pytest

from omym2.config import (
    ALBUM_YEAR_RESOLUTION_OLDEST,
    CONFIG_VERSION,
    DEFAULT_ALBUM_YEAR_RESOLUTION,
    DEFAULT_COMPANIONS_ENABLED,
    DEFAULT_HASHING_READ_CHUNK_SIZE_BYTES,
    DEFAULT_LOGGING_LEVEL,
    DEFAULT_LOGGING_RETENTION_FILES,
    DEFAULT_LOGGING_ROTATION_MAX_BYTES,
    DEFAULT_MUSICBRAINZ_APPLICATION_NAME,
    DEFAULT_MUSICBRAINZ_CACHE_POLICY,
    DEFAULT_MUSICBRAINZ_CONTACT,
    DEFAULT_MUSICBRAINZ_RATE_LIMIT_SECONDS,
    DEFAULT_MUSICBRAINZ_RETRY_LIMIT,
    DEFAULT_MUSICBRAINZ_TIMEOUT_SECONDS,
    DEFAULT_PATH_POLICY_DISC_NUMBER_CONDITION,
    DEFAULT_PATH_POLICY_DISC_NUMBER_STYLE,
    DEFAULT_PATH_POLICY_TEMPLATE,
    DEFAULT_UNKNOWN_ALBUM,
    DEFAULT_UNKNOWN_ARTIST,
    DEFAULT_UNPROCESSED_DIRECTORY,
    DEFAULT_UNPROCESSED_ENABLED,
    DEFAULT_UNPROCESSED_RESULT_PREVIEW_LIMIT,
    UNPROCESSED_RESULT_PREVIEW_LIMIT_MAX,
    UNPROCESSED_RESULT_PREVIEW_LIMIT_MIN,
)
from omym2.domain.models.app_config import (
    INVALID_ARTIST_ID_FALLBACK_MESSAGE,
    INVALID_CONFIG_VERSION_MESSAGE,
    INVALID_HASHING_READ_CHUNK_SIZE_MESSAGE,
    INVALID_LOGGING_DESTINATION_MESSAGE,
    INVALID_LOGGING_LEVEL_MESSAGE,
    INVALID_LOGGING_RETENTION_FILES_MESSAGE,
    INVALID_LOGGING_ROTATION_MAX_BYTES_MESSAGE,
    INVALID_MAX_FILENAME_LENGTH_MESSAGE,
    INVALID_METADATA_ALBUM_YEAR_RESOLUTION_MESSAGE,
    INVALID_MUSICBRAINZ_APPLICATION_NAME_MESSAGE,
    INVALID_MUSICBRAINZ_CACHE_POLICY_MESSAGE,
    INVALID_MUSICBRAINZ_CONTACT_MESSAGE,
    INVALID_MUSICBRAINZ_RATE_LIMIT_MESSAGE,
    INVALID_MUSICBRAINZ_RETRY_LIMIT_MESSAGE,
    INVALID_MUSICBRAINZ_TIMEOUT_MESSAGE,
    INVALID_PATH_POLICY_DISC_NUMBER_CONDITION_MESSAGE,
    INVALID_PATH_POLICY_DISC_NUMBER_STYLE_MESSAGE,
    INVALID_PATH_POLICY_TEMPLATE_EXTENSION_MESSAGE,
    INVALID_PATH_POLICY_TEMPLATE_PLACEHOLDER_MESSAGE,
    INVALID_PATH_POLICY_UNKNOWN_ALBUM_MESSAGE,
    INVALID_PATH_POLICY_UNKNOWN_ARTIST_MESSAGE,
    INVALID_UNPROCESSED_DIRECTORY_MESSAGE,
    INVALID_UNPROCESSED_RESULT_PREVIEW_LIMIT_MESSAGE,
    AppConfig,
    ArtistIdConfig,
    CompanionsConfig,
    HashingConfig,
    LoggingConfig,
    MetadataConfig,
    MusicBrainzConfig,
    PathPolicyConfig,
    UnprocessedConfig,
)

INVALID_CONFIG_VERSION = CONFIG_VERSION + 1
INVALID_MAX_FILENAME_LENGTH = 0
PATH_POLICY_STEM_TEMPLATE = "{album_artist}/{album}/{disc_track} - {title}"
PATH_POLICY_TEMPLATE_WITH_EXTENSION_PLACEHOLDER = "{album_artist}/{album}/{title}.{ext}"
PATH_POLICY_TEMPLATE_WITH_SPLIT_DISC_TRACK = "{album_artist}/{album}/{disc}-{track}_{title}"
PATH_POLICY_TEMPLATE_WITH_LITERAL_EXTENSION = "{album_artist}/{title}.mp3"
PATH_POLICY_TEMPLATE_WITH_UNKNOWN_PLACEHOLDER = "{album_artist}/{bitrate}/{title}"
UNSAFE_ARTIST_ID_FALLBACK_IDS = ("N/A", "..", "", "-LEAD", "TRAIL-", "a b")


def test_config_loads_default() -> None:
    """Default AppConfig mirrors the documented initial config policy."""
    config = AppConfig()

    assert config.version == CONFIG_VERSION
    assert config.metadata.album_year_resolution == DEFAULT_ALBUM_YEAR_RESOLUTION
    assert config.path_policy.template == DEFAULT_PATH_POLICY_TEMPLATE
    assert "{ext}" not in config.path_policy.template
    assert config.path_policy.unknown_artist == DEFAULT_UNKNOWN_ARTIST
    assert config.path_policy.unknown_album == DEFAULT_UNKNOWN_ALBUM
    assert config.path_policy.disc_number_style == DEFAULT_PATH_POLICY_DISC_NUMBER_STYLE
    assert config.path_policy.disc_number_condition == DEFAULT_PATH_POLICY_DISC_NUMBER_CONDITION
    assert config.musicbrainz == MusicBrainzConfig(
        enabled=True,
        application_name=DEFAULT_MUSICBRAINZ_APPLICATION_NAME,
        contact=DEFAULT_MUSICBRAINZ_CONTACT,
        timeout_seconds=DEFAULT_MUSICBRAINZ_TIMEOUT_SECONDS,
        retry_limit=DEFAULT_MUSICBRAINZ_RETRY_LIMIT,
        rate_limit_seconds=DEFAULT_MUSICBRAINZ_RATE_LIMIT_SECONDS,
        cache_policy=DEFAULT_MUSICBRAINZ_CACHE_POLICY,
    )
    assert config.hashing == HashingConfig(read_chunk_size_bytes=DEFAULT_HASHING_READ_CHUNK_SIZE_BYTES)
    assert config.logging == LoggingConfig(
        destination=None,
        level=DEFAULT_LOGGING_LEVEL,
        rotation_max_bytes=DEFAULT_LOGGING_ROTATION_MAX_BYTES,
        retention_files=DEFAULT_LOGGING_RETENTION_FILES,
    )
    assert config.companions == CompanionsConfig(enabled=DEFAULT_COMPANIONS_ENABLED)
    assert config.unprocessed == UnprocessedConfig(
        enabled=DEFAULT_UNPROCESSED_ENABLED,
        directory=DEFAULT_UNPROCESSED_DIRECTORY,
        result_preview_limit=DEFAULT_UNPROCESSED_RESULT_PREVIEW_LIMIT,
    )


@pytest.mark.parametrize(
    ("keywords", "message"),
    [
        ({"application_name": "   "}, INVALID_MUSICBRAINZ_APPLICATION_NAME_MESSAGE),
        ({"contact": ""}, INVALID_MUSICBRAINZ_CONTACT_MESSAGE),
        ({"timeout_seconds": 0.0}, INVALID_MUSICBRAINZ_TIMEOUT_MESSAGE),
        ({"timeout_seconds": float("nan")}, INVALID_MUSICBRAINZ_TIMEOUT_MESSAGE),
        ({"timeout_seconds": float("inf")}, INVALID_MUSICBRAINZ_TIMEOUT_MESSAGE),
        ({"retry_limit": -1}, INVALID_MUSICBRAINZ_RETRY_LIMIT_MESSAGE),
        ({"rate_limit_seconds": 0.5}, INVALID_MUSICBRAINZ_RATE_LIMIT_MESSAGE),
        ({"rate_limit_seconds": float("nan")}, INVALID_MUSICBRAINZ_RATE_LIMIT_MESSAGE),
        ({"rate_limit_seconds": float("inf")}, INVALID_MUSICBRAINZ_RATE_LIMIT_MESSAGE),
        ({"cache_policy": "none"}, INVALID_MUSICBRAINZ_CACHE_POLICY_MESSAGE),
    ],
)
def test_musicbrainz_config_rejects_invalid_controls(keywords: dict[str, object], message: str) -> None:
    """MusicBrainz settings enforce identity, bounds, and the closed cache policy."""
    with pytest.raises(ValueError, match=message):
        _ = MusicBrainzConfig(**keywords)  # pyright: ignore[reportArgumentType]  # Parameterized invalid values.


def test_hashing_config_rejects_nonpositive_chunk_size() -> None:
    """Hashing must advance through a positive read chunk."""
    with pytest.raises(ValueError, match=INVALID_HASHING_READ_CHUNK_SIZE_MESSAGE):
        _ = HashingConfig(read_chunk_size_bytes=0)


@pytest.mark.parametrize(
    "destination",
    ["", ".", "/logs/app.log", "C:/logs/app.log", "../app.log", "logs/../app.log", "./logs/app.log", "logs\\app.log"],
)
def test_logging_config_rejects_non_normalized_or_non_relative_destination(destination: str) -> None:
    """Log destinations cannot escape or depend on platform-specific path syntax."""
    with pytest.raises(ValueError, match=INVALID_LOGGING_DESTINATION_MESSAGE):
        _ = LoggingConfig(destination=destination)


def test_logging_config_accepts_normalized_application_relative_destination() -> None:
    """A normalized logical file path remains anchored by runtime composition."""
    assert LoggingConfig(destination="logs/omym2.log").destination == "logs/omym2.log"


@pytest.mark.parametrize(
    ("keywords", "message"),
    [
        ({"level": "TRACE"}, INVALID_LOGGING_LEVEL_MESSAGE),
        ({"rotation_max_bytes": 0}, INVALID_LOGGING_ROTATION_MAX_BYTES_MESSAGE),
        ({"retention_files": 0}, INVALID_LOGGING_RETENTION_FILES_MESSAGE),
    ],
)
def test_logging_config_rejects_invalid_controls(keywords: dict[str, object], message: str) -> None:
    """Logging severity, rotation, and retention use closed positive controls."""
    with pytest.raises(ValueError, match=message):
        _ = LoggingConfig(**keywords)  # pyright: ignore[reportArgumentType]  # Parameterized invalid values.


@pytest.mark.parametrize(
    "directory",
    [
        "",
        " ",
        ".",
        "..",
        "/absolute",
        "nested/path",
        "nested\\path",
        "C:",
        "name.",
        "name ",
        "CON",
        "con.txt",
        "AUX.json",
        "COM1",
        "LPT9.log",
        "bad:name",
        "bad*name",
        "control\x1fcharacter",
    ],
)
def test_unprocessed_config_rejects_nonportable_directory_component(directory: str) -> None:
    """The destination is one portable relative directory component on every platform."""
    with pytest.raises(ValueError, match=INVALID_UNPROCESSED_DIRECTORY_MESSAGE):
        _ = UnprocessedConfig(directory=directory)


@pytest.mark.parametrize(
    "result_preview_limit",
    [
        UNPROCESSED_RESULT_PREVIEW_LIMIT_MIN - 1,
        UNPROCESSED_RESULT_PREVIEW_LIMIT_MAX + 1,
        True,
        1.5,
    ],
)
def test_unprocessed_config_rejects_noninteger_or_out_of_bounds_preview_limit(
    result_preview_limit: object,
) -> None:
    """Preview size remains an integer inside the centralized inclusive bounds."""
    with pytest.raises(ValueError, match=INVALID_UNPROCESSED_RESULT_PREVIEW_LIMIT_MESSAGE):
        _ = UnprocessedConfig(
            result_preview_limit=result_preview_limit  # pyright: ignore[reportArgumentType]  # Invalid test value.
        )


def test_unprocessed_config_accepts_portable_directory_components_and_preview_bounds() -> None:
    """Unicode, spaces, and both inclusive preview bounds remain valid portable values."""
    assert UnprocessedConfig(directory="Review Later", result_preview_limit=UNPROCESSED_RESULT_PREVIEW_LIMIT_MIN)
    assert UnprocessedConfig(directory="レビュー待ち", result_preview_limit=UNPROCESSED_RESULT_PREVIEW_LIMIT_MAX)


def test_config_validation_fails_invalid_version() -> None:
    """Unknown config versions are rejected by the domain config model."""
    with pytest.raises(ValueError, match=INVALID_CONFIG_VERSION_MESSAGE):
        _ = AppConfig(version=INVALID_CONFIG_VERSION)


def test_config_validation_fails_invalid_path_policy() -> None:
    """PathPolicyConfig rejects max filename lengths that cannot produce paths."""
    with pytest.raises(ValueError, match=INVALID_MAX_FILENAME_LENGTH_MESSAGE):
        _ = PathPolicyConfig(max_filename_length=INVALID_MAX_FILENAME_LENGTH)


def test_metadata_config_accepts_supported_album_year_resolution() -> None:
    """MetadataConfig accepts documented album-year resolution methods."""
    config = MetadataConfig(album_year_resolution=ALBUM_YEAR_RESOLUTION_OLDEST)

    assert config.album_year_resolution == ALBUM_YEAR_RESOLUTION_OLDEST


def test_metadata_config_rejects_unknown_album_year_resolution() -> None:
    """MetadataConfig rejects unsupported album-year resolution methods."""
    with pytest.raises(ValueError, match=INVALID_METADATA_ALBUM_YEAR_RESOLUTION_MESSAGE):
        _ = MetadataConfig(album_year_resolution="median")


def test_path_policy_config_accepts_extensionless_stem_template() -> None:
    """PathPolicyConfig accepts templates that render only a destination stem."""
    config = PathPolicyConfig(template=PATH_POLICY_TEMPLATE_WITH_SPLIT_DISC_TRACK)

    assert config.template == PATH_POLICY_TEMPLATE_WITH_SPLIT_DISC_TRACK


def test_path_policy_config_rejects_extension_placeholder() -> None:
    """PathPolicyConfig rejects the removed extension placeholder."""
    with pytest.raises(ValueError, match=INVALID_PATH_POLICY_TEMPLATE_PLACEHOLDER_MESSAGE):
        _ = PathPolicyConfig(template=PATH_POLICY_TEMPLATE_WITH_EXTENSION_PLACEHOLDER)


def test_path_policy_config_rejects_unknown_placeholder() -> None:
    """PathPolicyConfig rejects placeholders outside the documented stem fields."""
    with pytest.raises(ValueError, match=INVALID_PATH_POLICY_TEMPLATE_PLACEHOLDER_MESSAGE):
        _ = PathPolicyConfig(template=PATH_POLICY_TEMPLATE_WITH_UNKNOWN_PLACEHOLDER)


def test_path_policy_config_rejects_combined_disc_track_placeholder() -> None:
    """PathPolicyConfig keeps disc and track as separate documented fields."""
    with pytest.raises(ValueError, match=INVALID_PATH_POLICY_TEMPLATE_PLACEHOLDER_MESSAGE):
        _ = PathPolicyConfig(template=PATH_POLICY_STEM_TEMPLATE)


def test_path_policy_config_rejects_template_with_literal_extension() -> None:
    """PathPolicyConfig blocks templates that would replace the source extension."""
    with pytest.raises(ValueError, match=INVALID_PATH_POLICY_TEMPLATE_EXTENSION_MESSAGE):
        _ = PathPolicyConfig(template=PATH_POLICY_TEMPLATE_WITH_LITERAL_EXTENSION)


def test_path_policy_config_rejects_empty_unknown_artist_or_album() -> None:
    """PathPolicyConfig rejects blank unknown_artist and unknown_album fallbacks."""
    with pytest.raises(ValueError, match=INVALID_PATH_POLICY_UNKNOWN_ARTIST_MESSAGE):
        _ = PathPolicyConfig(unknown_artist="   ")
    with pytest.raises(ValueError, match=INVALID_PATH_POLICY_UNKNOWN_ALBUM_MESSAGE):
        _ = PathPolicyConfig(unknown_album="")


def test_path_policy_config_rejects_unsupported_disc_settings() -> None:
    """PathPolicyConfig rejects unsupported {disc} style and condition values."""
    with pytest.raises(ValueError, match=INVALID_PATH_POLICY_DISC_NUMBER_STYLE_MESSAGE):
        _ = PathPolicyConfig(disc_number_style="prefixed")
    with pytest.raises(ValueError, match=INVALID_PATH_POLICY_DISC_NUMBER_CONDITION_MESSAGE):
        _ = PathPolicyConfig(disc_number_condition="sometimes")


@pytest.mark.parametrize("fallback_id", UNSAFE_ARTIST_ID_FALLBACK_IDS)
def test_artist_id_config_rejects_unsafe_fallback_id(fallback_id: str) -> None:
    """ArtistIdConfig rejects fallback_id values that are not sanitizer-stable.

    fallback_id can flow into generated IDs and saved entries (see
    generate_artist_id's no-usable-characters branch), so it must satisfy the
    same pattern as entries values rather than only non-emptiness.
    """
    with pytest.raises(ValueError, match=INVALID_ARTIST_ID_FALLBACK_MESSAGE):
        _ = ArtistIdConfig(fallback_id=fallback_id)


def test_artist_id_config_accepts_default_fallback_id() -> None:
    """The documented default fallback_id (NOART) satisfies the entries value pattern."""
    config = ArtistIdConfig()

    assert config.fallback_id == "NOART"
