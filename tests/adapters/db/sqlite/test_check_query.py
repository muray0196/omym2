"""
Summary: Tests SQLiteCheckRunRepository/SQLiteCheckIssueRepository migration, persistence, and queries.
Why: Protects the check-results persistence contract: migration upgrade safety, round-trip fidelity,
the replace-on-write invariant, FK cascade cleanup, and the browsing SQL contract (issue_seq keyset
math, filter pushdown, facets, and groups).
"""

from __future__ import annotations

import sqlite3
from datetime import UTC, datetime
from typing import TYPE_CHECKING, cast
from uuid import UUID

from omym2.adapters.config.application_paths import default_application_paths
from omym2.adapters.db.sqlite import migration_runner
from omym2.adapters.db.sqlite.migration_runner import migrate_database
from omym2.adapters.db.sqlite.unit_of_work import SQLiteUnitOfWork
from omym2.domain.models.check_issue import CheckIssue, CheckIssueType
from omym2.domain.models.check_run import CheckRun
from omym2.domain.models.library import Library, LibraryStatus
from omym2.domain.models.plan import Plan, PlanStatus, PlanType
from omym2.domain.models.track import Track, TrackStatus
from omym2.domain.models.track_metadata import TrackMetadata
from omym2.shared.ids import CheckRunId, LibraryId, PlanId, TrackId
from omym2.shared.pagination import PageRequest

if TYPE_CHECKING:
    from pathlib import Path

    import pytest

BASE_TIME = datetime(2026, 1, 1, tzinfo=UTC)
CONFIG_HASH = "config-hash"
CONTENT_HASH = "content-hash"
METADATA_HASH = "metadata-hash"
LIBRARY_ID = LibraryId(UUID("018f6a4f-3c2d-7b8a-9abc-def0123456c0"))
SECOND_LIBRARY_ID = LibraryId(UUID("018f6a4f-3c2d-7b8a-9abc-def0123456c1"))
LIBRARY_ROOT = "/music/library"
PLAN_ID = PlanId(UUID("018f6a4f-3c2d-7b8a-9abc-def0123456d0"))
TRACK_ID = TrackId(UUID("018f6a4f-3c2d-7b8a-9abc-def0123456e0"))
CHECK_RUN_ID = CheckRunId(UUID("018f6a4f-3c2d-7b8a-9abc-def0123456f0"))
SECOND_CHECK_RUN_ID = CheckRunId(UUID("018f6a4f-3c2d-7b8a-9abc-def0123456f1"))
TARGET_PATH = "Artist/Album/01_Title.flac"

REQUIRED_CHECK_TABLES = {"check_runs", "check_issues"}
REQUIRED_CHECK_INDEXES = {"idx_check_issues_library_type"}
TWO_ITEM_LIMIT = 2
THREE_ISSUE_TOTAL = 3
TWO_ISSUE_TYPE_GROUP_TOTAL = 2


def test_check_results_migration_creates_tables_and_index_on_fresh_database(tmp_path: Path) -> None:
    """The check-results migration creates check_runs, check_issues, and their browsing index."""
    database_file = default_application_paths(tmp_path).database_file

    migrate_database(database_file)

    assert _table_names(database_file) >= REQUIRED_CHECK_TABLES
    assert _index_names(database_file) >= REQUIRED_CHECK_INDEXES


