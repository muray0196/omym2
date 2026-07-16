"""
Summary: Tests the SQLite persistence foundation.
Why: Verifies storage, migration, and UnitOfWork behavior.
"""

from __future__ import annotations

import json
import sqlite3
from contextlib import nullcontext
from dataclasses import replace
from datetime import UTC, datetime, timedelta
from typing import TYPE_CHECKING, cast
from uuid import UUID

import pytest

from omym2.adapters.config.application_paths import default_application_paths
from omym2.adapters.db.sqlite import migration_runner
from omym2.adapters.db.sqlite import unit_of_work as unit_of_work_module
from omym2.adapters.db.sqlite.migration_runner import (
    SQLiteMigration,
    ensure_database_migrated,
    migrate_database,
)
from omym2.adapters.db.sqlite.repositories import INVALID_ARTIST_NAME_DIAGNOSTICS_MESSAGE
from omym2.adapters.db.sqlite.unit_of_work import SQLiteUnitOfWork
from omym2.domain.models.accepted_artist_name import (
    AcceptedArtistName,
    ArtistNameProvider,
    SelectedArtistNameKind,
)
from omym2.domain.models.artist_name_resolution import (
    ArtistNameDiagnostics,
    ArtistNameResolutionDiagnostic,
    ArtistNameResolutionIssue,
    ArtistNameResolutionProvenance,
)
from omym2.domain.models.check_issue import CheckIssue, CheckIssueType
from omym2.domain.models.check_run import CheckRun
from omym2.domain.models.companion_asset import CompanionAsset, CompanionAssetKind, CompanionAssetStatus
from omym2.domain.models.file_event import FileEvent, FileEventStatus, FileEventType
from omym2.domain.models.library import Library, LibraryStatus
from omym2.domain.models.plan import Plan, PlanStatus, PlanType
from omym2.domain.models.plan_action import ActionStatus, ActionType, PlanAction, PlanActionDependency
from omym2.domain.models.run import Run, RunStatus
from omym2.domain.models.track import Track, TrackStatus
from omym2.domain.models.track_metadata import TrackMetadata
from omym2.shared.ids import (
    ActionId,
    CheckRunId,
    CompanionAssetId,
    EventId,
    LibraryId,
    PlanId,
    RunId,
    TrackId,
)
from omym2.shared.pagination import PageRequest

if TYPE_CHECKING:
    from collections.abc import Callable
    from os import PathLike
    from pathlib import Path

ACTION_ID = ActionId(UUID("018f6a4f-3c2d-7b8a-9abc-def01234567b"))
BASE_TIME = datetime(2026, 1, 1, tzinfo=UTC)
ACCEPTED_ARTIST_SOURCE_KEY = "宇多田ヒカル"
ACCEPTED_ARTIST_SOURCE_NAME = "宇多田ヒカル"
ACCEPTED_ARTIST_RESOLVED_NAME = "Hikaru Utada"
MUSICBRAINZ_ARTIST_ID = "db2f4f3a-f0c2-4c96-bea3-636f4b44f57b"
ACCEPTED_ARTIST_NAMES_MIGRATION_NAME = "202607150001_accepted_artist_names.sql"
CHECK_ISSUE_COUNT = 1
CHECK_RUN_ID = CheckRunId(UUID("018f6a4f-3c2d-7b8a-9abc-def012345684"))
COMPANION_ASSET_ID = CompanionAssetId(UUID("018f6a4f-3c2d-7b8a-9abc-def012345689"))
COMPANION_ASSETS_MIGRATION_NAME = "202607160003_companion_assets.sql"
PLAN_SOURCE_COMPANION_CHECK_MIGRATION_NAME = "202607160004_plan_source_and_companion_check.sql"
COMPANION_CONTENT_HASH = "companion-content-hash"
COMPANION_SOURCE_PATH = "Artist/Album/cover.jpg"
COMPANION_TARGET_PATH = "Artist/Album 2/cover.jpg"
CONFIG_HASH = "config-hash"
CONTENT_HASH = "content-hash"
EVENT_ID = EventId(UUID("018f6a4f-3c2d-7b8a-9abc-def01234567e"))
EVENT_SEQUENCE_EARLY = 1
EVENT_SEQUENCE_LATE = 2
EVENT_SEQUENCE_THIRD = 3
EXPECTED_REENTER_CONNECTION_COUNT = 2
FINISHED_TIME = BASE_TIME + timedelta(minutes=5)
UNDO_CREATED_TIME = FINISHED_TIME + timedelta(minutes=1)
POST_UNDO_TIME = UNDO_CREATED_TIME + timedelta(minutes=1)
LATE_ACTION_ID = ActionId(UUID("018f6a4f-3c2d-7b8a-9abc-def01234567c"))
LATE_EVENT_ID = EventId(UUID("018f6a4f-3c2d-7b8a-9abc-def01234567f"))
LIBRARY_ID = LibraryId(UUID("018f6a4f-3c2d-7b8a-9abc-def012345678"))
LIBRARY_ROOT = "/music/library"
METADATA_HASH = "metadata-hash"
OTHER_LIBRARY_ID = LibraryId(UUID("018f6a4f-3c2d-7b8a-9abc-def012345683"))
PLAN_ID = PlanId(UUID("018f6a4f-3c2d-7b8a-9abc-def01234567a"))
PLAN_SUMMARY = {"moves": "1"}
PERFORMANCE_INDEX_MIGRATION_NAME = "202607110001_performance_indexes.sql"
PLAN_ACTION_DIAGNOSTICS_MIGRATION_NAME = "202607160001_plan_action_artist_name_diagnostics.sql"
STAT_BASELINE_MIGRATION_NAME = "202607110002_track_stat_baseline.sql"
UNDO_PROVENANCE_MIGRATION_NAME = "202607130002_undo_provenance_and_apply_claim.sql"
REUSED_BEGIN_COUNT = 3
REUSED_COMMIT_COUNT = 2
REUSED_CONNECTION_COUNT = 1
REUSED_ROLLBACK_COUNT = 1
ROLLBACK_ERROR = "force rollback"
RUN_ID = RunId(UUID("018f6a4f-3c2d-7b8a-9abc-def01234567d"))
SECOND_RUN_EVENT_ID = EventId(UUID("018f6a4f-3c2d-7b8a-9abc-def012345680"))
SECOND_RUN_ID = RunId(UUID("018f6a4f-3c2d-7b8a-9abc-def012345681"))
SECOND_PLAN_ID = PlanId(UUID("018f6a4f-3c2d-7b8a-9abc-def012345685"))
SECOND_ACTION_ID = ActionId(UUID("018f6a4f-3c2d-7b8a-9abc-def012345686"))
UNDO_PLAN_ID = PlanId(UUID("018f6a4f-3c2d-7b8a-9abc-def012345687"))
UNDO_ACTION_ID = ActionId(UUID("018f6a4f-3c2d-7b8a-9abc-def012345688"))
SORT_ORDER_EARLY = 1
SORT_ORDER_LATE = 2
SOURCE_PATH = "/incoming/song.flac"
SUCCEEDED_EVENT_ID = EventId(UUID("018f6a4f-3c2d-7b8a-9abc-def012345682"))
TARGET_PATH = "Artist/Album/01_Title.flac"
TRACK_ARTIST = "Artist"
TRACK_ID = TrackId(UUID("018f6a4f-3c2d-7b8a-9abc-def012345679"))
TRACK_SIZE = 1024
TRACK_TITLE = "Title"

REQUIRED_TABLES = {
    "accepted_artist_names",
    "companion_assets",
    "file_events",
    "libraries",
    "operations",
    "plan_actions",
    "plan_action_dependencies",
    "plans",
    "runs",
    "schema_migrations",
    "tracks",
}

REQUIRED_BROWSING_INDEXES = {
    "idx_plans_created",
    "idx_plans_library_created",
    "idx_tracks_current_path",
    "idx_tracks_status",
    "idx_plan_actions_status",
    "idx_plan_actions_type",
    "idx_runs_started",
}

PERFORMANCE_INDEX_COLUMNS = {
    "idx_check_issues_check_run_id": ("check_run_id",),
    "idx_file_events_library_status": ("library_id", "status", "sequence_no"),
}

REMOVED_REDUNDANT_INDEXES = {
    "idx_plans_library_id",
    "idx_tracks_library_id",
}

UNDO_PROVENANCE_INDEXES = {
    "idx_plan_actions_reverse_event_status": ("reverses_event_id", "status", "action_id"),
    "idx_plans_source_run_status": ("source_run_id", "status", "created_at", "plan_id"),
    "uq_plan_actions_plan_reverse_event": ("plan_id", "reverses_event_id"),
    "uq_plans_active_undo_source_run": ("source_run_id",),
    "uq_runs_plan_id": ("plan_id",),
}

UNDO_PROVENANCE_INDEX_FLAGS = {
    "idx_plan_actions_reverse_event_status": (False, False),
    "idx_plans_source_run_status": (False, False),
    "uq_plan_actions_plan_reverse_event": (True, True),
    "uq_plans_active_undo_source_run": (True, True),
    "uq_runs_plan_id": (True, False),
}


def test_sqlite_migrations_create_required_tables(tmp_path: Path) -> None:
    """Migration runner creates the SQLite table set."""
    database_file = default_application_paths(tmp_path).database_file

    migrate_database(database_file)

    assert _table_names(database_file) >= REQUIRED_TABLES


