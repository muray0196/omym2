"""
Summary: Tests atomic Apply claims, ready-Plan cancellation, and interruption repair.
Why: Prevents duplicate execution and preserves only durable evidence after process loss.
"""

from __future__ import annotations

from collections import deque
from dataclasses import dataclass
from datetime import UTC, datetime
from typing import TYPE_CHECKING, override
from uuid import UUID

import pytest

from omym2.config import FILE_EVENT_SEQUENCE_START, PLAN_ACTION_SORT_ORDER_START, PLAN_ACTION_SORT_ORDER_STEP
from omym2.domain.models.file_event import FileEvent, FileEventStatus, FileEventType
from omym2.domain.models.library import Library, LibraryStatus
from omym2.domain.models.operation import Operation, OperationErrorCode, OperationKind, OperationStatus
from omym2.domain.models.plan import Plan, PlanStatus, PlanType
from omym2.domain.models.plan_action import ActionStatus, ActionType, PlanAction, PlanActionReason
from omym2.domain.models.run import Run, RunStatus
from omym2.features.apply.dto import ClaimApplyRequest
from omym2.features.apply.ports import ApplyPlanPorts
from omym2.features.apply.usecases.apply_plan import PlanCannotBeAppliedError
from omym2.features.apply.usecases.claim_apply import ClaimApplyUseCase, LibraryRootChangedError
from omym2.features.common_ports import IdempotencyKeyReusedError, OperationInProgressError
from omym2.features.operations.ports import OperationPorts
from omym2.features.operations.usecases.reconcile_operations import ReconcileOperationsUseCase
from omym2.features.plans.dto import CancelPlanRequest
from omym2.features.plans.ports import PlanQueryPorts
from omym2.features.plans.usecases.cancel_plan import CancelPlanUseCase, PlanCannotBeCancelledError
from omym2.features.plans.usecases.get_plan_header import PlanNotFoundError
from omym2.shared.ids import ActionId, EventId, LibraryId, OperationId, PlanId, RunId
from tests.fakes.in_memory_repositories import InMemoryPlanRepository, InMemoryUnitOfWork
from tests.fakes.runtime import FixedClock, SequenceIdGenerator

if TYPE_CHECKING:
    from omym2.domain.models.file_snapshot import FileSnapshot, FilesystemIdentity
    from omym2.domain.models.operation import OperationLookup
    from omym2.features.common_ports import FileSystemPath

ACTION_IDS = tuple(
    ActionId(UUID(value))
    for value in (
        "018f6a4f-3c2d-7b8a-9abc-def012345690",
        "018f6a4f-3c2d-7b8a-9abc-def012345691",
        "018f6a4f-3c2d-7b8a-9abc-def012345692",
        "018f6a4f-3c2d-7b8a-9abc-def012345693",
    )
)
BASE_TIME = datetime(2026, 1, 1, tzinfo=UTC)
COMPLETED_TIME = datetime(2026, 1, 2, tzinfo=UTC)
CONFIG_HASH = "config-hash"
EVENT_ID = EventId(UUID("018f6a4f-3c2d-7b8a-9abc-def012345694"))
FINGERPRINT = "apply-plan-fingerprint"
IDEMPOTENCY_KEY = UUID("018f6a4f-3c2d-7b8a-9abc-def012345695")
LIBRARY_ID = LibraryId(UUID("018f6a4f-3c2d-7b8a-9abc-def012345696"))
LIBRARY_ROOT = "/music/library"
MOVED_LIBRARY_ROOT = "/music/moved-library"
OPERATION_ID = OperationId(UUID("018f6a4f-3c2d-7b8a-9abc-def012345697"))
OTHER_OPERATION_ID = OperationId(UUID("018f6a4f-3c2d-7b8a-9abc-def012345698"))
OTHER_IDEMPOTENCY_KEY = UUID("018f6a4f-3c2d-7b8a-9abc-def012345699")
PLAN_ID = PlanId(UUID("018f6a4f-3c2d-7b8a-9abc-def01234569a"))
RUN_ID = RunId(UUID("018f6a4f-3c2d-7b8a-9abc-def01234569b"))
SINGLE_COMMIT_COUNT = 1
SOURCE_PATH = "Unsorted/Title.flac"
TARGET_PATH = "Artist/Album/Title.flac"


