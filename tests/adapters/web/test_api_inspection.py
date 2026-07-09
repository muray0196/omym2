"""
Summary: Tests Web check JSON API routes.
Why: Verifies persisted check browsing (list/facets/groups) and the recompute-and-persist POST
route for the React UI. Tracks browsing is covered in test_api_tracks.py, Plan browsing in
test_api_plans.py, and Run/FileEvent browsing in test_api_history.py.
"""

from __future__ import annotations

from datetime import UTC, datetime
from typing import TYPE_CHECKING, Protocol, cast
from uuid import UUID

from fastapi.testclient import TestClient

from omym2.adapters.config.application_paths import default_application_paths
from omym2.adapters.config.default_config import default_app_config
from omym2.adapters.db.sqlite.unit_of_work import SQLiteUnitOfWork
from omym2.config import (
    WEB_API_CHECK_FACETS_ROUTE,
    WEB_API_CHECK_GROUPS_ROUTE,
    WEB_API_CHECK_ROUTE,
    WEB_API_CHECK_RUN_ROUTE,
    WEB_API_SETTINGS_ROUTE,
    WEB_CSRF_HEADER_NAME,
)
from omym2.domain.models.check_issue import CheckIssue, CheckIssueType
from omym2.domain.models.check_run import CheckRun
from omym2.domain.models.library import Library, LibraryStatus
from omym2.domain.services.config_fingerprint import calculate_path_policy_fingerprint
from omym2.platform.web_composition import build_web_app as create_web_app
from omym2.shared.ids import CheckRunId, LibraryId
from omym2.shared.pagination import MAX_PAGE_LIMIT

if TYPE_CHECKING:
    from pathlib import Path

BASE_TIME = datetime(2026, 1, 1, tzinfo=UTC)
ERROR_STATUS_CODE = 400
FORBIDDEN_STATUS_CODE = 403
SUCCESS_STATUS_CODE = 200
LIBRARY_ID = LibraryId(UUID("018f6a4f-3c2d-7b8a-9abc-def012345678"))
SECOND_LIBRARY_ID = LibraryId(UUID("018f6a4f-3c2d-7b8a-9abc-def012345679"))
CHECK_RUN_ID = CheckRunId(UUID("018f6a4f-3c2d-7b8a-9abc-def01234567a"))
SECOND_CHECK_RUN_ID = CheckRunId(UUID("018f6a4f-3c2d-7b8a-9abc-def01234567b"))
FIVE_ISSUE_TOTAL = 5
TWO_ITEM_LIMIT = 2
THREE_ISSUE_STATUS_TOTAL = 3
TWO_ISSUE_GROUP_TOTAL = 2
CLAMPED_LIMIT_REQUEST = 1000


class _JsonResponse(Protocol):
    def json(self) -> object: ...


def test_check_api_paginates_forward_with_keyset_cursor_and_terminates(tmp_path: Path) -> None:
    """A limit=2 walk over 5 persisted CheckIssues visits every issue once, then next_cursor is null."""
    app_paths = default_application_paths(tmp_path)
    library_root = tmp_path / "library"
    library_root.mkdir()
    with SQLiteUnitOfWork(app_paths.database_file) as uow:
        uow.libraries.save(_library(str(library_root)))
        uow.check_runs.save(_check_run())
        uow.check_issues.save_many(CHECK_RUN_ID, tuple(_issue(path=f"{index}/1.flac") for index in range(5)))
        uow.commit()
    client = TestClient(create_web_app(app_paths.config_file, app_paths.database_file))

    visited: list[str | None] = []
    cursor: str | None = None
    last_page: dict[str, object] | None = None
    for _ in range(FIVE_ISSUE_TOTAL + 1):
        params = {"limit": str(TWO_ITEM_LIMIT)} | ({"cursor": cursor} if cursor else {})
        response = client.get(WEB_API_CHECK_ROUTE, params=params)
        assert response.status_code == SUCCESS_STATUS_CODE
        payload = _json_payload(response)
        items = _object_list_payload(payload, "items")
        page = _object_payload(payload, "page")
        visited.extend(cast("str", item["path"]) for item in items)
        assert page["total"] == FIVE_ISSUE_TOTAL
        assert payload["checked_at"] == BASE_TIME.isoformat()
        last_page = page
        next_cursor = page["next_cursor"]
        if next_cursor is None:
            break
        cursor = cast("str", next_cursor)

    assert visited == [f"{index}/1.flac" for index in range(5)]
    assert len(visited) == len(set(visited))
    assert last_page is not None
    assert last_page["next_cursor"] is None


