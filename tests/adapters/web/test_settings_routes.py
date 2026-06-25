"""
Summary: Tests Phase 12 Web settings routes.
Why: Verifies settings display, validation, diff, preview, and saving through HTTP.
"""

from __future__ import annotations

import re
from typing import TYPE_CHECKING

from fastapi.testclient import TestClient

from omym2.adapters.config.toml_config_store import TomlConfigStore
from omym2.adapters.web.app import create_web_app
from omym2.adapters.web.schemas.settings_form import (
    FIELD_ADD_AUTO_APPLY,
    FIELD_ADD_DEFAULT_MODE,
    FIELD_COLLISION_ON_DUPLICATE_HASH,
    FIELD_COLLISION_ON_MISSING_METADATA,
    FIELD_COLLISION_ON_TARGET_EXISTS,
    FIELD_INCOMING,
    FIELD_LIBRARY,
    FIELD_METADATA_PREFER_ALBUM_ARTIST,
    FIELD_METADATA_REQUIRE_ALBUM,
    FIELD_METADATA_REQUIRE_ARTIST,
    FIELD_METADATA_REQUIRE_TITLE,
    FIELD_ORGANIZE_AUTO_APPLY,
    FIELD_ORGANIZE_DEFAULT_MODE,
    FIELD_ORGANIZE_ONLY_MISPLACED,
    FIELD_PATH_POLICY_MAX_FILENAME_LENGTH,
    FIELD_PATH_POLICY_SANITIZE,
    FIELD_PATH_POLICY_TEMPLATE,
    FIELD_PATH_POLICY_UNKNOWN_ALBUM,
    FIELD_PATH_POLICY_UNKNOWN_ARTIST,
    FIELD_REFRESH_AUTO_APPLY,
    FIELD_REFRESH_DEFAULT_MODE,
    FIELD_UI_SHOW_ADVANCED_SETTINGS,
    FIELD_UI_THEME,
    FORM_ACTION_FIELD,
    FORM_ACTION_SAVE,
    FORM_ACTION_VALIDATE,
    FORM_CSRF_FIELD,
    HTML_CHECKED_VALUE,
)
from omym2.domain.models.app_config import AppConfig, PathsConfig

if TYPE_CHECKING:
    from pathlib import Path

EXPECTED_DEFAULT_PREVIEW = "Aimer/2024_Example Album/1-03_Example Song.flac"
EXPECTED_UPDATED_PREVIEW = "Aimer/03_Example Song.flac"
ERROR_STATUS_CODE = 400
FORBIDDEN_STATUS_CODE = 403
INCOMING_PATH = "/music/incoming"
INVALID_MAX_FILENAME_LENGTH = "not-an-int"
LIBRARY_PATH = "/music/library"
SUCCESS_STATUS_CODE = 200
CSRF_TOKEN_PATTERN = re.compile(r'name="csrf_token" value="([^"]+)"')
UPDATED_TEMPLATE = "{artist}/{track}_{title}"


def test_settings_page_displays_current_config_and_preview(tmp_path: Path) -> None:
    """GET settings renders the current config without creating a missing file."""
    config_path = tmp_path / "config.toml"
    client = TestClient(create_web_app(config_path))

    response = client.get("/settings")

    assert response.status_code == SUCCESS_STATUS_CODE
    assert "OMYM2 Settings" in response.text
    assert EXPECTED_DEFAULT_PREVIEW in response.text
    assert not config_path.exists()


def test_settings_validate_displays_diff_without_saving(tmp_path: Path) -> None:
    """Validate renders proposed changes and leaves persisted config untouched."""
    config_path = tmp_path / "config.toml"
    client = TestClient(create_web_app(config_path))
    form_data = _settings_form_data(
        AppConfig(paths=PathsConfig(library=LIBRARY_PATH), path_policy=AppConfig().path_policy),
        action=FORM_ACTION_VALIDATE,
    )
    form_data[FIELD_PATH_POLICY_TEMPLATE] = UPDATED_TEMPLATE

    response = client.post("/settings", data=form_data)

    assert response.status_code == SUCCESS_STATUS_CODE
    assert "Settings are valid." in response.text
    assert "Path template" in response.text
    assert EXPECTED_UPDATED_PREVIEW in response.text
    assert not config_path.exists()


def test_settings_save_persists_config(tmp_path: Path) -> None:
    """Save writes validated settings through the config store."""
    config_path = tmp_path / "config.toml"
    client = TestClient(create_web_app(config_path))
    csrf_token = _csrf_token(client)
    form_data = _settings_form_data(
        AppConfig(paths=PathsConfig(library=LIBRARY_PATH, incoming=INCOMING_PATH)),
        action=FORM_ACTION_SAVE,
        csrf_token=csrf_token,
    )

    response = client.post("/settings", data=form_data)

    assert response.status_code == SUCCESS_STATUS_CODE
    assert "Settings saved." in response.text
    saved_config = TomlConfigStore(config_path).load()
    assert saved_config.paths.library == LIBRARY_PATH
    assert saved_config.paths.incoming == INCOMING_PATH