def test_claim_apply_commits_plan_run_and_operation_together() -> None:
    """One accepted claim commits all durable execution identities."""
    uow = _ready_uow()

    result = ClaimApplyUseCase(_claim_ports(uow)).execute(_claim_request())

    assert result.is_new
    assert isinstance(result.lookup, Operation)
    assert result.lookup.status is OperationStatus.QUEUED
    assert result.lookup.plan_id == PLAN_ID
    assert result.lookup.run_id == RUN_ID
    assert _stored_plan(uow).status is PlanStatus.APPLYING
    run = _stored_run(uow)
    assert run.status is RunStatus.RUNNING
    assert run.plan_id == PLAN_ID
    assert uow.operations.lookup(OPERATION_ID) == result.lookup
    assert uow.commit_count == SINGLE_COMMIT_COUNT
    assert uow.file_events.records == {}


def test_claim_apply_expires_root_mismatch_without_creating_execution_records() -> None:
    """A pre-claim root mismatch expires the Plan before Run or Operation creation."""
    uow = _ready_uow(library_root=MOVED_LIBRARY_ROOT)

    with pytest.raises(LibraryRootChangedError):
        _ = ClaimApplyUseCase(_claim_ports(uow)).execute(_claim_request())

    assert _stored_plan(uow).status is PlanStatus.EXPIRED
    assert uow.runs.records == {}
    assert uow.operations.records == {}
    assert uow.file_events.records == {}
    assert uow.commit_count == SINGLE_COMMIT_COUNT


def test_claim_apply_cas_race_creates_no_partial_execution_state() -> None:
    """A lost ready-to-applying CAS cannot leak a Run or Operation."""
    uow = LosingApplyClaimUnitOfWork()
    uow.libraries.save(_library())
    uow.plans.save(_plan())

    with pytest.raises(PlanCannotBeAppliedError):
        _ = ClaimApplyUseCase(_claim_ports(uow)).execute(_claim_request())

    assert _stored_plan(uow).status is PlanStatus.READY
    assert uow.runs.records == {}
    assert uow.operations.records == {}
    assert uow.commit_count == 0


def test_claim_apply_rejects_single_use_plan_after_execution_started() -> None:
    """A non-ready Plan cannot create a second Run or durable Operation."""
    uow = _ready_uow()
    uow.plans.save(_plan(status=PlanStatus.APPLYING))

    with pytest.raises(PlanCannotBeAppliedError):
        _ = ClaimApplyUseCase(_claim_ports(uow)).execute(_claim_request())

    assert uow.runs.records == {}
    assert uow.operations.records == {}
    assert uow.commit_count == 0


def test_claim_apply_exact_replay_returns_existing_operation_without_side_effects() -> None:
    """The same key and fingerprint return the retained claim without new IDs."""
    uow = _ready_uow()
    usecase = ClaimApplyUseCase(_claim_ports(uow))
    first = usecase.execute(_claim_request())

    replay = usecase.execute(_claim_request())

    assert first.is_new
    assert not replay.is_new
    assert replay.lookup == first.lookup
    assert uow.commit_count == SINGLE_COMMIT_COUNT
    assert tuple(uow.runs.records) == (RUN_ID,)
    assert tuple(uow.operations.records) == (OPERATION_ID,)


def test_claim_apply_rejects_reused_key_with_different_fingerprint() -> None:
    """A retained key cannot identify different canonical Apply work."""
    uow = _ready_uow()
    usecase = ClaimApplyUseCase(_claim_ports(uow))
    _ = usecase.execute(_claim_request())

    with pytest.raises(IdempotencyKeyReusedError):
        _ = usecase.execute(_claim_request(fingerprint="different-fingerprint"))

    assert uow.commit_count == SINGLE_COMMIT_COUNT
    assert tuple(uow.operations.records) == (OPERATION_ID,)


