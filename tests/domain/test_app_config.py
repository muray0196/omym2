"""
Summary: Tests application config domain models.
Why: Ensures defaults match the documented initial configuration shape.
"""

from __future__ import annotations

from typing import cast

import pytest

from omym2.config import (
    ALBUM_YEAR_RESOLUTION_OLDEST,
    CONFIG_VERSION,
    DEFAULT_ALBUM_YEAR_RESOLUTION,
    DEFAULT_PATH_POLICY_DISC_NUMBER_CONDITION,
    DEFAULT_PATH_POLICY_DISC_NUMBER_STYLE,
    DEFAULT_PATH_POLICY_TEMPLATE,
    DEFAULT_UNKNOWN_ALBUM,
    DEFAULT_UNKNOWN_ARTIST,
)
from omym2.domain.models.app_config import (
    INVALID_ARTIST_ID_ENTRY_VALUE_MESSAGE,
    INVALID_ARTIST_ID_FALLBACK_MESSAGE,
    INVALID_ARTIST_NAME_PREFERENCE_MESSAGE,
    INVALID_CONFIG_VERSION_MESSAGE,
    INVALID_MAX_FILENAME_LENGTH_MESSAGE,
    INVALID_METADATA_ALBUM_YEAR_RESOLUTION_MESSAGE,
    INVALID_PATH_POLICY_DISC_NUMBER_CONDITION_MESSAGE,
    INVALID_PATH_POLICY_DISC_NUMBER_STYLE_MESSAGE,
    INVALID_PATH_POLICY_TEMPLATE_EXTENSION_MESSAGE,
    INVALID_PATH_POLICY_TEMPLATE_PLACEHOLDER_MESSAGE,
    INVALID_PATH_POLICY_UNKNOWN_ALBUM_MESSAGE,
    INVALID_PATH_POLICY_UNKNOWN_ARTIST_MESSAGE,
    AppConfig,
    ArtistIdConfig,
    ArtistNameConfig,
    MetadataConfig,
    PathPolicyConfig,
)

INVALID_CONFIG_VERSION = CONFIG_VERSION + 1
INVALID_MAX_FILENAME_LENGTH = 0
PATH_POLICY_STEM_TEMPLATE = "{album_artist}/{album}/{disc_track} - {title}"
PATH_POLICY_TEMPLATE_WITH_EXTENSION_PLACEHOLDER = "{album_artist}/{album}/{title}.{ext}"
PATH_POLICY_TEMPLATE_WITH_SPLIT_DISC_TRACK = "{album_artist}/{album}/{disc}-{track}_{title}"
PATH_POLICY_TEMPLATE_WITH_LITERAL_EXTENSION = "{album_artist}/{title}.mp3"
PATH_POLICY_TEMPLATE_WITH_UNKNOWN_PLACEHOLDER = "{album_artist}/{bitrate}/{title}"
UNSAFE_ARTIST_ID_ENTRY_VALUES = ("a/b", "..", "", "../escape", "a\\b")
GENERATED_STYLE_ARTIST_ID_ENTRY_VALUES = ("SOMEID", "NOART", "artist_id-1")
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


def test_config_default_artist_id_entries_are_immutable_and_per_instance() -> None:
    """Default AppConfig entries cannot be mutated or shared across instances."""
    first_config = AppConfig()
    second_config = AppConfig()

    first_entries = first_config.artist_ids.entries
    assert first_entries is not None
    with pytest.raises(TypeError):
        cast("dict[str, str]", first_entries)["Aimer"] = "AIMR"

    assert first_config.artist_ids == ArtistIdConfig()
    assert second_config.artist_ids == ArtistIdConfig()


def test_config_default_artist_name_preferences_are_immutable_and_per_instance() -> None:
    """Default display-name preferences cannot mutate cached or separate configs."""
    first_config = AppConfig()
    second_config = AppConfig()

    first_preferences = first_config.artist_names.preferences
    assert first_preferences is not None
    with pytest.raises(TypeError):
        cast("dict[str, str]", first_preferences)["宇多田ヒカル"] = "Hikaru Utada"

    assert first_config.artist_names == ArtistNameConfig()
    assert second_config.artist_names == ArtistNameConfig()


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


@pytest.mark.parametrize("entry_value", UNSAFE_ARTIST_ID_ENTRY_VALUES)
def test_artist_id_config_rejects_unsafe_entry_values(entry_value: str) -> None:
    """ArtistIdConfig rejects saved entry values that are not sanitizer-stable."""
    with pytest.raises(ValueError, match=INVALID_ARTIST_ID_ENTRY_VALUE_MESSAGE):
        _ = ArtistIdConfig(entries={"X": entry_value})


@pytest.mark.parametrize("entry_value", GENERATED_STYLE_ARTIST_ID_ENTRY_VALUES)
def test_artist_id_config_accepts_generated_style_values(entry_value: str) -> None:
    """ArtistIdConfig accepts saved entry values matching generator/config style output."""
    config = ArtistIdConfig(entries={"X": entry_value})

    assert config.entries == {"X": entry_value}


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


@pytest.mark.parametrize(
    ("source_name", "display_name"),
    [("", "Hikaru Utada"), ("   ", "Hikaru Utada"), ("宇多田ヒカル", ""), ("宇多田ヒカル", "   ")],
)
def test_artist_name_config_rejects_blank_preferences(source_name: str, display_name: str) -> None:
    """ArtistNameConfig rejects preference keys and values with no visible text."""
    with pytest.raises(ValueError, match=INVALID_ARTIST_NAME_PREFERENCE_MESSAGE):
        _ = ArtistNameConfig(preferences={source_name: display_name})
