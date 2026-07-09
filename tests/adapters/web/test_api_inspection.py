"""
Summary: Tests Web check JSON API routes.
Why: Verifies check data for the React UI. Tracks browsing is covered in test_api_tracks.py,
Plan browsing in test_api_plans.py, and Run/FileEvent browsing in test_api_history.py.
"""

from __future__ import annotations

from datetime import UTC, datetime
from typing import TYPE_CHECKING
from uuid import UUID

from fastapi.testclient import TestClient

from omym2.adapters.config.application_paths import default_application_paths
from omym2.adapters.config.default_config import default_app_config
from omym2.adapters.db.sqlite.unit_of_work import SQLiteUnitOfWork
from omym2.config import CONFIG_FILE_ENCODING, WEB_API_CHECK_ROUTE
from omym2.domain.models.library import Library, LibraryStatus
from omym2.domain.services.config_fingerprint import calculate_path_policy_fingerprint
from omym2.platform.web_composition import build_web_app as create_web_app
from omym2.shared.ids import LibraryId

if TYPE_CHECKING:
    from pathlib import Path

BASE_TIME = datetime(2026, 1, 1, tzinfo=UTC)
ERROR_STATUS_CODE = 400
LIBRARY_ID = LibraryId(UUID("018f6a4f-3c2d-7b8a-9abc-def012345678"))
SUCCESS_STATUS_CODE = 200


def test_check_api_returns_issues_and_config_errors(tmp_path: Path) -> None:
    """Check API returns usecase issues and preserves config error categorization."""
    app_paths = default_application_paths(tmp_path)
    library_root = tmp_path / "library"
    library_root.mkdir()
    with SQLiteUnitOfWork(app_paths.database_file) as uow:
        uow.libraries.save(_library(str(library_root), status=LibraryStatus.BLOCKED))
        uow.commit()
    client = TestClient(create_web_app(app_paths.config_file, app_paths.database_file))

    response = client.get(WEB_API_CHECK_ROUTE)

    assert response.status_code == SUCCESS_STATUS_CODE
    assert response.json()["errors"] == []
    assert response.json()["issues"][0]["issue_type"] == "library_blocked"
    assert response.json()["issues"][0]["library_id"] == str(LIBRARY_ID)

    app_paths.config_file.parent.mkdir(parents=True)
    _ = app_paths.config_file.write_text("version = ", encoding=CONFIG_FILE_ENCODING)
    invalid_response = client.get(WEB_API_CHECK_ROUTE)

    assert invalid_response.status_code == ERROR_STATUS_CODE
    assert invalid_response.json()["issues"] == []
    assert "Invalid TOML" in invalid_response.json()["errors"][0]


def _library(library_root: str, *, status: LibraryStatus = LibraryStatus.REGISTERED) -> Library:
    return Library(
        library_id=LIBRARY_ID,
        root_path=library_root,
        path_policy_hash=calculate_path_policy_fingerprint(
            default_app_config().path_policy,
            default_app_config().artist_ids,
        ),
        registered_at=BASE_TIME,
        status=status,
        created_at=BASE_TIME,
        updated_at=BASE_TIME,
    )
