"""
Summary: Tests typed Settings edit, preview, validation, save, and draft routes.
Why: Protects recovery, revision conflicts, field errors, and draft-only behavior.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import TYPE_CHECKING, cast

from fastapi.testclient import TestClient

from omym2.adapters.web.app import create_web_app
from omym2.adapters.web.routes.api_context import ApiRouteContext, SettingsRouteContext
from omym2.adapters.web.schemas.settings import AppConfigResource
from omym2.config import (
    HTTP_CONFLICT_STATUS,
    HTTP_FORBIDDEN_STATUS,
    HTTP_OK_STATUS,
    HTTP_UNPROCESSABLE_CONTENT_STATUS,
    WEB_API_SETTINGS_ARTIST_IDS_ROUTE,
    WEB_API_SETTINGS_PREVIEW_ROUTE,
    WEB_API_SETTINGS_ROUTE,
    WEB_API_SETTINGS_VALIDATE_ROUTE,
    WEB_CSRF_HEADER_NAME,
)
from omym2.domain.models.app_config import AppConfig, ArtistIdConfig, PathsConfig, UiConfig
from omym2.features.artist_ids.usecases.generate_artist_id_draft import GenerateArtistIdDraftUseCase
from omym2.features.common_ports import ConfigRevisionMismatchError, ConfigSnapshot, ConfigSnapshotState
from omym2.features.settings.ports import SettingsPorts
from omym2.features.settings.usecases.get_settings_edit import GetSettingsEditUseCase
from omym2.features.settings.usecases.preview_path_policy import PreviewPathPolicyUseCase
from omym2.features.settings.usecases.save_settings_candidate import SaveSettingsCandidateUseCase
from omym2.features.settings.usecases.validate_settings_candidate import ValidateSettingsCandidateUseCase

if TYPE_CHECKING:
    from pathlib import Path

    from httpx2 import Response

CONFIG_REVISION = "v1:web-settings-current"
SAVED_CONFIG_REVISION = "v1:web-settings-saved"
STALE_CONFIG_REVISION = "v1:web-settings-stale"
CSRF_TOKEN = "settings-csrf-token"  # noqa: S105  # Deterministic non-secret test token.
PERSISTED_CONFIG_ERROR = "Persisted Config is invalid."
UNSUPPORTED_THEME = "sepia"
LIBRARY_PATH = "/music/library"
SOURCE_ARTIST = "Existing Artist"
SOURCE_ARTIST_ID = "EXST"
NEW_ARTIST = "New Artist"
UNRELATED_BOOTSTRAP_EXECUTION_MESSAGE = "Unrelated Bootstrap handler must not execute."


def test_get_settings_returns_invalid_recovery_data_choices_and_preview(tmp_path: Path) -> None:
    """Malformed persisted Config stays a successful editable recovery resource."""
    store = FakeConfigStore(state=ConfigSnapshotState.INVALID, errors=(PERSISTED_CONFIG_ERROR,))
    client = _client(tmp_path, store)

    response = client.get(WEB_API_SETTINGS_ROUTE)

    assert response.status_code == HTTP_OK_STATUS
    data = _data(response)
    assert data["config_revision"] == CONFIG_REVISION
    validation = _object(data, "validation")
    assert validation["valid"] is False
    assert _first_error(validation)["code"] == "config_invalid"
    assert _first_error(validation)["field"] == "config"
    assert _object(data, "choices")["command_modes"] == ["plan_first"]
    assert _object(data, "preview")["path"] == "Aimer/2024_Example-Album/1-03_Example-Song.flac"


def test_app_config_resource_round_trips_complete_hidden_config_fields() -> None:
    """Settings serialization retains fields hidden by the bundled presentation."""
    config = AppConfig(
        paths=PathsConfig(library=LIBRARY_PATH),
        ui=UiConfig(theme="dark", show_advanced_settings=True),
    )

    resource = AppConfigResource.from_domain(config)

    assert resource.to_domain() == config


def test_validate_settings_returns_field_changes_and_typed_invalid_result(tmp_path: Path) -> None:
    """Candidate validation is read-only and reports unsupported hidden round-trip choices."""
    store = FakeConfigStore()
    client = _client(tmp_path, store)
    candidate = AppConfig(paths=PathsConfig(library=LIBRARY_PATH), ui=UiConfig(theme=UNSUPPORTED_THEME))

    response = client.post(WEB_API_SETTINGS_VALIDATE_ROUTE, json=_candidate_body(candidate, CONFIG_REVISION))

    assert response.status_code == HTTP_OK_STATUS
    data = _data(response)
    validation = _object(data, "validation")
    assert validation["valid"] is False
    assert _first_error(validation)["field"] == "ui.theme"
    assert [change["field"] for change in _list(data, "changes")] == ["paths.library", "ui.theme"]
    assert store.save_count == 0


def test_validate_settings_rejects_a_stale_edit_base(tmp_path: Path) -> None:
    """Validation never reports against raw storage other than the caller's edit base."""
    client = _client(tmp_path, FakeConfigStore())

    response = client.post(WEB_API_SETTINGS_VALIDATE_ROUTE, json=_candidate_body(AppConfig(), STALE_CONFIG_REVISION))

    assert response.status_code == HTTP_CONFLICT_STATUS
    assert _first_error(_response_object(response))["code"] == "config_changed"


