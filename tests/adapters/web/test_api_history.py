"""
Summary: Tests Web Run history JSON API routes.
Why: Verifies keyset paged Run/FileEvent browsing, status facets, and the header-only Run detail contract.
"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from typing import TYPE_CHECKING, Protocol, cast
from uuid import UUID

from fastapi.testclient import TestClient

from omym2.adapters.config.application_paths import default_application_paths
from omym2.adapters.config.default_config import default_app_config
from omym2.adapters.db.sqlite.unit_of_work import SQLiteUnitOfWork
from omym2.config import WEB_API_HISTORY_FACETS_ROUTE, WEB_API_HISTORY_ROUTE
from omym2.domain.models.file_event import FileEvent, FileEventStatus, FileEventType
from omym2.domain.models.library import Library, LibraryStatus
from omym2.domain.models.plan import Plan, PlanStatus, PlanType
from omym2.domain.models.plan_action import ActionStatus, ActionType, PlanAction
from omym2.domain.models.run import Run, RunStatus
from omym2.domain.services.config_fingerprint import calculate_config_fingerprint, calculate_path_policy_fingerprint
from omym2.platform.web_composition import build_web_app as create_web_app
from omym2.shared.ids import ActionId, EventId, LibraryId, PlanId, RunId
from omym2.shared.pagination import MAX_PAGE_LIMIT

if TYPE_CHECKING:
    from pathlib import Path

ACTION_ID = ActionId(UUID("018f6a4f-3c2d-7b8a-9abc-def01234567b"))
BASE_TIME = datetime(2026, 1, 1, tzinfo=UTC)
CONTENT_HASH = "content"
METADATA_HASH = "metadata"
ERROR_STATUS_CODE = 400
SERVER_ERROR_STATUS_CODE = 500
SUCCESS_STATUS_CODE = 200
NOT_FOUND_STATUS_CODE = 404
INVALID_RUN_ID_TEXT = "not-a-uuid"
LIBRARY_ID = LibraryId(UUID("018f6a4f-3c2d-7b8a-9abc-def012345678"))
SECOND_LIBRARY_ID = LibraryId(UUID("018f6a4f-3c2d-7b8a-9abc-def012345679"))
MISSING_RUN_ID = RunId(UUID("018f6a4f-3c2d-7b8a-9abc-def012345699"))
PLAN_ID = PlanId(UUID("018f6a4f-3c2d-7b8a-9abc-def01234567a"))
RUN_ID = RunId(UUID("018f6a4f-3c2d-7b8a-9abc-def0123456d1"))
SECOND_RUN_ID = RunId(UUID("018f6a4f-3c2d-7b8a-9abc-def0123456d2"))
THIRD_RUN_ID = RunId(UUID("018f6a4f-3c2d-7b8a-9abc-def0123456d3"))
EVENT_ID = EventId(UUID("018f6a4f-3c2d-7b8a-9abc-def01234567e"))
SECOND_EVENT_ID = EventId(UUID("018f6a4f-3c2d-7b8a-9abc-def01234567f"))
SOURCE_PATH = "/incoming/Imported.flac"
TARGET_PATH = "Artist/2026_Album/1-02_Title.flac"
SECOND_TARGET_PATH = "Artist/2026_Album/1-03_Title.flac"
ONE_ITEM_LIMIT = 1
CLAMPED_LIMIT_REQUEST = 1000
THREE_RUN_TOTAL = 3
TWO_EVENT_TOTAL = 2


class _JsonResponse(Protocol):
    def json(self) -> object: ...


def test_history_api_paginates_newest_first_with_keyset_cursor_and_terminates(tmp_path: Path) -> None:
    """A limit=1 walk over 3 Runs visits every Run once, newest first, then next_cursor is null."""
    app_paths = default_application_paths(tmp_path)
    library_root = tmp_path / "library"
    library_root.mkdir()
    _seed_run_pages(app_paths.database_file, str(library_root))
    client = TestClient(create_web_app(app_paths.config_file, app_paths.database_file))

    visited: list[str] = []
    cursor: str | None = None
    last_page: dict[str, object] | None = None
    for _ in range(THREE_RUN_TOTAL + 1):
        params = {"limit": str(ONE_ITEM_LIMIT)} | ({"cursor": cursor} if cursor else {})
        response = client.get(WEB_API_HISTORY_ROUTE, params=params)
        assert response.status_code == SUCCESS_STATUS_CODE
        payload = _json_payload(response)
        items = _object_list_payload(payload, "items")
        page = _object_payload(payload, "page")
        visited.extend(cast("str", item["run_id"]) for item in items)
        assert page["total"] == THREE_RUN_TOTAL
        assert page["limit"] == ONE_ITEM_LIMIT
        last_page = page
        next_cursor = page["next_cursor"]
        if next_cursor is None:
            break
        cursor = cast("str", next_cursor)

    assert visited == [str(THIRD_RUN_ID), str(SECOND_RUN_ID), str(RUN_ID)]
    assert len(visited) == len(set(visited))
    assert last_page is not None
    assert last_page["next_cursor"] is None


def test_history_api_breaks_started_at_ties_by_run_id_desc(tmp_path: Path) -> None:
    """Runs sharing one started_at are ordered and keyset-walked by run_id DESC."""
    app_paths = default_application_paths(tmp_path)
    library_root = tmp_path / "library"
    library_root.mkdir()
    run_ids = (RUN_ID, SECOND_RUN_ID, THIRD_RUN_ID)
    with SQLiteUnitOfWork(app_paths.database_file) as uow:
        uow.libraries.save(_library(str(library_root)))
        uow.plans.save(_plan(str(library_root)))
        for run_id in run_ids:
            uow.runs.save(_run(run_id=run_id, started_at=BASE_TIME))
        uow.commit()
    client = TestClient(create_web_app(app_paths.config_file, app_paths.database_file))

    visited: list[str] = []
    cursor: str | None = None
    for _ in range(len(run_ids)):
        params = {"limit": str(ONE_ITEM_LIMIT)} | ({"cursor": cursor} if cursor else {})
        response = client.get(WEB_API_HISTORY_ROUTE, params=params)
        assert response.status_code == SUCCESS_STATUS_CODE
        payload = _json_payload(response)
        items = _object_list_payload(payload, "items")
        visited.extend(cast("str", item["run_id"]) for item in items)
        next_cursor = _object_payload(payload, "page")["next_cursor"]
        if next_cursor is None:
            break
        cursor = cast("str", next_cursor)

    assert visited == [str(THIRD_RUN_ID), str(SECOND_RUN_ID), str(RUN_ID)]


def test_history_api_filters_by_status_and_library(tmp_path: Path) -> None:
    """Status and library_id filters combine as AND; page.total counts the filtered rows."""
    app_paths = default_application_paths(tmp_path)
    library_root = tmp_path / "library"
    library_root.mkdir()
    with SQLiteUnitOfWork(app_paths.database_file) as uow:
        uow.libraries.save(_library(str(library_root)))
        uow.libraries.save(_library(f"{library_root}-second", library_id=SECOND_LIBRARY_ID))
        uow.plans.save(_plan(str(library_root)))
        uow.runs.save(_run(run_id=RUN_ID, started_at=BASE_TIME, status=RunStatus.SUCCEEDED))
        uow.runs.save(_run(run_id=SECOND_RUN_ID, started_at=BASE_TIME + timedelta(minutes=1), status=RunStatus.FAILED))
        uow.runs.save(
            _run(
                run_id=THIRD_RUN_ID,
                started_at=BASE_TIME + timedelta(minutes=2),
                status=RunStatus.SUCCEEDED,
                library_id=SECOND_LIBRARY_ID,
            )
        )
        uow.commit()
    client = TestClient(create_web_app(app_paths.config_file, app_paths.database_file))

    response = client.get(
        WEB_API_HISTORY_ROUTE,
        params={"status": "succeeded", "library_id": str(LIBRARY_ID)},
    )

    assert response.status_code == SUCCESS_STATUS_CODE
    payload = _json_payload(response)
    items = _object_list_payload(payload, "items")
    page = _object_payload(payload, "page")
    assert [item["run_id"] for item in items] == [str(RUN_ID)]
    assert page["total"] == 1


def test_history_api_rejects_invalid_cursor_status_and_low_limit(tmp_path: Path) -> None:
    """Malformed cursors, unknown statuses, and limit=0 return the documented 400 envelope."""
    app_paths = default_application_paths(tmp_path)
    client = TestClient(create_web_app(app_paths.config_file, app_paths.database_file))

    cursor_response = client.get(WEB_API_HISTORY_ROUTE, params={"cursor": "not-valid-base64url!!"})
    status_response = client.get(WEB_API_HISTORY_ROUTE, params={"status": "not-a-status"})
    limit_response = client.get(WEB_API_HISTORY_ROUTE, params={"limit": "0"})

    assert cursor_response.status_code == ERROR_STATUS_CODE
    assert cursor_response.json() == {"items": [], "page": None, "errors": ["Invalid cursor."]}
    assert status_response.status_code == ERROR_STATUS_CODE
    assert status_response.json() == {
        "items": [],
        "page": None,
        "errors": ["Invalid run status filter: not-a-status"],
    }
    assert limit_response.status_code == ERROR_STATUS_CODE
    assert limit_response.json()["page"] is None


def test_history_api_clamps_limit_above_maximum(tmp_path: Path) -> None:
    """A limit above 500 is clamped down to 500, not rejected."""
    app_paths = default_application_paths(tmp_path)
    client = TestClient(create_web_app(app_paths.config_file, app_paths.database_file))

    response = client.get(WEB_API_HISTORY_ROUTE, params={"limit": str(CLAMPED_LIMIT_REQUEST)})

    assert response.status_code == SUCCESS_STATUS_CODE
    page = _object_payload(_json_payload(response), "page")
    assert page["limit"] == MAX_PAGE_LIMIT


def test_history_api_reports_database_errors(tmp_path: Path) -> None:
    """History API reports database startup errors as JSON."""
    app_paths = default_application_paths(tmp_path)
    invalid_database_path = tmp_path / "not-a-database"
    invalid_database_path.mkdir()
    client = TestClient(create_web_app(app_paths.config_file, invalid_database_path))

    response = client.get(WEB_API_HISTORY_ROUTE)

    assert response.status_code == SERVER_ERROR_STATUS_CODE
    assert response.json()["items"] == []
    assert response.json()["page"] is None
    assert "Inspection failed" in response.json()["errors"][0]


def test_history_facets_api_returns_status_counts(tmp_path: Path) -> None:
    """Facets returns status value/count pairs ordered count DESC then value ASC, plus total."""
    app_paths = default_application_paths(tmp_path)
    library_root = tmp_path / "library"
    library_root.mkdir()
    with SQLiteUnitOfWork(app_paths.database_file) as uow:
        uow.libraries.save(_library(str(library_root)))
        uow.plans.save(_plan(str(library_root)))
        uow.runs.save(_run(run_id=RUN_ID, started_at=BASE_TIME, status=RunStatus.SUCCEEDED))
        uow.runs.save(
            _run(run_id=SECOND_RUN_ID, started_at=BASE_TIME + timedelta(minutes=1), status=RunStatus.SUCCEEDED)
        )
        uow.runs.save(_run(run_id=THIRD_RUN_ID, started_at=BASE_TIME + timedelta(minutes=2), status=RunStatus.FAILED))
        uow.commit()
    client = TestClient(create_web_app(app_paths.config_file, app_paths.database_file))

    response = client.get(WEB_API_HISTORY_FACETS_ROUTE)

    assert response.status_code == SUCCESS_STATUS_CODE
    payload = _json_payload(response)
    facets = _object_payload(payload, "facets")
    assert facets["status"] == [
        {"value": RunStatus.SUCCEEDED.value, "count": 2},
        {"value": RunStatus.FAILED.value, "count": 1},
    ]
    assert payload["total"] == THREE_RUN_TOTAL
    assert payload["errors"] == []


def test_run_detail_api_returns_header_only(tmp_path: Path) -> None:
    """Run detail returns the header without an embedded file_events array."""
    app_paths = default_application_paths(tmp_path)
    library_root = tmp_path / "library"
    library_root.mkdir()
    _seed_run_detail(app_paths.database_file, str(library_root))
    client = TestClient(create_web_app(app_paths.config_file, app_paths.database_file))

    response = client.get(f"{WEB_API_HISTORY_ROUTE}/{RUN_ID}")

    assert response.status_code == SUCCESS_STATUS_CODE
    payload = _json_payload(response)
    detail = _object_payload(payload, "detail")
    run = _object_payload(detail, "run")
    assert payload["errors"] == []
    assert set(detail) == {"run"}
    assert run["run_id"] == str(RUN_ID)
    assert run["plan_id"] == str(PLAN_ID)
    assert run["status"] == RunStatus.SUCCEEDED.value


def test_run_detail_api_returns_not_found_for_missing_or_invalid_run(tmp_path: Path) -> None:
    """Run detail reports missing and malformed Run IDs as not found."""
    app_paths = default_application_paths(tmp_path)
    client = TestClient(create_web_app(app_paths.config_file, app_paths.database_file))

    missing_response = client.get(f"{WEB_API_HISTORY_ROUTE}/{MISSING_RUN_ID}")
    invalid_response = client.get(f"{WEB_API_HISTORY_ROUTE}/{INVALID_RUN_ID_TEXT}")

    assert missing_response.status_code == NOT_FOUND_STATUS_CODE
    assert missing_response.json() == {"detail": None, "errors": ["Run was not found."]}
    assert invalid_response.status_code == NOT_FOUND_STATUS_CODE
    assert invalid_response.json() == {"detail": None, "errors": ["Run was not found."]}


def test_run_events_api_paginates_with_keyset_cursor_and_terminates(tmp_path: Path) -> None:
    """A limit=1 walk over a Run's FileEvents visits every event once, in sequence order."""
    app_paths = default_application_paths(tmp_path)
    library_root = tmp_path / "library"
    library_root.mkdir()
    _seed_run_detail(app_paths.database_file, str(library_root))
    client = TestClient(create_web_app(app_paths.config_file, app_paths.database_file))

    visited: list[str] = []
    cursor: str | None = None
    for _ in range(TWO_EVENT_TOTAL + 1):
        params = {"limit": str(ONE_ITEM_LIMIT)} | ({"cursor": cursor} if cursor else {})
        response = client.get(f"{WEB_API_HISTORY_ROUTE}/{RUN_ID}/events", params=params)
        assert response.status_code == SUCCESS_STATUS_CODE
        payload = _json_payload(response)
        items = _object_list_payload(payload, "items")
        page = _object_payload(payload, "page")
        visited.extend(cast("str", item["event_id"]) for item in items)
        assert page["total"] == TWO_EVENT_TOTAL
        next_cursor = page["next_cursor"]
        if next_cursor is None:
            break
        cursor = cast("str", next_cursor)

    assert visited == [str(EVENT_ID), str(SECOND_EVENT_ID)]


