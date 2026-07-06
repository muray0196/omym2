"""
Summary: Tests Web settings JSON API routes.
Why: Verifies React-facing settings load, validation, preview, and saving.
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Protocol, cast

from fastapi.testclient import TestClient

from omym2.adapters.config.toml_config_store import TomlConfigStore
from omym2.adapters.web.app import create_web_app
from omym2.config import (
    ALBUM_YEAR_RESOLUTION_OLDEST,
    CONFIG_FILE_ENCODING,
    WEB_API_ARTIST_IDS_GENERATE_ROUTE,
    WEB_API_SETTINGS_PREVIEW_ROUTE,
    WEB_API_SETTINGS_ROUTE,
    WEB_API_SETTINGS_SAVE_ROUTE,
    WEB_API_SETTINGS_VALIDATE_ROUTE,
    WEB_CSRF_HEADER_NAME,
)
from omym2.domain.models.app_config import AppConfig, ArtistIdConfig, MetadataConfig, PathPolicyConfig, PathsConfig

if TYPE_CHECKING:
    from pathlib import Path

ERROR_STATUS_CODE = 400
EXPECTED_DEFAULT_PREVIEW = "Aimer/2024_Example-Album/1-03_Example-Song.flac"
EXPECTED_D_PREFIXED_PREVIEW = "Aimer/2024_Example-Album/D1-03_Example-Song.flac"
EXPECTED_UPDATED_PREVIEW = "Aimer/03_Example-Song.flac"
EXPECTED_UNICODE_PREVIEW = "こんにちは/2024_你好/1-03_Café-Song.flac"
FORBIDDEN_STATUS_CODE = 403
INCOMING_PATH = "/music/incoming"
LIBRARY_PATH = "/music/library"
SUCCESS_STATUS_CODE = 200
UPDATED_TEMPLATE = "{artist}/{track}_{title}"
ARTIST_NAME = "John Smith"
ARTIST_ID = "JOHNSMTH"
EDITED_ARTIST_ID = "MANUAL"
DISC_NUMBER_STYLE_D_PREFIXED = "d_prefixed"
DISC_NUMBER_CONDITION_MULTIPLE_DISCS = "multiple_discs"


class _JsonResponse(Protocol):
    def json(self) -> object: ...


def test_get_settings_returns_config_choices_validation_preview_and_csrf(tmp_path: Path) -> None:
    """Settings load returns the full React settings bootstrap payload."""
    config_path = tmp_path / "config.toml"
    client = TestClient(create_web_app(config_path))

    response = client.get(WEB_API_SETTINGS_ROUTE)

    assert response.status_code == SUCCESS_STATUS_CODE
    payload = _json_payload(response)
    assert (
        _object_payload(_object_payload(payload, "config"), "path_policy")["template"]
        == AppConfig().path_policy.template
    )
    assert (
        _object_payload(_object_payload(payload, "config"), "metadata")["album_year_resolution"]
        == AppConfig().metadata.album_year_resolution
    )
    assert (
        _object_payload(_object_payload(payload, "config"), "path_policy")["disc_number_style"]
        == AppConfig().path_policy.disc_number_style
    )
    assert _object_payload(_object_payload(payload, "config"), "artist_ids")["entries"] == {}
    assert _object_payload(payload, "choices")["command_modes"] == ["plan_first"]
    assert _object_payload(payload, "choices")["album_year_resolution_methods"] == [
        "latest",
        "most_frequent",
        "oldest",
    ]
    assert _object_payload(payload, "choices")["disc_number_styles"] == ["d_prefixed", "plain"]
    assert _object_payload(payload, "choices")["disc_number_conditions"] == ["always", "multiple_discs"]
    assert _object_payload(payload, "validation")["valid"] is True
    assert _object_payload(payload, "preview")["path"] == EXPECTED_DEFAULT_PREVIEW
    assert payload["errors"] == []
    assert isinstance(payload["csrf_token"], str)
    assert payload["csrf_token"] != ""
    assert not config_path.exists()


def test_validate_settings_returns_changes_and_preview_without_saving(tmp_path: Path) -> None:
    """Settings validate reports proposed changes without writing TOML."""
    config_path = tmp_path / "config.toml"
    client = TestClient(create_web_app(config_path))
    payload = _settings_payload(AppConfig(paths=PathsConfig(library=LIBRARY_PATH), path_policy=AppConfig().path_policy))
    _path_policy_payload(payload)["template"] = UPDATED_TEMPLATE

    response = client.post(WEB_API_SETTINGS_VALIDATE_ROUTE, json=payload)

    assert response.status_code == SUCCESS_STATUS_CODE
    response_payload = _json_payload(response)
    assert response_payload["valid"] is True
    assert response_payload["errors"] == []
    assert _object_payload(response_payload, "preview")["path"] == EXPECTED_UPDATED_PREVIEW
    assert response_payload["changes"] == [
        {"label": "Library path", "before": "Not set", "after": LIBRARY_PATH},
        {"label": "Path template", "before": AppConfig().path_policy.template, "after": UPDATED_TEMPLATE},
    ]
    assert not config_path.exists()


def test_preview_settings_returns_backend_path_policy_result(tmp_path: Path) -> None:
    """Settings preview renders custom sample metadata through the backend usecase."""
    client = TestClient(create_web_app(tmp_path / "config.toml"))
    payload = _settings_payload(AppConfig())
    payload["metadata"] = {
        "title": "Café Song",
        "artist": "こんにちは",
        "album": "你好",
        "album_artist": "",
        "year": "2024",
        "disc_number": "1",
        "track_number": "3",
        "extension": "FLAC",
    }

    response = client.post(WEB_API_SETTINGS_PREVIEW_ROUTE, json=payload)

    assert response.status_code == SUCCESS_STATUS_CODE
    response_payload = _json_payload(response)
    assert response_payload["path"] == EXPECTED_UNICODE_PREVIEW
    assert response_payload["errors"] == []


def test_preview_settings_accepts_disc_total_for_multi_disc_only(tmp_path: Path) -> None:
    """Settings preview uses disc_total to demonstrate multi-disc-only rendering."""
    client = TestClient(create_web_app(tmp_path / "config.toml"))
    payload = _settings_payload(
        AppConfig(
            path_policy=PathPolicyConfig(
                disc_number_style=DISC_NUMBER_STYLE_D_PREFIXED,
                disc_number_condition=DISC_NUMBER_CONDITION_MULTIPLE_DISCS,
            )
        )
    )
    payload["metadata"] = {
        "title": "Example Song",
        "artist": "Aimer",
        "album": "Example Album",
        "album_artist": "Aimer",
        "year": "2024",
        "disc_number": "1",
        "disc_total": "2",
        "track_number": "3",
        "extension": "FLAC",
    }

    response = client.post(WEB_API_SETTINGS_PREVIEW_ROUTE, json=payload)

    assert response.status_code == SUCCESS_STATUS_CODE
    response_payload = _json_payload(response)
    assert response_payload["path"] == EXPECTED_D_PREFIXED_PREVIEW
    assert response_payload["errors"] == []


def test_preview_settings_rejects_invalid_metadata(tmp_path: Path) -> None:
    """Preview metadata parsing reports invalid sample numbers without saving settings."""
    client = TestClient(create_web_app(tmp_path / "config.toml"))
    payload = _settings_payload(AppConfig())
    payload["metadata"] = {"title": "Song", "track_number": "not-a-number", "extension": "flac"}

    response = client.post(WEB_API_SETTINGS_PREVIEW_ROUTE, json=payload)

    assert response.status_code == ERROR_STATUS_CODE
    response_payload = _json_payload(response)
    assert response_payload["path"] is None
    assert response_payload["errors"] == ["Preview metadata.track_number must be an integer."]


def test_save_settings_persists_valid_config_with_csrf(tmp_path: Path) -> None:
    """Settings save writes through the settings usecase when CSRF is valid."""
    config_path = tmp_path / "config.toml"
    client = TestClient(create_web_app(config_path))
    csrf_token = _csrf_token(client)
    payload = _settings_payload(AppConfig(paths=PathsConfig(library=LIBRARY_PATH, incoming=INCOMING_PATH)))

    response = client.post(WEB_API_SETTINGS_SAVE_ROUTE, json=payload, headers={WEB_CSRF_HEADER_NAME: csrf_token})

    assert response.status_code == SUCCESS_STATUS_CODE
    response_payload = _json_payload(response)
    assert response_payload["saved"] is True
    assert response_payload["errors"] == []
    assert _object_payload(_object_payload(response_payload, "config"), "paths")["library"] == LIBRARY_PATH
    saved_config = TomlConfigStore(config_path).load()
    assert saved_config.paths.library == LIBRARY_PATH
    assert saved_config.paths.incoming == INCOMING_PATH


def test_save_settings_persists_editable_artist_id_entries(tmp_path: Path) -> None:
    """Settings save lets users edit artist ID entries in TOML config."""
    config_path = tmp_path / "config.toml"
    client = TestClient(create_web_app(config_path))
    csrf_token = _csrf_token(client)
    payload = _settings_payload(AppConfig(artist_ids=ArtistIdConfig(entries={ARTIST_NAME: EDITED_ARTIST_ID})))

    response = client.post(WEB_API_SETTINGS_SAVE_ROUTE, json=payload, headers={WEB_CSRF_HEADER_NAME: csrf_token})

    assert response.status_code == SUCCESS_STATUS_CODE
    saved_config = TomlConfigStore(config_path).load()
    assert saved_config.artist_ids.entries == {ARTIST_NAME: EDITED_ARTIST_ID}


def test_save_settings_persists_album_year_resolution(tmp_path: Path) -> None:
    """Settings save writes the album-year resolution method through TOML."""
    config_path = tmp_path / "config.toml"
    client = TestClient(create_web_app(config_path))
    csrf_token = _csrf_token(client)
    payload = _settings_payload(AppConfig(metadata=MetadataConfig(album_year_resolution=ALBUM_YEAR_RESOLUTION_OLDEST)))

    response = client.post(WEB_API_SETTINGS_SAVE_ROUTE, json=payload, headers={WEB_CSRF_HEADER_NAME: csrf_token})

    assert response.status_code == SUCCESS_STATUS_CODE
    saved_config = TomlConfigStore(config_path).load()
    assert saved_config.metadata.album_year_resolution == ALBUM_YEAR_RESOLUTION_OLDEST


def test_save_settings_persists_disc_number_settings(tmp_path: Path) -> None:
    """Settings save persists path policy disc rendering fields."""
    config_path = tmp_path / "config.toml"
    client = TestClient(create_web_app(config_path))
    csrf_token = _csrf_token(client)
    payload = _settings_payload(
        AppConfig(
            path_policy=PathPolicyConfig(
                disc_number_style=DISC_NUMBER_STYLE_D_PREFIXED,
                disc_number_condition=DISC_NUMBER_CONDITION_MULTIPLE_DISCS,
            )
        )
    )

    response = client.post(WEB_API_SETTINGS_SAVE_ROUTE, json=payload, headers={WEB_CSRF_HEADER_NAME: csrf_token})

    assert response.status_code == SUCCESS_STATUS_CODE
    saved_config = TomlConfigStore(config_path).load()
    assert saved_config.path_policy.disc_number_style == DISC_NUMBER_STYLE_D_PREFIXED
    assert saved_config.path_policy.disc_number_condition == DISC_NUMBER_CONDITION_MULTIPLE_DISCS


def test_generate_artist_ids_saves_missing_entries_without_overwriting(tmp_path: Path) -> None:
    """Settings API can generate missing IDs and preserve existing manual edits."""
    config_path = tmp_path / "config.toml"
    TomlConfigStore(config_path).save(AppConfig(artist_ids=ArtistIdConfig(entries={"Jane Doe": EDITED_ARTIST_ID})))
    client = TestClient(create_web_app(config_path))
    csrf_token = _csrf_token(client)

    response = client.post(
        WEB_API_ARTIST_IDS_GENERATE_ROUTE,
        json={"artist_names": [ARTIST_NAME, "Jane Doe"]},
        headers={WEB_CSRF_HEADER_NAME: csrf_token},
    )

    assert response.status_code == SUCCESS_STATUS_CODE
    response_payload = _json_payload(response)
    assert response_payload["generated"] is True
    assert _list_payload(response_payload, "entries") == [
        {
            "source_artist": ARTIST_NAME,
            "generation_artist": ARTIST_NAME,
            "artist_id": ARTIST_ID,
            "saved": True,
            "overwritten": False,
        },
        {
            "source_artist": "Jane Doe",
            "generation_artist": "Jane Doe",
            "artist_id": EDITED_ARTIST_ID,
            "saved": False,
            "overwritten": False,
        },
    ]
    assert TomlConfigStore(config_path).load().artist_ids.entries == {
        ARTIST_NAME: ARTIST_ID,
        "Jane Doe": EDITED_ARTIST_ID,
    }


def test_generate_artist_ids_returns_invalid_persisted_config_errors(tmp_path: Path) -> None:
    """Settings API generation reports TOML validation errors as JSON."""
    config_path = tmp_path / "config.toml"
    _ = config_path.write_text(
        'version = 1\n[artist_ids]\nmax_length = 0\nfallback_id = "NOART"\n',
        encoding=CONFIG_FILE_ENCODING,
    )
    client = TestClient(create_web_app(config_path))
    csrf_token = _csrf_token(client)

    response = client.post(
        WEB_API_ARTIST_IDS_GENERATE_ROUTE,
        json={"artist_names": [ARTIST_NAME]},
        headers={WEB_CSRF_HEADER_NAME: csrf_token},
    )

    assert response.status_code == ERROR_STATUS_CODE
    response_payload = _json_payload(response)
    assert response_payload["generated"] is False
    assert "ArtistIdConfig max_length must be positive." in _list_payload(response_payload, "errors")
    assert _list_payload(response_payload, "entries") == []


def test_save_settings_clears_existing_config_errors_after_successful_write(tmp_path: Path) -> None:
    """A successful save must not return stale errors from the replaced TOML file."""
    config_path = tmp_path / "config.toml"
    _ = config_path.write_text("version = ", encoding=CONFIG_FILE_ENCODING)
    client = TestClient(create_web_app(config_path))
    csrf_token = _csrf_token(client)
    payload = _settings_payload(AppConfig(paths=PathsConfig(library=LIBRARY_PATH)))

    response = client.post(WEB_API_SETTINGS_SAVE_ROUTE, json=payload, headers={WEB_CSRF_HEADER_NAME: csrf_token})

    assert response.status_code == SUCCESS_STATUS_CODE
    response_payload = _json_payload(response)
    assert response_payload["saved"] is True
    assert response_payload["errors"] == []
    assert _object_payload(response_payload, "validation")["valid"] is True
    assert TomlConfigStore(config_path).load().paths.library == LIBRARY_PATH


def test_save_settings_rejects_missing_csrf_without_saving(tmp_path: Path) -> None:
    """Browser-originated save requests cannot write settings without the API token."""
    config_path = tmp_path / "config.toml"
    client = TestClient(create_web_app(config_path))
    payload = _settings_payload(AppConfig(paths=PathsConfig(library=LIBRARY_PATH, incoming=INCOMING_PATH)))

    response = client.post(WEB_API_SETTINGS_SAVE_ROUTE, json=payload)

    assert response.status_code == FORBIDDEN_STATUS_CODE
    response_payload = _json_payload(response)
    assert response_payload["saved"] is False
    assert "CSRF validation" in str(_list_payload(response_payload, "errors")[0])
    assert not config_path.exists()


def test_save_settings_rejects_invalid_config_without_saving(tmp_path: Path) -> None:
    """Invalid JSON config returns validation errors and avoids writing TOML."""
    config_path = tmp_path / "config.toml"
    client = TestClient(create_web_app(config_path))
    csrf_token = _csrf_token(client)
    payload = _settings_payload(AppConfig())
    _path_policy_payload(payload)["max_filename_length"] = "not-an-int"

    response = client.post(WEB_API_SETTINGS_SAVE_ROUTE, json=payload, headers={WEB_CSRF_HEADER_NAME: csrf_token})

    assert response.status_code == ERROR_STATUS_CODE
    response_payload = _json_payload(response)
    assert response_payload["saved"] is False
    assert "must be an integer" in str(_list_payload(response_payload, "errors")[0])
    assert not config_path.exists()


def test_validate_settings_rejects_missing_config_object(tmp_path: Path) -> None:
    """Settings validate requires the documented request envelope."""
    client = TestClient(create_web_app(tmp_path / "config.toml"))

    response = client.post(WEB_API_SETTINGS_VALIDATE_ROUTE, json={})

    assert response.status_code == ERROR_STATUS_CODE
    response_payload = _json_payload(response)
    assert response_payload["valid"] is False
    assert response_payload["errors"] == ["Request body must contain a config object."]


def _settings_payload(config: AppConfig) -> dict[str, object]:
    return {
        "config": {
            "version": config.version,
            "paths": {"library": config.paths.library, "incoming": config.paths.incoming},
            "add": {"default_mode": config.add.default_mode, "auto_apply": config.add.auto_apply},
            "organize": {
                "default_mode": config.organize.default_mode,
                "auto_apply": config.organize.auto_apply,
                "only_misplaced": config.organize.only_misplaced,
            },
            "refresh": {"default_mode": config.refresh.default_mode, "auto_apply": config.refresh.auto_apply},
            "path_policy": {
                "template": config.path_policy.template,
                "unknown_artist": config.path_policy.unknown_artist,
                "unknown_album": config.path_policy.unknown_album,
                "sanitize": config.path_policy.sanitize,
                "max_filename_length": config.path_policy.max_filename_length,
                "disc_number_style": config.path_policy.disc_number_style,
                "disc_number_condition": config.path_policy.disc_number_condition,
            },
            "artist_ids": {
                "max_length": config.artist_ids.max_length,
                "fallback_id": config.artist_ids.fallback_id,
                "entries": dict(config.artist_ids.entries or {}),
            },
            "metadata": {
                "prefer_album_artist": config.metadata.prefer_album_artist,
                "require_title": config.metadata.require_title,
                "require_artist": config.metadata.require_artist,
                "require_album": config.metadata.require_album,
                "album_year_resolution": config.metadata.album_year_resolution,
            },
            "collision": {
                "on_target_exists": config.collision.on_target_exists,
                "on_duplicate_hash": config.collision.on_duplicate_hash,
                "on_missing_metadata": config.collision.on_missing_metadata,
            },
            "ui": {
                "theme": config.ui.theme,
                "show_advanced_settings": config.ui.show_advanced_settings,
            },
        }
    }


def _path_policy_payload(payload: dict[str, object]) -> dict[str, object]:
    return _object_payload(_object_payload(payload, "config"), "path_policy")


def _json_payload(response: _JsonResponse) -> dict[str, object]:
    return cast("dict[str, object]", response.json())


def _object_payload(payload: dict[str, object], key: str) -> dict[str, object]:
    value = payload[key]
    assert isinstance(value, dict)
    return cast("dict[str, object]", value)


def _list_payload(payload: dict[str, object], key: str) -> list[object]:
    value = payload[key]
    assert isinstance(value, list)
    return cast("list[object]", value)


def _csrf_token(client: TestClient) -> str:
    response = client.get(WEB_API_SETTINGS_ROUTE)
    assert response.status_code == SUCCESS_STATUS_CODE
    token = _json_payload(response)["csrf_token"]
    assert isinstance(token, str)
    return token