def test_preview_returns_domain_errors_as_data_without_config_writes(tmp_path: Path) -> None:
    """Self-contained preview failures stay typed 200 results and never touch ConfigStore."""
    store = FakeConfigStore()
    client = _client(tmp_path, store)
    config_resource = AppConfigResource.from_domain(AppConfig()).model_dump(mode="json")
    path_policy = cast("dict[str, object]", config_resource["path_policy"])
    path_policy["max_filename_length"] = 0

    response = client.post(
        WEB_API_SETTINGS_PREVIEW_ROUTE,
        json={
            "path_policy": path_policy,
            "artist_ids": config_resource["artist_ids"],
            "metadata": {"title": "Song", "artist": "Artist"},
            "file_extension": ".flac",
        },
    )

    assert response.status_code == HTTP_OK_STATUS
    preview = _data(response)
    assert preview["path"] is None
    assert _first_error(preview)["code"] == "validation_failed"
    assert store.save_count == 0


def test_save_settings_returns_new_revision_and_rejects_invalid_or_stale_candidates(tmp_path: Path) -> None:
    """PUT reports successful CAS, 422 invalid candidates, and 409 stale revisions without extra writes."""
    store = FakeConfigStore()
    client = _client(tmp_path, store)
    valid = AppConfig(paths=PathsConfig(library=LIBRARY_PATH))

    saved = client.put(
        WEB_API_SETTINGS_ROUTE,
        json=_candidate_body(valid, CONFIG_REVISION),
        headers={WEB_CSRF_HEADER_NAME: CSRF_TOKEN},
    )
    invalid = client.put(
        WEB_API_SETTINGS_ROUTE,
        json=_candidate_body(AppConfig(ui=UiConfig(theme=UNSUPPORTED_THEME)), SAVED_CONFIG_REVISION),
        headers={WEB_CSRF_HEADER_NAME: CSRF_TOKEN},
    )
    stale = client.put(
        WEB_API_SETTINGS_ROUTE,
        json=_candidate_body(AppConfig(), CONFIG_REVISION),
        headers={WEB_CSRF_HEADER_NAME: CSRF_TOKEN},
    )

    assert saved.status_code == HTTP_OK_STATUS
    assert _data(saved)["config_revision"] == SAVED_CONFIG_REVISION
    assert [change["field"] for change in _list(_data(saved), "changes")] == ["paths.library"]
    assert invalid.status_code == HTTP_UNPROCESSABLE_CONTENT_STATUS
    assert _first_error(_response_object(invalid))["field"] == "ui.theme"
    assert stale.status_code == HTTP_CONFLICT_STATUS
    assert _first_error(_response_object(stale))["code"] == "config_changed"
    assert store.save_count == 1


def test_save_settings_requires_csrf_before_config_validation(tmp_path: Path) -> None:
    """Missing mutation authorization is rejected before Settings callbacks can save."""
    store = FakeConfigStore()
    client = _client(tmp_path, store)

    response = client.put(
        WEB_API_SETTINGS_ROUTE,
        json=_candidate_body(AppConfig(), CONFIG_REVISION),
    )

    assert response.status_code == HTTP_FORBIDDEN_STATUS
    assert _first_error(_response_object(response))["code"] == "csrf_invalid"
    assert store.save_count == 0


