"""
Summary: Tests isolated M2 read-only Web route families.
Why: Verifies typed envelopes, cursor projection, and persisted Check freshness before parent wiring.
"""

from __future__ import annotations

from datetime import UTC, datetime
from types import SimpleNamespace
from typing import TYPE_CHECKING, cast
from uuid import UUID

import pytest
from fastapi import APIRouter, FastAPI
from fastapi.testclient import TestClient

from omym2.adapters.web.routes.check import create_check_router
from omym2.adapters.web.routes.history import create_history_router
from omym2.adapters.web.routes.libraries import create_libraries_router
from omym2.config import (
    HTTP_OK_STATUS,
    HTTP_UNPROCESSABLE_CONTENT_STATUS,
    WEB_API_CHECK_ROUTE,
    WEB_API_HISTORY_ROUTE,
    WEB_API_LIBRARIES_ROUTE,
    WEB_API_RUN_DETAIL_ROUTE,
)
from omym2.domain.models.check_issue import CheckIssue, CheckIssueType
from omym2.domain.models.library import Library, LibraryStatus
from omym2.domain.models.run import Run, RunStatus
from omym2.features.check.dto import ListCheckIssuesResult
from omym2.features.history.dto import RunCapabilitiesResult, RunCapabilityReason, RunDetailResult
from omym2.features.libraries.dto import LibraryInspection
from omym2.shared.ids import LibraryId, OperationId, PlanId, RunId
from omym2.shared.pagination import Page

if TYPE_CHECKING:
    from collections.abc import Callable

NOW = datetime(2026, 7, 13, tzinfo=UTC)
LIBRARY_ID = LibraryId(UUID("018f6a4f-3c2d-7b8a-9abc-def012345621"))
PLAN_ID = PlanId(UUID("018f6a4f-3c2d-7b8a-9abc-def012345622"))
RUN_ID = RunId(UUID("018f6a4f-3c2d-7b8a-9abc-def012345623"))
OPERATION_ID = OperationId(UUID("018f6a4f-3c2d-7b8a-9abc-def012345624"))


def test_library_list_serializes_effective_readiness() -> None:
    """Library list uses the feature projection rather than persisted status inference."""
    library = Library(
        library_id=LIBRARY_ID,
        root_path="/music/library",
        path_policy_hash="stored-policy",
        registered_at=NOW,
        status=LibraryStatus.REGISTERED,
        created_at=NOW,
        updated_at=NOW,
    )

    def inspect_libraries(_request: object) -> tuple[LibraryInspection, ...]:
        return (
            LibraryInspection(
                library=library,
                effective_status=LibraryStatus.STALE,
                is_registered=True,
                is_path_policy_current=False,
            ),
        )

    context = SimpleNamespace(inspect_libraries=inspect_libraries)

    response = _client(create_libraries_router, context).get(WEB_API_LIBRARIES_ROUTE)
    items = _objects(_object(_payload(cast("object", response.json())), "data"), "items")

    assert response.status_code == HTTP_OK_STATUS
    assert items[0]["status"] == "stale"
    assert items[0]["library_id"] == str(LIBRARY_ID)


def test_history_list_serializes_opaque_next_cursor() -> None:
    """History returns the repository key as an opaque cursor with the effective limit."""
    run = Run(
        run_id=RUN_ID,
        plan_id=PLAN_ID,
        library_id=LIBRARY_ID,
        status=RunStatus.SUCCEEDED,
        started_at=NOW,
        completed_at=NOW,
    )

    def list_runs(_request: object) -> Page[Run]:
        return Page(
            items=(run,),
            next_cursor_key=(NOW.isoformat(), str(RUN_ID)),
            total=2,
        )

    context = SimpleNamespace(list_runs=list_runs)

    response = _client(create_history_router, context).get(WEB_API_HISTORY_ROUTE, params={"limit": 1})
    data = _object(_payload(cast("object", response.json())), "data")
    items = _objects(data, "items")
    page = _object(data, "page")

    assert response.status_code == HTTP_OK_STATUS
    assert items[0]["run_id"] == str(RUN_ID)
    assert page["limit"] == 1
    assert isinstance(page["next_cursor"], str)


