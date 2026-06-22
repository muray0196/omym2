"""
Summary: Tests the SQLite persistence foundation.
Why: Verifies Phase 5 storage, migration, and UnitOfWork behavior.
"""

from __future__ import annotations

import sqlite3
from datetime import UTC, datetime, timedelta
from uuid import UUID

import pytest

from omym2.adapters.config.application_paths import default_application_paths
from omym2.adapters.db.sqlite import migration_runner
from omym2.adapters.db.sqlite.migration_runner import SQLiteMigration, migrate_database
from omym2.adapters.db.sqlite.unit_of_work import SQLiteUnitOfWork
from omym2.domain.models.file_event import FileEvent, FileEventStatus, FileEventType
from omym2.domain.models.library import Library, LibraryStatus
from omym2.domain.models.plan import Plan, PlanStatus, PlanType
from omym2.domain.models.plan_action import ActionStatus, ActionType, PlanAction
from omym2.domain.models.run import Run, RunStatus
from omym2.domain.models.track import Track, TrackStatus
from omym2.domain.models.track_metadata import TrackMetadata
from omym2.shared.ids import ActionId, EventId, LibraryId, PlanId, RunId, TrackId

ACTION_ID = ActionId(UUID("018f6a4f-3c2d-7b8a-9abc-def01234567b"))
BASE_TIME = datetime(2026, 1, 1, tzinfo=UTC)
CONFIG_HASH = "config-hash"
CONTENT_HASH = "content-hash"
EVENT_ID = EventId(UUID("018f6a4f-3c2d-7b8a-9abc-def01234567e"))
EVENT_SEQUENCE_EARLY = 1
EVENT_SEQUENCE_LATE = 2
FINISHED_TIME = BASE_TIME + timedelta(minutes=5)
LATE_ACTION_ID = ActionId(UUID("018f6a4f-3c2d-7b8a-9abc-def01234567c"))
LATE_EVENT_ID = EventId(UUID("018f6a4f-3c2d-7b8a-9abc-def01234567f"))
LIBRARY_ID = LibraryId(UUID("018f6a4f-3c2d-7b8a-9abc-def012345678"))
LIBRARY_ROOT = "/music/library"
METADATA_HASH = "metadata-hash"
PLAN_ID = PlanId(UUID("018f6a4f-3c2d-7b8a-9abc-def01234567a"))
PLAN_SUMMARY = {"moves": "1"}
ROLLBACK_ERROR = "force rollback"
RUN_ID = RunId(UUID("018f6a4f-3c2d-7b8a-9abc-def01234567d"))
SORT_ORDER_EARLY = 1
SORT_ORDER_LATE = 2
SOURCE_PATH = "/incoming/song.flac"
TARGET_PATH = "Artist/Album/01_Title.flac"
TRACK_ARTIST = "Artist"
TRACK_ID = TrackId(UUID("018f6a4f-3c2d-7b8a-9abc-def012345679"))
TRACK_TITLE = "Title"

REQUIRED_TABLES = {
    "file_events",
    "libraries",
    "plan_actions",
    "plans",
    "runs",
    "schema_migrations",
    "tracks",
}


def test_sqlite_migrations_create_required_tables(tmp_path) -> None:
    """Migration runner creates the Phase 5 SQLite table set."""
    database_file = default_application_paths(tmp_path).database_file

    migrate_database(database_file)

    assert _table_names(database_file) >= REQUIRED_TABLES


def test_sqlite_migration_script_rolls_back_with_marker_on_failure(tmp_path, monkeypatch) -> None:
    """Failing migration scripts leave no partial schema objects behind."""
    database_file = default_application_paths(tmp_path).database_file
    migration = SQLiteMigration(
        name="999999999999_failing.sql",
        sql="""
        CREATE TABLE partially_applied (
            id TEXT PRIMARY KEY
        );
        INSERT INTO missing_table (id) VALUES ('boom');
        """,
    )
    monkeypatch.setattr(migration_runner, "load_packaged_migrations", lambda: (migration,))

    with pytest.raises(sqlite3.DatabaseError):
        migrate_database(database_file)

    assert "partially_applied" not in _table_names(database_file)
    assert _applied_migrations(database_file) == set()


def test_internal_storage_is_created_lazily_when_needed(tmp_path) -> None:
    """Entering SQLiteUnitOfWork creates the internal .data database path."""
    paths = default_application_paths(tmp_path)

    assert not paths.data_dir.exists()

    with SQLiteUnitOfWork(paths.database_file):
        pass

    assert paths.data_dir.is_dir()
    assert paths.database_file.is_file()


