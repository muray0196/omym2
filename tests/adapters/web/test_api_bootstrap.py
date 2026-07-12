"""
Summary: Tests the typed Bootstrap Web API.
Why: Verifies recovery and readiness remain available across Config and SQLite states.
"""

from __future__ import annotations

from datetime import UTC, datetime
from typing import TYPE_CHECKING, cast
from uuid import UUID

from fastapi.testclient import TestClient

from omym2.adapters.config.default_config import default_app_config
from omym2.adapters.config.toml_config_store import TomlConfigStore
from omym2.adapters.db.sqlite.unit_of_work import SQLiteUnitOfWork
from omym2.config import (
    HTTP_OK_STATUS,
    MILLISECONDS_PER_SECOND,
    OPERATION_POLL_BACKOFF_FACTOR,
    OPERATION_POLL_INITIAL_SECONDS,
    OPERATION_POLL_MAX_SECONDS,
    WEB_API_BOOTSTRAP_ROUTE,
    WEB_CONTENT_SECURITY_POLICY,
    WEB_CORRELATION_HEADER_NAME,
    WEB_CSP_HEADER_NAME,
    WEB_STATUS_CATALOG_VERSION,
)
from omym2.domain.models.library import Library, LibraryStatus
from omym2.domain.services.config_fingerprint import calculate_path_policy_fingerprint
from omym2.platform.web_composition import build_web_app
from omym2.shared.ids import LibraryId

if TYPE_CHECKING:
    from pathlib import Path

NOW = datetime(2026, 7, 13, tzinfo=UTC)
LIBRARY_ID = LibraryId(UUID("018f6a4f-3c2d-7b8a-9abc-def012345670"))
SECOND_LIBRARY_ID = LibraryId(UUID("018f6a4f-3c2d-7b8a-9abc-def012345671"))


def test_missing_config_bootstrap_uses_defaults_and_reports_unregistered_library(tmp_path: Path) -> None:
    """First use has a real revision and recovery capability without creating Config."""
    config_path = tmp_path / "config.toml"
    client = _client(config_path, tmp_path / "state.sqlite3")

    response = client.get(WEB_API_BOOTSTRAP_ROUTE)
    payload = _payload(cast("object", response.json()))
    data = _object(payload, "data")
    config_validation = _object(data, "config_validation")
    capabilities = _object(data, "runtime_capabilities")

    assert response.status_code == HTTP_OK_STATUS
    assert payload["errors"] == []
    assert data["active_library"] is None
    assert config_validation["valid"] is True
    assert isinstance(config_validation["config_revision"], str)
    assert config_validation["errors"] == []
    assert capabilities["can_read_state"] is True
    assert capabilities["can_change_settings"] is True
    assert capabilities["can_start_operations"] is False
    assert _error_codes(data["library_diagnostics"]) == ["library_unregistered"]
    assert not config_path.exists()


def test_invalid_config_bootstrap_returns_recovery_data_and_structured_errors(tmp_path: Path) -> None:
    """Malformed TOML does not prevent CSRF issuance or Settings recovery."""
    config_path = tmp_path / "config.toml"
    _ = config_path.write_text("version = ", encoding="utf-8")
    client = _client(config_path, tmp_path / "state.sqlite3")

    response = client.get(WEB_API_BOOTSTRAP_ROUTE)
    payload = _payload(cast("object", response.json()))
    data = _object(payload, "data")
    config_validation = _object(data, "config_validation")
    capabilities = _object(data, "runtime_capabilities")

    assert response.status_code == HTTP_OK_STATUS
    assert isinstance(data["csrf_token"], str)
    assert config_validation["valid"] is False
    assert _error_codes(config_validation["errors"]) == ["config_invalid"]
    assert _error_codes(payload["errors"]) == ["config_invalid"]
    assert capabilities["can_change_settings"] is True
    assert capabilities["can_start_operations"] is False
    assert any(
        error["field"] == "runtime_capabilities.can_start_operations"
        for error in cast("list[dict[str, object]]", capabilities["disabled_reasons"])
    )