def test_check_api_filters_by_issue_type(tmp_path: Path) -> None:
    """The issue_type filter only returns CheckIssues with a matching issue_type."""
    app_paths = default_application_paths(tmp_path)
    library_root = tmp_path / "library"
    library_root.mkdir()
    with SQLiteUnitOfWork(app_paths.database_file) as uow:
        uow.libraries.save(_library(str(library_root)))
        uow.check_runs.save(_check_run())
        uow.check_issues.save_many(
            CHECK_RUN_ID,
            (
                _issue(issue_type=CheckIssueType.DB_FILE_MISSING, path="A/1.flac"),
                _issue(issue_type=CheckIssueType.UNMANAGED_FILE_EXISTS, path="B/1.flac"),
            ),
        )
        uow.commit()
    client = TestClient(create_web_app(app_paths.config_file, app_paths.database_file))

    response = client.get(WEB_API_CHECK_ROUTE, params={"issue_type": "db_file_missing"})

    assert response.status_code == SUCCESS_STATUS_CODE
    payload = _json_payload(response)
    items = _object_list_payload(payload, "items")
    assert [item["path"] for item in items] == ["A/1.flac"]


def test_check_api_filters_by_library_id(tmp_path: Path) -> None:
    """The library_id filter scopes CheckIssues to one Library."""
    app_paths = default_application_paths(tmp_path)
    library_root = tmp_path / "library"
    second_root = tmp_path / "second-library"
    library_root.mkdir()
    second_root.mkdir()
    with SQLiteUnitOfWork(app_paths.database_file) as uow:
        uow.libraries.save(_library(str(library_root)))
        uow.libraries.save(_library(str(second_root), library_id=SECOND_LIBRARY_ID))
        uow.check_runs.save(_check_run())
        uow.check_runs.save(_check_run(check_run_id=SECOND_CHECK_RUN_ID, library_id=SECOND_LIBRARY_ID))
        uow.check_issues.save_many(CHECK_RUN_ID, (_issue(path="A/1.flac"),))
        uow.check_issues.save_many(SECOND_CHECK_RUN_ID, (_issue(library_id=SECOND_LIBRARY_ID, path="B/1.flac"),))
        uow.commit()
    client = TestClient(create_web_app(app_paths.config_file, app_paths.database_file))

    response = client.get(WEB_API_CHECK_ROUTE, params={"library_id": str(LIBRARY_ID)})

    assert response.status_code == SUCCESS_STATUS_CODE
    payload = _json_payload(response)
    items = _object_list_payload(payload, "items")
    assert [item["path"] for item in items] == ["A/1.flac"]


def test_check_api_returns_checked_at_null_with_empty_items_on_fresh_db(tmp_path: Path) -> None:
    """A fresh DB with no check run ever completed returns checked_at null and empty items."""
    app_paths = default_application_paths(tmp_path)
    client = TestClient(create_web_app(app_paths.config_file, app_paths.database_file))

    response = client.get(WEB_API_CHECK_ROUTE)

    assert response.status_code == SUCCESS_STATUS_CODE
    payload = _json_payload(response)
    assert payload["items"] == []
    assert payload["checked_at"] is None


def test_check_api_rejects_invalid_cursor(tmp_path: Path) -> None:
    """An undecodable cursor returns the documented 400 invalid-cursor envelope."""
    app_paths = default_application_paths(tmp_path)
    client = TestClient(create_web_app(app_paths.config_file, app_paths.database_file))

    response = client.get(WEB_API_CHECK_ROUTE, params={"cursor": "not-valid-base64url!!"})

    assert response.status_code == ERROR_STATUS_CODE
    assert response.json() == {"items": [], "page": None, "errors": ["Invalid cursor."]}