def test_accepted_artist_name_migration_preserves_existing_managed_state(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Applying the additive cache migration leaves populated Library and Track rows intact."""
    database_file = default_application_paths(tmp_path).database_file
    packaged_migrations = migration_runner.load_packaged_migrations()
    prior_migrations = tuple(
        migration for migration in packaged_migrations if migration.name < ACCEPTED_ARTIST_NAMES_MIGRATION_NAME
    )

    with monkeypatch.context() as patched:
        patched.setattr(migration_runner, "load_packaged_migrations", lambda: prior_migrations)
        with SQLiteUnitOfWork(database_file) as uow:
            uow.libraries.save(_library())
            uow.tracks.save(_track())
            uow.commit()

    migrate_database(database_file)

    assert ACCEPTED_ARTIST_NAMES_MIGRATION_NAME in _applied_migrations(database_file)
    assert "accepted_artist_names" in _table_names(database_file)
    with SQLiteUnitOfWork(database_file) as uow:
        assert uow.libraries.get(LIBRARY_ID) == _library()
        assert uow.tracks.get(TRACK_ID) == _track()


def test_plan_action_diagnostics_migration_preserves_existing_actions(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """The additive diagnostics column leaves existing PlanActions intact with no fabricated evidence."""
    database_file = default_application_paths(tmp_path).database_file
    packaged_migrations = migration_runner.load_packaged_migrations()
    prior_migrations = tuple(
        migration for migration in packaged_migrations if migration.name < PLAN_ACTION_DIAGNOSTICS_MIGRATION_NAME
    )
    existing_action = _plan_action(ACTION_ID, SORT_ORDER_EARLY)

    with monkeypatch.context() as patched:
        patched.setattr(migration_runner, "load_packaged_migrations", lambda: prior_migrations)
        with SQLiteUnitOfWork(database_file) as uow:
            uow.libraries.save(_library())
            uow.tracks.save(_track())
            uow.commit()
        _insert_plan_without_source_root(database_file, _plan())
        _insert_plan_action_without_diagnostics(database_file, existing_action)

    migrate_database(database_file)

    assert PLAN_ACTION_DIAGNOSTICS_MIGRATION_NAME in _applied_migrations(database_file)
    assert _table_columns_for(database_file, "plan_actions")["artist_name_diagnostics_json"] == "TEXT"
    with SQLiteUnitOfWork(database_file) as uow:
        assert uow.plan_actions.get(ACTION_ID) == existing_action


def test_companion_asset_migration_preserves_existing_execution_state(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """The additive companion migration retains existing Tracks, actions, and events with null asset links."""
    database_file = default_application_paths(tmp_path).database_file
    packaged_migrations = migration_runner.load_packaged_migrations()
    prior_migrations = tuple(
        migration for migration in packaged_migrations if migration.name < COMPANION_ASSETS_MIGRATION_NAME
    )
    existing_action = _plan_action(ACTION_ID, SORT_ORDER_EARLY)
    existing_event = _file_event(EVENT_ID, ACTION_ID, EVENT_SEQUENCE_EARLY)

    with monkeypatch.context() as patched:
        patched.setattr(migration_runner, "load_packaged_migrations", lambda: prior_migrations)
        with SQLiteUnitOfWork(database_file) as uow:
            uow.libraries.save(_library())
            uow.tracks.save(_track())
            uow.commit()
        _insert_plan_without_source_root(database_file, _plan())
        with SQLiteUnitOfWork(database_file) as uow:
            uow.runs.save(_run())
            uow.commit()
        _insert_plan_action_without_diagnostics(database_file, existing_action)
        _insert_file_event_without_companion_asset(database_file, existing_event)

    migrate_database(database_file)

    assert COMPANION_ASSETS_MIGRATION_NAME in _applied_migrations(database_file)
    assert _table_columns_for(database_file, "plan_actions")["companion_asset_id"] == "TEXT"
    assert _table_columns_for(database_file, "plan_actions")["owner_action_id"] == "TEXT"
    assert _table_columns_for(database_file, "file_events")["companion_asset_id"] == "TEXT"
    with SQLiteUnitOfWork(database_file) as uow:
        assert uow.tracks.get(TRACK_ID) == _track()
        assert uow.plan_actions.get(ACTION_ID) == existing_action
        assert uow.file_events.get(EVENT_ID) == existing_event
        assert uow.companion_assets.list_by_library(LIBRARY_ID) == ()


def test_companion_asset_migration_creates_foreign_keys_and_indexes(tmp_path: Path) -> None:
    """Companion tables, preallocated audit links, owner constraints, and indexes are explicit."""
    database_file = default_application_paths(tmp_path).database_file

    migrate_database(database_file)

    companion_columns = _table_columns_for(database_file, "companion_assets")
    assert companion_columns == {
        "companion_asset_id": "TEXT",
        "library_id": "TEXT",
        "kind": "TEXT",
        "owner_track_id": "TEXT",
        "current_path": "TEXT",
        "canonical_path": "TEXT",
        "content_hash": "TEXT",
        "size": "INTEGER",
        "mtime": "TEXT",
        "status": "TEXT",
        "first_seen_at": "TEXT",
        "last_seen_at": "TEXT",
        "updated_at": "TEXT",
    }
    assert ("library_id", "libraries", "library_id", "RESTRICT") in _foreign_keys(database_file, "companion_assets")
    assert ("owner_track_id", "tracks", "track_id", "RESTRICT") in _foreign_keys(database_file, "companion_assets")
    plan_action_foreign_keys = _foreign_keys(database_file, "plan_actions")
    file_event_foreign_keys = _foreign_keys(database_file, "file_events")
    assert not any(column == "companion_asset_id" for column, *_ in plan_action_foreign_keys)
    assert ("owner_action_id", "plan_actions", "action_id", "SET NULL") in plan_action_foreign_keys
    assert not any(column == "companion_asset_id" for column, *_ in file_event_foreign_keys)
    assert {
        "plan_actions_owner_same_plan_insert",
        "plan_actions_owner_same_plan_update",
    } <= _trigger_names(database_file)
    assert _index_columns(database_file, "idx_companion_assets_library_current_path") == (
        "library_id",
        "current_path",
        "companion_asset_id",
    )
    assert _index_columns(database_file, "idx_plan_action_dependencies_depends_on") == (
        "depends_on_action_id",
        "action_id",
    )


def test_sqlite_companion_assets_and_execution_links_round_trip(tmp_path: Path) -> None:
    """SQLite restores companion state, semantic action/event kinds, ownership, and dependencies verbatim."""
    database_file = default_application_paths(tmp_path).database_file
    companion_asset = _companion_asset()
    owner_action = _plan_action(ACTION_ID, SORT_ORDER_EARLY)
    companion_action = replace(
        _plan_action(SECOND_ACTION_ID, SORT_ORDER_LATE),
        action_type=ActionType.MOVE_ARTWORK,
        source_path=COMPANION_SOURCE_PATH,
        target_path=COMPANION_TARGET_PATH,
        metadata_hash_at_plan=None,
        companion_asset_id=COMPANION_ASSET_ID,
        owner_action_id=ACTION_ID,
    )
    dependency = PlanActionDependency(
        plan_id=PLAN_ID,
        action_id=SECOND_ACTION_ID,
        depends_on_action_id=ACTION_ID,
    )
    companion_event = replace(
        _file_event(EVENT_ID, SECOND_ACTION_ID, EVENT_SEQUENCE_EARLY),
        event_type=FileEventType.MOVE_ARTWORK_FILE,
        source_path=COMPANION_SOURCE_PATH,
        target_path=COMPANION_TARGET_PATH,
        companion_asset_id=COMPANION_ASSET_ID,
    )

    with SQLiteUnitOfWork(database_file) as uow:
        uow.libraries.save(_library())
        uow.tracks.save(_track())
        uow.companion_assets.save(companion_asset)
        uow.plans.save(_plan())
        uow.plan_actions.save(owner_action)
        uow.plan_actions.save(companion_action)
        uow.plan_action_dependencies.save(dependency)
        uow.runs.save(_run())
        uow.file_events.save(companion_event)
        uow.commit()

    with SQLiteUnitOfWork(database_file) as uow:
        assert uow.companion_assets.get(COMPANION_ASSET_ID) == companion_asset
        assert uow.companion_assets.list_by_library(LIBRARY_ID) == (companion_asset,)
        assert uow.plan_actions.get(SECOND_ACTION_ID) == companion_action
        assert uow.plan_action_dependencies.list_by_action(SECOND_ACTION_ID) == (dependency,)
        assert uow.file_events.get(EVENT_ID) == companion_event


def test_plan_source_and_companion_check_links_round_trip_without_asset_row(tmp_path: Path) -> None:
    """A READY Plan retains its source root and Check can name a preallocated companion identity."""
    database_file = default_application_paths(tmp_path).database_file
    plan = replace(_plan(), source_root_at_plan="/incoming")
    issue = replace(_check_issue(), companion_asset_id=COMPANION_ASSET_ID)

    with SQLiteUnitOfWork(database_file) as uow:
        uow.libraries.save(_library())
        uow.tracks.save(_track())
        uow.plans.save(plan)
        uow.check_runs.save(_check_run())
        uow.check_issues.save_many(CHECK_RUN_ID, (issue,))
        uow.commit()

    assert PLAN_SOURCE_COMPANION_CHECK_MIGRATION_NAME in _applied_migrations(database_file)
    assert _table_columns_for(database_file, "plans")["source_root_at_plan"] == "TEXT"
    assert _table_columns_for(database_file, "check_issues")["companion_asset_id"] == "TEXT"
    assert not any(column == "companion_asset_id" for column, *_ in _foreign_keys(database_file, "check_issues"))
    assert _index_columns(database_file, "idx_check_issues_companion_asset") == (
        "companion_asset_id",
        "issue_seq",
    )
    with SQLiteUnitOfWork(database_file) as uow:
        assert uow.plans.get(PLAN_ID) == plan
        assert uow.companion_assets.get(COMPANION_ASSET_ID) is None
        assert uow.check_issues.query_page(
            LIBRARY_ID,
            issue_type=None,
            page=PageRequest(),
        ).items == (issue,)


def test_sqlite_plan_action_dependency_rejects_cross_plan_reference(tmp_path: Path) -> None:
    """A durable dependency cannot connect actions from different reviewed Plans."""
    database_file = default_application_paths(tmp_path).database_file

    with SQLiteUnitOfWork(database_file) as uow:
        uow.libraries.save(_library())
        uow.tracks.save(_track())
        uow.plans.save(_plan())
        uow.plans.save(_plan(plan_id=SECOND_PLAN_ID))
        uow.plan_actions.save(_plan_action(ACTION_ID, SORT_ORDER_EARLY))
        uow.plan_actions.save(_plan_action(SECOND_ACTION_ID, SORT_ORDER_EARLY, plan_id=SECOND_PLAN_ID))
        uow.commit()

    with pytest.raises(sqlite3.IntegrityError), SQLiteUnitOfWork(database_file) as uow:
        uow.plan_action_dependencies.save(
            PlanActionDependency(
                plan_id=PLAN_ID,
                action_id=ACTION_ID,
                depends_on_action_id=SECOND_ACTION_ID,
            )
        )


def test_sqlite_plan_action_owner_rejects_cross_plan_reference(tmp_path: Path) -> None:
    """A durable owner action cannot belong to a different reviewed Plan."""
    database_file = default_application_paths(tmp_path).database_file

    with SQLiteUnitOfWork(database_file) as uow:
        uow.libraries.save(_library())
        uow.tracks.save(_track())
        uow.plans.save(_plan())
        uow.plans.save(_plan(plan_id=SECOND_PLAN_ID))
        uow.plan_actions.save(_plan_action(ACTION_ID, SORT_ORDER_EARLY))
        uow.plan_actions.save(_plan_action(SECOND_ACTION_ID, SORT_ORDER_EARLY, plan_id=SECOND_PLAN_ID))
        uow.commit()

    with pytest.raises(sqlite3.IntegrityError), SQLiteUnitOfWork(database_file) as uow:
        uow.plan_actions.save(
            replace(
                _plan_action(UNDO_ACTION_ID, SORT_ORDER_LATE),
                owner_action_id=SECOND_ACTION_ID,
            )
        )


@pytest.mark.parametrize("moved_action_id", [ACTION_ID, UNDO_ACTION_ID])
def test_sqlite_plan_action_owner_rejects_cross_plan_update(
    tmp_path: Path,
    moved_action_id: ActionId,
) -> None:
    """Changing an owner or owned action's Plan cannot split the durable ownership pair."""
    database_file = default_application_paths(tmp_path).database_file

    with SQLiteUnitOfWork(database_file) as uow:
        uow.libraries.save(_library())
        uow.tracks.save(_track())
        uow.plans.save(_plan())
        uow.plans.save(_plan(plan_id=SECOND_PLAN_ID))
        uow.plan_actions.save(_plan_action(ACTION_ID, SORT_ORDER_EARLY))
        uow.plan_actions.save(
            replace(
                _plan_action(UNDO_ACTION_ID, SORT_ORDER_LATE),
                owner_action_id=ACTION_ID,
            )
        )
        uow.commit()

    with sqlite3.connect(database_file) as connection:
        _ = connection.execute("PRAGMA foreign_keys = ON")
        with pytest.raises(sqlite3.IntegrityError):
            _ = connection.execute(
                "UPDATE plan_actions SET plan_id = ? WHERE action_id = ?",
                (str(SECOND_PLAN_ID), str(moved_action_id)),
            )


def test_sqlite_accepted_artist_names_are_sticky_and_round_trip_provenance(tmp_path: Path) -> None:
    """Accepted artist-name persistence keeps the first result and restores all provenance."""
    database_file = default_application_paths(tmp_path).database_file
    accepted_name = _accepted_artist_name()
    replacement = replace(accepted_name, resolved_name="Utada Hikaru")

    with SQLiteUnitOfWork(database_file) as uow:
        assert uow.accepted_artist_names.find_by_source_key(ACCEPTED_ARTIST_SOURCE_KEY) is None
        assert uow.accepted_artist_names.insert_if_absent(accepted_name) is True
        uow.commit()

    with SQLiteUnitOfWork(database_file) as uow:
        assert uow.accepted_artist_names.insert_if_absent(replacement) is False
        uow.commit()

    with SQLiteUnitOfWork(database_file) as uow:
        assert uow.accepted_artist_names.find_by_source_key(ACCEPTED_ARTIST_SOURCE_KEY) == accepted_name


def test_sqlite_accepted_artist_names_allow_multiple_sources_for_one_provider_identity(tmp_path: Path) -> None:
    """Distinct source spellings may select the same MusicBrainz artist identity."""
    database_file = default_application_paths(tmp_path).database_file
    first = _accepted_artist_name()
    second = replace(first, source_key="Utada Hikaru", source_name="Utada Hikaru")

    with SQLiteUnitOfWork(database_file) as uow:
        assert uow.accepted_artist_names.insert_if_absent(first) is True
        assert uow.accepted_artist_names.insert_if_absent(second) is True
        uow.commit()

    with SQLiteUnitOfWork(database_file) as uow:
        assert uow.accepted_artist_names.find_by_source_key(first.source_key) == first
        assert uow.accepted_artist_names.find_by_source_key(second.source_key) == second


@pytest.mark.parametrize(
    ("provider", "selected_name_kind", "selected_locale"),
    [
        ("other", "alias", "en"),
        ("musicbrainz", "unsupported", None),
        ("musicbrainz", "sort_name", None),
        ("musicbrainz", "name", "en"),
    ],
    ids=["provider", "selection-kind", "sort-name", "non-alias-locale"],
)
def test_sqlite_accepted_artist_name_migration_rejects_invalid_provenance(
    tmp_path: Path,
    provider: str,
    selected_name_kind: str,
    selected_locale: str | None,
) -> None:
    """Schema constraints reject provider provenance outside the closed contract."""
    database_file = default_application_paths(tmp_path).database_file
    migrate_database(database_file)

    with sqlite3.connect(database_file) as connection, pytest.raises(sqlite3.IntegrityError):
        _ = connection.execute(
            """
            INSERT INTO accepted_artist_names (
                source_key,
                source_name,
                resolved_name,
                provider,
                provider_artist_id,
                selected_name_kind,
                selected_locale,
                accepted_at
            )
            VALUES (?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                ACCEPTED_ARTIST_SOURCE_KEY,
                ACCEPTED_ARTIST_SOURCE_NAME,
                ACCEPTED_ARTIST_RESOLVED_NAME,
                provider,
                MUSICBRAINZ_ARTIST_ID,
                selected_name_kind,
                selected_locale,
                BASE_TIME.isoformat(),
            ),
        )


def test_sqlite_accepted_artist_name_migration_rejects_null_source_key(tmp_path: Path) -> None:
    """The text primary key explicitly rejects SQLite's otherwise-permitted NULL values."""
    database_file = default_application_paths(tmp_path).database_file
    migrate_database(database_file)

    with sqlite3.connect(database_file) as connection, pytest.raises(sqlite3.IntegrityError):
        _ = connection.execute(
            """
            INSERT INTO accepted_artist_names (
                source_key,
                source_name,
                resolved_name,
                provider,
                provider_artist_id,
                selected_name_kind,
                selected_locale,
                accepted_at
            )
            VALUES (?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                None,
                ACCEPTED_ARTIST_SOURCE_NAME,
                ACCEPTED_ARTIST_RESOLVED_NAME,
                ArtistNameProvider.MUSICBRAINZ.value,
                MUSICBRAINZ_ARTIST_ID,
                SelectedArtistNameKind.ALIAS.value,
                "en",
                BASE_TIME.isoformat(),
            ),
        )


def test_sqlite_accepted_artist_name_insert_rolls_back_without_commit(tmp_path: Path) -> None:
    """Accepted artist-name inserts obey the surrounding UnitOfWork transaction."""
    database_file = default_application_paths(tmp_path).database_file

    with SQLiteUnitOfWork(database_file) as uow:
        assert uow.accepted_artist_names.insert_if_absent(_accepted_artist_name()) is True

    with SQLiteUnitOfWork(database_file) as uow:
        assert uow.accepted_artist_names.find_by_source_key(ACCEPTED_ARTIST_SOURCE_KEY) is None


def test_sqlite_migrations_create_browsing_indexes(tmp_path: Path) -> None:
    """Browsing migrations create every Plan/Track/PlanAction/Run browsing index."""
    database_file = default_application_paths(tmp_path).database_file

    migrate_database(database_file)

    assert _index_names(database_file) >= REQUIRED_BROWSING_INDEXES


def test_sqlite_performance_index_migration_replaces_redundant_indexes(tmp_path: Path) -> None:
    """Performance indexes have the intended columns and replace redundant single-column indexes."""
    database_file = default_application_paths(tmp_path).database_file

    migrate_database(database_file)

    index_names = _index_names(database_file)
    assert index_names >= set(PERFORMANCE_INDEX_COLUMNS)
    assert index_names.isdisjoint(REMOVED_REDUNDANT_INDEXES)
    for index_name, columns in PERFORMANCE_INDEX_COLUMNS.items():
        assert _index_columns(database_file, index_name) == columns


def test_sqlite_performance_index_migration_preserves_existing_managed_state(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """The performance-index migration preserves every populated managed row."""
    database_file = default_application_paths(tmp_path).database_file
    packaged_migrations = migration_runner.load_packaged_migrations()
    migrations_without_performance_indexes = tuple(
        migration for migration in packaged_migrations if migration.name != PERFORMANCE_INDEX_MIGRATION_NAME
    )
    event = _file_event(EVENT_ID, ACTION_ID, EVENT_SEQUENCE_EARLY)
    check_run = _check_run()
    check_issue = _check_issue()

    with monkeypatch.context() as patched:
        patched.setattr(
            migration_runner,
            "load_packaged_migrations",
            lambda: migrations_without_performance_indexes,
        )
        with SQLiteUnitOfWork(database_file) as uow:
            uow.libraries.save(_library())
            uow.tracks.save(_track())
            uow.plans.save(_plan())
            uow.plan_actions.save(_plan_action(ACTION_ID, SORT_ORDER_EARLY))
            uow.runs.save(_run())
            uow.file_events.save(event)
            uow.check_runs.save(check_run)
            uow.check_issues.save_many(CHECK_RUN_ID, (check_issue,))
            uow.commit()

    assert _index_names(database_file) >= REMOVED_REDUNDANT_INDEXES

    migrate_database(database_file)

    assert PERFORMANCE_INDEX_MIGRATION_NAME in _applied_migrations(database_file)
    with SQLiteUnitOfWork(database_file) as uow:
        assert uow.libraries.get(LIBRARY_ID) == _library()
        assert uow.tracks.get(TRACK_ID) == _track()
        assert uow.plans.get(PLAN_ID) == _plan()
        assert uow.plan_actions.get(ACTION_ID) == _plan_action(ACTION_ID, SORT_ORDER_EARLY)
        assert uow.runs.get(RUN_ID) == _run()
        assert uow.file_events.get(EVENT_ID) == event
        assert uow.check_runs.latest(LIBRARY_ID) == check_run
        assert uow.check_issues.query_page(LIBRARY_ID, issue_type=None, page=PageRequest()).items == (check_issue,)


def test_track_stat_baseline_migration_preserves_existing_tracks_with_null_baseline(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Existing Track rows remain intact and ineligible for stat trust after migration."""
    database_file = default_application_paths(tmp_path).database_file
    packaged_migrations = migration_runner.load_packaged_migrations()
    prior_migrations = tuple(
        migration for migration in packaged_migrations if migration.name < STAT_BASELINE_MIGRATION_NAME
    )

    with monkeypatch.context() as patched:
        patched.setattr(migration_runner, "load_packaged_migrations", lambda: prior_migrations)
        migrate_database(database_file)
        _insert_track_before_stat_baseline_migration(database_file)

    migrate_database(database_file)

    assert STAT_BASELINE_MIGRATION_NAME in _applied_migrations(database_file)
    assert _table_columns(database_file)["size"] == "INTEGER"
    assert _table_columns(database_file)["mtime"] == "TEXT"
    with SQLiteUnitOfWork(database_file) as uow:
        assert uow.tracks.get(TRACK_ID) == _track(size=None, mtime=None)


def test_track_stat_baseline_migration_rejects_negative_size(tmp_path: Path) -> None:
    """The Track stat-baseline column rejects negative persisted sizes."""
    database_file = default_application_paths(tmp_path).database_file
    with SQLiteUnitOfWork(database_file) as uow:
        uow.libraries.save(_library())
        uow.tracks.save(_track())
        uow.commit()

    with sqlite3.connect(database_file) as connection, pytest.raises(sqlite3.IntegrityError):
        _ = connection.execute(
            "UPDATE tracks SET size = -1 WHERE track_id = ?",
            (str(TRACK_ID),),
        )


def test_undo_provenance_migration_creates_columns_foreign_keys_and_indexes(tmp_path: Path) -> None:
    """Fresh databases expose the implemented Undo provenance and single-use indexes."""
    database_file = default_application_paths(tmp_path).database_file

    migrate_database(database_file)

    assert _table_columns_for(database_file, "plans")["source_run_id"] == "TEXT"
    assert _table_columns_for(database_file, "plan_actions")["reverses_event_id"] == "TEXT"
    assert ("source_run_id", "runs", "run_id", "RESTRICT") in _foreign_keys(database_file, "plans")
    assert (
        "reverses_event_id",
        "file_events",
        "event_id",
        "RESTRICT",
    ) in _foreign_keys(database_file, "plan_actions")
    assert _index_names(database_file) >= set(UNDO_PROVENANCE_INDEXES)
    for index_name, columns in UNDO_PROVENANCE_INDEXES.items():
        assert _index_columns(database_file, index_name) == columns

    index_flags = {
        **_index_flags(database_file, "plan_actions"),
        **_index_flags(database_file, "plans"),
        **_index_flags(database_file, "runs"),
    }
    assert {name: index_flags[name] for name in UNDO_PROVENANCE_INDEX_FLAGS} == UNDO_PROVENANCE_INDEX_FLAGS


def test_undo_provenance_migration_backfills_provable_legacy_history(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """One proven legacy source Run and FileEvent become durable Undo provenance."""
    database_file = default_application_paths(tmp_path).database_file
    _migrate_before_undo_provenance(database_file, monkeypatch)
    _insert_legacy_undo_history(database_file, source_candidate_count=1)

    migrate_database(database_file)

    assert UNDO_PROVENANCE_MIGRATION_NAME in _applied_migrations(database_file)
    with sqlite3.connect(database_file) as connection:
        plan_row = cast(
            "tuple[str] | None",
            connection.execute(
                "SELECT source_run_id FROM plans WHERE plan_id = ?",
                (str(UNDO_PLAN_ID),),
            ).fetchone(),
        )
        action_row = cast(
            "tuple[str] | None",
            connection.execute(
                "SELECT reverses_event_id FROM plan_actions WHERE action_id = ?",
                (str(UNDO_ACTION_ID),),
            ).fetchone(),
        )
    assert plan_row == (str(RUN_ID),)
    assert action_row == (str(EVENT_ID),)


@pytest.mark.parametrize("source_candidate_count", [0, 2], ids=["absent", "ambiguous"])
def test_undo_provenance_migration_rolls_back_unprovable_legacy_history(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    source_candidate_count: int,
) -> None:
    """Absent or ambiguous legacy provenance fails without changing schema or managed rows."""
    database_file = default_application_paths(tmp_path).database_file
    _migrate_before_undo_provenance(database_file, monkeypatch)
    _insert_legacy_undo_history(database_file, source_candidate_count=source_candidate_count)

    with pytest.raises(sqlite3.IntegrityError, match="invalid = 0"):
        migrate_database(database_file)

    assert UNDO_PROVENANCE_MIGRATION_NAME not in _applied_migrations(database_file)
    assert "source_run_id" not in _table_columns_for(database_file, "plans")
    assert "reverses_event_id" not in _table_columns_for(database_file, "plan_actions")
    assert _index_names(database_file).isdisjoint(UNDO_PROVENANCE_INDEXES)
    with sqlite3.connect(database_file) as connection:
        undo_plan_count = cast(
            "tuple[int] | None",
            connection.execute(
                "SELECT COUNT(*) FROM plans WHERE plan_id = ?",
                (str(UNDO_PLAN_ID),),
            ).fetchone(),
        )
        undo_action_count = cast(
            "tuple[int] | None",
            connection.execute(
                "SELECT COUNT(*) FROM plan_actions WHERE action_id = ?",
                (str(UNDO_ACTION_ID),),
            ).fetchone(),
        )
    assert undo_plan_count == (1,)
    assert undo_action_count == (1,)


@pytest.mark.parametrize(
    "tamper_kind",
    [
        "event_completed_after_undo",
        "run_completed_after_undo",
        "source_action_path_mismatch",
        "source_action_not_applied",
        "source_plan_not_terminal",
    ],
)
def test_undo_provenance_migration_rejects_inconsistent_legacy_evidence(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    tamper_kind: str,
) -> None:
    """Backfill refuses history that cannot prove the exact completed source mutation."""
    database_file = default_application_paths(tmp_path).database_file
    _migrate_before_undo_provenance(database_file, monkeypatch)
    _insert_legacy_undo_history(database_file, source_candidate_count=1)
    _tamper_legacy_undo_source(database_file, tamper_kind)

    with pytest.raises(sqlite3.IntegrityError, match="invalid = 0"):
        migrate_database(database_file)

    assert UNDO_PROVENANCE_MIGRATION_NAME not in _applied_migrations(database_file)
    assert "source_run_id" not in _table_columns_for(database_file, "plans")
    assert "reverses_event_id" not in _table_columns_for(database_file, "plan_actions")


def test_runs_reject_a_second_execution_attempt_for_one_plan(tmp_path: Path) -> None:
    """The single-use Plan constraint permits at most one Run."""
    database_file = default_application_paths(tmp_path).database_file
    with SQLiteUnitOfWork(database_file) as uow:
        uow.libraries.save(_library())
        uow.plans.save(_plan())
        uow.runs.save(_run())
        uow.commit()

    with SQLiteUnitOfWork(database_file) as uow, pytest.raises(sqlite3.IntegrityError):
        uow.runs.save(_run(run_id=SECOND_RUN_ID))

    with SQLiteUnitOfWork(database_file) as uow:
        assert uow.runs.list_by_plan(PLAN_ID) == (_run(),)


def test_sqlite_migration_script_rolls_back_with_marker_on_failure(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
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


def test_ensure_database_migrated_loads_packaged_migrations_once(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """A second ensure call for one path reuses the process-wide cache."""
    database_file = default_application_paths(tmp_path).database_file
    load_calls = 0
    real_load_packaged_migrations = migration_runner.load_packaged_migrations

    def _counting_load() -> tuple[SQLiteMigration, ...]:
        nonlocal load_calls
        load_calls += 1
        return real_load_packaged_migrations()

    monkeypatch.setattr(migration_runner, "load_packaged_migrations", _counting_load)

    ensure_database_migrated(database_file)
    ensure_database_migrated(database_file)

    assert load_calls == 1
    assert _table_names(database_file) >= REQUIRED_TABLES


def test_ensure_database_migrated_recreates_deleted_database(tmp_path: Path) -> None:
    """Deleting the database file forces re-migration despite the cache."""
    database_file = default_application_paths(tmp_path).database_file

    ensure_database_migrated(database_file)
    database_file.unlink()
    ensure_database_migrated(database_file)

    assert _table_names(database_file) >= REQUIRED_TABLES


def test_sqlite_unit_of_work_reenters_sequentially(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """Outside a usecase scope, sequential transactions still use separate connections."""
    database_file = default_application_paths(tmp_path).database_file
    library = _library()
    uow = SQLiteUnitOfWork(database_file)
    connections = _record_uow_connections(monkeypatch)

    with uow:
        uow.libraries.save(library)
        uow.commit()

    with uow:
        assert uow.libraries.get(LIBRARY_ID) == library

    assert len(connections) == EXPECTED_REENTER_CONNECTION_COUNT
    for connection in connections:
        _assert_connection_closed(connection)


def test_sqlite_unit_of_work_usecase_scope_reuses_one_connection_per_transaction(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """A usecase scope reuses one connection while retaining separate transaction boundaries."""
    database_file = default_application_paths(tmp_path).database_file
    ensure_database_migrated(database_file)
    statements: list[str] = []
    connections = _record_uow_connections(monkeypatch, statements=statements)
    uow = SQLiteUnitOfWork(database_file)
    library = _library()

    with uow.usecase_scope():
        with uow:
            uow.libraries.save(library)
            uow.commit()

        with pytest.raises(RuntimeError, match="must be entered"):
            _ = uow.libraries
        with pytest.raises(RuntimeError, match="must be entered"):
            uow.commit()

        with uow:
            assert uow.libraries.get(LIBRARY_ID) == library

        with uow:
            uow.libraries.save(library)
            uow.commit()

        assert len(connections) == REUSED_CONNECTION_COUNT
        _ = connections[0].execute("SELECT 1")

    normalized_statements = [statement.strip().upper() for statement in statements]
    assert normalized_statements.count("BEGIN") == REUSED_BEGIN_COUNT
    assert normalized_statements.count("COMMIT") == REUSED_COMMIT_COUNT
    assert normalized_statements.count("ROLLBACK") == REUSED_ROLLBACK_COUNT
    _assert_connection_closed(connections[0])


def test_sqlite_unit_of_work_usecase_scope_keeps_wal_until_disposal(tmp_path: Path) -> None:
    """Committed WAL data remains while the shared connection is open and clears on its final close."""
    database_file = default_application_paths(tmp_path).database_file
    ensure_database_migrated(database_file)
    wal_file = database_file.with_name(f"{database_file.name}-wal")
    uow = SQLiteUnitOfWork(database_file)

    with uow.usecase_scope():
        with uow:
            uow.libraries.save(_library())
            uow.commit()

        assert wal_file.is_file()
        assert wal_file.stat().st_size > 0

    assert not wal_file.exists() or wal_file.stat().st_size == 0


def test_sqlite_unit_of_work_usecase_scope_rolls_back_and_closes_on_exception(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """An exception rolls back its transaction and deterministically closes the shared connection."""
    database_file = default_application_paths(tmp_path).database_file
    ensure_database_migrated(database_file)
    connections = _record_uow_connections(monkeypatch)
    uow = SQLiteUnitOfWork(database_file)

    with pytest.raises(RuntimeError, match=ROLLBACK_ERROR):
        _save_library_in_usecase_then_fail(uow)

    assert len(connections) == REUSED_CONNECTION_COUNT
    _assert_connection_closed(connections[0])
    with SQLiteUnitOfWork(database_file) as verification_uow:
        assert verification_uow.libraries.get(LIBRARY_ID) is None


@pytest.mark.parametrize("retain_connection", [False, True], ids=["ordinary", "usecase-scope"])
def test_sqlite_unit_of_work_closes_failed_begin_and_can_retry(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    *,
    retain_connection: bool,
) -> None:
    """A failed BEGIN releases its connection and leaves the UnitOfWork reusable."""
    database_file = default_application_paths(tmp_path).database_file
    ensure_database_migrated(database_file)
    connections = _record_uow_connections_with_first_begin_denied(monkeypatch)
    uow = SQLiteUnitOfWork(database_file)
    resource_scope = uow.usecase_scope() if retain_connection else nullcontext()

    with resource_scope:
        with pytest.raises(sqlite3.DatabaseError), uow:
            pass

        _assert_connection_closed(connections[0])
        with pytest.raises(RuntimeError, match="must be entered"):
            _ = uow.libraries

        with uow:
            assert uow.libraries.list_all() == ()

    assert len(connections) == EXPECTED_REENTER_CONNECTION_COUNT
    _assert_connection_closed(connections[1])


def test_internal_storage_is_created_lazily_when_needed(tmp_path: Path) -> None:
    """Entering SQLiteUnitOfWork creates the internal .data database path."""
    paths = default_application_paths(tmp_path)

    assert not paths.data_dir.exists()

    with SQLiteUnitOfWork(paths.database_file):
        pass

    assert paths.data_dir.is_dir()
    assert paths.database_file.is_file()


def test_sqlite_repositories_round_trip_domain_models(tmp_path: Path) -> None:
    """SQLite repositories persist and restore every persisted domain model."""
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
        assert uow.plans.get(PLAN_ID) == plan
        assert uow.plans.list_by_library(LIBRARY_ID) == (plan,)
        assert uow.plan_actions.get(ACTION_ID) == action_early
        assert uow.plan_actions.list_by_plan(PLAN_ID) == (action_early, action_late)
        assert uow.runs.get(RUN_ID) == run
        assert uow.runs.list_by_library(LIBRARY_ID) == (run,)
        assert uow.runs.list_by_plan(PLAN_ID) == (run,)
        assert uow.file_events.get(EVENT_ID) == event_early
        assert uow.file_events.list_by_run(RUN_ID) == (event_early, event_late)
        assert uow.file_events.list_by_library(LIBRARY_ID) == (event_early, event_late)


def test_sqlite_plan_action_unknown_to_binary_fails_closed_on_read(tmp_path: Path) -> None:
    """A downgrade cannot decode or apply a persisted action type it does not understand."""
    database_file = default_application_paths(tmp_path).database_file
    with SQLiteUnitOfWork(database_file) as uow:
        uow.libraries.save(_library())
        uow.tracks.save(_track())
        uow.plans.save(_plan())
        uow.plan_actions.save(_plan_action(ACTION_ID, SORT_ORDER_EARLY))
        uow.commit()

    with sqlite3.connect(database_file) as connection:
        _ = connection.execute(
            "UPDATE plan_actions SET action_type = ? WHERE action_id = ?",
            ("future_file_move", str(ACTION_ID)),
        )
        connection.commit()

    with SQLiteUnitOfWork(database_file) as uow, pytest.raises(ValueError, match="future_file_move"):
        _ = uow.plan_actions.list_by_plan(PLAN_ID)


def test_sqlite_plan_actions_round_trip_typed_artist_name_diagnostics(tmp_path: Path) -> None:
    """PlanAction persistence restores the complete typed naming review snapshot."""
    database_file = default_application_paths(tmp_path).database_file
    diagnostics = _artist_name_diagnostics()
    action = _plan_action(ACTION_ID, SORT_ORDER_EARLY, artist_name_diagnostics=diagnostics)

    with SQLiteUnitOfWork(database_file) as uow:
        uow.libraries.save(_library())
        uow.tracks.save(_track())
        uow.plans.save(_plan())
        uow.plan_actions.save(action)
        uow.commit()

    with SQLiteUnitOfWork(database_file) as uow:
        assert uow.plan_actions.get(ACTION_ID) == action

    with sqlite3.connect(database_file) as connection:
        row = cast(
            "tuple[str] | None",
            connection.execute(
                "SELECT artist_name_diagnostics_json FROM plan_actions WHERE action_id = ?",
                (str(ACTION_ID),),
            ).fetchone(),
        )
        assert row is not None
        assert json.loads(row[0]) == {
            "album_artist": {
                "issue": ArtistNameResolutionIssue.AMBIGUOUS_MATCH.value,
                "provenance": ArtistNameResolutionProvenance.ORIGINAL.value,
                "resolved_name": ACCEPTED_ARTIST_SOURCE_NAME,
                "source_name": ACCEPTED_ARTIST_SOURCE_NAME,
            },
            "artist": {
                "issue": None,
                "provenance": ArtistNameResolutionProvenance.ACCEPTED_MUSICBRAINZ.value,
                "resolved_name": ACCEPTED_ARTIST_RESOLVED_NAME,
                "source_name": ACCEPTED_ARTIST_SOURCE_NAME,
            },
        }


@pytest.mark.parametrize("invalid_payload", ["{", "[]"])
def test_sqlite_plan_action_diagnostics_column_rejects_non_object_json(
    tmp_path: Path,
    invalid_payload: str,
) -> None:
    """The additive column cannot retain malformed or non-object diagnostics JSON."""
    database_file = default_application_paths(tmp_path).database_file
    with SQLiteUnitOfWork(database_file) as uow:
        uow.libraries.save(_library())
        uow.tracks.save(_track())
        uow.plans.save(_plan())
        uow.plan_actions.save(_plan_action(ACTION_ID, SORT_ORDER_EARLY))
        uow.commit()

    with sqlite3.connect(database_file) as connection, pytest.raises(sqlite3.IntegrityError):
        _ = connection.execute(
            "UPDATE plan_actions SET artist_name_diagnostics_json = ? WHERE action_id = ?",
            (invalid_payload, str(ACTION_ID)),
        )


@pytest.mark.parametrize("missing_field", ["source_name", "resolved_name", "issue"])
def test_sqlite_plan_actions_reject_incomplete_artist_name_diagnostics(
    tmp_path: Path,
    missing_field: str,
) -> None:
    """Nullable diagnostic fields remain required so missing evidence is not fabricated as null."""
    database_file = default_application_paths(tmp_path).database_file
    with SQLiteUnitOfWork(database_file) as uow:
        uow.libraries.save(_library())
        uow.tracks.save(_track())
        uow.plans.save(_plan())
        uow.plan_actions.save(
            _plan_action(ACTION_ID, SORT_ORDER_EARLY, artist_name_diagnostics=_artist_name_diagnostics())
        )
        uow.commit()

    payload = {
        "artist": {
            "source_name": ACCEPTED_ARTIST_SOURCE_NAME,
            "resolved_name": ACCEPTED_ARTIST_RESOLVED_NAME,
            "provenance": ArtistNameResolutionProvenance.ACCEPTED_MUSICBRAINZ.value,
            "issue": None,
        },
        "album_artist": {
            "source_name": ACCEPTED_ARTIST_SOURCE_NAME,
            "resolved_name": ACCEPTED_ARTIST_SOURCE_NAME,
            "provenance": ArtistNameResolutionProvenance.ORIGINAL.value,
            "issue": ArtistNameResolutionIssue.AMBIGUOUS_MATCH.value,
        },
    }
    artist_payload = cast("dict[str, object]", payload["artist"])
    _ = artist_payload.pop(missing_field)
    with sqlite3.connect(database_file) as connection:
        _ = connection.execute(
            "UPDATE plan_actions SET artist_name_diagnostics_json = ? WHERE action_id = ?",
            (json.dumps(payload), str(ACTION_ID)),
        )

    with (
        SQLiteUnitOfWork(database_file) as uow,
        pytest.raises(
            TypeError,
            match=INVALID_ARTIST_NAME_DIAGNOSTICS_MESSAGE,
        ),
    ):
        _ = uow.plan_actions.get(ACTION_ID)


def test_sqlite_repositories_round_trip_undo_provenance(tmp_path: Path) -> None:
    """Plan and PlanAction repositories preserve Run and FileEvent provenance verbatim."""
    database_file = default_application_paths(tmp_path).database_file
    source_plan = _plan().mark_applied()
    source_action = _plan_action(ACTION_ID, SORT_ORDER_EARLY).mark_applied()
    source_run = _run().mark_succeeded(FINISHED_TIME)
    source_event = _file_event(EVENT_ID, ACTION_ID, EVENT_SEQUENCE_EARLY).mark_succeeded(FINISHED_TIME)
    undo_plan = _plan(
        plan_id=UNDO_PLAN_ID,
        plan_type=PlanType.UNDO,
        source_run_id=RUN_ID,
    )
    undo_action = replace(
        _plan_action(UNDO_ACTION_ID, SORT_ORDER_EARLY, plan_id=UNDO_PLAN_ID),
        source_path=TARGET_PATH,
        target_path=SOURCE_PATH,
        reverses_event_id=EVENT_ID,
    )

    with SQLiteUnitOfWork(database_file) as uow:
        uow.libraries.save(_library())
        uow.tracks.save(_track())
        uow.plans.save(source_plan)
        uow.plan_actions.save(source_action)
        uow.runs.save(source_run)
        uow.file_events.save(source_event)
        uow.plans.save(undo_plan)
        uow.plan_actions.save(undo_action)
        uow.commit()

    with SQLiteUnitOfWork(database_file) as uow:
        assert uow.plans.get(UNDO_PLAN_ID) == undo_plan
        assert uow.plan_actions.get(UNDO_ACTION_ID) == undo_action


def test_sqlite_file_events_list_pending_by_library_filters_status_and_orders_by_sequence(tmp_path: Path) -> None:
    """list_pending_by_library returns PENDING events in (sequence_no, event_id) order for one Library."""
    database_file = default_application_paths(tmp_path).database_file
    event_late = _file_event(LATE_EVENT_ID, LATE_ACTION_ID, EVENT_SEQUENCE_LATE)
    event_early = _file_event(EVENT_ID, ACTION_ID, EVENT_SEQUENCE_EARLY)
    event_second_run = _file_event(
        SECOND_RUN_EVENT_ID,
        SECOND_ACTION_ID,
        EVENT_SEQUENCE_EARLY,
        run_id=SECOND_RUN_ID,
    )
    event_succeeded = _file_event(SUCCEEDED_EVENT_ID, ACTION_ID, EVENT_SEQUENCE_THIRD).mark_succeeded(FINISHED_TIME)

    with SQLiteUnitOfWork(database_file) as uow:
        uow.libraries.save(_library())
        uow.tracks.save(_track())
        uow.plans.save(_plan())
        uow.plans.save(_plan(plan_id=SECOND_PLAN_ID))
        uow.plan_actions.save(_plan_action(ACTION_ID, SORT_ORDER_EARLY))
        uow.plan_actions.save(_plan_action(LATE_ACTION_ID, SORT_ORDER_LATE))
        uow.plan_actions.save(_plan_action(SECOND_ACTION_ID, SORT_ORDER_EARLY, plan_id=SECOND_PLAN_ID))
        uow.runs.save(_run())
        uow.runs.save(_run(run_id=SECOND_RUN_ID, plan_id=SECOND_PLAN_ID))
        uow.file_events.save(event_late)
        uow.file_events.save(event_early)
        uow.file_events.save(event_second_run)
        uow.file_events.save(event_succeeded)
        uow.commit()

    with SQLiteUnitOfWork(database_file) as uow:
        assert uow.file_events.list_pending_by_library(LIBRARY_ID) == (event_early, event_second_run, event_late)
        assert uow.file_events.list_pending_by_library(OTHER_LIBRARY_ID) == ()


def test_sqlite_unit_of_work_rolls_back_when_not_committed(tmp_path: Path) -> None:
    """Closing without commit leaves no repository writes behind."""
    database_file = default_application_paths(tmp_path).database_file

    with SQLiteUnitOfWork(database_file) as uow:
        uow.libraries.save(_library())

    with SQLiteUnitOfWork(database_file) as uow:
        assert uow.libraries.get(LIBRARY_ID) is None


def test_sqlite_unit_of_work_rolls_back_on_exception(tmp_path: Path) -> None:
    """Exceptions inside the UnitOfWork rollback uncommitted writes."""
    database_file = default_application_paths(tmp_path).database_file

    with pytest.raises(RuntimeError, match=ROLLBACK_ERROR):
        _save_library_then_fail(database_file)

    with SQLiteUnitOfWork(database_file) as uow:
        assert uow.libraries.get(LIBRARY_ID) is None


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


def _accepted_artist_name() -> AcceptedArtistName:
    return AcceptedArtistName(
        source_key=ACCEPTED_ARTIST_SOURCE_KEY,
        source_name=ACCEPTED_ARTIST_SOURCE_NAME,
        resolved_name=ACCEPTED_ARTIST_RESOLVED_NAME,
        provider=ArtistNameProvider.MUSICBRAINZ,
        provider_artist_id=MUSICBRAINZ_ARTIST_ID,
        selected_name_kind=SelectedArtistNameKind.ALIAS,
        selected_locale="en",
        accepted_at=BASE_TIME,
    )


def _artist_name_diagnostics() -> ArtistNameDiagnostics:
    return ArtistNameDiagnostics(
        artist=ArtistNameResolutionDiagnostic(
            source_name=ACCEPTED_ARTIST_SOURCE_NAME,
            resolved_name=ACCEPTED_ARTIST_RESOLVED_NAME,
            provenance=ArtistNameResolutionProvenance.ACCEPTED_MUSICBRAINZ,
        ),
        album_artist=ArtistNameResolutionDiagnostic(
            source_name=ACCEPTED_ARTIST_SOURCE_NAME,
            resolved_name=ACCEPTED_ARTIST_SOURCE_NAME,
            provenance=ArtistNameResolutionProvenance.ORIGINAL,
            issue=ArtistNameResolutionIssue.AMBIGUOUS_MATCH,
        ),
    )


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


def _table_columns(database_file: Path) -> dict[str, str]:
    return _table_columns_for(database_file, "tracks")


def _table_columns_for(database_file: Path, table_name: str) -> dict[str, str]:
    with sqlite3.connect(database_file) as connection:
        rows = connection.execute(
            "SELECT name, type FROM pragma_table_info(?)",
            (table_name,),
        ).fetchall()
    return {str(row[0]): str(row[1]) for row in cast("list[tuple[object, ...]]", rows)}


def _index_columns(database_file: Path, index_name: str) -> tuple[str, ...]:
    with sqlite3.connect(database_file) as connection:
        rows = connection.execute(
            "SELECT name FROM pragma_index_info(?) ORDER BY seqno",
            (index_name,),
        ).fetchall()
    return tuple(str(row[0]) for row in cast("list[tuple[object, ...]]", rows))


def _index_flags(database_file: Path, table_name: str) -> dict[str, tuple[bool, bool]]:
    with sqlite3.connect(database_file) as connection:
        rows = connection.execute(
            'SELECT name, "unique", partial FROM pragma_index_list(?)',
            (table_name,),
        ).fetchall()
    return {str(row[0]): (bool(row[1]), bool(row[2])) for row in cast("list[tuple[object, ...]]", rows)}


def _foreign_keys(database_file: Path, table_name: str) -> set[tuple[str, str, str, str]]:
    with sqlite3.connect(database_file) as connection:
        rows = connection.execute(
            'SELECT "from", "table", "to", on_delete FROM pragma_foreign_key_list(?)',
            (table_name,),
        ).fetchall()
    return {(str(row[0]), str(row[1]), str(row[2]), str(row[3])) for row in cast("list[tuple[object, ...]]", rows)}


def _trigger_names(database_file: Path) -> set[str]:
    with sqlite3.connect(database_file) as connection:
        rows = connection.execute("SELECT name FROM sqlite_master WHERE type = 'trigger'").fetchall()
    return {str(row[0]) for row in cast("list[tuple[object, ...]]", rows)}


def _applied_migrations(database_file: Path) -> set[str]:
    with sqlite3.connect(database_file) as connection:
        rows = connection.execute("SELECT migration_name FROM schema_migrations").fetchall()
    return {str(row[0]) for row in cast("list[tuple[object, ...]]", rows)}


def _save_library_then_fail(database_file: Path) -> None:
    with SQLiteUnitOfWork(database_file) as uow:
        uow.libraries.save(_library())
        raise RuntimeError(ROLLBACK_ERROR)


def _save_library_in_usecase_then_fail(uow: SQLiteUnitOfWork) -> None:
    with uow.usecase_scope(), uow:
        uow.libraries.save(_library())
        raise RuntimeError(ROLLBACK_ERROR)


def _record_uow_connections(
    monkeypatch: pytest.MonkeyPatch,
    *,
    statements: list[str] | None = None,
) -> list[sqlite3.Connection]:
    real_open = cast(
        "Callable[[str | PathLike[str]], sqlite3.Connection]",
        vars(unit_of_work_module)["open_sqlite_connection"],
    )
    connections: list[sqlite3.Connection] = []

    def recording_open(database_path: str | PathLike[str]) -> sqlite3.Connection:
        connection = real_open(database_path)
        if statements is not None:
            _ = connection.set_trace_callback(statements.append)
        connections.append(connection)
        return connection

    monkeypatch.setattr(unit_of_work_module, "open_sqlite_connection", recording_open)
    return connections


def _record_uow_connections_with_first_begin_denied(
    monkeypatch: pytest.MonkeyPatch,
) -> list[sqlite3.Connection]:
    real_open = cast(
        "Callable[[str | PathLike[str]], sqlite3.Connection]",
        vars(unit_of_work_module)["open_sqlite_connection"],
    )
    connections: list[sqlite3.Connection] = []

    def deny_transaction(
        action_code: int,
        first_argument: str | None,
        second_argument: str | None,
        database_name: str | None,
        trigger_name: str | None,
    ) -> int:
        del first_argument, second_argument, database_name, trigger_name
        return sqlite3.SQLITE_DENY if action_code == sqlite3.SQLITE_TRANSACTION else sqlite3.SQLITE_OK

    def open_with_first_begin_denied(database_path: str | PathLike[str]) -> sqlite3.Connection:
        connection = real_open(database_path)
        connections.append(connection)
        if len(connections) == REUSED_CONNECTION_COUNT:
            _ = connection.set_authorizer(deny_transaction)
        return connection

    monkeypatch.setattr(unit_of_work_module, "open_sqlite_connection", open_with_first_begin_denied)
    return connections


def _assert_connection_closed(connection: sqlite3.Connection) -> None:
    with pytest.raises(sqlite3.ProgrammingError):
        _ = connection.execute("SELECT 1")


def _insert_track_before_stat_baseline_migration(database_file: Path) -> None:
    with sqlite3.connect(database_file) as connection:
        _ = connection.execute(
            """
            INSERT INTO libraries (
                library_id, root_path, path_policy_hash, registered_at, status, created_at, updated_at
            )
            VALUES (?, ?, ?, ?, ?, ?, ?)
            """,
            (
                str(LIBRARY_ID),
                LIBRARY_ROOT,
                CONFIG_HASH,
                BASE_TIME.isoformat(),
                LibraryStatus.REGISTERED.value,
                BASE_TIME.isoformat(),
                BASE_TIME.isoformat(),
            ),
        )
        _ = connection.execute(
            """
            INSERT INTO tracks (
                track_id,
                library_id,
                current_path,
                canonical_path,
                content_hash,
                metadata_hash,
                metadata_json,
                status,
                first_seen_at,
                last_seen_at,
                updated_at
            )
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                str(TRACK_ID),
                str(LIBRARY_ID),
                TARGET_PATH,
                TARGET_PATH,
                CONTENT_HASH,
                METADATA_HASH,
                '{"artist":"Artist","title":"Title"}',
                TrackStatus.ACTIVE.value,
                BASE_TIME.isoformat(),
                BASE_TIME.isoformat(),
                BASE_TIME.isoformat(),
            ),
        )


def _migrate_before_undo_provenance(database_file: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    packaged_migrations = migration_runner.load_packaged_migrations()
    prior_migrations = tuple(
        migration for migration in packaged_migrations if migration.name < UNDO_PROVENANCE_MIGRATION_NAME
    )
    with monkeypatch.context() as patched:
        patched.setattr(migration_runner, "load_packaged_migrations", lambda: prior_migrations)
        migrate_database(database_file)


def _insert_legacy_undo_history(database_file: Path, *, source_candidate_count: int) -> None:
    source_candidates = (
        (PLAN_ID, ACTION_ID, RUN_ID, EVENT_ID),
        (SECOND_PLAN_ID, SECOND_ACTION_ID, SECOND_RUN_ID, SECOND_RUN_EVENT_ID),
    )
    with sqlite3.connect(database_file) as connection:
        _ = connection.execute("PRAGMA foreign_keys = ON")
        _ = connection.execute(
            """
            INSERT INTO libraries (
                library_id, root_path, path_policy_hash, registered_at, status, created_at, updated_at
            )
            VALUES (?, ?, ?, ?, ?, ?, ?)
            """,
            (
                str(LIBRARY_ID),
                LIBRARY_ROOT,
                CONFIG_HASH,
                BASE_TIME.isoformat(),
                LibraryStatus.REGISTERED.value,
                BASE_TIME.isoformat(),
                BASE_TIME.isoformat(),
            ),
        )
        _ = connection.execute(
            """
            INSERT INTO tracks (
                track_id,
                library_id,
                current_path,
                canonical_path,
                content_hash,
                metadata_hash,
                metadata_json,
                status,
                first_seen_at,
                last_seen_at,
                updated_at
            )
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                str(TRACK_ID),
                str(LIBRARY_ID),
                TARGET_PATH,
                TARGET_PATH,
                CONTENT_HASH,
                METADATA_HASH,
                '{"artist":"Artist","title":"Title"}',
                TrackStatus.ACTIVE.value,
                BASE_TIME.isoformat(),
                BASE_TIME.isoformat(),
                BASE_TIME.isoformat(),
            ),
        )

        for source_plan_id, source_action_id, source_run_id, source_event_id in source_candidates[
            :source_candidate_count
        ]:
            _ = connection.execute(
                """
                INSERT INTO plans (
                    plan_id,
                    library_id,
                    plan_type,
                    status,
                    created_at,
                    config_hash,
                    library_root_at_plan,
                    summary_json
                )
                VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    str(source_plan_id),
                    str(LIBRARY_ID),
                    PlanType.ADD.value,
                    PlanStatus.APPLIED.value,
                    BASE_TIME.isoformat(),
                    CONFIG_HASH,
                    LIBRARY_ROOT,
                    "{}",
                ),
            )
            _ = connection.execute(
                """
                INSERT INTO plan_actions (
                    action_id,
                    plan_id,
                    library_id,
                    track_id,
                    action_type,
                    source_path,
                    target_path,
                    content_hash_at_plan,
                    metadata_hash_at_plan,
                    status,
                    reason,
                    sort_order
                )
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    str(source_action_id),
                    str(source_plan_id),
                    str(LIBRARY_ID),
                    str(TRACK_ID),
                    ActionType.MOVE.value,
                    SOURCE_PATH,
                    TARGET_PATH,
                    CONTENT_HASH,
                    METADATA_HASH,
                    ActionStatus.APPLIED.value,
                    None,
                    SORT_ORDER_EARLY,
                ),
            )
            _ = connection.execute(
                """
                INSERT INTO runs (
                    run_id, plan_id, library_id, status, started_at, completed_at, error_summary
                )
                VALUES (?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    str(source_run_id),
                    str(source_plan_id),
                    str(LIBRARY_ID),
                    RunStatus.SUCCEEDED.value,
                    BASE_TIME.isoformat(),
                    FINISHED_TIME.isoformat(),
                    None,
                ),
            )
            _ = connection.execute(
                """
                INSERT INTO file_events (
                    event_id,
                    library_id,
                    run_id,
                    plan_action_id,
                    event_type,
                    source_path,
                    target_path,
                    status,
                    started_at,
                    completed_at,
                    error_code,
                    error_message,
                    sequence_no
                )
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    str(source_event_id),
                    str(LIBRARY_ID),
                    str(source_run_id),
                    str(source_action_id),
                    FileEventType.MOVE_FILE.value,
                    SOURCE_PATH,
                    TARGET_PATH,
                    FileEventStatus.SUCCEEDED.value,
                    BASE_TIME.isoformat(),
                    FINISHED_TIME.isoformat(),
                    None,
                    None,
                    EVENT_SEQUENCE_EARLY,
                ),
            )

        _ = connection.execute(
            """
            INSERT INTO plans (
                plan_id,
                library_id,
                plan_type,
                status,
                created_at,
                config_hash,
                library_root_at_plan,
                summary_json
            )
            VALUES (?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                str(UNDO_PLAN_ID),
                str(LIBRARY_ID),
                PlanType.UNDO.value,
                PlanStatus.READY.value,
                UNDO_CREATED_TIME.isoformat(),
                CONFIG_HASH,
                LIBRARY_ROOT,
                "{}",
            ),
        )
        _ = connection.execute(
            """
            INSERT INTO plan_actions (
                action_id,
                plan_id,
                library_id,
                track_id,
                action_type,
                source_path,
                target_path,
                content_hash_at_plan,
                metadata_hash_at_plan,
                status,
                reason,
                sort_order
            )
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                str(UNDO_ACTION_ID),
                str(UNDO_PLAN_ID),
                str(LIBRARY_ID),
                str(TRACK_ID),
                ActionType.MOVE.value,
                TARGET_PATH,
                SOURCE_PATH,
                CONTENT_HASH,
                METADATA_HASH,
                ActionStatus.PLANNED.value,
                None,
                SORT_ORDER_EARLY,
            ),
        )


def _tamper_legacy_undo_source(database_file: Path, tamper_kind: str) -> None:
    with sqlite3.connect(database_file) as connection:
        if tamper_kind == "event_completed_after_undo":
            _ = connection.execute(
                "UPDATE file_events SET completed_at = ? WHERE event_id = ?",
                (POST_UNDO_TIME.isoformat(), str(EVENT_ID)),
            )
        elif tamper_kind == "run_completed_after_undo":
            _ = connection.execute(
                "UPDATE runs SET completed_at = ? WHERE run_id = ?",
                (POST_UNDO_TIME.isoformat(), str(RUN_ID)),
            )
        elif tamper_kind == "source_action_path_mismatch":
            _ = connection.execute(
                "UPDATE plan_actions SET target_path = ? WHERE action_id = ?",
                ("Artist/Album/02_Other.flac", str(ACTION_ID)),
            )
        elif tamper_kind == "source_action_not_applied":
            _ = connection.execute(
                "UPDATE plan_actions SET status = ? WHERE action_id = ?",
                (ActionStatus.FAILED.value, str(ACTION_ID)),
            )
        elif tamper_kind == "source_plan_not_terminal":
            _ = connection.execute(
                "UPDATE plans SET status = ? WHERE plan_id = ?",
                (PlanStatus.READY.value, str(PLAN_ID)),
            )
        else:
            raise AssertionError(tamper_kind)


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


def _track(*, size: int | None = TRACK_SIZE, mtime: datetime | None = BASE_TIME) -> Track:
    return Track(
        track_id=TRACK_ID,
        library_id=LIBRARY_ID,
        current_path=TARGET_PATH,
        canonical_path=TARGET_PATH,
        content_hash=CONTENT_HASH,
        metadata_hash=METADATA_HASH,
        size=size,
        mtime=mtime,
        metadata=TrackMetadata(title=TRACK_TITLE, artist=TRACK_ARTIST),
        status=TrackStatus.ACTIVE,
        first_seen_at=BASE_TIME,
        last_seen_at=BASE_TIME,
        updated_at=BASE_TIME,
    )


def _companion_asset() -> CompanionAsset:
    return CompanionAsset(
        companion_asset_id=COMPANION_ASSET_ID,
        library_id=LIBRARY_ID,
        kind=CompanionAssetKind.ARTWORK,
        owner_track_id=TRACK_ID,
        current_path=COMPANION_SOURCE_PATH,
        canonical_path=COMPANION_TARGET_PATH,
        content_hash=COMPANION_CONTENT_HASH,
        size=TRACK_SIZE,
        mtime=BASE_TIME,
        status=CompanionAssetStatus.ACTIVE,
        first_seen_at=BASE_TIME,
        last_seen_at=BASE_TIME,
        updated_at=BASE_TIME,
    )


def _check_run() -> CheckRun:
    return CheckRun(
        check_run_id=CHECK_RUN_ID,
        library_id=LIBRARY_ID,
        checked_at=BASE_TIME,
        total_count=CHECK_ISSUE_COUNT,
    )


def _check_issue() -> CheckIssue:
    return CheckIssue(
        issue_type=CheckIssueType.DB_FILE_MISSING,
        library_id=LIBRARY_ID,
        path=TARGET_PATH,
        track_id=TRACK_ID,
        plan_id=PLAN_ID,
    )


def _plan(
    *,
    plan_id: PlanId = PLAN_ID,
    plan_type: PlanType = PlanType.ADD,
    source_run_id: RunId | None = None,
) -> Plan:
    return Plan(
        plan_id=plan_id,
        library_id=LIBRARY_ID,
        plan_type=plan_type,
        status=PlanStatus.READY,
        created_at=BASE_TIME,
        config_hash=CONFIG_HASH,
        library_root_at_plan=LIBRARY_ROOT,
        source_run_id=source_run_id,
        summary=PLAN_SUMMARY,
    )


def _plan_action(
    action_id: ActionId,
    sort_order: int,
    *,
    plan_id: PlanId = PLAN_ID,
    artist_name_diagnostics: ArtistNameDiagnostics | None = None,
) -> PlanAction:
    return PlanAction(
        action_id=action_id,
        plan_id=plan_id,
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
        artist_name_diagnostics=artist_name_diagnostics,
    )


def _insert_plan_action_without_diagnostics(database_file: Path, action: PlanAction) -> None:
    with sqlite3.connect(database_file) as connection:
        _ = connection.execute("PRAGMA foreign_keys = ON")
        _ = connection.execute(
            """
            INSERT INTO plan_actions (
                action_id,
                plan_id,
                library_id,
                track_id,
                action_type,
                source_path,
                target_path,
                reverses_event_id,
                content_hash_at_plan,
                metadata_hash_at_plan,
                status,
                reason,
                sort_order
            )
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                str(action.action_id),
                str(action.plan_id),
                str(action.library_id),
                None if action.track_id is None else str(action.track_id),
                action.action_type.value,
                action.source_path,
                action.target_path,
                None if action.reverses_event_id is None else str(action.reverses_event_id),
                action.content_hash_at_plan,
                action.metadata_hash_at_plan,
                action.status.value,
                None if action.reason is None else action.reason.value,
                action.sort_order,
            ),
        )


def _insert_plan_without_source_root(database_file: Path, plan: Plan) -> None:
    with sqlite3.connect(database_file) as connection:
        _ = connection.execute("PRAGMA foreign_keys = ON")
        _ = connection.execute(
            """
            INSERT INTO plans (
                plan_id,
                library_id,
                source_run_id,
                plan_type,
                status,
                created_at,
                config_hash,
                library_root_at_plan,
                summary_json
            )
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                str(plan.plan_id),
                str(plan.library_id),
                None if plan.source_run_id is None else str(plan.source_run_id),
                plan.plan_type.value,
                plan.status.value,
                plan.created_at.isoformat(),
                plan.config_hash,
                plan.library_root_at_plan,
                json.dumps(plan.summary),
            ),
        )


def _insert_file_event_without_companion_asset(database_file: Path, event: FileEvent) -> None:
    with sqlite3.connect(database_file) as connection:
        _ = connection.execute("PRAGMA foreign_keys = ON")
        _ = connection.execute(
            """
            INSERT INTO file_events (
                event_id,
                library_id,
                run_id,
                plan_action_id,
                event_type,
                source_path,
                target_path,
                status,
                started_at,
                completed_at,
                error_code,
                error_message,
                sequence_no
            )
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                str(event.event_id),
                str(event.library_id),
                str(event.run_id),
                str(event.plan_action_id),
                event.event_type.value,
                event.source_path,
                event.target_path,
                event.status.value,
                event.started_at.isoformat(),
                None if event.completed_at is None else event.completed_at.isoformat(),
                event.error_code,
                event.error_message,
                event.sequence_no,
            ),
        )


def _run(*, run_id: RunId = RUN_ID, plan_id: PlanId = PLAN_ID) -> Run:
    return Run(
        run_id=run_id,
        plan_id=plan_id,
        library_id=LIBRARY_ID,
        status=RunStatus.RUNNING,
        started_at=BASE_TIME,
    )


def _file_event(event_id: EventId, action_id: ActionId, sequence_no: int, *, run_id: RunId = RUN_ID) -> FileEvent:
    return FileEvent(
        event_id=event_id,
        library_id=LIBRARY_ID,
        run_id=run_id,
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
