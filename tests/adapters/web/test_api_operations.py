"""
Summary: Tests durable Operation polling and mutation acceptance Web routes.
Why: Protects typed planning, Apply, Undo, replay, authorization, and retention behavior.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import UTC, datetime, timedelta
from time import monotonic, sleep
from typing import TYPE_CHECKING, cast
from uuid import UUID

import pytest
from fastapi.testclient import TestClient

from omym2.adapters.config.default_config import default_app_config
from omym2.adapters.config.toml_config_store import TomlConfigStore
from omym2.adapters.db.sqlite.unit_of_work import SQLiteUnitOfWork
from omym2.adapters.web.app import create_web_app
from omym2.adapters.web.routes.api_context import ApiRouteContext, OperationsRouteContext
from omym2.adapters.web.schema_app import create_api_schema_app
from omym2.config import (
    HTTP_ACCEPTED_STATUS,
    HTTP_CONFLICT_STATUS,
    HTTP_FORBIDDEN_STATUS,
    HTTP_GONE_STATUS,
    HTTP_NOT_FOUND_STATUS,
    HTTP_OK_STATUS,
    HTTP_UNPROCESSABLE_CONTENT_STATUS,
    MILLISECONDS_PER_SECOND,
    OPERATION_POLL_INITIAL_SECONDS,
    OPERATION_RECONCILE_INTERVAL_SECONDS,
    OPERATION_RESULT_RETENTION_HOURS,
    OPERATION_TOMBSTONE_RETENTION_DAYS,
    WEB_API_ADD_PLAN_ROUTE,
    WEB_API_APPLY_PLAN_ROUTE,
    WEB_API_BOOTSTRAP_ROUTE,
    WEB_API_CHECK_RUN_ROUTE,
    WEB_API_OPERATION_ROUTE,
    WEB_API_ORGANIZE_PLAN_ROUTE,
    WEB_API_REFRESH_PLAN_ROUTE,
    WEB_API_UNDO_PLAN_ROUTE,
    WEB_CSRF_HEADER_NAME,
    WEB_IDEMPOTENCY_HEADER_NAME,
)
from omym2.domain.models.library import Library, LibraryStatus
from omym2.domain.models.operation import (
    CheckCompletedResult,
    Operation,
    OperationKind,
    OperationLookup,
)
from omym2.domain.services.config_fingerprint import calculate_path_policy_fingerprint
from omym2.features.add.dto import CreateAddPlanRequest
from omym2.features.apply.usecases.apply_plan import PlanCannotBeAppliedError
from omym2.features.apply.usecases.claim_apply import LibraryRootChangedError
from omym2.features.check.dto import CheckLibraryRequest
from omym2.features.common_ports import (
    ExclusiveOperationBusyError,
    ExclusiveOperationRequest,
    IdempotencyKeyReusedError,
)
from omym2.features.operations.dto import (
    OperationExpiredError,
    OperationNotFoundError,
    ReserveOperationResult,
)
from omym2.features.organize.dto import CreateOrganizePlanRequest
from omym2.features.refresh.dto import CreateRefreshPlanRequest, RefreshTargetKind
from omym2.features.undo.dto import CreateUndoPlanRequest
from omym2.features.undo.usecases.create_undo_plan import (
    NOTHING_TO_UNDO_MESSAGE,
    PENDING_FILE_EVENT_REQUIRES_REVIEW_MESSAGE,
    UndoPlanError,
)
from omym2.platform.web_composition import build_web_app
from omym2.shared.ids import CheckRunId, LibraryId, OperationId, PlanId, RunId

if TYPE_CHECKING:
    from pathlib import Path

    from httpx2 import Response

NOW = datetime(2026, 7, 13, 1, tzinfo=UTC)
STARTED_AT = NOW + timedelta(seconds=1)
COMPLETED_AT = STARTED_AT + timedelta(seconds=1)
OPERATION_ID = OperationId(UUID("018f6a4f-3c2d-7b8a-9abc-def012345680"))
SECOND_OPERATION_ID = OperationId(UUID("018f6a4f-3c2d-7b8a-9abc-def012345681"))
CHECK_RUN_ID = CheckRunId(UUID("018f6a4f-3c2d-7b8a-9abc-def012345682"))
LIBRARY_ID = LibraryId(UUID("018f6a4f-3c2d-7b8a-9abc-def012345683"))
IDEMPOTENCY_KEY = UUID("018f6a4f-3c2d-7b8a-9abc-def012345684")
PLAN_ID = PlanId(UUID("018f6a4f-3c2d-7b8a-9abc-def012345685"))
RUN_ID = RunId(UUID("018f6a4f-3c2d-7b8a-9abc-def012345686"))
CSRF_TOKEN = "operation-csrf-token"  # noqa: S105  # Deterministic non-secret test token.
INVALID_CSRF_TOKEN = "invalid-operation-csrf-token"  # noqa: S105  # Deterministic non-secret test token.
REQUEST_FINGERPRINT = "canonical-request-fingerprint"
UNRELATED_BOOTSTRAP_MESSAGE = "Unrelated Bootstrap handler must not execute."
OPERATION_POLL_TIMEOUT_MESSAGE = "Operation did not become terminal before the polling deadline."


def test_get_operation_returns_active_and_terminal_resources(tmp_path: Path) -> None:
    """Polling returns complete active and retained terminal resource projections."""
    running = _queued_operation(OperationKind.CHECK).mark_running(STARTED_AT)
    terminal = _succeeded_check_operation()

    running_response = _client(tmp_path, FakeOperations(running)).get(_operation_url(OPERATION_ID))
    terminal_response = _client(tmp_path, FakeOperations(terminal)).get(_operation_url(OPERATION_ID))

    assert running_response.status_code == HTTP_OK_STATUS
    assert _data(running_response) == {
        "operation_id": str(OPERATION_ID),
        "kind": "check",
        "status": "running",
        "library_id": None,
        "plan_id": None,
        "run_id": None,
        "progress": {
            "stage_code": None,
            "completed_units": None,
            "total_units": None,
            "message": None,
        },
        "result": None,
        "error": None,
        "requested_at": NOW.isoformat().replace("+00:00", "Z"),
        "started_at": STARTED_AT.isoformat().replace("+00:00", "Z"),
        "completed_at": None,
    }
    assert terminal_response.status_code == HTTP_OK_STATUS
    terminal_data = _data(terminal_response)
    assert terminal_data["status"] == "succeeded"
    assert terminal_data["result"] == {
        "kind": "check_completed",
        "check_run_ids": [str(CHECK_RUN_ID)],
        "issue_count": 0,
    }
    assert terminal_data["completed_at"] == COMPLETED_AT.isoformat().replace("+00:00", "Z")


@pytest.mark.parametrize(
    ("failure", "operation_id", "expected_status", "expected_code"),
    [
        (OperationNotFoundError(), OPERATION_ID, HTTP_NOT_FOUND_STATUS, "operation_not_found"),
        (OperationExpiredError(), SECOND_OPERATION_ID, HTTP_GONE_STATUS, "operation_expired"),
    ],
)
def test_get_operation_translates_retention_lookup_failures(
    tmp_path: Path,
    failure: Exception,
    operation_id: OperationId,
    expected_status: int,
    expected_code: str,
) -> None:
    """Unknown and retained-tombstone identities remain distinct typed failures."""
    response = _client(tmp_path, FakeOperations(failure)).get(_operation_url(operation_id))

    assert response.status_code == expected_status
    assert _first_error(response)["code"] == expected_code


def test_get_operation_rejects_invalid_uuid_without_calling_context(tmp_path: Path) -> None:
    """Malformed Operation identities are rejected by the typed path boundary."""
    operations = FakeOperations(_queued_operation(OperationKind.CHECK))

    response = _client(tmp_path, operations).get(_operation_url("not-a-uuid"))

    assert response.status_code == HTTP_UNPROCESSABLE_CONTENT_STATUS
    assert response.json()["data"] is None
    assert _first_error(response)["code"] == "validation_failed"
    assert _first_error(response)["field"] == "path.operation_id"
    assert operations.get_count == 0


@pytest.mark.parametrize(
    ("route", "body", "kind", "expected_request"),
    [
        (
            WEB_API_ADD_PLAN_ROUTE,
            {"source_path": "/incoming", "library_id": str(LIBRARY_ID)},
            OperationKind.ADD_PLAN,
            CreateAddPlanRequest(source_path="/incoming", library_id=LIBRARY_ID),
        ),
        (
            WEB_API_ORGANIZE_PLAN_ROUTE,
            {"library_root": "/library"},
            OperationKind.ORGANIZE_PLAN,
            CreateOrganizePlanRequest(trust_stat=False, library_root="/library"),
        ),
        (
            WEB_API_REFRESH_PLAN_ROUTE,
            {"library_id": str(LIBRARY_ID), "target_kind": "directory", "target_path": "Artist/Album"},
            OperationKind.REFRESH_PLAN,
            CreateRefreshPlanRequest(
                trust_stat=False,
                library_id=LIBRARY_ID,
                target_path="Artist/Album",
                target_kind=RefreshTargetKind.DIRECTORY,
            ),
        ),
        (
            WEB_API_CHECK_RUN_ROUTE,
            {"library_id": str(LIBRARY_ID)},
            OperationKind.CHECK,
            CheckLibraryRequest(trust_stat=False, library_id=LIBRARY_ID),
        ),
    ],
)
def test_operation_start_routes_return_accepted_reference_and_location(
    tmp_path: Path,
    route: str,
    body: dict[str, object],
    kind: OperationKind,
    expected_request: object,
) -> None:
    """Every M3 start route translates its body and returns one typed polling reference."""
    operations = FakeOperations(_queued_operation(kind))

    response = _client(tmp_path, operations).post(route, json=body, headers=_mutation_headers())

    assert response.status_code == HTTP_ACCEPTED_STATUS
    assert response.headers["Location"] == _operation_url(OPERATION_ID)
    assert _data(response) == {
        "operation_id": str(OPERATION_ID),
        "kind": kind.value,
        "status": "queued",
        "status_url": _operation_url(OPERATION_ID),
        "poll_after_ms": int(OPERATION_POLL_INITIAL_SECONDS * MILLISECONDS_PER_SECOND),
    }
    assert operations.start_calls == [(kind, expected_request, IDEMPOTENCY_KEY)]


@pytest.mark.parametrize(
    ("route", "kind", "expected_request"),
    [
        (WEB_API_APPLY_PLAN_ROUTE.format(plan_id=PLAN_ID), OperationKind.APPLY_PLAN, PLAN_ID),
        (
            WEB_API_UNDO_PLAN_ROUTE.format(run_id=RUN_ID),
            OperationKind.UNDO_PLAN,
            CreateUndoPlanRequest(run_id=RUN_ID),
        ),
    ],
)
def test_m4_operation_routes_accept_bodyless_apply_and_undo_requests(
    tmp_path: Path,
    route: str,
    kind: OperationKind,
    expected_request: object,
) -> None:
    """Apply and Undo translate path identity into durable Operation acceptance."""
    operations = FakeOperations(_queued_operation(kind))

    response = _client(tmp_path, operations).post(route, headers=_mutation_headers())

    assert response.status_code == HTTP_ACCEPTED_STATUS
    assert response.headers["Location"] == _operation_url(OPERATION_ID)
    assert _data(response)["kind"] == kind.value
    assert operations.start_calls == [(kind, expected_request, IDEMPOTENCY_KEY)]


@pytest.mark.parametrize(
    ("route", "failure", "expected_code"),
    [
        (
            WEB_API_APPLY_PLAN_ROUTE.format(plan_id=PLAN_ID),
            PlanCannotBeAppliedError("not ready"),
            "plan_not_ready",
        ),
        (
            WEB_API_APPLY_PLAN_ROUTE.format(plan_id=PLAN_ID),
            LibraryRootChangedError("root changed"),
            "library_root_changed",
        ),
        (
            WEB_API_UNDO_PLAN_ROUTE.format(run_id=RUN_ID),
            UndoPlanError(NOTHING_TO_UNDO_MESSAGE),
            "nothing_to_undo",
        ),
        (
            WEB_API_UNDO_PLAN_ROUTE.format(run_id=RUN_ID),
            UndoPlanError(PENDING_FILE_EVENT_REQUIRES_REVIEW_MESSAGE),
            "pending_file_event_requires_review",
        ),
    ],
)
def test_m4_operation_routes_translate_synchronous_claim_and_preflight_conflicts(
    tmp_path: Path,
    route: str,
    failure: Exception,
    expected_code: str,
) -> None:
    """Atomic Apply claims and lock-held Undo validation keep their typed synchronous 409s."""
    operations = FakeOperations(_queued_operation(OperationKind.CHECK), start_failure=failure)

    response = _client(tmp_path, operations).post(route, headers=_mutation_headers())

    assert response.status_code == HTTP_CONFLICT_STATUS
    assert _first_error(response)["code"] == expected_code


@pytest.mark.parametrize(
    ("replay_state", "expected_status", "expected_resource_status"),
    [
        ("active", HTTP_ACCEPTED_STATUS, "queued"),
        ("terminal", HTTP_OK_STATUS, "succeeded"),
    ],
)
def test_exact_active_and_terminal_replay_keep_status_and_location(
    tmp_path: Path,
    replay_state: str,
    expected_status: int,
    expected_resource_status: str,
) -> None:
    """An exact replay is never redispatched and returns its retained HTTP projection."""
    operation = _succeeded_check_operation() if replay_state == "terminal" else _queued_operation(OperationKind.CHECK)
    operations = FakeOperations(operation, is_new=False)

    response = _client(tmp_path, operations).post(
        WEB_API_CHECK_RUN_ROUTE,
        json={"library_id": None},
        headers=_mutation_headers(),
    )

    assert response.status_code == expected_status
    assert response.headers["Location"] == _operation_url(OPERATION_ID)
    assert _data(response)["status"] == expected_resource_status
    assert len(operations.start_calls) == 1


def test_operation_start_translates_idempotency_reuse_and_busy_remediation(tmp_path: Path) -> None:
    """Request-identity and active-slot conflicts keep separate typed 409 outcomes."""
    reused = FakeOperations(_queued_operation(OperationKind.CHECK), start_failure=IdempotencyKeyReusedError())
    busy = FakeOperations(
        _queued_operation(OperationKind.CHECK),
        start_failure=ExclusiveOperationBusyError(
            ExclusiveOperationRequest(operation_name="check"),
            "busy",
        ),
        active_operation_id=SECOND_OPERATION_ID,
    )

    reused_response = _client(tmp_path, reused).post(
        WEB_API_CHECK_RUN_ROUTE,
        json={"library_id": None},
        headers=_mutation_headers(),
    )
    busy_response = _client(tmp_path, busy).post(
        WEB_API_CHECK_RUN_ROUTE,
        json={"library_id": None},
        headers=_mutation_headers(),
    )

    assert reused_response.status_code == HTTP_CONFLICT_STATUS
    assert _first_error(reused_response)["code"] == "idempotency_key_reused"
    assert busy_response.status_code == HTTP_CONFLICT_STATUS
    busy_error = _first_error(busy_response)
    assert busy_error["code"] == "operation_in_progress"
    assert busy_error["retryable"] is True
    assert busy_error["remediation"] == {
        "label": "View active Operation",
        "route": _operation_url(SECOND_OPERATION_ID),
    }


@pytest.mark.parametrize("csrf_token", [None, INVALID_CSRF_TOKEN])
def test_csrf_rejection_precedes_malformed_body_and_headers(tmp_path: Path, csrf_token: str | None) -> None:
    """Missing or invalid CSRF is rejected before JSON and idempotency parsing can run."""
    operations = FakeOperations(_queued_operation(OperationKind.ADD_PLAN))
    headers = {"Content-Type": "application/json", WEB_IDEMPOTENCY_HEADER_NAME: "not-a-uuid"}
    if csrf_token is not None:
        headers[WEB_CSRF_HEADER_NAME] = csrf_token

    response = _client(tmp_path, operations).post(WEB_API_ADD_PLAN_ROUTE, content="{", headers=headers)

    assert response.status_code == HTTP_FORBIDDEN_STATUS
    assert _first_error(response)["code"] == "csrf_invalid"
    assert operations.start_calls == []


@pytest.mark.parametrize(
    "route",
    [
        WEB_API_APPLY_PLAN_ROUTE.format(plan_id="not-a-uuid"),
        WEB_API_UNDO_PLAN_ROUTE.format(run_id="not-a-uuid"),
    ],
)
def test_m4_dynamic_mutation_routes_reject_csrf_before_path_and_header_validation(
    tmp_path: Path,
    route: str,
) -> None:
    """Template-based CSRF matching protects Apply and Undo before UUID parsing."""
    operations = FakeOperations(_queued_operation(OperationKind.CHECK))

    response = _client(tmp_path, operations).post(
        route,
        headers={WEB_IDEMPOTENCY_HEADER_NAME: "not-a-uuid"},
    )

    assert response.status_code == HTTP_FORBIDDEN_STATUS
    assert _first_error(response)["code"] == "csrf_invalid"
    assert operations.start_calls == []


@pytest.mark.parametrize(
    ("route", "body"),
    [
        (WEB_API_ADD_PLAN_ROUTE, {"source_path": "  ", "library_id": None}),
        (WEB_API_ORGANIZE_PLAN_ROUTE, {"library_root": ""}),
        (
            WEB_API_REFRESH_PLAN_ROUTE,
            {"library_id": str(LIBRARY_ID), "target_kind": "file", "target_path": None},
        ),
        (
            WEB_API_REFRESH_PLAN_ROUTE,
            {"library_id": str(LIBRARY_ID), "target_kind": "all", "target_path": "unexpected"},
        ),
    ],
)
def test_operation_path_and_target_validation_uses_typed_422_envelope(
    tmp_path: Path,
    route: str,
    body: dict[str, object],
) -> None:
    """Empty paths and contradictory Refresh targets fail at the typed request boundary."""
    operations = FakeOperations(_queued_operation(OperationKind.CHECK))

    response = _client(tmp_path, operations).post(route, json=body, headers=_mutation_headers())

    assert response.status_code == HTTP_UNPROCESSABLE_CONTENT_STATUS
    assert response.json()["data"] is None
    assert _first_error(response)["code"] == "validation_failed"
    assert str(_first_error(response)["field"]).startswith("body")
    assert operations.start_calls == []


def test_operation_openapi_declares_location_and_typed_validation_responses() -> None:
    """Generated clients see Location on replay/acceptance and no FastAPI error schema."""
    schema = cast("dict[str, object]", create_api_schema_app().openapi())
    paths = _mapping(schema, "paths")

    for route in (
        WEB_API_ADD_PLAN_ROUTE,
        WEB_API_ORGANIZE_PLAN_ROUTE,
        WEB_API_REFRESH_PLAN_ROUTE,
        WEB_API_CHECK_RUN_ROUTE,
        WEB_API_APPLY_PLAN_ROUTE,
        WEB_API_UNDO_PLAN_ROUTE,
    ):
        operation = _mapping(_mapping(paths, route), "post")
        responses = _mapping(operation, "responses")
        for status in ("200", "202", "410"):
            assert "Location" in _mapping(_mapping(responses, status), "headers")
        assert _response_schema(responses, "422") == {"$ref": "#/components/schemas/ApiFailureEnvelope"}

    get_responses = _mapping(_mapping(_mapping(paths, WEB_API_OPERATION_ROUTE), "get"), "responses")
    assert _response_schema(get_responses, "422") == {"$ref": "#/components/schemas/ApiFailureEnvelope"}
    schemas = _mapping(_mapping(schema, "components"), "schemas")
    assert "HTTPValidationError" not in schemas


def test_composed_check_operation_can_be_polled_to_persisted_success(tmp_path: Path) -> None:
    """The production composition accepts Check, runs it, and exposes its durable result."""
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

    app = build_web_app(config_path, database_path, tmp_path / "missing-static")
    with TestClient(app, base_url="http://localhost") as client:
        csrf_token = cast("str", _data(client.get(WEB_API_BOOTSTRAP_ROUTE))["csrf_token"])
        accepted = client.post(
            WEB_API_CHECK_RUN_ROUTE,
            json={"library_id": str(LIBRARY_ID)},
            headers={
                WEB_CSRF_HEADER_NAME: csrf_token,
                WEB_IDEMPOTENCY_HEADER_NAME: str(IDEMPOTENCY_KEY),
            },
        )
        terminal = _poll_terminal(client, accepted.headers["Location"])

    assert accepted.status_code == HTTP_ACCEPTED_STATUS
    assert terminal.status_code == HTTP_OK_STATUS
    terminal_data = _data(terminal)
    assert terminal_data["status"] == "succeeded"
    result = _object(terminal_data, "result")
    assert result["kind"] == "check_completed"
    assert result["issue_count"] == 0
    assert len(cast("list[str]", result["check_run_ids"])) == 1


@dataclass(slots=True)
class FakeOperations:
    """Thin route-context fake that records translated Operation starts."""

    lookup: Operation | Exception
    is_new: bool = True
    start_failure: Exception | None = None
    active_operation_id: OperationId | None = None
    get_count: int = 0
    start_calls: list[tuple[OperationKind, object, UUID]] = field(default_factory=list)

    def route_context(self) -> OperationsRouteContext:
        """Expose this fake through the public Web composition protocol."""
        return OperationsRouteContext(
            get_operation=self.get_operation,
            active_operation_id=lambda: self.active_operation_id,
            start_add_plan=self.start_add_plan,
            start_organize_plan=self.start_organize_plan,
            start_refresh_plan=self.start_refresh_plan,
            start_check=self.start_check,
            start_apply_plan=self.start_apply_plan,
            start_undo_plan=self.start_undo_plan,
        )

    def get_operation(self, _operation_id: OperationId) -> Operation:
        """Return or raise the configured retained lookup outcome."""
        self.get_count += 1
        if isinstance(self.lookup, Exception):
            raise self.lookup
        return self.lookup

    def start_add_plan(self, request: CreateAddPlanRequest, key: UUID) -> ReserveOperationResult:
        """Record one Add translation."""
        return self._start(OperationKind.ADD_PLAN, request, key)

    def start_organize_plan(self, request: CreateOrganizePlanRequest, key: UUID) -> ReserveOperationResult:
        """Record one Organize translation."""
        return self._start(OperationKind.ORGANIZE_PLAN, request, key)

    def start_refresh_plan(self, request: CreateRefreshPlanRequest, key: UUID) -> ReserveOperationResult:
        """Record one Refresh translation."""
        return self._start(OperationKind.REFRESH_PLAN, request, key)

    def start_check(self, request: CheckLibraryRequest, key: UUID) -> ReserveOperationResult:
        """Record one Check translation."""
        return self._start(OperationKind.CHECK, request, key)

    def start_apply_plan(self, plan_id: PlanId, key: UUID) -> ReserveOperationResult:
        """Record one Apply translation."""
        return self._start(OperationKind.APPLY_PLAN, plan_id, key)

    def start_undo_plan(self, request: CreateUndoPlanRequest, key: UUID) -> ReserveOperationResult:
        """Record one Undo translation."""
        return self._start(OperationKind.UNDO_PLAN, request, key)

    def _start(self, kind: OperationKind, request: object, key: UUID) -> ReserveOperationResult:
        self.start_calls.append((kind, request, key))
        if self.start_failure is not None:
            raise self.start_failure
        if isinstance(self.lookup, Exception):
            raise self.lookup
        return ReserveOperationResult(lookup=cast("OperationLookup", self.lookup), is_new=self.is_new)


def _queued_operation(kind: OperationKind) -> Operation:
    return Operation.queued(
        operation_id=OPERATION_ID,
        kind=kind,
        idempotency_key=IDEMPOTENCY_KEY,
        request_fingerprint=REQUEST_FINGERPRINT,
        requested_at=NOW,
    )


def _succeeded_check_operation() -> Operation:
    return (
        _queued_operation(OperationKind.CHECK)
        .mark_running(STARTED_AT)
        .mark_succeeded(
            result=CheckCompletedResult((CHECK_RUN_ID,), 0),
            completed_at=COMPLETED_AT,
            result_expires_at=COMPLETED_AT + timedelta(hours=OPERATION_RESULT_RETENTION_HOURS),
            tombstone_expires_at=COMPLETED_AT + timedelta(days=OPERATION_TOMBSTONE_RETENTION_DAYS),
        )
    )


def _client(tmp_path: Path, operations: FakeOperations) -> TestClient:
    context = ApiRouteContext(
        csrf_token=CSRF_TOKEN,
        get_bootstrap=_must_not_execute,
        operations=operations.route_context(),
    )
    app = create_web_app(context, tmp_path / "missing-static", allowed_hosts=("testserver",))
    return TestClient(app, raise_server_exceptions=False)


def _mutation_headers() -> dict[str, str]:
    return {
        WEB_CSRF_HEADER_NAME: CSRF_TOKEN,
        WEB_IDEMPOTENCY_HEADER_NAME: str(IDEMPOTENCY_KEY),
    }


def _operation_url(operation_id: object) -> str:
    return WEB_API_OPERATION_ROUTE.format(operation_id=operation_id)


def _must_not_execute():
    raise AssertionError(UNRELATED_BOOTSTRAP_MESSAGE)


def _poll_terminal(client: TestClient, location: str) -> Response:
    deadline = monotonic() + OPERATION_RECONCILE_INTERVAL_SECONDS
    while monotonic() < deadline:
        response = client.get(location)
        if _data(response)["status"] in {"succeeded", "failed", "interrupted"}:
            return response
        sleep(OPERATION_POLL_INITIAL_SECONDS)
    raise AssertionError(OPERATION_POLL_TIMEOUT_MESSAGE)


def _response_object(response: Response) -> dict[str, object]:
    return cast("dict[str, object]", response.json())


def _data(response: Response) -> dict[str, object]:
    data = _response_object(response)["data"]
    assert isinstance(data, dict)
    return cast("dict[str, object]", data)


def _object(value: dict[str, object], key: str) -> dict[str, object]:
    nested = value[key]
    assert isinstance(nested, dict)
    return cast("dict[str, object]", nested)


def _first_error(response: Response) -> dict[str, object]:
    errors = _response_object(response)["errors"]
    assert isinstance(errors, list)
    return cast("dict[str, object]", errors[0])


def _mapping(value: dict[str, object], key: str) -> dict[str, object]:
    nested = value[key]
    assert isinstance(nested, dict)
    return cast("dict[str, object]", nested)


def _response_schema(responses: dict[str, object], status_code: str) -> dict[str, object]:
    response = _mapping(responses, status_code)
    content = _mapping(response, "content")
    media_type = _mapping(content, "application/json")
    return _mapping(media_type, "schema")