def test_settings_save_rejects_missing_csrf_token(tmp_path: Path) -> None:
    """Cross-origin form posts cannot save settings without the page token."""
    config_path = tmp_path / "config.toml"
    client = TestClient(create_web_app(config_path))
    form_data = _settings_form_data(
        AppConfig(paths=PathsConfig(library=LIBRARY_PATH, incoming=INCOMING_PATH)),
        action=FORM_ACTION_SAVE,
    )

    response = client.post("/settings", data=form_data)

    assert response.status_code == FORBIDDEN_STATUS_CODE
    assert "CSRF validation" in response.text
    assert not config_path.exists()


def test_settings_rejects_invalid_form_without_saving(tmp_path: Path) -> None:
    """Invalid form data returns validation errors and avoids writing config."""
    config_path = tmp_path / "config.toml"
    client = TestClient(create_web_app(config_path))
    form_data = _settings_form_data(AppConfig(), action=FORM_ACTION_SAVE)
    form_data[FIELD_PATH_POLICY_MAX_FILENAME_LENGTH] = INVALID_MAX_FILENAME_LENGTH

    response = client.post("/settings", data=form_data)

    assert response.status_code == ERROR_STATUS_CODE
    assert "must be an integer" in response.text
    assert not config_path.exists()


def _settings_form_data(config: AppConfig, *, action: str, csrf_token: str | None = None) -> dict[str, str]:
    form_data = {
        FORM_ACTION_FIELD: action,
        FIELD_LIBRARY: config.paths.library or "",
        FIELD_INCOMING: config.paths.incoming or "",
        FIELD_ADD_DEFAULT_MODE: config.add.default_mode,
        FIELD_ORGANIZE_DEFAULT_MODE: config.organize.default_mode,
        FIELD_REFRESH_DEFAULT_MODE: config.refresh.default_mode,
        FIELD_PATH_POLICY_TEMPLATE: config.path_policy.template,
        FIELD_PATH_POLICY_UNKNOWN_ARTIST: config.path_policy.unknown_artist,
        FIELD_PATH_POLICY_UNKNOWN_ALBUM: config.path_policy.unknown_album,
        FIELD_PATH_POLICY_MAX_FILENAME_LENGTH: str(config.path_policy.max_filename_length),
        FIELD_COLLISION_ON_TARGET_EXISTS: config.collision.on_target_exists,
        FIELD_COLLISION_ON_DUPLICATE_HASH: config.collision.on_duplicate_hash,
        FIELD_COLLISION_ON_MISSING_METADATA: config.collision.on_missing_metadata,
        FIELD_UI_THEME: config.ui.theme,
    }
    if csrf_token is not None:
        form_data[FORM_CSRF_FIELD] = csrf_token
    _set_checkbox(form_data, FIELD_ADD_AUTO_APPLY, value=config.add.auto_apply)
    _set_checkbox(form_data, FIELD_ORGANIZE_AUTO_APPLY, value=config.organize.auto_apply)
    _set_checkbox(form_data, FIELD_ORGANIZE_ONLY_MISPLACED, value=config.organize.only_misplaced)
    _set_checkbox(form_data, FIELD_REFRESH_AUTO_APPLY, value=config.refresh.auto_apply)
    _set_checkbox(form_data, FIELD_PATH_POLICY_SANITIZE, value=config.path_policy.sanitize)
    _set_checkbox(form_data, FIELD_METADATA_PREFER_ALBUM_ARTIST, value=config.metadata.prefer_album_artist)
    _set_checkbox(form_data, FIELD_METADATA_REQUIRE_TITLE, value=config.metadata.require_title)
    _set_checkbox(form_data, FIELD_METADATA_REQUIRE_ARTIST, value=config.metadata.require_artist)
    _set_checkbox(form_data, FIELD_METADATA_REQUIRE_ALBUM, value=config.metadata.require_album)
    _set_checkbox(form_data, FIELD_UI_SHOW_ADVANCED_SETTINGS, value=config.ui.show_advanced_settings)
    return form_data


def _set_checkbox(form_data: dict[str, str], field_name: str, *, value: bool) -> None:
    if value:
        form_data[field_name] = HTML_CHECKED_VALUE


def _csrf_token(client: TestClient) -> str:
    response = client.get("/settings")
    match = CSRF_TOKEN_PATTERN.search(response.text)
    assert match is not None
    return match.group(1)