def test_bootstrap_projects_one_current_library_as_ready(tmp_path: Path) -> None:
    """Current registered Library enables operation starts in the readiness snapshot."""
    config_path = tmp_path / "config.toml"
    database_path = tmp_path / "state.sqlite3"
    config = default_app_config()
    TomlConfigStore(config_path).save(config)
    path_policy_hash = calculate_path_policy_fingerprint(
        config.path_policy,
        config.artist_ids,
        config.metadata.album_year_resolution,
    )
    _save_libraries(database_path, _library(LIBRARY_ID, path_policy_hash))

    response = _client(config_path, database_path).get(WEB_API_BOOTSTRAP_ROUTE)
    data = _object(_payload(cast("object", response.json())), "data")
    library = _object(data, "active_library")
    capabilities = _object(data, "runtime_capabilities")
    polling = _object(data, "operation_polling")

    assert library["library_id"] == str(LIBRARY_ID)
    assert library["status"] == "registered"
    assert library["is_path_policy_current"] is True
    assert capabilities["can_start_operations"] is True
    assert capabilities["disabled_reasons"] == []
    assert data["status_catalog_version"] == WEB_STATUS_CATALOG_VERSION
    assert polling == {
        "initial_ms": int(OPERATION_POLL_INITIAL_SECONDS * MILLISECONDS_PER_SECOND),
        "backoff_factor": OPERATION_POLL_BACKOFF_FACTOR,
        "max_ms": int(OPERATION_POLL_MAX_SECONDS * MILLISECONDS_PER_SECOND),
    }
    assert data["active_operation_id"] is None


def test_bootstrap_refuses_to_guess_between_libraries(tmp_path: Path) -> None:
    """Multiple Library rows produce an explicit ambiguous diagnostic."""
    config_path = tmp_path / "config.toml"
    database_path = tmp_path / "state.sqlite3"
    config = default_app_config()
    TomlConfigStore(config_path).save(config)
    _save_libraries(database_path, _library(LIBRARY_ID, "one"), _library(SECOND_LIBRARY_ID, "two"))

    data = _object(
        _payload(
            cast(
                "object",
                _client(config_path, database_path).get(WEB_API_BOOTSTRAP_ROUTE).json(),
            )
        ),
        "data",
    )

    assert data["active_library"] is None
    assert _error_codes(data["library_diagnostics"]) == ["library_selection_ambiguous"]


def test_bootstrap_degrades_when_database_is_unavailable(tmp_path: Path) -> None:
    """Persistence failure preserves Config recovery data in a 200 Bootstrap envelope."""
    database_path = tmp_path / "database-directory"
    database_path.mkdir()

    response = _client(tmp_path / "config.toml", database_path).get(WEB_API_BOOTSTRAP_ROUTE)
    payload = _payload(cast("object", response.json()))
    data = _object(payload, "data")
    capabilities = _object(data, "runtime_capabilities")

    assert response.status_code == HTTP_OK_STATUS
    assert _error_codes(payload["errors"]) == ["storage_unavailable"]
    assert capabilities["can_read_state"] is False
    assert capabilities["can_start_operations"] is False
    assert [error["field"] for error in cast("list[dict[str, object]]", capabilities["disabled_reasons"])] == [
        "runtime_capabilities.can_read_state",
        "runtime_capabilities.can_start_operations",
    ]


def test_bootstrap_response_has_security_and_correlation_headers(tmp_path: Path) -> None:
    """API responses carry the common production security baseline."""
    response = _client(tmp_path / "config.toml", tmp_path / "state.sqlite3").get(WEB_API_BOOTSTRAP_ROUTE)

    assert response.headers[WEB_CSP_HEADER_NAME] == WEB_CONTENT_SECURITY_POLICY
    assert response.headers[WEB_CORRELATION_HEADER_NAME]
    assert response.headers["X-Content-Type-Options"] == "nosniff"
    assert response.headers["Referrer-Policy"] == "no-referrer"
    assert response.headers["X-Frame-Options"] == "DENY"


def _client(config_path: Path, database_path: Path) -> TestClient:
    return TestClient(build_web_app(config_path, database_path), base_url="http://localhost")


def _save_libraries(database_path: Path, *libraries: Library) -> None:
    with SQLiteUnitOfWork(database_path) as uow:
        for library in libraries:
            uow.libraries.save(library)
        uow.commit()


def _library(library_id: LibraryId, path_policy_hash: str) -> Library:
    return Library(
        library_id=library_id,
        root_path=f"/music/{library_id}",
        path_policy_hash=path_policy_hash,
        registered_at=NOW,
        status=LibraryStatus.REGISTERED,
        created_at=NOW,
        updated_at=NOW,
    )


def _payload(value: object) -> dict[str, object]:
    assert isinstance(value, dict)
    return cast("dict[str, object]", value)


def _object(payload: dict[str, object], key: str) -> dict[str, object]:
    value = payload[key]
    assert isinstance(value, dict)
    return cast("dict[str, object]", value)


def _error_codes(value: object) -> list[object]:
    assert isinstance(value, list)
    codes: list[object] = []
    for error in cast("list[object]", value):
        assert isinstance(error, dict)
        codes.append(cast("dict[str, object]", error)["code"])
    return codes