def test_claim_apply_rejects_reused_key_from_different_operation_kind() -> None:
    """A key retained for another Operation kind cannot be reused for Apply."""
    uow = _ready_uow()
    retained = _operation(
        operation_id=OTHER_OPERATION_ID,
        idempotency_key=IDEMPOTENCY_KEY,
        kind=OperationKind.CHECK,
    )
    uow.operations.save(retained)

    with pytest.raises(IdempotencyKeyReusedError):
        _ = ClaimApplyUseCase(_claim_ports(uow)).execute(_claim_request())

    assert _stored_plan(uow).status is PlanStatus.READY
    assert uow.runs.records == {}
    assert uow.operations.lookup(OTHER_OPERATION_ID) == retained
    assert uow.commit_count == 0


def test_claim_apply_rejects_another_active_operation() -> None:
    """A different active durable Operation retains the single global slot."""
    uow = _ready_uow()
    active = _operation(
        operation_id=OTHER_OPERATION_ID,
        idempotency_key=OTHER_IDEMPOTENCY_KEY,
        kind=OperationKind.CHECK,
    )
    uow.operations.save(active)

    with pytest.raises(OperationInProgressError) as error:
        _ = ClaimApplyUseCase(_claim_ports(uow)).execute(_claim_request())

    assert error.value.active_operation == active
    assert _stored_plan(uow).status is PlanStatus.READY
    assert uow.runs.records == {}
    assert tuple(uow.operations.records) == (OTHER_OPERATION_ID,)
    assert uow.commit_count == 0


def test_cancel_plan_compare_and_sets_ready_to_cancelled_without_operation() -> None:
    """Cancellation is one synchronous Plan-only transition."""
    uow = _ready_uow()

    cancelled = CancelPlanUseCase(PlanQueryPorts(uow)).execute(CancelPlanRequest(PLAN_ID))

    assert cancelled.status is PlanStatus.CANCELLED
    assert _stored_plan(uow).status is PlanStatus.CANCELLED
    assert uow.commit_count == SINGLE_COMMIT_COUNT
    assert uow.operations.records == {}
    assert uow.runs.records == {}
    assert uow.file_events.records == {}


def test_cancel_plan_losing_cas_race_does_not_overwrite_plan() -> None:
    """A stale ready read cannot cancel after another claimant wins."""
    uow = InMemoryUnitOfWork(plans=LosingPlanRepository())
    uow.libraries.save(_library())
    uow.plans.save(_plan())

    with pytest.raises(PlanCannotBeCancelledError):
        _ = CancelPlanUseCase(PlanQueryPorts(uow)).execute(CancelPlanRequest(PLAN_ID))

    assert _stored_plan(uow).status is PlanStatus.READY
    assert uow.commit_count == 0


def test_cancel_plan_rejects_missing_plan() -> None:
    """Cancellation distinguishes a missing Plan from a lost status race."""
    uow = InMemoryUnitOfWork()

    with pytest.raises(PlanNotFoundError):
        _ = CancelPlanUseCase(PlanQueryPorts(uow)).execute(CancelPlanRequest(PLAN_ID))

    assert uow.commit_count == 0