def test_check_api_rejects_invalid_issue_type_filter(tmp_path: Path) -> None:
    """An unknown issue_type filter value returns a 400 with items/page emptied."""
    app_paths = default_application_paths(tmp_path)
    client = TestClient(create_web_app(app_paths.config_file, app_paths.database_file))

    response = client.get(WEB_API_CHECK_ROUTE, params={"issue_type": "not-a-type"})

    assert response.status_code == ERROR_STATUS_CODE
    payload = _json_payload(response)
    assert payload["items"] == []
    assert payload["page"] is None
    assert payload["errors"] == ["Invalid issue_type filter: not-a-type"]


def test_check_api_rejects_limit_below_one(tmp_path: Path) -> None:
    """limit=0 is a request error, not a silently substituted default."""
    app_paths = default_application_paths(tmp_path)
    client = TestClient(create_web_app(app_paths.config_file, app_paths.database_file))

    response = client.get(WEB_API_CHECK_ROUTE, params={"limit": "0"})

    assert response.status_code == ERROR_STATUS_CODE
    payload = _json_payload(response)
    assert payload["items"] == []
    assert payload["page"] is None


def test_check_api_clamps_limit_above_maximum(tmp_path: Path) -> None:
    """A limit above 500 is clamped down to 500, not rejected."""
    app_paths = default_application_paths(tmp_path)
    client = TestClient(create_web_app(app_paths.config_file, app_paths.database_file))

    response = client.get(WEB_API_CHECK_ROUTE, params={"limit": str(CLAMPED_LIMIT_REQUEST)})

    assert response.status_code == SUCCESS_STATUS_CODE
    payload = _json_payload(response)
    page = _object_payload(payload, "page")
    assert page["limit"] == MAX_PAGE_LIMIT


def test_check_facets_api_returns_issue_type_counts_and_checked_at(tmp_path: Path) -> None:
    """Facets returns issue_type value/count pairs ordered count DESC then value ASC, plus checked_at."""
    app_paths = default_application_paths(tmp_path)
    library_root = tmp_path / "library"
    library_root.mkdir()
    with SQLiteUnitOfWork(app_paths.database_file) as uow:
        uow.libraries.save(_library(str(library_root)))
        uow.check_runs.save(_check_run())
        uow.check_issues.save_many(
            CHECK_RUN_ID,
            (
                _issue(issue_type=CheckIssueType.DB_FILE_MISSING, path="A/1.flac"),
                _issue(issue_type=CheckIssueType.DB_FILE_MISSING, path="B/1.flac"),
                _issue(issue_type=CheckIssueType.UNMANAGED_FILE_EXISTS, path="C/1.flac"),
            ),
        )
        uow.commit()
    client = TestClient(create_web_app(app_paths.config_file, app_paths.database_file))

    response = client.get(WEB_API_CHECK_FACETS_ROUTE)

    assert response.status_code == SUCCESS_STATUS_CODE
    payload = _json_payload(response)
    facets = _object_payload(payload, "facets")
    assert facets["issue_type"] == [
        {"value": CheckIssueType.DB_FILE_MISSING.value, "count": 2},
        {"value": CheckIssueType.UNMANAGED_FILE_EXISTS.value, "count": 1},
    ]
    assert payload["total"] == THREE_ISSUE_STATUS_TOTAL
    assert payload["checked_at"] == BASE_TIME.isoformat()
    assert payload["errors"] == []


def test_check_facets_api_returns_checked_at_null_on_fresh_db(tmp_path: Path) -> None:
    """Facets returns checked_at null when no check run has ever completed."""
    app_paths = default_application_paths(tmp_path)
    client = TestClient(create_web_app(app_paths.config_file, app_paths.database_file))

    response = client.get(WEB_API_CHECK_FACETS_ROUTE)

    assert response.status_code == SUCCESS_STATUS_CODE
    payload = _json_payload(response)
    assert payload["total"] == 0
    assert payload["checked_at"] is None


