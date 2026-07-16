"""
Summary: Tests durable Operation lifecycle invariants.
Why: Prevents invalid results, errors, and timestamp combinations from reaching persistence.
"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from uuid import UUID

import pytest

from omym2.domain.models.operation import (
    CheckCompletedResult,
    Operation,
    OperationError,
    OperationErrorCode,
    OperationKind,
    OperationStatus,
    OperationTombstone,
    PlanCreatedResult,
    RegisteredWithoutPlanResult,
    RunCompletedResult,
)
from omym2.shared.ids import CheckRunId, LibraryId, OperationId, PlanId, RunId

BASE_TIME = datetime(2026, 7, 13, tzinfo=UTC)
STARTED_TIME = BASE_TIME + timedelta(seconds=1)
COMPLETED_TIME = STARTED_TIME + timedelta(seconds=1)
RESULT_EXPIRY_TIME = COMPLETED_TIME + timedelta(hours=24)
TOMBSTONE_EXPIRY_TIME = COMPLETED_TIME + timedelta(days=30)
TRACK_COUNT = 3
ISSUE_COUNT = 1
IDEMPOTENCY_KEY = UUID("1e53732d-4b41-4833-b27a-e3f58bcfc764")
OPERATION_ID = OperationId(UUID("018f6a4f-3c2d-7b8a-9abc-def012345686"))
LIBRARY_ID = LibraryId(UUID("018f6a4f-3c2d-7b8a-9abc-def012345678"))
PLAN_ID = PlanId(UUID("018f6a4f-3c2d-7b8a-9abc-def01234567a"))
OTHER_PLAN_ID = PlanId(UUID("018f6a4f-3c2d-7b8a-9abc-def012345689"))
RUN_ID = RunId(UUID("018f6a4f-3c2d-7b8a-9abc-def01234567d"))
CHECK_RUN_ID = CheckRunId(UUID("018f6a4f-3c2d-7b8a-9abc-def012345684"))
REQUEST_FINGERPRINT = "request-fingerprint"


def test_operation_transitions_from_queued_through_typed_success() -> None:
    """A queued Plan operation records running state and one linked typed result."""
    queued = _queued(OperationKind.ADD_PLAN)

    running = queued.mark_running(STARTED_TIME)
    succeeded = running.mark_succeeded(
        result=PlanCreatedResult(PLAN_ID),
        completed_at=COMPLETED_TIME,
        result_expires_at=RESULT_EXPIRY_TIME,
        tombstone_expires_at=TOMBSTONE_EXPIRY_TIME,
    )

    assert succeeded.status is OperationStatus.SUCCEEDED
    assert succeeded.plan_id == PLAN_ID
    assert succeeded.result == PlanCreatedResult(PLAN_ID)
    assert succeeded.error is None
    assert succeeded.is_terminal


def test_operation_result_types_validate_required_counts_and_ids() -> None:
    """Every typed result preserves its required payload and rejects impossible counts."""
    assert RegisteredWithoutPlanResult(LIBRARY_ID, TRACK_COUNT).track_count == TRACK_COUNT
    assert CheckCompletedResult((CHECK_RUN_ID,), ISSUE_COUNT).check_run_ids == (CHECK_RUN_ID,)
    assert RunCompletedResult(RUN_ID).run_id == RUN_ID

    with pytest.raises(ValueError, match="at least one"):
        _ = CheckCompletedResult((), ISSUE_COUNT)
    with pytest.raises(ValueError, match="nonnegative"):
        _ = RegisteredWithoutPlanResult(LIBRARY_ID, -1)


def test_operation_rejects_result_for_wrong_kind() -> None:
    """A successful Operation cannot persist a result belonging to another workflow."""
    running = _queued(OperationKind.CHECK).mark_running(STARTED_TIME)

    with pytest.raises(ValueError, match="result does not match"):
        _ = running.mark_succeeded(
            result=PlanCreatedResult(PLAN_ID),
            completed_at=COMPLETED_TIME,
            result_expires_at=RESULT_EXPIRY_TIME,
            tombstone_expires_at=TOMBSTONE_EXPIRY_TIME,
        )


def test_operation_rejects_result_that_replaces_an_existing_association() -> None:
    """Completion cannot silently relink an accepted Operation to a different durable resource."""
    running = Operation.queued(
        operation_id=OPERATION_ID,
        kind=OperationKind.ADD_PLAN,
        idempotency_key=IDEMPOTENCY_KEY,
        request_fingerprint=REQUEST_FINGERPRINT,
        requested_at=BASE_TIME,
        library_id=LIBRARY_ID,
        plan_id=PLAN_ID,
    ).mark_running(STARTED_TIME)

    with pytest.raises(ValueError, match="result does not match"):
        _ = running.mark_succeeded(
            result=PlanCreatedResult(OTHER_PLAN_ID),
            completed_at=COMPLETED_TIME,
            result_expires_at=RESULT_EXPIRY_TIME,
            tombstone_expires_at=TOMBSTONE_EXPIRY_TIME,
        )


def test_operation_failure_and_interruption_require_matching_error_codes() -> None:
    """Normal failures and interruptions retain distinct typed terminal evidence."""
    failure = OperationError(
        code=OperationErrorCode.OPERATION_FAILED,
        message="The operation failed.",
        retryable=True,
    )
    interruption = OperationError(
        code=OperationErrorCode.OPERATION_INTERRUPTED,
        message="The worker stopped before completion.",
        retryable=False,
    )

    failed = (
        _queued(OperationKind.CHECK)
        .mark_running(STARTED_TIME)
        .mark_failed(
            error=failure,
            completed_at=COMPLETED_TIME,
            result_expires_at=RESULT_EXPIRY_TIME,
            tombstone_expires_at=TOMBSTONE_EXPIRY_TIME,
        )
    )
    interrupted = _queued(OperationKind.CHECK).mark_interrupted(
        error=interruption,
        completed_at=COMPLETED_TIME,
        result_expires_at=RESULT_EXPIRY_TIME,
        tombstone_expires_at=TOMBSTONE_EXPIRY_TIME,
    )

    assert failed.status is OperationStatus.FAILED
    assert failed.started_at == STARTED_TIME
    assert interrupted.status is OperationStatus.INTERRUPTED
    assert interrupted.started_at is None
    with pytest.raises(ValueError, match="error does not match"):
        _ = _queued(OperationKind.CHECK).mark_interrupted(
            error=failure,
            completed_at=COMPLETED_TIME,
            result_expires_at=RESULT_EXPIRY_TIME,
            tombstone_expires_at=TOMBSTONE_EXPIRY_TIME,
        )


def test_operation_rejects_invalid_status_fields_and_timestamp_order() -> None:
    """Direct restoration rejects lifecycle combinations that cannot be exposed as a full resource."""
    with pytest.raises(ValueError, match="lifecycle status"):
        _ = Operation(
            operation_id=OPERATION_ID,
            kind=OperationKind.CHECK,
            status=OperationStatus.QUEUED,
            idempotency_key=IDEMPOTENCY_KEY,
            request_fingerprint=REQUEST_FINGERPRINT,
            requested_at=BASE_TIME,
            updated_at=BASE_TIME,
            started_at=STARTED_TIME,
        )

    with pytest.raises(ValueError, match="timestamps must be monotonic"):
        _ = _queued(OperationKind.CHECK).mark_running(BASE_TIME - timedelta(seconds=1))


def test_operation_tombstone_retains_only_replay_identity() -> None:
    """Expired payloads retain the identity required for 410 and idempotency classification."""
    tombstone = OperationTombstone(
        operation_id=OPERATION_ID,
        idempotency_key=IDEMPOTENCY_KEY,
        kind=OperationKind.CHECK,
        request_fingerprint=REQUEST_FINGERPRINT,
        tombstone_expires_at=TOMBSTONE_EXPIRY_TIME,
    )

    assert tombstone.operation_id == OPERATION_ID
    assert tombstone.idempotency_key == IDEMPOTENCY_KEY
    assert tombstone.tombstone_expires_at == TOMBSTONE_EXPIRY_TIME


def _queued(kind: OperationKind) -> Operation:
    return Operation.queued(
        operation_id=OPERATION_ID,
        kind=kind,
        idempotency_key=IDEMPOTENCY_KEY,
        request_fingerprint=REQUEST_FINGERPRINT,
        requested_at=BASE_TIME,
        library_id=LIBRARY_ID,
    )
