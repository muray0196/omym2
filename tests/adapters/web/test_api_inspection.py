"""
Summary: Tests Web inspection JSON API routes.
Why: Verifies history, check, and Tracks data for the React UI.
"""

from __future__ import annotations

from datetime import UTC, datetime
from typing import TYPE_CHECKING, Protocol, cast
from uuid import UUID

from fastapi.testclient import TestClient

from omym2.adapters.config.application_paths import default_application_paths
from omym2.adapters.config.default_config import default_app_config
from omym2.adapters.db.sqlite.unit_of_work import SQLiteUnitOfWork
from omym2.adapters.web.app import create_web_app
from omym2.config import (
    CONFIG_FILE_ENCODING,
    WEB_API_CHECK_ROUTE,
    WEB_API_HISTORY_ROUTE,
    WEB_API_TRACKS_ROUTE,
)
from omym2.domain.models.file_event import FileEvent, FileEventStatus, FileEventType
from omym2.domain.models.library import Library, LibraryStatus
from omym2.domain.models.plan import Plan, PlanStatus, PlanType
from omym2.domain.models.plan_action import ActionStatus, ActionType, PlanAction
from omym2.domain.models.run import Run, RunStatus
from omym2.domain.models.track import Track, TrackStatus
from omym2.domain.models.track_metadata import TrackMetadata
from omym2.domain.services.config_fingerprint import calculate_config_fingerprint, calculate_path_policy_fingerprint
from omym2.shared.ids import ActionId, EventId, LibraryId, PlanId, RunId, TrackId

if TYPE_CHECKING:
    from pathlib import Path

ACTION_ID = ActionId(UUID("018f6a4f-3c2d-7b8a-9abc-def01234567b"))
BASE_TIME = datetime(2026, 1, 1, tzinfo=UTC)
CONTENT_HASH = "content"
EVENT_ID = EventId(UUID("018f6a4f-3c2d-7b8a-9abc-def01234567e"))
ERROR_STATUS_CODE = 400
INVALID_RUN_ID_TEXT = "not-a-uuid"
LIBRARY_ID = LibraryId(UUID("018f6a4f-3c2d-7b8a-9abc-def012345678"))
METADATA_HASH = "metadata"
MISSING_RUN_ID = RunId(UUID("018f6a4f-3c2d-7b8a-9abc-def012345699"))
PLAN_ID = PlanId(UUID("018f6a4f-3c2d-7b8a-9abc-def01234567a"))
RUN_ID = RunId(UUID("018f6a4f-3c2d-7b8a-9abc-def01234567d"))
SUCCESS_STATUS_CODE = 200
NOT_FOUND_STATUS_CODE = 404
SERVER_ERROR_STATUS_CODE = 500
SOURCE_PATH = "/incoming/Imported.flac"
TARGET_PATH = "Artist/2026_Album/1-02_Title.flac"
TRACK_ID = TrackId(UUID("018f6a4f-3c2d-7b8a-9abc-def012345679"))
TRACK_ALBUM = "Album"
TRACK_ARTIST = "Artist"
TRACK_TITLE = "Title"

METADATA = TrackMetadata(title=TRACK_TITLE, artist=TRACK_ARTIST, album=TRACK_ALBUM, year=2026, track_number=2)


class _JsonResponse(Protocol):
    def json(self) -> object: ...


def test_history_api_lists_runs(tmp_path: Path) -> None:
    """History API returns persisted Runs newest-first."""
    app_paths = default_application_paths(tmp_path)
    library_root = tmp_path / "library"
    library_root.mkdir()
    _seed_run_history(app_paths.database_file, str(library_root))
    client = TestClient(create_web_app(app_paths.config_file, app_paths.database_file))

    response = client.get(WEB_API_HISTORY_ROUTE)

    assert response.status_code == SUCCESS_STATUS_CODE
    assert response.json()["errors"] == []
    assert response.json()["runs"] == [
        {
            "run_id": str(RUN_ID),
            "plan_id": str(PLAN_ID),
            "library_id": str(LIBRARY_ID),
            "status": RunStatus.SUCCEEDED.value,
            "started_at": BASE_TIME.isoformat(),
            "completed_at": BASE_TIME.isoformat(),
            "error_summary": None,
        }
    ]


def test_history_api_returns_empty_runs(tmp_path: Path) -> None:
    """History API reports an empty database without an error."""
    app_paths = default_application_paths(tmp_path)
    client = TestClient(create_web_app(app_paths.config_file, app_paths.database_file))

    response = client.get(WEB_API_HISTORY_ROUTE)

    assert response.status_code == SUCCESS_STATUS_CODE
    assert response.json() == {"runs": [], "errors": []}


def test_run_detail_api_lists_file_events(tmp_path: Path) -> None:
    """Run detail API returns one Run and its durable FileEvents."""
    app_paths = default_application_paths(tmp_path)
    library_root = tmp_path / "library"
    library_root.mkdir()
    _seed_run_history(app_paths.database_file, str(library_root))
    client = TestClient(create_web_app(app_paths.config_file, app_paths.database_file))

    response = client.get(f"{WEB_API_HISTORY_ROUTE}/{RUN_ID}")

    assert response.status_code == SUCCESS_STATUS_CODE
    payload = _json_payload(response)
    detail = _object_payload(payload, "detail")
    run = _object_payload(detail, "run")
    first_event = _object_list_payload(detail, "file_events")[0]
    assert payload["errors"] == []
    assert run["run_id"] == str(RUN_ID)
    assert first_event["event_id"] == str(EVENT_ID)
    assert first_event["plan_action_id"] == str(ACTION_ID)
    assert first_event["source_path"] == SOURCE_PATH
    assert first_event["target_path"] == TARGET_PATH
    assert first_event["event_type"] == FileEventType.MOVE_FILE.value
    assert first_event["status"] == FileEventStatus.SUCCEEDED.value
    assert first_event["sequence_no"] == 1