def test_run_events_api_filters_by_status(tmp_path: Path) -> None:
    """The status filter only returns events with a matching status; total matches the filter."""
    app_paths = default_application_paths(tmp_path)
    library_root = tmp_path / "library"
    library_root.mkdir()
    _seed_run_detail(app_paths.database_file, str(library_root))
    client = TestClient(create_web_app(app_paths.config_file, app_paths.database_file))

    response = client.get(f"{WEB_API_HISTORY_ROUTE}/{RUN_ID}/events", params={"status": "failed"})

    assert response.status_code == SUCCESS_STATUS_CODE
    payload = _json_payload(response)
    items = _object_list_payload(payload, "items")
    page = _object_payload(payload, "page")
    assert [item["event_id"] for item in items] == [str(SECOND_EVENT_ID)]
    assert items[0]["status"] == FileEventStatus.FAILED.value
    assert page["total"] == 1


def test_run_events_api_rejects_invalid_status_and_cursor(tmp_path: Path) -> None:
    """Unknown status filters and malformed cursors return the documented 400 envelope."""
    app_paths = default_application_paths(tmp_path)
    library_root = tmp_path / "library"
    library_root.mkdir()
    _seed_run_detail(app_paths.database_file, str(library_root))
    client = TestClient(create_web_app(app_paths.config_file, app_paths.database_file))

    status_response = client.get(f"{WEB_API_HISTORY_ROUTE}/{RUN_ID}/events", params={"status": "moved"})
    cursor_response = client.get(
        f"{WEB_API_HISTORY_ROUTE}/{RUN_ID}/events",
        params={"cursor": "not-valid-base64url!!"},
    )

    assert status_response.status_code == ERROR_STATUS_CODE
    assert status_response.json() == {
        "items": [],
        "page": None,
        "errors": ["Invalid event status filter: moved"],
    }
    assert cursor_response.status_code == ERROR_STATUS_CODE
    assert cursor_response.json() == {"items": [], "page": None, "errors": ["Invalid cursor."]}


