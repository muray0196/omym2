"""
Summary: Tests M4 Web execution mutations against real lock and SQLite adapters.
Why: Proves synchronous preflight and Apply/Cancel race responses before dispatch.
"""

from __future__ import annotations

from datetime import UTC, datetime
from typing import TYPE_CHECKING, cast
from uuid import UUID

import pytest
from fastapi.testclient import TestClient

from omym2.adapters.config.application_paths import default_application_paths
from omym2.adapters.db.sqlite.unit_of_work import SQLiteUnitOfWork
from omym2.adapters.metadata.mutagen_reader import MutagenMetadataReader
from omym2.adapters.web.app import create_web_app
from omym2.config import (
    HTTP_ACCEPTED_STATUS,
    HTTP_CONFLICT_STATUS,
    HTTP_NOT_FOUND_STATUS,
    HTTP_OK_STATUS,
    WEB_API_APPLY_PLAN_ROUTE,
    WEB_API_CANCEL_PLAN_ROUTE,
    WEB_API_RUN_DETAIL_ROUTE,
    WEB_API_RUN_EVENTS_ROUTE,
    WEB_API_UNDO_PLAN_ROUTE,
    WEB_CSRF_HEADER_NAME,
    WEB_IDEMPOTENCY_HEADER_NAME,
)
from omym2.domain.models.library import Library, LibraryStatus
from omym2.domain.models.plan import Plan, PlanStatus, PlanType
from omym2.domain.models.plan_action import ActionStatus, ActionType, PlanAction
from omym2.domain.models.track_metadata import TrackMetadata
from omym2.domain.services.content_fingerprint import calculate_content_fingerprint
from omym2.domain.services.metadata_fingerprint import calculate_metadata_fingerprint
from omym2.features.apply.usecases.apply_plan import TARGET_EXISTS_MOVE_FAILURE_MESSAGE
from omym2.features.common_ports import ExclusiveOperationRequest
from omym2.platform.runtime_context import runtime_context_for
from omym2.platform.web_composition import build_api_route_context
from omym2.shared.ids import ActionId, LibraryId, PlanId, RunId

if TYPE_CHECKING:
    from pathlib import Path

    from omym2.features.common_ports import FileSystemPath

NOW = datetime(2026, 7, 13, tzinfo=UTC)
LIBRARY_ID = LibraryId(UUID("018f6a4f-3c2d-7b8a-9abc-def012345690"))
PLAN_ID = PlanId(UUID("018f6a4f-3c2d-7b8a-9abc-def012345691"))
RUN_ID = RunId(UUID("018f6a4f-3c2d-7b8a-9abc-def012345692"))
IDEMPOTENCY_KEY = UUID("018f6a4f-3c2d-7b8a-9abc-def012345693")
ACTION_ID = ActionId(UUID("018f6a4f-3c2d-7b8a-9abc-def012345694"))
AUDIO_CONTENT = b"not-real-audio"
SENSITIVE_LIBRARY_COMPONENT = "private-owner-token"
SOURCE_PATH = "Incoming/Secret.flac"
TARGET_PATH = "Artist/Existing.flac"


@pytest.mark.parametrize(
    ("route", "plan_status", "expected_code"),
    [
        (WEB_API_APPLY_PLAN_ROUTE, PlanStatus.READY, "operation_in_progress"),
        (WEB_API_CANCEL_PLAN_ROUTE, PlanStatus.READY, "operation_in_progress"),
        (WEB_API_APPLY_PLAN_ROUTE, PlanStatus.APPLYING, "plan_not_ready"),
        (WEB_API_CANCEL_PLAN_ROUTE, PlanStatus.APPLYING, "plan_not_ready"),
    ],
)
def test_apply_and_cancel_distinguish_unrelated_contention_from_a_committed_winner(
    tmp_path: Path,
    route: str,
    plan_status: PlanStatus,
    expected_code: str,
) -> None:
    """A committed claim wins the race, while contention against a ready Plan stays generic."""
    paths = default_application_paths(tmp_path)
    library_root = tmp_path / "library"
    library_root.mkdir()
    _seed_plan(paths.database_file, library_root, plan_status)
    context = build_api_route_context(paths.config_file, paths.database_file)
    client = TestClient(
        create_web_app(context, tmp_path / "missing-static", allowed_hosts=("testserver",)),
        raise_server_exceptions=False,
    )
    owner_runtime = runtime_context_for(paths.config_file, paths.database_file)

    try:
        with owner_runtime.exclusive_operation_lock.hold(ExclusiveOperationRequest(operation_name="race_winner")):
            response = client.post(
                route.format(plan_id=PLAN_ID),
                headers={
                    WEB_CSRF_HEADER_NAME: context.csrf_token,
                    WEB_IDEMPOTENCY_HEADER_NAME: str(IDEMPOTENCY_KEY),
                },
            )
    finally:
        assert context.close_runtime is not None
        context.close_runtime()

    assert response.status_code == HTTP_CONFLICT_STATUS
    assert response.json()["errors"][0]["code"] == expected_code
    with SQLiteUnitOfWork(paths.database_file) as uow:
        persisted = uow.plans.get(PLAN_ID)
    assert persisted is not None
    assert persisted.status is plan_status