def test_run_detail_api_returns_not_found_for_missing_or_invalid_run(tmp_path: Path) -> None:
    """Run detail API reports missing and malformed Run IDs as not found."""
    app_paths = default_application_paths(tmp_path)
    client = TestClient(create_web_app(app_paths.config_file, app_paths.database_file))

    missing_response = client.get(f"{WEB_API_HISTORY_ROUTE}/{MISSING_RUN_ID}")
    invalid_response = client.get(f"{WEB_API_HISTORY_ROUTE}/{INVALID_RUN_ID_TEXT}")

    assert missing_response.status_code == NOT_FOUND_STATUS_CODE
    assert missing_response.json() == {"detail": None, "errors": ["Run was not found."]}
    assert invalid_response.status_code == NOT_FOUND_STATUS_CODE
    assert invalid_response.json() == {"detail": None, "errors": ["Run was not found."]}


def test_history_api_reports_database_errors(tmp_path: Path) -> None:
    """History API reports database startup errors as JSON."""
    app_paths = default_application_paths(tmp_path)
    invalid_database_path = tmp_path / "not-a-database"
    invalid_database_path.mkdir()
    client = TestClient(create_web_app(app_paths.config_file, invalid_database_path))

    response = client.get(WEB_API_HISTORY_ROUTE)

    assert response.status_code == SERVER_ERROR_STATUS_CODE
    assert response.json()["runs"] == []
    assert "Inspection failed" in response.json()["errors"][0]


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


def test_tracks_api_returns_empty_and_managed_tracks(tmp_path: Path) -> None:
    """Tracks API returns managed Track state without checking the filesystem."""
    app_paths = default_application_paths(tmp_path)
    client = TestClient(create_web_app(app_paths.config_file, app_paths.database_file))

    empty_response = client.get(WEB_API_TRACKS_ROUTE)

    assert empty_response.status_code == SUCCESS_STATUS_CODE
    assert empty_response.json() == {"tracks": [], "errors": []}

    library_root = tmp_path / "library"
    library_root.mkdir()
    with SQLiteUnitOfWork(app_paths.database_file) as uow:
        uow.libraries.save(_library(str(library_root)))
        uow.tracks.save(_track())
        uow.commit()

    response = client.get(WEB_API_TRACKS_ROUTE)

    assert response.status_code == SUCCESS_STATUS_CODE
    payload = _json_payload(response)
    first_track = _object_list_payload(payload, "tracks")[0]
    metadata = _object_payload(first_track, "metadata")
    assert payload["errors"] == []
    assert first_track["track_id"] == str(TRACK_ID)
    assert first_track["library_id"] == str(LIBRARY_ID)
    assert first_track["status"] == TrackStatus.ACTIVE.value
    assert first_track["current_path"] == TARGET_PATH
    assert metadata["title"] == TRACK_TITLE
    assert metadata["artist"] == TRACK_ARTIST
    assert metadata["album"] == TRACK_ALBUM


def test_tracks_api_reports_database_errors(tmp_path: Path) -> None:
    """Tracks API reports database startup errors as JSON."""
    app_paths = default_application_paths(tmp_path)
    invalid_database_path = tmp_path / "not-a-database"
    invalid_database_path.mkdir()
    client = TestClient(create_web_app(app_paths.config_file, invalid_database_path))

    response = client.get(WEB_API_TRACKS_ROUTE)

    assert response.status_code == SERVER_ERROR_STATUS_CODE
    assert response.json()["tracks"] == []
    assert "Inspection failed" in response.json()["errors"][0]


def _seed_run_history(database_file: Path, library_root: str) -> None:
    with SQLiteUnitOfWork(database_file) as uow:
        uow.libraries.save(_library(library_root))
        uow.plans.save(_plan(library_root))
        uow.plan_actions.save(_action())
        uow.runs.save(_run())
        uow.file_events.save(_event())
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


def _library(library_root: str, *, status: LibraryStatus = LibraryStatus.REGISTERED) -> Library:
    return Library(
        library_id=LIBRARY_ID,
        root_path=library_root,
        path_policy_hash=calculate_path_policy_fingerprint(default_app_config().path_policy),
        registered_at=BASE_TIME,
        status=status,
        created_at=BASE_TIME,
        updated_at=BASE_TIME,
    )


def _track() -> Track:
    return Track(
        track_id=TRACK_ID,
        library_id=LIBRARY_ID,
        current_path=TARGET_PATH,
        canonical_path=TARGET_PATH,
        content_hash=CONTENT_HASH,
        metadata_hash=METADATA_HASH,
        metadata=METADATA,
        status=TrackStatus.ACTIVE,
        first_seen_at=BASE_TIME,
        last_seen_at=BASE_TIME,
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


def _run() -> Run:
    return Run(
        run_id=RUN_ID,
        plan_id=PLAN_ID,
        library_id=LIBRARY_ID,
        status=RunStatus.SUCCEEDED,
        started_at=BASE_TIME,
        completed_at=BASE_TIME,
    )


def _event() -> FileEvent:
    return FileEvent(
        event_id=EVENT_ID,
        library_id=LIBRARY_ID,
        run_id=RUN_ID,
        plan_action_id=ACTION_ID,
        event_type=FileEventType.MOVE_FILE,
        source_path=SOURCE_PATH,
        target_path=TARGET_PATH,
        status=FileEventStatus.SUCCEEDED,
        started_at=BASE_TIME,
        completed_at=BASE_TIME,
        error_code=None,
        error_message=None,
        sequence_no=1,
    )