def test_run_events_api_returns_not_found_for_unknown_run(tmp_path: Path) -> None:
    """An unknown Run ID returns a 404 list envelope."""
    app_paths = default_application_paths(tmp_path)
    client = TestClient(create_web_app(app_paths.config_file, app_paths.database_file))

    response = client.get(f"{WEB_API_HISTORY_ROUTE}/{MISSING_RUN_ID}/events")

    assert response.status_code == NOT_FOUND_STATUS_CODE
    assert response.json() == {"items": [], "page": None, "errors": ["Run was not found."]}


def _seed_run_pages(database_file: Path, library_root: str) -> None:
    """Seed three Runs with distinct started_at timestamps for paging tests."""
    with SQLiteUnitOfWork(database_file) as uow:
        uow.libraries.save(_library(library_root))
        uow.plans.save(_plan(library_root))
        uow.runs.save(_run(run_id=RUN_ID, started_at=BASE_TIME))
        uow.runs.save(_run(run_id=SECOND_RUN_ID, started_at=BASE_TIME + timedelta(minutes=1)))
        uow.runs.save(_run(run_id=THIRD_RUN_ID, started_at=BASE_TIME + timedelta(minutes=2)))
        uow.commit()


def _seed_run_detail(database_file: Path, library_root: str) -> None:
    """Seed one Run with two FileEvents (one succeeded, one failed) in sequence order."""
    with SQLiteUnitOfWork(database_file) as uow:
        uow.libraries.save(_library(library_root))
        uow.plans.save(_plan(library_root))
        uow.plan_actions.save(_action())
        uow.runs.save(_run(run_id=RUN_ID, started_at=BASE_TIME))
        uow.file_events.save(
            _event(event_id=EVENT_ID, sequence_no=1, status=FileEventStatus.SUCCEEDED, target_path=TARGET_PATH)
        )
        uow.file_events.save(
            _event(
                event_id=SECOND_EVENT_ID,
                sequence_no=2,
                status=FileEventStatus.FAILED,
                target_path=SECOND_TARGET_PATH,
            )
        )
        uow.commit()


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