def test_sqlite_repositories_round_trip_domain_models(tmp_path) -> None:
    """SQLite repositories persist and restore every Phase 5 domain model."""
    database_file = default_application_paths(tmp_path).database_file
    library = _library()
    track = _track()
    plan = _plan()
    action_late = _plan_action(LATE_ACTION_ID, SORT_ORDER_LATE)
    action_early = _plan_action(ACTION_ID, SORT_ORDER_EARLY)
    run = _run()
    event_late = _file_event(LATE_EVENT_ID, LATE_ACTION_ID, EVENT_SEQUENCE_LATE)
    event_early = _file_event(EVENT_ID, ACTION_ID, EVENT_SEQUENCE_EARLY)

    with SQLiteUnitOfWork(database_file) as uow:
        uow.libraries.save(library)
        uow.tracks.save(track)
        uow.plans.save(plan)
        uow.plan_actions.save(action_late)
        uow.plan_actions.save(action_early)
        uow.runs.save(run)
        uow.file_events.save(event_late)
        uow.file_events.save(event_early)
        uow.commit()

    with SQLiteUnitOfWork(database_file) as uow:
        assert uow.libraries.get(LIBRARY_ID) == library
        assert uow.libraries.find_by_root_path(LIBRARY_ROOT) == library
        assert uow.libraries.list_all() == (library,)
        assert uow.tracks.get(TRACK_ID) == track
        assert uow.tracks.list_by_library(LIBRARY_ID) == (track,)
        assert uow.tracks.find_by_content_hash(LIBRARY_ID, CONTENT_HASH) == (track,)
        assert uow.plans.get(PLAN_ID) == plan
        assert uow.plans.list_by_library(LIBRARY_ID) == (plan,)
        assert uow.plan_actions.get(ACTION_ID) == action_early
        assert uow.plan_actions.list_by_plan(PLAN_ID) == (action_early, action_late)
        assert uow.runs.get(RUN_ID) == run
        assert uow.runs.list_by_library(LIBRARY_ID) == (run,)
        assert uow.runs.list_by_plan(PLAN_ID) == (run,)
        assert uow.file_events.get(EVENT_ID) == event_early
        assert uow.file_events.list_by_run(RUN_ID) == (event_early, event_late)


def test_sqlite_unit_of_work_rolls_back_when_not_committed(tmp_path) -> None:
    """Closing without commit leaves no repository writes behind."""
    database_file = default_application_paths(tmp_path).database_file

    with SQLiteUnitOfWork(database_file) as uow:
        uow.libraries.save(_library())

    with SQLiteUnitOfWork(database_file) as uow:
        assert uow.libraries.get(LIBRARY_ID) is None


def test_sqlite_unit_of_work_rolls_back_on_exception(tmp_path) -> None:
    """Exceptions inside the UnitOfWork rollback uncommitted writes."""
    database_file = default_application_paths(tmp_path).database_file

    with pytest.raises(RuntimeError, match=ROLLBACK_ERROR):
        _save_library_then_fail(database_file)

    with SQLiteUnitOfWork(database_file) as uow:
        assert uow.libraries.get(LIBRARY_ID) is None


def _table_names(database_file) -> set[str]:
    with sqlite3.connect(database_file) as connection:
        rows = connection.execute(
            """
            SELECT name
            FROM sqlite_master
            WHERE type = 'table'
            """
        ).fetchall()
    return {str(row[0]) for row in rows}


def _applied_migrations(database_file) -> set[str]:
    with sqlite3.connect(database_file) as connection:
        rows = connection.execute("SELECT migration_name FROM schema_migrations").fetchall()
    return {str(row[0]) for row in rows}


def _save_library_then_fail(database_file) -> None:
    with SQLiteUnitOfWork(database_file) as uow:
        uow.libraries.save(_library())
        raise RuntimeError(ROLLBACK_ERROR)


def _library() -> Library:
    return Library(
        library_id=LIBRARY_ID,
        root_path=LIBRARY_ROOT,
        path_policy_hash=CONFIG_HASH,
        registered_at=BASE_TIME,
        status=LibraryStatus.REGISTERED,
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
        metadata=TrackMetadata(title=TRACK_TITLE, artist=TRACK_ARTIST),
        status=TrackStatus.ACTIVE,
        first_seen_at=BASE_TIME,
        last_seen_at=BASE_TIME,
        updated_at=BASE_TIME,
    )


def _plan() -> Plan:
    return Plan(
        plan_id=PLAN_ID,
        library_id=LIBRARY_ID,
        plan_type=PlanType.ADD,
        status=PlanStatus.READY,
        created_at=BASE_TIME,
        config_hash=CONFIG_HASH,
        library_root_at_plan=LIBRARY_ROOT,
        summary=PLAN_SUMMARY,
    )


def _plan_action(action_id: ActionId, sort_order: int) -> PlanAction:
    return PlanAction(
        action_id=action_id,
        plan_id=PLAN_ID,
        library_id=LIBRARY_ID,
        track_id=TRACK_ID,
        action_type=ActionType.MOVE,
        source_path=SOURCE_PATH,
        target_path=TARGET_PATH,
        content_hash_at_plan=CONTENT_HASH,
        metadata_hash_at_plan=METADATA_HASH,
        status=ActionStatus.PLANNED,
        reason=None,
        sort_order=sort_order,
    )


def _run() -> Run:
    return Run(
        run_id=RUN_ID,
        plan_id=PLAN_ID,
        library_id=LIBRARY_ID,
        status=RunStatus.RUNNING,
        started_at=BASE_TIME,
    )


def _file_event(event_id: EventId, action_id: ActionId, sequence_no: int) -> FileEvent:
    return FileEvent(
        event_id=event_id,
        library_id=LIBRARY_ID,
        run_id=RUN_ID,
        plan_action_id=action_id,
        event_type=FileEventType.MOVE_FILE,
        source_path=SOURCE_PATH,
        target_path=TARGET_PATH,
        status=FileEventStatus.PENDING,
        started_at=BASE_TIME,
        completed_at=None,
        error_code=None,
        error_message=None,
        sequence_no=sequence_no,
    )