def test_undo_preflight_returns_not_found_without_reserving_an_operation(tmp_path: Path) -> None:
    """Undo eligibility is revalidated under the lock before its durable reservation exists."""
    paths = default_application_paths(tmp_path)
    context = build_api_route_context(paths.config_file, paths.database_file)
    client = TestClient(
        create_web_app(context, tmp_path / "missing-static", allowed_hosts=("testserver",)),
        raise_server_exceptions=False,
    )

    try:
        response = client.post(
            WEB_API_UNDO_PLAN_ROUTE.format(run_id=RUN_ID),
            headers={
                WEB_CSRF_HEADER_NAME: context.csrf_token,
                WEB_IDEMPOTENCY_HEADER_NAME: str(IDEMPOTENCY_KEY),
            },
        )
    finally:
        assert context.close_runtime is not None
        context.close_runtime()

    assert response.status_code == HTTP_NOT_FOUND_STATUS
    assert response.json()["errors"][0]["code"] == "run_not_found"
    with SQLiteUnitOfWork(paths.database_file) as uow:
        assert uow.operations.find_by_idempotency_key(IDEMPOTENCY_KEY) is None


def test_apply_route_claims_and_completes_one_durable_run(tmp_path: Path) -> None:
    """Web Apply uses the atomic claim and returns a pollable run_completed Operation."""
    paths = default_application_paths(tmp_path)
    library_root = tmp_path / "library"
    library_root.mkdir()
    _seed_plan(paths.database_file, library_root, PlanStatus.READY)
    with SQLiteUnitOfWork(paths.database_file) as uow:
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
                sort_order=1,
            )
        )
        uow.commit()
    context = build_api_route_context(paths.config_file, paths.database_file)
    client = TestClient(
        create_web_app(context, tmp_path / "missing-static", allowed_hosts=("testserver",)),
        raise_server_exceptions=False,
    )

    accepted = client.post(
        WEB_API_APPLY_PLAN_ROUTE.format(plan_id=PLAN_ID),
        headers={
            WEB_CSRF_HEADER_NAME: context.csrf_token,
            WEB_IDEMPOTENCY_HEADER_NAME: str(IDEMPOTENCY_KEY),
        },
    )
    assert context.close_runtime is not None
    context.close_runtime()
    terminal = client.get(accepted.headers["Location"])

    assert accepted.status_code == HTTP_ACCEPTED_STATUS
    assert terminal.status_code == HTTP_OK_STATUS
    terminal_payload = cast("dict[str, object]", terminal.json())
    raw_terminal_data = terminal_payload["data"]
    assert isinstance(raw_terminal_data, dict)
    terminal_data = cast("dict[str, object]", raw_terminal_data)
    raw_result = terminal_data["result"]
    assert isinstance(raw_result, dict)
    result = cast("dict[str, object]", raw_result)
    assert terminal_data["status"] == "succeeded"
    assert result["kind"] == "run_completed"
    with SQLiteUnitOfWork(paths.database_file) as uow:
        plan = uow.plans.get(PLAN_ID)
        action = uow.plan_actions.get(ACTION_ID)
        runs = tuple(uow.runs.list_by_plan(PLAN_ID))
    assert plan is not None
    assert plan.status is PlanStatus.APPLIED
    assert action is not None
    assert action.status is ActionStatus.APPLIED
    assert len(runs) == 1
    assert result["run_id"] == str(runs[0].run_id)