def test_check_groups_api_returns_ordered_groups_with_keyset(tmp_path: Path) -> None:
    """Groups are ordered count DESC/key ASC, and the (count, key) keyset walks every group once."""
    app_paths = default_application_paths(tmp_path)
    library_root = tmp_path / "library"
    library_root.mkdir()
    with SQLiteUnitOfWork(app_paths.database_file) as uow:
        uow.libraries.save(_library(str(library_root)))
        uow.check_runs.save(_check_run())
        uow.check_issues.save_many(
            CHECK_RUN_ID,
            (
                _issue(issue_type=CheckIssueType.DB_FILE_MISSING, path="A/1.flac"),
                _issue(issue_type=CheckIssueType.DB_FILE_MISSING, path="B/1.flac"),
                _issue(issue_type=CheckIssueType.UNMANAGED_FILE_EXISTS, path="C/1.flac"),
            ),
        )
        uow.commit()
    client = TestClient(create_web_app(app_paths.config_file, app_paths.database_file))

    first_response = client.get(WEB_API_CHECK_GROUPS_ROUTE, params={"group_by": "issue_type", "limit": "1"})

    assert first_response.status_code == SUCCESS_STATUS_CODE
    first_payload = _json_payload(first_response)
    assert first_payload["group_by"] == "issue_type"
    first_items = _object_list_payload(first_payload, "items")
    assert first_items == [
        {"key": CheckIssueType.DB_FILE_MISSING.value, "label": CheckIssueType.DB_FILE_MISSING.value, "count": 2}
    ]
    first_page = _object_payload(first_payload, "page")
    assert first_page["total"] == TWO_ISSUE_GROUP_TOTAL
    next_cursor = first_page["next_cursor"]
    assert next_cursor is not None

    second_response = client.get(
        WEB_API_CHECK_GROUPS_ROUTE,
        params={"group_by": "issue_type", "limit": "1", "cursor": cast("str", next_cursor)},
    )

    assert second_response.status_code == SUCCESS_STATUS_CODE
    second_payload = _json_payload(second_response)
    second_items = _object_list_payload(second_payload, "items")
    assert second_items == [
        {
            "key": CheckIssueType.UNMANAGED_FILE_EXISTS.value,
            "label": CheckIssueType.UNMANAGED_FILE_EXISTS.value,
            "count": 1,
        }
    ]
    second_page = _object_payload(second_payload, "page")
    assert second_page["next_cursor"] is None


def test_check_groups_api_rejects_invalid_group_by(tmp_path: Path) -> None:
    """An unknown group_by value returns a 400 with items/page emptied and group_by null."""
    app_paths = default_application_paths(tmp_path)
    client = TestClient(create_web_app(app_paths.config_file, app_paths.database_file))

    response = client.get(WEB_API_CHECK_GROUPS_ROUTE, params={"group_by": "not-a-grouping"})

    assert response.status_code == ERROR_STATUS_CODE
    payload = _json_payload(response)
    assert payload["group_by"] is None
    assert payload["items"] == []
    assert payload["page"] is None
    assert payload["errors"] == ["Invalid group_by filter: not-a-grouping"]


def test_check_groups_api_requires_group_by(tmp_path: Path) -> None:
    """A missing group_by value is a request error, not a silent default."""
    app_paths = default_application_paths(tmp_path)
    client = TestClient(create_web_app(app_paths.config_file, app_paths.database_file))

    response = client.get(WEB_API_CHECK_GROUPS_ROUTE)

    assert response.status_code == ERROR_STATUS_CODE
    assert response.json()["errors"] == ["Query parameter group_by is required."]


def test_check_run_api_recomputes_persists_and_get_reflects_it(tmp_path: Path) -> None:
    """POST /api/check/run recomputes and persists findings that a subsequent GET then reads."""
    app_paths = default_application_paths(tmp_path)
    library_root = tmp_path / "library"
    library_root.mkdir()
    with SQLiteUnitOfWork(app_paths.database_file) as uow:
        uow.libraries.save(_library(str(library_root), status=LibraryStatus.BLOCKED))
        uow.commit()
    client = TestClient(create_web_app(app_paths.config_file, app_paths.database_file))

    run_response = client.post(
        WEB_API_CHECK_RUN_ROUTE,
        json={},
        headers={WEB_CSRF_HEADER_NAME: _csrf_token(client)},
    )

    assert run_response.status_code == SUCCESS_STATUS_CODE
    run_payload = _json_payload(run_response)
    assert run_payload["errors"] == []
    assert isinstance(run_payload["checked_at"], str)
    total = run_payload["total"]
    assert isinstance(total, int)
    assert total >= 1

    get_response = client.get(WEB_API_CHECK_ROUTE)
    get_payload = _json_payload(get_response)
    items = _object_list_payload(get_payload, "items")
    assert any(item["issue_type"] == "library_blocked" for item in items)
    assert get_payload["checked_at"] == run_payload["checked_at"]
    page = _object_payload(get_payload, "page")
    assert page["total"] == total