@pytest.mark.parametrize("operation_status", [OperationStatus.QUEUED, OperationStatus.RUNNING])
def test_reconcile_apply_interrupts_queued_or_running_operation_with_confirmed_success(
    operation_status: OperationStatus,
) -> None:
    """Confirmed eligible success derives a normal Plan and Run result after interruption."""
    uow = _claimed_apply_uow(operation_status)
    uow.plan_actions.save(_action(ACTION_IDS[0], ActionType.MOVE, ActionStatus.APPLIED))

    repaired = ReconcileOperationsUseCase(_operation_ports(uow)).execute()

    assert repaired == (OPERATION_ID,)
    assert _stored_plan(uow).status is PlanStatus.APPLIED
    run = _stored_run(uow)
    assert run.status is RunStatus.SUCCEEDED
    assert run.completed_at == COMPLETED_TIME
    operation = _stored_operation(uow)
    assert operation.status is OperationStatus.INTERRUPTED
    assert operation.completed_at == COMPLETED_TIME
    assert operation.error is not None
    assert operation.error.code is OperationErrorCode.OPERATION_INTERRUPTED


def test_reconcile_apply_preserves_pending_and_derives_partial_from_confirmed_action_evidence() -> None:
    """Unknown mutation evidence stays pending while other durable success makes the Run partial."""
    uow = _claimed_apply_uow(OperationStatus.RUNNING)
    uow.plan_actions.save(_action(ACTION_IDS[0], ActionType.MOVE, ActionStatus.APPLIED))
    uow.plan_actions.save(_action(ACTION_IDS[1], ActionType.MOVE, ActionStatus.PLANNED))
    uow.plan_actions.save(_action(ACTION_IDS[2], ActionType.REFRESH_METADATA, ActionStatus.PLANNED))
    uow.plan_actions.save(
        _action(
            ACTION_IDS[3],
            ActionType.MOVE,
            ActionStatus.BLOCKED,
            reason=PlanActionReason.TARGET_EXISTS,
        )
    )
    skip_action_id = ActionId(UUID("018f6a4f-3c2d-7b8a-9abc-def01234569c"))
    uow.plan_actions.save(
        _action(
            skip_action_id,
            ActionType.SKIP,
            ActionStatus.PLANNED,
            reason=PlanActionReason.DUPLICATE_HASH,
        )
    )
    uow.file_events.save(_pending_event(ACTION_IDS[1]))

    repaired = ReconcileOperationsUseCase(_operation_ports(uow)).execute()

    assert repaired == (OPERATION_ID,)
    assert _stored_plan(uow).status is PlanStatus.PARTIAL_FAILED
    assert _stored_run(uow).status is RunStatus.PARTIAL_FAILED
    assert _stored_action(uow, ACTION_IDS[0]).status is ActionStatus.APPLIED
    for action_id in (ACTION_IDS[1], ACTION_IDS[2]):
        action = _stored_action(uow, action_id)
        assert action.status is ActionStatus.FAILED
        assert action.reason is PlanActionReason.OPERATION_INTERRUPTED
    blocked = _stored_action(uow, ACTION_IDS[3])
    assert blocked.status is ActionStatus.BLOCKED
    assert blocked.reason is PlanActionReason.TARGET_EXISTS
    skip = _stored_action(uow, skip_action_id)
    assert skip.status is ActionStatus.APPLIED
    assert skip.reason is PlanActionReason.DUPLICATE_HASH
    assert _stored_event(uow).status is FileEventStatus.PENDING
    assert _stored_operation(uow).status is OperationStatus.INTERRUPTED


def test_reconcile_apply_derives_failure_without_confirmed_eligible_success_and_is_idempotent() -> None:
    """Unconfirmed eligible work becomes failed once and pending evidence remains unchanged."""
    uow = _claimed_apply_uow(OperationStatus.QUEUED)
    uow.plan_actions.save(_action(ACTION_IDS[0], ActionType.MOVE, ActionStatus.PLANNED))
    uow.file_events.save(_pending_event(ACTION_IDS[0]))
    usecase = ReconcileOperationsUseCase(_operation_ports(uow))

    first = usecase.execute()
    first_operation = _stored_operation(uow)
    second = usecase.execute()

    assert first == (OPERATION_ID,)
    assert second == ()
    assert _stored_plan(uow).status is PlanStatus.FAILED
    assert _stored_run(uow).status is RunStatus.FAILED
    action = _stored_action(uow, ACTION_IDS[0])
    assert action.status is ActionStatus.FAILED
    assert action.reason is PlanActionReason.OPERATION_INTERRUPTED
    assert _stored_event(uow).status is FileEventStatus.PENDING
    assert _stored_operation(uow) == first_operation
    assert uow.commit_count == SINGLE_COMMIT_COUNT


