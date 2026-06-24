"""
Summary: Tests TOML-backed config persistence.
Why: Verifies Phase 4 settings storage without touching the user home.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

import pytest

from omym2.adapters.config.toml_config_store import TomlConfigStore, dump_config_toml, load_config_text
from omym2.config import CONFIG_FILE_ENCODING
from omym2.domain.models.app_config import (
    INVALID_MAX_FILENAME_LENGTH_MESSAGE,
    AppConfig,
    PathsConfig,
    UiConfig,
)
from omym2.features.common_ports import ConfigStoreValidationError

if TYPE_CHECKING:
    from pathlib import Path

CONFIG_FILE_NAME = "config.toml"
INCOMING_PATH = "/music/incoming"
INVALID_MAX_FILENAME_LENGTH = 0
LIBRARY_PATH = "/music/library"
UI_THEME_DARK = "dark"


def test_toml_config_store_loads_default_when_config_missing(tmp_path: Path) -> None:
    """Missing config resolves to AppConfig defaults without creating a file."""
    config_path = tmp_path / CONFIG_FILE_NAME

    config = TomlConfigStore(config_path).load()

    assert config == AppConfig()
    assert not config_path.exists()


def test_toml_config_store_saves_and_loads_config(tmp_path: Path) -> None:
    """Saved TOML round-trips through the config adapter."""
    config_path = tmp_path / "nested" / CONFIG_FILE_NAME
    store = TomlConfigStore(config_path)
    config = AppConfig(
        paths=PathsConfig(library=LIBRARY_PATH, incoming=INCOMING_PATH),
        ui=UiConfig(theme=UI_THEME_DARK),
    )

    store.save(config)

    assert config_path.is_file()
    assert store.load() == config


def test_toml_config_text_round_trips_default_config() -> None:
    """The deterministic TOML serializer produces loadable config text."""
    config = AppConfig()

    assert load_config_text(dump_config_toml(config)) == config


def test_toml_config_store_validation_fails_invalid_path_policy(tmp_path: Path) -> None:
    """Adapter validation reports domain path policy errors through ConfigStore."""
    config_path = tmp_path / CONFIG_FILE_NAME
    _ = config_path.write_text(
        "\n".join(
            (
                "version = 1",
                "",
                "[path_policy]",
                f"max_filename_length = {INVALID_MAX_FILENAME_LENGTH}",
            )
        ),
        encoding=CONFIG_FILE_ENCODING,
    )

    with pytest.raises(ConfigStoreValidationError, match=INVALID_MAX_FILENAME_LENGTH_MESSAGE):
        _ = TomlConfigStore(config_path).load()


def test_toml_config_store_validation_fails_invalid_toml(tmp_path: Path) -> None:
    """Malformed TOML is reported as a config validation error."""
    config_path = tmp_path / CONFIG_FILE_NAME
    _ = config_path.write_text("version = ", encoding=CONFIG_FILE_ENCODING)

    with pytest.raises(ConfigStoreValidationError, match="Invalid TOML"):
        _ = TomlConfigStore(config_path).load()