def test_artist_id_generation_uses_form_draft_without_saving_config(tmp_path: Path) -> None:
    """Draft generation preserves existing entries and returns new values without persistence."""
    store = FakeConfigStore()
    client = _client(tmp_path, store)
    artist_ids = AppConfigResource.from_domain(
        AppConfig(artist_ids=ArtistIdConfig(entries={SOURCE_ARTIST: SOURCE_ARTIST_ID}))
    ).artist_ids

    response = client.post(
        WEB_API_SETTINGS_ARTIST_IDS_ROUTE,
        json={
            "artist_names": [SOURCE_ARTIST, NEW_ARTIST, NEW_ARTIST],
            "overwrite": False,
            "artist_ids": artist_ids.model_dump(mode="json"),
        },
    )

    assert response.status_code == HTTP_OK_STATUS
    entries = _list(_data(response), "entries")
    assert [entry["source_artist"] for entry in entries] == [SOURCE_ARTIST, NEW_ARTIST]
    assert entries[0]["artist_id"] == SOURCE_ARTIST_ID
    assert entries[0]["overwritten"] is False
    assert store.save_count == 0


def _client(tmp_path: Path, store: FakeConfigStore) -> TestClient:
    ports = SettingsPorts(config_store=store)
    context = SettingsRouteContext(
        get_settings=GetSettingsEditUseCase(ports).execute,
        validate_settings=ValidateSettingsCandidateUseCase(ports).execute,
        preview_path_policy=PreviewPathPolicyUseCase().execute,
        save_settings=SaveSettingsCandidateUseCase(ports).execute,
        generate_artist_id_draft=GenerateArtistIdDraftUseCase(
            language_detector=StaticLanguageDetector(),
            artist_resolver=StaticArtistNameResolver(),
        ).execute,
    )
    app = create_web_app(
        ApiRouteContext(
            csrf_token=CSRF_TOKEN,
            get_bootstrap=_must_not_execute,
            settings=context,
        ),
        tmp_path / "missing-static",
    )
    return TestClient(app, base_url="http://localhost", raise_server_exceptions=False)


def _candidate_body(config: AppConfig, config_revision: str) -> dict[str, object]:
    return {
        "config": AppConfigResource.from_domain(config).model_dump(mode="json"),
        "expected_config_revision": config_revision,
    }


def _must_not_execute():
    raise AssertionError(UNRELATED_BOOTSTRAP_EXECUTION_MESSAGE)


def _response_object(response: Response) -> dict[str, object]:
    return cast("dict[str, object]", response.json())


def _data(response: Response) -> dict[str, object]:
    data = _response_object(response)["data"]
    assert isinstance(data, dict)
    return cast("dict[str, object]", data)


def _object(value: dict[str, object], key: str) -> dict[str, object]:
    nested = value[key]
    assert isinstance(nested, dict)
    return cast("dict[str, object]", nested)


def _list(value: dict[str, object], key: str) -> list[dict[str, object]]:
    nested = value[key]
    assert isinstance(nested, list)
    return cast("list[dict[str, object]]", nested)


def _first_error(value: dict[str, object]) -> dict[str, object]:
    return _list(value, "errors")[0]


@dataclass(slots=True)
class FakeConfigStore:
    """Revision-aware ConfigStore fake for typed Settings routes."""

    config: AppConfig = field(default_factory=AppConfig)
    state: ConfigSnapshotState = ConfigSnapshotState.VALID
    errors: tuple[str, ...] = ()
    config_revision: str = CONFIG_REVISION
    save_count: int = 0

    def read_snapshot(self) -> ConfigSnapshot:
        """Return configured current or recovery state."""
        return ConfigSnapshot(self.state, self.config, self.config_revision, self.errors)

    def load(self) -> AppConfig:
        """Return the current recovery Config."""
        return self.config

    def save(self, config: AppConfig, *, expected_config_revision: str) -> ConfigSnapshot:
        """Install one candidate only for the current opaque revision."""
        if expected_config_revision != self.config_revision:
            raise ConfigRevisionMismatchError(expected_config_revision, self.config_revision)
        self.save_count += 1
        self.config = config
        self.state = ConfigSnapshotState.VALID
        self.errors = ()
        self.config_revision = SAVED_CONFIG_REVISION
        return self.read_snapshot()


@dataclass(frozen=True, slots=True)
class StaticLanguageDetector:
    """Treat route-test artists as generation-ready."""

    def is_japanese(self, text: str) -> bool:
        """Return false without model I/O."""
        _ = text
        return False


@dataclass(frozen=True, slots=True)
class StaticArtistNameResolver:
    """Resolver fake unused for generation-ready names."""

    def english_or_latin_name(self, source_artist: str) -> str | None:
        """Return no alternate name."""
        _ = source_artist
        return None