def test_history_rejects_invalid_cursor_with_typed_validation_envelope() -> None:
    """Malformed opaque cursors fail before a repository query is invoked."""

    def list_runs(_request: object) -> Page[Run]:
        pytest.fail("cursor must fail before the query")

    context = SimpleNamespace(list_runs=list_runs)

    response = _client(create_history_router, context).get(WEB_API_HISTORY_ROUTE, params={"cursor": "!"})

    assert response.status_code == HTTP_UNPROCESSABLE_CONTENT_STATUS
    assert response.json()["errors"][0]["code"] == "validation_failed"
    assert response.json()["errors"][0]["field"] == "query.cursor"


def test_history_detail_projects_only_the_related_active_operation() -> None:
    """Run detail uses the platform's typed related-Operation projection."""
    run = Run(
        run_id=RUN_ID,
        plan_id=PLAN_ID,
        library_id=LIBRARY_ID,
        status=RunStatus.SUCCEEDED,
        started_at=NOW,
        completed_at=NOW,
    )

    def get_run_detail(_request: object) -> RunDetailResult:
        return RunDetailResult(
            run=run,
            capabilities=RunCapabilitiesResult(can_create_undo=True, disabled_reasons=()),
        )

    def active_operation_id(_run_id: RunId) -> OperationId:
        return OPERATION_ID

    context = SimpleNamespace(
        get_run_detail=get_run_detail,
        active_operation_id=active_operation_id,
    )

    response = _client(create_history_router, context).get(WEB_API_RUN_DETAIL_ROUTE.format(run_id=RUN_ID))

    assert response.status_code == HTTP_OK_STATUS
    assert _object(_payload(cast("object", response.json())), "data")["active_operation_id"] == str(OPERATION_ID)


def test_history_detail_serializes_already_undone_capability_reason() -> None:
    """An applied or in-progress Undo remains a typed disabled capability, not a route failure."""
    run = Run(
        run_id=RUN_ID,
        plan_id=PLAN_ID,
        library_id=LIBRARY_ID,
        status=RunStatus.SUCCEEDED,
        started_at=NOW,
        completed_at=NOW,
    )

    def get_run_detail(_request: object) -> RunDetailResult:
        return RunDetailResult(
            run=run,
            capabilities=RunCapabilitiesResult(
                can_create_undo=False,
                disabled_reasons=(RunCapabilityReason.ALREADY_UNDONE_OR_IN_PROGRESS,),
            ),
        )

    def active_operation_id(_run_id: RunId) -> None:
        return None

    context = SimpleNamespace(
        get_run_detail=get_run_detail,
        active_operation_id=active_operation_id,
    )

    response = _client(create_history_router, context).get(WEB_API_RUN_DETAIL_ROUTE.format(run_id=RUN_ID))
    data = _object(_payload(cast("object", response.json())), "data")
    capabilities = _object(data, "capabilities")
    reasons = _objects(capabilities, "disabled_reasons")

    assert response.status_code == HTTP_OK_STATUS
    assert capabilities["can_create_undo"] is False
    assert reasons[0]["code"] == "already_undone_or_in_progress"


def test_check_list_serializes_persisted_freshness_without_running_check() -> None:
    """Health GET returns persisted issues and checked_at from its query usecase result."""
    issue = CheckIssue(
        issue_type=CheckIssueType.DB_FILE_MISSING,
        library_id=LIBRARY_ID,
        path="Artist/Track.flac",
    )

    def list_check_issues(_request: object) -> ListCheckIssuesResult:
        return ListCheckIssuesResult(
            page=Page(items=(issue,), next_cursor_key=None, total=1),
            checked_at=NOW,
        )

    context = SimpleNamespace(list_check_issues=list_check_issues)

    response = _client(create_check_router, context).get(WEB_API_CHECK_ROUTE)
    data = _object(_payload(cast("object", response.json())), "data")
    items = _objects(data, "items")

    assert response.status_code == HTTP_OK_STATUS
    assert items[0]["issue_type"] == "db_file_missing"
    assert data["checked_at"] == NOW.isoformat().replace("+00:00", "Z")


def _client(router_factory: Callable[[], APIRouter], context: object) -> TestClient:
    app = FastAPI()
    app.state.api_route_context = SimpleNamespace(libraries=context, history=context, check=context)
    app.include_router(router_factory())
    return TestClient(app)


def _payload(value: object) -> dict[str, object]:
    assert isinstance(value, dict)
    return cast("dict[str, object]", value)


def _object(payload: dict[str, object], key: str) -> dict[str, object]:
    return _payload(payload[key])


def _objects(payload: dict[str, object], key: str) -> list[dict[str, object]]:
    values = payload[key]
    assert isinstance(values, list)
    return [_payload(value) for value in cast("list[object]", values)]
