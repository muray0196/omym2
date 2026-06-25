"""
Summary: Tests Phase 13 Web inspection routes.
Why: Verifies history, run detail, check, and Tracks render through HTTP.
"""

from __future__ import annotations

from datetime import UTC, datetime
from typing import TYPE_CHECKING
from uuid import UUID

from fastapi.testclient import TestClient

from omym2.adapters.config.application_paths import default_application_paths
from omym2.adapters.config.default_config import default_app_config
from omym2.adapters.db.sqlite.unit_of_work import SQLiteUnitOfWork
from omym2.adapters.web.app import create_web_app
from omym2.config import (
    CONFIG_FILE_ENCODING,
    WEB_CHECK_ROUTE,
    WEB_HISTORY_ROUTE,
    WEB_SETTINGS_ROUTE,
    WEB_TRACKS_ROUTE,
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


def test_history_page_lists_runs_and_links_to_detail(tmp_path: Path) -> None:
    """History screen renders persisted Runs through the Web route."""
    app_paths = default_application_paths(tmp_path)
    library_root = tmp_path / "library"
    library_root.mkdir()
    _seed_run_history(app_paths.database_file, str(library_root))
    client = TestClient(create_web_app(app_paths.config_file, app_paths.database_file))

    response = client.get(WEB_HISTORY_ROUTE)

    assert response.status_code == SUCCESS_STATUS_CODE
    assert "OMYM2 History" in response.text
    assert str(RUN_ID) in response.text
    assert f"/history/{RUN_ID}" in response.text
    assert str(PLAN_ID) in response.text
    assert str(LIBRARY_ID) in response.text
    assert RunStatus.SUCCEEDED.value in response.text


def test_history_page_renders_empty_state(tmp_path: Path) -> None:
    """History screen reports an empty database without an error."""
    app_paths = default_application_paths(tmp_path)
    client = TestClient(create_web_app(app_paths.config_file, app_paths.database_file))

    response = client.get(WEB_HISTORY_ROUTE)

    assert response.status_code == SUCCESS_STATUS_CODE
    assert "No runs." in response.text


def test_run_detail_page_lists_file_events(tmp_path: Path) -> None:
    """Run detail screen renders durable FileEvents in sequence order."""
    app_paths = default_application_paths(tmp_path)
    library_root = tmp_path / "library"
    library_root.mkdir()
    _seed_run_history(app_paths.database_file, str(library_root))
    client = TestClient(create_web_app(app_paths.config_file, app_paths.database_file))

    response = client.get(f"/history/{RUN_ID}")

    assert response.status_code == SUCCESS_STATUS_CODE
    assert "OMYM2 Run Detail" in response.text
    assert str(RUN_ID) in response.text
    assert str(PLAN_ID) in response.text
    assert str(LIBRARY_ID) in response.text
    assert str(EVENT_ID) in response.text
    assert str(ACTION_ID) in response.text
    assert SOURCE_PATH in response.text
    assert TARGET_PATH in response.text
    assert FileEventType.MOVE_FILE.value in response.text
    assert FileEventStatus.SUCCEEDED.value in response.text
    assert ">1<" in response.text


def test_run_detail_page_returns_not_found_for_missing_run(tmp_path: Path) -> None:
    """Run detail screen reports missing or invalid Run IDs as not found."""
    app_paths = default_application_paths(tmp_path)
    client = TestClient(create_web_app(app_paths.config_file, app_paths.database_file))

    response = client.get(f"/history/{MISSING_RUN_ID}")

    assert response.status_code == NOT_FOUND_STATUS_CODE
    assert "Run was not found." in response.text


def test_run_detail_page_returns_not_found_for_invalid_run_id(tmp_path: Path) -> None:
    """Run detail screen treats malformed Run IDs as not found."""
    app_paths = default_application_paths(tmp_path)
    client = TestClient(create_web_app(app_paths.config_file, app_paths.database_file))

    response = client.get(f"/history/{INVALID_RUN_ID_TEXT}")

    assert response.status_code == NOT_FOUND_STATUS_CODE
    assert "Run was not found." in response.text


def test_history_page_renders_database_errors(tmp_path: Path) -> None:
    """History screen reports database startup errors as local HTML."""
    app_paths = default_application_paths(tmp_path)
    invalid_database_path = tmp_path / "not-a-database"
    invalid_database_path.mkdir()
    client = TestClient(create_web_app(app_paths.config_file, invalid_database_path))

    response = client.get("/history")

    assert response.status_code == SERVER_ERROR_STATUS_CODE
    assert "Inspection failed" in response.text


def test_check_page_renders_no_issues_for_empty_database(tmp_path: Path) -> None:
    """Check screen reports a clean empty database as no issues."""
    app_paths = default_application_paths(tmp_path)
    client = TestClient(create_web_app(app_paths.config_file, app_paths.database_file))

    response = client.get(WEB_CHECK_ROUTE)

    assert response.status_code == SUCCESS_STATUS_CODE
    assert "No issues." in response.text


def test_check_page_renders_library_state_issue(tmp_path: Path) -> None:
    """Check screen renders usecase issues without route-level filesystem work."""
    app_paths = default_application_paths(tmp_path)
    library_root = tmp_path / "library"
    library_root.mkdir()
    with SQLiteUnitOfWork(app_paths.database_file) as uow:
        uow.libraries.save(_library(str(library_root), status=LibraryStatus.BLOCKED))
        uow.commit()
    client = TestClient(create_web_app(app_paths.config_file, app_paths.database_file))

    response = client.get(WEB_CHECK_ROUTE)

    assert response.status_code == SUCCESS_STATUS_CODE
    assert "OMYM2 Check" in response.text
    assert response.text.count("library_blocked") == 1
    assert str(LIBRARY_ID) in response.text


def test_check_page_renders_config_validation_error(tmp_path: Path) -> None:
    """Check screen reports invalid TOML config as a client-facing error."""
    app_paths = default_application_paths(tmp_path)
    app_paths.config_file.parent.mkdir(parents=True)
    _ = app_paths.config_file.write_text("version = ", encoding=CONFIG_FILE_ENCODING)
    client = TestClient(create_web_app(app_paths.config_file, app_paths.database_file))

    response = client.get(WEB_CHECK_ROUTE)

    assert response.status_code == ERROR_STATUS_CODE
    assert "Invalid TOML" in response.text


def test_tracks_page_renders_empty_state(tmp_path: Path) -> None:
    """Tracks screen reports an empty database without an error."""
    app_paths = default_application_paths(tmp_path)
    client = TestClient(create_web_app(app_paths.config_file, app_paths.database_file))

    response = client.get(WEB_TRACKS_ROUTE)

    assert response.status_code == SUCCESS_STATUS_CODE
    assert "No tracks." in response.text


def test_tracks_page_renders_managed_tracks(tmp_path: Path) -> None:
    """Tracks screen renders DB state without checking the filesystem."""
    app_paths = default_application_paths(tmp_path)
    library_root = tmp_path / "library"
    library_root.mkdir()
    with SQLiteUnitOfWork(app_paths.database_file) as uow:
        uow.libraries.save(_library(str(library_root)))
        uow.tracks.save(_track())
        uow.commit()
    client = TestClient(create_web_app(app_paths.config_file, app_paths.database_file))

    response = client.get(WEB_TRACKS_ROUTE)

    assert response.status_code == SUCCESS_STATUS_CODE
    assert "OMYM2 Tracks" in response.text
    assert str(TRACK_ID) in response.text
    assert str(LIBRARY_ID) in response.text
    assert TRACK_TITLE in response.text
    assert TRACK_ARTIST in response.text
    assert TRACK_ALBUM in response.text
    assert TARGET_PATH in response.text
    assert TrackStatus.ACTIVE.value in response.text


def test_top_navigation_marks_active_screen(tmp_path: Path) -> None:
    """Each console route marks its navigation item as active."""
    app_paths = default_application_paths(tmp_path)
    client = TestClient(create_web_app(app_paths.config_file, app_paths.database_file))

    for route in (WEB_SETTINGS_ROUTE, WEB_HISTORY_ROUTE, WEB_CHECK_ROUTE, WEB_TRACKS_ROUTE):
        response = client.get(route)

        assert response.status_code == SUCCESS_STATUS_CODE
        assert f'class="topnav__link--active" href="{route}"' in response.text


def _seed_run_history(database_file: Path, library_root: str) -> None:
    with SQLiteUnitOfWork(database_file) as uow:
        uow.libraries.save(_library(library_root))
        uow.plans.save(_plan(library_root))
        uow.plan_actions.save(_action())
        uow.runs.save(_run())
        uow.file_events.save(_event())
        uow.commit()


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