def _library(library_root: str, *, library_id: LibraryId = LIBRARY_ID) -> Library:
    return Library(
        library_id=library_id,
        root_path=library_root,
        path_policy_hash=calculate_path_policy_fingerprint(
            default_app_config().path_policy,
            default_app_config().artist_ids,
        ),
        registered_at=BASE_TIME,
        status=LibraryStatus.REGISTERED,
        created_at=BASE_TIME,
        updated_at=BASE_TIME,
    )


def _plan(library_root: str) -> Plan:
    return Plan(
        plan_id=PLAN_ID,
        library_id=LIBRARY_ID,
        plan_type=PlanType.ADD,
        status=PlanStatus.APPLIED,
        created_at=BASE_TIME,
        config_hash=calculate_config_fingerprint(default_app_config()),
        library_root_at_plan=library_root,
        summary={"action_count": "1"},
    )


def _action() -> PlanAction:
    return PlanAction(
        action_id=ACTION_ID,
        plan_id=PLAN_ID,
        library_id=LIBRARY_ID,
        track_id=None,
        action_type=ActionType.MOVE,
        source_path=SOURCE_PATH,
        target_path=TARGET_PATH,
        content_hash_at_plan=CONTENT_HASH,
        metadata_hash_at_plan=METADATA_HASH,
        status=ActionStatus.APPLIED,
        reason=None,
        sort_order=1,
    )


def _run(
    *,
    run_id: RunId,
    started_at: datetime,
    status: RunStatus = RunStatus.SUCCEEDED,
    library_id: LibraryId = LIBRARY_ID,
) -> Run:
    return Run(
        run_id=run_id,
        plan_id=PLAN_ID,
        library_id=library_id,
        status=status,
        started_at=started_at,
        completed_at=started_at,
    )


def _event(
    *,
    event_id: EventId,
    sequence_no: int,
    status: FileEventStatus,
    target_path: str,
) -> FileEvent:
    return FileEvent(
        event_id=event_id,
        library_id=LIBRARY_ID,
        run_id=RUN_ID,
        plan_action_id=ACTION_ID,
        event_type=FileEventType.MOVE_FILE,
        source_path=SOURCE_PATH,
        target_path=target_path,
        status=status,
        started_at=BASE_TIME,
        completed_at=BASE_TIME,
        error_code=None if status == FileEventStatus.SUCCEEDED else "error",
        error_message=None if status == FileEventStatus.SUCCEEDED else "failed to move",
        sequence_no=sequence_no,
    )