@dataclass(slots=True)
class LosingApplyClaimUnitOfWork(InMemoryUnitOfWork):
    """UnitOfWork fake whose atomic Apply compare-and-set loses a race."""

    @override
    def claim_apply(self, plan_id: PlanId, run: Run, operation: Operation) -> bool:
        """Reject the staged claim without changing any managed record."""
        del plan_id, run, operation
        return False


@dataclass(slots=True)
class LosingPlanRepository(InMemoryPlanRepository):
    """Plan repository fake whose status compare-and-set loses a race."""

    @override
    def compare_and_set_status(
        self,
        plan_id: PlanId,
        expected_status: PlanStatus,
        replacement_status: PlanStatus,
    ) -> bool:
        """Reject the requested status transition without overwriting state."""
        del plan_id, expected_status, replacement_status
        return False


class UnusedFileMover:
    """FileMover fake that rejects accidental mutation during claim tests."""

    def move(  # noqa: PLR0913  # Fake mirrors the stable FileMover safety port.
        self,
        source: FileSystemPath,
        target: FileSystemPath,
        *,
        source_root: FileSystemPath | None = None,
        target_root: FileSystemPath | None = None,
        expected_source_identity: FilesystemIdentity | None = None,
        expected_source_content_hash: str | None = None,
    ) -> None:
        """Fail because claim acceptance must not reach a filesystem mutation."""
        del source, target, source_root, target_root, expected_source_identity, expected_source_content_hash
        raise AssertionError


class UnusedSnapshotReader:
    """Snapshot fake that rejects accidental reads during claim tests."""

    def capture(self, path: FileSystemPath) -> FileSnapshot:
        """Fail because claim acceptance must not inspect files."""
        del path
        raise AssertionError


class UnusedPathResolver:
    """Path fake that rejects accidental resolution during claim tests."""

    def resolve_library_path(self, library_root: FileSystemPath, library_relative_path: str) -> str:
        """Fail because claim acceptance must not resolve paths."""
        del library_root, library_relative_path
        raise AssertionError

    def relative_to_library(self, library_root: FileSystemPath, path: FileSystemPath) -> str:
        """Fail because claim acceptance must not normalize paths."""
        del library_root, path
        raise AssertionError


def _ready_uow(*, library_root: str = LIBRARY_ROOT) -> InMemoryUnitOfWork:
    uow = InMemoryUnitOfWork()
    uow.libraries.save(_library(root_path=library_root))
    uow.plans.save(_plan())
    return uow


def _claimed_apply_uow(operation_status: OperationStatus) -> InMemoryUnitOfWork:
    uow = InMemoryUnitOfWork()
    uow.libraries.save(_library())
    uow.plans.save(_plan(status=PlanStatus.APPLYING))
    uow.runs.save(_run())
    operation = _operation()
    if operation_status is OperationStatus.RUNNING:
        operation = operation.mark_running(BASE_TIME)
    uow.operations.save(operation)
    return uow


def _claim_ports(uow: InMemoryUnitOfWork) -> ApplyPlanPorts:
    return ApplyPlanPorts(
        uow=uow,
        file_mover=UnusedFileMover(),
        file_snapshot_reader=UnusedSnapshotReader(),
        path_resolver=UnusedPathResolver(),
        clock=FixedClock(BASE_TIME),
        id_generator=SequenceIdGenerator(
            run_ids=deque((RUN_ID,)),
            operation_ids=deque((OPERATION_ID,)),
        ),
    )


def _operation_ports(uow: InMemoryUnitOfWork) -> OperationPorts:
    return OperationPorts(
        uow=uow,
        clock=FixedClock(COMPLETED_TIME),
        id_generator=SequenceIdGenerator(),
    )


