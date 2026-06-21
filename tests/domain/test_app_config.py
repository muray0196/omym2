"""
Summary: Tests application config domain models.
Why: Ensures defaults match the documented initial configuration shape.
"""

from __future__ import annotations

import pytest

from omym2.config import (
    CONFIG_VERSION,
    DEFAULT_PATH_POLICY_TEMPLATE,
    DEFAULT_UNKNOWN_ALBUM,
    DEFAULT_UNKNOWN_ARTIST,
)
from omym2.domain.models.app_config import (
    INVALID_CONFIG_VERSION_MESSAGE,
    INVALID_MAX_FILENAME_LENGTH_MESSAGE,
    INVALID_PATH_POLICY_TEMPLATE_EXTENSION_MESSAGE,
    AppConfig,
    PathPolicyConfig,
)

INVALID_CONFIG_VERSION = CONFIG_VERSION + 1
INVALID_MAX_FILENAME_LENGTH = 0
PATH_POLICY_TEMPLATE_WITHOUT_EXTENSION = "{album_artist}/{title}"
PATH_POLICY_TEMPLATE_WITH_LITERAL_EXTENSION = "{album_artist}/{title}.mp3"


def test_config_loads_default() -> None:
    """Default AppConfig mirrors the documented initial config policy."""
    config = AppConfig()

    assert config.version == CONFIG_VERSION
    assert config.path_policy.template == DEFAULT_PATH_POLICY_TEMPLATE
    assert config.path_policy.unknown_artist == DEFAULT_UNKNOWN_ARTIST
    assert config.path_policy.unknown_album == DEFAULT_UNKNOWN_ALBUM


def test_config_validation_fails_invalid_version() -> None:
    """Unknown config versions are rejected by the domain config model."""
    with pytest.raises(ValueError, match=INVALID_CONFIG_VERSION_MESSAGE):
        AppConfig(version=INVALID_CONFIG_VERSION)


def test_config_validation_fails_invalid_path_policy() -> None:
    """PathPolicyConfig rejects max filename lengths that cannot produce paths."""
    with pytest.raises(ValueError, match=INVALID_MAX_FILENAME_LENGTH_MESSAGE):
        PathPolicyConfig(max_filename_length=INVALID_MAX_FILENAME_LENGTH)


def test_path_policy_config_rejects_template_without_source_extension() -> None:
    """PathPolicyConfig blocks templates that would drop the source extension."""
    with pytest.raises(ValueError, match=INVALID_PATH_POLICY_TEMPLATE_EXTENSION_MESSAGE):
        PathPolicyConfig(template=PATH_POLICY_TEMPLATE_WITHOUT_EXTENSION)


def test_path_policy_config_rejects_template_with_literal_extension() -> None:
    """PathPolicyConfig blocks templates that would replace the source extension."""
    with pytest.raises(ValueError, match=INVALID_PATH_POLICY_TEMPLATE_EXTENSION_MESSAGE):
        PathPolicyConfig(template=PATH_POLICY_TEMPLATE_WITH_LITERAL_EXTENSION)