def test_check_run_api_scopes_to_one_library(tmp_path: Path) -> None:
    """POST /api/check/run with a library_id body only recomputes and persists that Library."""
    app_paths = default_application_paths(tmp_path)
    library_root = tmp_path / "library"
    second_root = tmp_path / "second-library"
    library_root.mkdir()
    second_root.mkdir()
    with SQLiteUnitOfWork(app_paths.database_file) as uow:
        uow.libraries.save(_library(str(library_root), status=LibraryStatus.BLOCKED))
        uow.libraries.save(_library(str(second_root), library_id=SECOND_LIBRARY_ID, status=LibraryStatus.BLOCKED))
        uow.commit()
    client = TestClient(create_web_app(app_paths.config_file, app_paths.database_file))

    response = client.post(
        WEB_API_CHECK_RUN_ROUTE,
        json={"library_id": str(LIBRARY_ID)},
        headers={WEB_CSRF_HEADER_NAME: _csrf_token(client)},
    )

    assert response.status_code == SUCCESS_STATUS_CODE
    with SQLiteUnitOfWork(app_paths.database_file) as uow:
        assert uow.check_runs.latest(LIBRARY_ID) is not None
        assert uow.check_runs.latest(SECOND_LIBRARY_ID) is None


def test_check_run_api_requires_csrf_token(tmp_path: Path) -> None:
    """Check run POSTs reject requests without the Web CSRF header."""
    app_paths = default_application_paths(tmp_path)
    client = TestClient(create_web_app(app_paths.config_file, app_paths.database_file))

    response = client.post(WEB_API_CHECK_RUN_ROUTE, json={})

    assert response.status_code == FORBIDDEN_STATUS_CODE
    assert response.json() == {
        "checked_at": None,
        "total": None,
        "errors": ["Check run request failed CSRF validation."],
    }


def _json_payload(response: _JsonResponse) -> dict[str, object]:
    return cast("dict[str, object]", response.json())


def _object_payload(payload: dict[str, object], key: str) -> dict[str, object]:
    value = payload[key]
    assert isinstance(value, dict)
    return cast("dict[str, object]", value)


def _object_list_payload(payload: dict[str, object], key: str) -> list[dict[str, object]]:
    value = payload[key]
    assert isinstance(value, list)
    return cast("list[dict[str, object]]", value)


def _csrf_token(client: TestClient) -> str:
    response = client.get(WEB_API_SETTINGS_ROUTE)
    assert response.status_code == SUCCESS_STATUS_CODE
    token = _json_payload(response)["csrf_token"]
    assert isinstance(token, str)
    return token


def _library(
    library_root: str,
    *,
    library_id: LibraryId = LIBRARY_ID,
    status: LibraryStatus = LibraryStatus.REGISTERED,
) -> Library:
    return Library(
        library_id=library_id,
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


def _check_run(
    *,
    check_run_id: CheckRunId = CHECK_RUN_ID,
    library_id: LibraryId = LIBRARY_ID,
    checked_at: datetime = BASE_TIME,
) -> CheckRun:
    return CheckRun(check_run_id=check_run_id, library_id=library_id, checked_at=checked_at, total_count=1)


def _issue(
    *,
    library_id: LibraryId = LIBRARY_ID,
    issue_type: CheckIssueType = CheckIssueType.UNMANAGED_FILE_EXISTS,
    path: str = "A/1.flac",
) -> CheckIssue:
    return CheckIssue(issue_type=issue_type, library_id=library_id, path=path)