def _claim_request(*, fingerprint: str = FINGERPRINT) -> ClaimApplyRequest:
    return ClaimApplyRequest(
        plan_id=PLAN_ID,
        idempotency_key=IDEMPOTENCY_KEY,
        request_fingerprint=fingerprint,
    )


def _library(*, root_path: str = LIBRARY_ROOT) -> Library:
    return Library(
        library_id=LIBRARY_ID,
        root_path=root_path,
        path_policy_hash=CONFIG_HASH,
        registered_at=BASE_TIME,
        status=LibraryStatus.REGISTERED,
        created_at=BASE_TIME,
        updated_at=BASE_TIME,
    )


def _plan(*, status: PlanStatus = PlanStatus.READY) -> Plan:
    return Plan(
        plan_id=PLAN_ID,
        library_id=LIBRARY_ID,
        plan_type=PlanType.ADD,
        status=status,
        created_at=BASE_TIME,
        config_hash=CONFIG_HASH,
        library_root_at_plan=LIBRARY_ROOT,
    )


def _run() -> Run:
    return Run(
        run_id=RUN_ID,
        plan_id=PLAN_ID,
        library_id=LIBRARY_ID,
        status=RunStatus.RUNNING,
        started_at=BASE_TIME,
    )


def _operation(
    *,
    operation_id: OperationId = OPERATION_ID,
    idempotency_key: UUID = IDEMPOTENCY_KEY,
    kind: OperationKind = OperationKind.APPLY_PLAN,
) -> Operation:
    is_apply = kind is OperationKind.APPLY_PLAN
    return Operation.queued(
        operation_id=operation_id,
        kind=kind,
        idempotency_key=idempotency_key,
        request_fingerprint=FINGERPRINT,
        requested_at=BASE_TIME,
        library_id=LIBRARY_ID if is_apply else None,
        plan_id=PLAN_ID if is_apply else None,
        run_id=RUN_ID if is_apply else None,
    )


def _action(
    action_id: ActionId,
    action_type: ActionType,
    status: ActionStatus,
    *,
    reason: PlanActionReason | None = None,
) -> PlanAction:
    action_index = ACTION_IDS.index(action_id) if action_id in ACTION_IDS else len(ACTION_IDS)
    return PlanAction(
        action_id=action_id,
        plan_id=PLAN_ID,
        library_id=LIBRARY_ID,
        track_id=None,
        action_type=action_type,
        source_path=SOURCE_PATH,
        target_path=TARGET_PATH,
        content_hash_at_plan="content-hash",
        metadata_hash_at_plan="metadata-hash",
        status=status,
        reason=reason,
        sort_order=PLAN_ACTION_SORT_ORDER_START + (action_index * PLAN_ACTION_SORT_ORDER_STEP),
    )


def _pending_event(action_id: ActionId) -> FileEvent:
    return FileEvent(
        event_id=EVENT_ID,
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
        sequence_no=FILE_EVENT_SEQUENCE_START,
    )


def _stored_plan(uow: InMemoryUnitOfWork) -> Plan:
    plan = uow.plans.get(PLAN_ID)
    assert plan is not None
    return plan


def _stored_run(uow: InMemoryUnitOfWork) -> Run:
    run = uow.runs.get(RUN_ID)
    assert run is not None
    return run


def _stored_operation(uow: InMemoryUnitOfWork) -> Operation:
    operation: OperationLookup | None = uow.operations.lookup(OPERATION_ID)
    assert isinstance(operation, Operation)
    return operation


def _stored_action(uow: InMemoryUnitOfWork, action_id: ActionId) -> PlanAction:
    action = uow.plan_actions.get(action_id)
    assert action is not None
    return action


def _stored_event(uow: InMemoryUnitOfWork) -> FileEvent:
    event = uow.file_events.get(EVENT_ID)
    assert event is not None
    return event
