"""
Summary: Tests CLI composition against durable Operation persistence.
Why: Proves long-running CLI work records the same lifecycle as Web work.
"""

from __future__ import annotations

import sqlite3
from datetime import UTC, datetime
from typing import TYPE_CHECKING, cast
from uuid import UUID

from omym2.adapters.config.default_config import default_app_config
from omym2.adapters.config.toml_config_store import TomlConfigStore
from omym2.adapters.db.sqlite.unit_of_work import SQLiteUnitOfWork
from omym2.config import PLAN_ACTION_SORT_ORDER_START
from omym2.domain.models.library import Library, LibraryStatus
from omym2.domain.models.operation import (
    CheckCompletedResult,
    Operation,
    OperationKind,
    OperationStatus,
    RunCompletedResult,
)
from omym2.domain.models.plan import Plan, PlanStatus, PlanType
from omym2.domain.models.plan_action import ActionStatus, ActionType, PlanAction
from omym2.domain.models.run import RunStatus
from omym2.domain.services.config_fingerprint import calculate_path_policy_fingerprint
from omym2.features.check.dto import CheckLibraryRequest
from omym2.platform.cli_composition import build_command_dependencies
from omym2.shared.ids import ActionId, LibraryId, OperationId, PlanId

if TYPE_CHECKING:
    from pathlib import Path

LIBRARY_ID = LibraryId(UUID("018f6a4f-3c2d-7b8a-9abc-def012345701"))
PLAN_ID = PlanId(UUID("018f6a4f-3c2d-7b8a-9abc-def012345702"))
ACTION_ID = ActionId(UUID("018f6a4f-3c2d-7b8a-9abc-def012345703"))
NOW = datetime(2026, 7, 13, 1, tzinfo=UTC)


def test_cli_check_persists_succeeded_operation_with_result(tmp_path: Path) -> None:
    """Production CLI composition commits Check evidence and terminal Operation together."""
    config_path = tmp_path / "config.toml"
    database_path = tmp_path / "state.sqlite3"
    library_root = tmp_path / "library"
    library_root.mkdir()
    config = default_app_config()
    config_store = TomlConfigStore(config_path)
    _ = config_store.save(config, expected_config_revision=config_store.read_snapshot().config_revision)
    path_policy_hash = calculate_path_policy_fingerprint(
        config.path_policy,
        config.artist_ids,
        config.metadata.album_year_resolution,
    )
    with SQLiteUnitOfWork(database_path) as uow:
        uow.libraries.save(
            Library(
                library_id=LIBRARY_ID,
                root_path=str(library_root),
                path_policy_hash=path_policy_hash,
                registered_at=NOW,
                status=LibraryStatus.REGISTERED,
                created_at=NOW,
                updated_at=NOW,
            )
        )
        uow.commit()

    dependencies = build_command_dependencies(config_path, database_path)
    check_result = dependencies.check.check_library(CheckLibraryRequest(trust_stat=False))

    with sqlite3.connect(database_path) as connection:
        rows = cast("list[tuple[str]]", connection.execute("SELECT operation_id FROM operations").fetchall())
    assert len(rows) == 1
    operation_id = OperationId(UUID(rows[0][0]))
    with SQLiteUnitOfWork(database_path) as uow:
        operation = uow.operations.lookup(operation_id)

    assert isinstance(operation, Operation)
    assert operation.kind is OperationKind.CHECK
    assert operation.status is OperationStatus.SUCCEEDED
    assert operation.result == CheckCompletedResult(
        check_run_ids=check_result.check_run_ids,
        issue_count=len(check_result.issues),
    )


def test_cli_apply_persists_atomic_claim_and_succeeded_operation_result(tmp_path: Path) -> None:
    """Production CLI Apply records the same claimed Run and terminal result as Web Apply."""
    config_path = tmp_path / "config.toml"
    database_path = tmp_path / "state.sqlite3"
    library_root = tmp_path / "library"
    library_root.mkdir()
    with SQLiteUnitOfWork(database_path) as uow:
        uow.libraries.save(
            Library(
                library_id=LIBRARY_ID,
                root_path=str(library_root),
                path_policy_hash="path-policy",
                registered_at=NOW,
                status=LibraryStatus.REGISTERED,
                created_at=NOW,
                updated_at=NOW,
            )
        )
        uow.plans.save(
            Plan(
                plan_id=PLAN_ID,
                library_id=LIBRARY_ID,
                plan_type=PlanType.ADD,
                status=PlanStatus.READY,
                created_at=NOW,
                config_hash="config-hash",
                library_root_at_plan=str(library_root),
            )
        )
        uow.plan_actions.save(
            PlanAction(
                action_id=ACTION_ID,
                plan_id=PLAN_ID,
                library_id=LIBRARY_ID,
                track_id=None,
                action_type=ActionType.SKIP,
                source_path="Artist/source.flac",
                target_path="Artist/source.flac",
                content_hash_at_plan=None,
                metadata_hash_at_plan=None,
                status=ActionStatus.PLANNED,
                reason=None,
                sort_order=PLAN_ACTION_SORT_ORDER_START,
            )
        )
        uow.commit()

    dependencies = build_command_dependencies(config_path, database_path)
    run = dependencies.apply.apply_plan(PLAN_ID)

    with sqlite3.connect(database_path) as connection:
        rows = cast("list[tuple[str]]", connection.execute("SELECT operation_id FROM operations").fetchall())
    assert len(rows) == 1
    operation_id = OperationId(UUID(rows[0][0]))
    with SQLiteUnitOfWork(database_path) as uow:
        operation = uow.operations.lookup(operation_id)
        plan = uow.plans.get(PLAN_ID)

    assert run.status is RunStatus.SUCCEEDED
    assert plan is not None
    assert plan.status is PlanStatus.APPLIED
    assert isinstance(operation, Operation)
    assert operation.kind is OperationKind.APPLY_PLAN
    assert operation.status is OperationStatus.SUCCEEDED
    assert operation.plan_id == PLAN_ID
    assert operation.run_id == run.run_id
    assert operation.result == RunCompletedResult(run.run_id)