def test_check_results_migration_applies_on_database_migrated_from_initial_schema_with_data(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """The check-results migration upgrades a DB that only has the initial schema and existing data."""
    database_file = default_application_paths(tmp_path).database_file
    real_load_packaged_migrations = migration_runner.load_packaged_migrations
    initial_only = tuple(
        migration
        for migration in real_load_packaged_migrations()
        if migration.name == "202606220001_initial_schema.sql"
    )

    with monkeypatch.context() as patched:
        patched.setattr(migration_runner, "load_packaged_migrations", lambda: initial_only)
        migrate_database(database_file)

    assert "check_runs" not in _table_names(database_file)

    with SQLiteUnitOfWork(database_file) as uow:
        uow.libraries.save(_library())
        uow.commit()

    migrate_database(database_file)

    assert _table_names(database_file) >= REQUIRED_CHECK_TABLES
    assert _index_names(database_file) >= REQUIRED_CHECK_INDEXES
    with SQLiteUnitOfWork(database_file) as uow:
        assert uow.libraries.get(LIBRARY_ID) == _library()


def test_check_run_and_issue_repositories_round_trip_domain_models(tmp_path: Path) -> None:
    """SQLite check repositories persist and restore CheckRun and CheckIssue verbatim."""
    database_file = default_application_paths(tmp_path).database_file
    check_run = _check_run()
    issue = CheckIssue(
        issue_type=CheckIssueType.PLAN_SOURCE_CHANGED,
        library_id=LIBRARY_ID,
        path=TARGET_PATH,
        track_id=TRACK_ID,
        plan_id=PLAN_ID,
        detail="source_changed",
    )

    with SQLiteUnitOfWork(database_file) as uow:
        uow.libraries.save(_library())
        uow.tracks.save(_track())
        uow.plans.save(_plan())
        uow.check_runs.save(check_run)
        uow.check_issues.save_many(CHECK_RUN_ID, (issue,))
        uow.commit()

    with SQLiteUnitOfWork(database_file) as uow:
        assert uow.check_runs.latest(LIBRARY_ID) == check_run
        assert uow.check_runs.latest(SECOND_LIBRARY_ID) is None
        assert uow.check_runs.earliest_checked_at() == BASE_TIME
        page = uow.check_issues.query_page(LIBRARY_ID, issue_type=None, page=PageRequest())
        assert page.items == (issue,)
        assert page.total == 1


def test_check_run_delete_for_library_cascades_check_issues(tmp_path: Path) -> None:
    """Deleting a Library's CheckRun cascades to delete its CheckIssues via FK ON DELETE CASCADE."""
    database_file = default_application_paths(tmp_path).database_file
    with SQLiteUnitOfWork(database_file) as uow:
        uow.libraries.save(_library())
        uow.check_runs.save(_check_run())
        uow.check_issues.save_many(CHECK_RUN_ID, (_check_issue(),))
        uow.commit()

    with SQLiteUnitOfWork(database_file) as uow:
        uow.check_runs.delete_for_library(LIBRARY_ID)
        uow.commit()

    with SQLiteUnitOfWork(database_file) as uow:
        assert uow.check_runs.latest(LIBRARY_ID) is None
        page = uow.check_issues.query_page(LIBRARY_ID, issue_type=None, page=PageRequest())
        assert page.items == ()
        assert page.total == 0


def test_check_issue_replace_on_write_advances_issue_seq_and_drops_prior_findings(tmp_path: Path) -> None:
    """A second check run replaces the first Library's findings; issue_seq never reuses old values."""
    database_file = default_application_paths(tmp_path).database_file
    with SQLiteUnitOfWork(database_file) as uow:
        uow.libraries.save(_library())
        uow.check_runs.save(_check_run())
        uow.check_issues.save_many(
            CHECK_RUN_ID,
            (_check_issue(path="A/1.flac"), _check_issue(path="B/1.flac")),
        )
        uow.commit()
    first_max_issue_seq = _max_issue_seq(database_file)
    assert first_max_issue_seq is not None

    with SQLiteUnitOfWork(database_file) as uow:
        uow.check_issues.delete_for_library(LIBRARY_ID)
        uow.check_runs.delete_for_library(LIBRARY_ID)
        uow.check_runs.save(_check_run(check_run_id=SECOND_CHECK_RUN_ID))
        uow.check_issues.save_many(SECOND_CHECK_RUN_ID, (_check_issue(path="C/1.flac"),))
        uow.commit()
    second_max_issue_seq = _max_issue_seq(database_file)

    assert second_max_issue_seq is not None
    assert second_max_issue_seq > first_max_issue_seq

    with SQLiteUnitOfWork(database_file) as uow:
        assert uow.check_runs.latest(LIBRARY_ID) == _check_run(check_run_id=SECOND_CHECK_RUN_ID)
        page = uow.check_issues.query_page(LIBRARY_ID, issue_type=None, page=PageRequest())
        assert [issue.path for issue in page.items] == ["C/1.flac"]


def test_check_issue_query_page_walks_issues_in_seq_order_with_keyset_cursor(tmp_path: Path) -> None:
    """A limit=2 keyset walk over 3 CheckIssues visits every issue once, in issue_seq ASC order."""
    database_file = default_application_paths(tmp_path).database_file
    with SQLiteUnitOfWork(database_file) as uow:
        uow.libraries.save(_library())
        uow.check_runs.save(_check_run())
        uow.check_issues.save_many(
            CHECK_RUN_ID,
            (
                _check_issue(path="A/1.flac"),
                _check_issue(path="B/1.flac"),
                _check_issue(path="C/1.flac"),
            ),
        )
        uow.commit()

    visited: list[str | None] = []
    cursor: tuple[str, ...] | None = None
    with SQLiteUnitOfWork(database_file) as uow:
        for _ in range(THREE_ISSUE_TOTAL):
            page = uow.check_issues.query_page(
                None,
                issue_type=None,
                page=PageRequest(limit=TWO_ITEM_LIMIT, cursor_key=cursor),
            )
            visited.extend(issue.path for issue in page.items)
            assert page.total == THREE_ISSUE_TOTAL
            if page.next_cursor_key is None:
                break
            cursor = page.next_cursor_key

    assert visited == ["A/1.flac", "B/1.flac", "C/1.flac"]


def test_check_issue_query_page_filters_by_library_and_issue_type(tmp_path: Path) -> None:
    """library_id and issue_type filters narrow both the rows and the total."""
    database_file = default_application_paths(tmp_path).database_file
    with SQLiteUnitOfWork(database_file) as uow:
        uow.libraries.save(_library())
        uow.libraries.save(_library(library_id=SECOND_LIBRARY_ID, root_path="/music/second"))
        uow.check_runs.save(_check_run())
        uow.check_runs.save(_check_run(check_run_id=SECOND_CHECK_RUN_ID, library_id=SECOND_LIBRARY_ID))
        uow.check_issues.save_many(
            CHECK_RUN_ID,
            (
                _check_issue(issue_type=CheckIssueType.DB_FILE_MISSING, path="A/1.flac"),
                _check_issue(issue_type=CheckIssueType.UNMANAGED_FILE_EXISTS, path="B/1.flac"),
            ),
        )
        uow.check_issues.save_many(
            SECOND_CHECK_RUN_ID,
            (_check_issue(library_id=SECOND_LIBRARY_ID, issue_type=CheckIssueType.DB_FILE_MISSING, path="C/1.flac"),),
        )
        uow.commit()

    with SQLiteUnitOfWork(database_file) as uow:
        page = uow.check_issues.query_page(LIBRARY_ID, issue_type=CheckIssueType.DB_FILE_MISSING, page=PageRequest())

    assert [issue.path for issue in page.items] == ["A/1.flac"]
    assert page.total == 1


def test_check_issue_type_facets_order_count_desc_then_value_asc(tmp_path: Path) -> None:
    """issue_type_facets is ordered count DESC, then value ASC."""
    database_file = default_application_paths(tmp_path).database_file
    with SQLiteUnitOfWork(database_file) as uow:
        uow.libraries.save(_library())
        uow.check_runs.save(_check_run())
        uow.check_issues.save_many(
            CHECK_RUN_ID,
            (
                _check_issue(issue_type=CheckIssueType.DB_FILE_MISSING, path="A/1.flac"),
                _check_issue(issue_type=CheckIssueType.DB_FILE_MISSING, path="B/1.flac"),
                _check_issue(issue_type=CheckIssueType.UNMANAGED_FILE_EXISTS, path="C/1.flac"),
            ),
        )
        uow.commit()

    with SQLiteUnitOfWork(database_file) as uow:
        facets = uow.check_issues.issue_type_facets(LIBRARY_ID)

    assert [(facet.value, facet.count) for facet in facets] == [
        (CheckIssueType.DB_FILE_MISSING.value, 2),
        (CheckIssueType.UNMANAGED_FILE_EXISTS.value, 1),
    ]


def test_check_issue_group_page_groups_by_issue_type_ordered_count_desc_key_asc(tmp_path: Path) -> None:
    """group_page groups CheckIssues by issue_type, ordered count DESC then key ASC."""
    database_file = default_application_paths(tmp_path).database_file
    with SQLiteUnitOfWork(database_file) as uow:
        uow.libraries.save(_library())
        uow.check_runs.save(_check_run())
        uow.check_issues.save_many(
            CHECK_RUN_ID,
            (
                _check_issue(issue_type=CheckIssueType.DB_FILE_MISSING, path="A/1.flac"),
                _check_issue(issue_type=CheckIssueType.DB_FILE_MISSING, path="B/1.flac"),
                _check_issue(issue_type=CheckIssueType.UNMANAGED_FILE_EXISTS, path="C/1.flac"),
            ),
        )
        uow.commit()

    with SQLiteUnitOfWork(database_file) as uow:
        page = uow.check_issues.group_page(LIBRARY_ID, PageRequest())

    assert [(group.key, group.label, group.count) for group in page.items] == [
        (CheckIssueType.DB_FILE_MISSING.value, CheckIssueType.DB_FILE_MISSING.value, 2),
        (CheckIssueType.UNMANAGED_FILE_EXISTS.value, CheckIssueType.UNMANAGED_FILE_EXISTS.value, 1),
    ]
    assert page.total == TWO_ISSUE_TYPE_GROUP_TOTAL


def _table_names(database_file: Path) -> set[str]:
    with sqlite3.connect(database_file) as connection:
        rows = connection.execute(
            """
            SELECT name
            FROM sqlite_master
            WHERE type = 'table'
            """
        ).fetchall()
    return {str(row[0]) for row in cast("list[tuple[object, ...]]", rows)}


def _index_names(database_file: Path) -> set[str]:
    with sqlite3.connect(database_file) as connection:
        rows = connection.execute(
            """
            SELECT name
            FROM sqlite_master
            WHERE type = 'index'
            """
        ).fetchall()
    return {str(row[0]) for row in cast("list[tuple[object, ...]]", rows)}


def _max_issue_seq(database_file: Path) -> int | None:
    with sqlite3.connect(database_file) as connection:
        row = cast("tuple[object, ...]", connection.execute("SELECT MAX(issue_seq) FROM check_issues").fetchone())
    value = row[0]
    return None if value is None else cast("int", value)


def _library(
    *,
    library_id: LibraryId = LIBRARY_ID,
    root_path: str = LIBRARY_ROOT,
) -> Library:
    return Library(
        library_id=library_id,
        root_path=root_path,
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
        size=None,
        mtime=None,
        metadata=TrackMetadata(title="Title", artist="Artist"),
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
    )


def _check_run(
    *,
    check_run_id: CheckRunId = CHECK_RUN_ID,
    library_id: LibraryId = LIBRARY_ID,
    checked_at: datetime = BASE_TIME,
    total_count: int = 1,
) -> CheckRun:
    return CheckRun(
        check_run_id=check_run_id,
        library_id=library_id,
        checked_at=checked_at,
        total_count=total_count,
    )


def _check_issue(
    *,
    library_id: LibraryId = LIBRARY_ID,
    issue_type: CheckIssueType = CheckIssueType.UNMANAGED_FILE_EXISTS,
    path: str = TARGET_PATH,
) -> CheckIssue:
    return CheckIssue(issue_type=issue_type, library_id=library_id, path=path)