def test_apply_move_failure_redacts_sensitive_path_from_history_json(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Apply persists and serves stable move diagnostics without raw OS path details."""
    _patch_metadata_reader(monkeypatch)
    paths = default_application_paths(tmp_path)
    library_root = tmp_path / SENSITIVE_LIBRARY_COMPONENT
    source_file = library_root.joinpath(*SOURCE_PATH.split("/"))
    target_file = library_root.joinpath(*TARGET_PATH.split("/"))
    source_file.parent.mkdir(parents=True)
    target_file.parent.mkdir(parents=True)
    _ = source_file.write_bytes(AUDIO_CONTENT)
    _ = target_file.write_bytes(AUDIO_CONTENT)
    _seed_plan(paths.database_file, library_root, PlanStatus.READY)
    with SQLiteUnitOfWork(paths.database_file) as uow:
        uow.plan_actions.save(
            PlanAction(
                action_id=ACTION_ID,
                plan_id=PLAN_ID,
                library_id=LIBRARY_ID,
                track_id=None,
                action_type=ActionType.MOVE,
                source_path=SOURCE_PATH,
                target_path=TARGET_PATH,
                content_hash_at_plan=calculate_content_fingerprint(AUDIO_CONTENT),
                metadata_hash_at_plan=calculate_metadata_fingerprint(TrackMetadata(title="Secret")),
                status=ActionStatus.PLANNED,
                reason=None,
                sort_order=1,
            )
        )
        uow.commit()
    context = build_api_route_context(paths.config_file, paths.database_file)
    client = TestClient(
        create_web_app(context, tmp_path / "missing-static", allowed_hosts=("testserver",)),
        raise_server_exceptions=False,
    )

    try:
        accepted = client.post(
            WEB_API_APPLY_PLAN_ROUTE.format(plan_id=PLAN_ID),
            headers={
                WEB_CSRF_HEADER_NAME: context.csrf_token,
                WEB_IDEMPOTENCY_HEADER_NAME: str(IDEMPOTENCY_KEY),
            },
        )
    finally:
        assert context.close_runtime is not None
        context.close_runtime()

    assert accepted.status_code == HTTP_ACCEPTED_STATUS
    with SQLiteUnitOfWork(paths.database_file) as uow:
        runs = tuple(uow.runs.list_by_plan(PLAN_ID))
    assert len(runs) == 1
    run_id = runs[0].run_id

    run_response = client.get(WEB_API_RUN_DETAIL_ROUTE.format(run_id=run_id))
    events_response = client.get(WEB_API_RUN_EVENTS_ROUTE.format(run_id=run_id))
    run_payload = cast("dict[str, object]", run_response.json())
    run_data = cast("dict[str, object]", run_payload["data"])
    run_resource = cast("dict[str, object]", run_data["run"])
    events_payload = cast("dict[str, object]", events_response.json())
    events_data = cast("dict[str, object]", events_payload["data"])
    event_items = cast("list[dict[str, object]]", events_data["items"])

    assert run_response.status_code == HTTP_OK_STATUS
    assert events_response.status_code == HTTP_OK_STATUS
    assert run_resource["error_summary"] == TARGET_EXISTS_MOVE_FAILURE_MESSAGE
    assert event_items[0]["error_code"] == "target_exists"
    assert event_items[0]["error_message"] == TARGET_EXISTS_MOVE_FAILURE_MESSAGE
    assert SENSITIVE_LIBRARY_COMPONENT not in run_response.text
    assert SENSITIVE_LIBRARY_COMPONENT not in events_response.text


def _seed_plan(database_path: Path, library_root: Path, status: PlanStatus) -> None:
    """Persist the minimum Plan identity needed to exercise lock-contention classification."""
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
                status=status,
                created_at=NOW,
                config_hash="config-hash",
                library_root_at_plan=str(library_root),
            )
        )
        uow.commit()


def _patch_metadata_reader(monkeypatch: pytest.MonkeyPatch) -> None:
    def read(self: MutagenMetadataReader, path: FileSystemPath) -> TrackMetadata:
        del self, path
        return TrackMetadata(title="Secret")

    monkeypatch.setattr(MutagenMetadataReader, "read", read)
