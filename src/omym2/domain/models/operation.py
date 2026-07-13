"""
Summary: Defines durable background Operation lifecycle records.
Why: Preserves accepted request identity, progress, results, and interruption across process loss.
"""

from __future__ import annotations

from dataclasses import dataclass, field, replace
from enum import StrEnum
from re import fullmatch
from typing import TYPE_CHECKING

from omym2.shared.time import as_utc

if TYPE_CHECKING:
    from datetime import datetime
    from uuid import UUID

    from omym2.shared.ids import CheckRunId, LibraryId, OperationId, PlanId, RunId

INVALID_OPERATION_TRANSITION_MESSAGE = "Operation status transition is not allowed."
INVALID_OPERATION_STATE_MESSAGE = "Operation fields do not match its lifecycle status."
INVALID_OPERATION_TIME_ORDER_MESSAGE = "Operation timestamps must be monotonic."
INVALID_OPERATION_PROGRESS_MESSAGE = "Operation progress counts must be a valid nullable pair."
INVALID_OPERATION_PROGRESS_ORDER_MESSAGE = "Operation progress counts must be monotonic within one stage."
INVALID_OPERATION_STAGE_CODE_MESSAGE = "Operation stage_code must be stable snake_case."
INVALID_OPERATION_RESULT_MESSAGE = "Operation result does not match its kind or durable associations."
INVALID_OPERATION_ERROR_MESSAGE = "Operation error does not match its terminal status."
EMPTY_OPERATION_IDENTITY_MESSAGE = "Operation idempotency and fingerprint values must not be empty."
EMPTY_CHECK_RUN_IDS_MESSAGE = "A check_completed result requires at least one CheckRun ID."
NEGATIVE_RESULT_COUNT_MESSAGE = "Operation result counts must be nonnegative."
EMPTY_OPERATION_ERROR_MESSAGE = "Operation error messages must not be empty."
EMPTY_REMEDIATION_LABEL_MESSAGE = "Operation remediation labels must not be empty."


class OperationKind(StrEnum):
    """Supported durable Operation kinds."""

    ADD_PLAN = "add_plan"
    ORGANIZE_PLAN = "organize_plan"
    REFRESH_PLAN = "refresh_plan"
    CHECK = "check"
    APPLY_PLAN = "apply_plan"
    UNDO_PLAN = "undo_plan"


class OperationStatus(StrEnum):
    """Supported durable Operation lifecycle statuses."""

    QUEUED = "queued"
    RUNNING = "running"
    SUCCEEDED = "succeeded"
    FAILED = "failed"
    INTERRUPTED = "interrupted"


class OperationResultKind(StrEnum):
    """Supported typed Operation success-result discriminants."""

    PLAN_CREATED = "plan_created"
    REGISTERED_WITHOUT_PLAN = "registered_without_plan"
    CHECK_COMPLETED = "check_completed"
    RUN_COMPLETED = "run_completed"


class OperationErrorCode(StrEnum):
    """Supported terminal Operation error codes."""

    OPERATION_INTERRUPTED = "operation_interrupted"
    METADATA_READ_FAILED = "metadata_read_failed"
    OPERATION_FAILED = "operation_failed"


ACTIVE_OPERATION_STATUSES = frozenset({OperationStatus.QUEUED, OperationStatus.RUNNING})
TERMINAL_OPERATION_STATUSES = frozenset(
    {OperationStatus.SUCCEEDED, OperationStatus.FAILED, OperationStatus.INTERRUPTED}
)


@dataclass(frozen=True, slots=True)
class PlanCreatedResult:
    """Typed success result for a newly created reviewed Plan."""

    plan_id: PlanId
    kind: OperationResultKind = field(default=OperationResultKind.PLAN_CREATED, init=False)


@dataclass(frozen=True, slots=True)
class RegisteredWithoutPlanResult:
    """Typed success result for clean Library registration."""

    library_id: LibraryId
    track_count: int
    kind: OperationResultKind = field(default=OperationResultKind.REGISTERED_WITHOUT_PLAN, init=False)

    def __post_init__(self) -> None:
        """Reject impossible persisted Track counts."""
        if self.track_count < 0:
            raise ValueError(NEGATIVE_RESULT_COUNT_MESSAGE)


@dataclass(frozen=True, slots=True)
class CheckCompletedResult:
    """Typed success result for one persisted Check across selected Libraries."""

    check_run_ids: tuple[CheckRunId, ...]
    issue_count: int
    kind: OperationResultKind = field(default=OperationResultKind.CHECK_COMPLETED, init=False)

    def __post_init__(self) -> None:
        """Normalize IDs and reject empty or impossible completion evidence."""
        object.__setattr__(self, "check_run_ids", tuple(self.check_run_ids))
        if not self.check_run_ids:
            raise ValueError(EMPTY_CHECK_RUN_IDS_MESSAGE)
        if self.issue_count < 0:
            raise ValueError(NEGATIVE_RESULT_COUNT_MESSAGE)


@dataclass(frozen=True, slots=True)
class RunCompletedResult:
    """Typed success result for one completed Apply Run."""

    run_id: RunId
    kind: OperationResultKind = field(default=OperationResultKind.RUN_COMPLETED, init=False)


type OperationResult = PlanCreatedResult | RegisteredWithoutPlanResult | CheckCompletedResult | RunCompletedResult


@dataclass(frozen=True, slots=True)
class OperationProgress:
    """One durable, display-safe progress snapshot."""

    stage_code: str | None = None
    completed_units: int | None = None
    total_units: int | None = None
    message: str | None = None

    def __post_init__(self) -> None:
        """Validate open stage codes and real, bounded progress counts."""
        if self.stage_code is not None and fullmatch(r"[a-z][a-z0-9]*(?:_[a-z0-9]+)*", self.stage_code) is None:
            raise ValueError(INVALID_OPERATION_STAGE_CODE_MESSAGE)
        if (self.completed_units is None) != (self.total_units is None):
            raise ValueError(INVALID_OPERATION_PROGRESS_MESSAGE)
        if (
            self.completed_units is not None
            and self.total_units is not None
            and (self.completed_units < 0 or self.total_units < 0 or self.completed_units > self.total_units)
        ):
            raise ValueError(INVALID_OPERATION_PROGRESS_MESSAGE)


@dataclass(frozen=True, slots=True)
class OperationRemediation:
    """Optional display-safe recovery guidance for a terminal Operation error."""

    label: str
    route: str | None = None
    command: str | None = None

    def __post_init__(self) -> None:
        """Require a visible label for optional recovery guidance."""
        if not self.label:
            raise ValueError(EMPTY_REMEDIATION_LABEL_MESSAGE)


@dataclass(frozen=True, slots=True)
class OperationError:
    """Typed, redacted terminal Operation failure."""

    code: OperationErrorCode
    message: str
    retryable: bool
    field: str | None = None
    remediation: OperationRemediation | None = None

    def __post_init__(self) -> None:
        """Reject errors that cannot be displayed safely."""
        if not self.message:
            raise ValueError(EMPTY_OPERATION_ERROR_MESSAGE)


@dataclass(frozen=True, slots=True)
class Operation:
    """Full durable record for one accepted background request."""

    operation_id: OperationId
    kind: OperationKind
    status: OperationStatus
    idempotency_key: UUID
    request_fingerprint: str
    requested_at: datetime
    updated_at: datetime
    library_id: LibraryId | None = None
    plan_id: PlanId | None = None
    run_id: RunId | None = None
    progress: OperationProgress = field(default_factory=OperationProgress)
    result: OperationResult | None = None
    error: OperationError | None = None
    started_at: datetime | None = None
    completed_at: datetime | None = None
    result_expires_at: datetime | None = None
    tombstone_expires_at: datetime | None = None

    def __post_init__(self) -> None:
        """Normalize timestamps and enforce the complete lifecycle invariant."""
        if not str(self.idempotency_key) or not self.request_fingerprint:
            raise ValueError(EMPTY_OPERATION_IDENTITY_MESSAGE)
        object.__setattr__(self, "requested_at", as_utc(self.requested_at))
        object.__setattr__(self, "updated_at", as_utc(self.updated_at))
        if self.started_at is not None:
            object.__setattr__(self, "started_at", as_utc(self.started_at))
        if self.completed_at is not None:
            object.__setattr__(self, "completed_at", as_utc(self.completed_at))
        if self.result_expires_at is not None:
            object.__setattr__(self, "result_expires_at", as_utc(self.result_expires_at))
        if self.tombstone_expires_at is not None:
            object.__setattr__(self, "tombstone_expires_at", as_utc(self.tombstone_expires_at))
        self._validate_time_order()
        self._validate_status_fields()
        self._validate_result()
        self._validate_error()

    @classmethod
    def queued(  # noqa: PLR0913  # Durable acceptance requires the full request identity and optional links.
        cls,
        *,
        operation_id: OperationId,
        kind: OperationKind,
        idempotency_key: UUID,
        request_fingerprint: str,
        requested_at: datetime,
        library_id: LibraryId | None = None,
        plan_id: PlanId | None = None,
        run_id: RunId | None = None,
    ) -> Operation:
        """Create one newly accepted queued Operation."""
        return cls(
            operation_id=operation_id,
            kind=kind,
            status=OperationStatus.QUEUED,
            idempotency_key=idempotency_key,
            request_fingerprint=request_fingerprint,
            requested_at=requested_at,
            updated_at=requested_at,
            library_id=library_id,
            plan_id=plan_id,
            run_id=run_id,
        )

    @property
    def is_terminal(self) -> bool:
        """Return whether this Operation can no longer execute."""
        return self.status in TERMINAL_OPERATION_STATUSES

    def mark_running(self, started_at: datetime) -> Operation:
        """Return this queued Operation after worker dispatch starts."""
        if self.status is not OperationStatus.QUEUED:
            raise ValueError(INVALID_OPERATION_TRANSITION_MESSAGE)
        return replace(self, status=OperationStatus.RUNNING, started_at=started_at, updated_at=started_at)

    def update_progress(self, progress: OperationProgress, updated_at: datetime) -> Operation:
        """Return this running Operation with a newer durable progress snapshot."""
        if self.status is not OperationStatus.RUNNING:
            raise ValueError(INVALID_OPERATION_TRANSITION_MESSAGE)
        if as_utc(updated_at) < self.updated_at:
            raise ValueError(INVALID_OPERATION_TIME_ORDER_MESSAGE)
        if (
            self.progress.stage_code == progress.stage_code
            and self.progress.completed_units is not None
            and self.progress.total_units is not None
            and progress.completed_units is not None
            and progress.total_units is not None
            and (
                progress.completed_units < self.progress.completed_units
                or progress.total_units < self.progress.total_units
            )
        ):
            raise ValueError(INVALID_OPERATION_PROGRESS_ORDER_MESSAGE)
        return replace(self, progress=progress, updated_at=updated_at)

    def mark_succeeded(
        self,
        *,
        result: OperationResult,
        completed_at: datetime,
        result_expires_at: datetime,
        tombstone_expires_at: datetime,
    ) -> Operation:
        """Return this running Operation with one typed success result."""
        if self.status is not OperationStatus.RUNNING:
            raise ValueError(INVALID_OPERATION_TRANSITION_MESSAGE)
        associations: dict[str, object] = {}
        if isinstance(result, PlanCreatedResult):
            if self.plan_id is not None and self.plan_id != result.plan_id:
                raise ValueError(INVALID_OPERATION_RESULT_MESSAGE)
            associations["plan_id"] = result.plan_id
        elif isinstance(result, RegisteredWithoutPlanResult):
            if self.library_id is not None and self.library_id != result.library_id:
                raise ValueError(INVALID_OPERATION_RESULT_MESSAGE)
            associations["library_id"] = result.library_id
        elif isinstance(result, RunCompletedResult):
            if self.run_id is not None and self.run_id != result.run_id:
                raise ValueError(INVALID_OPERATION_RESULT_MESSAGE)
            associations["run_id"] = result.run_id
        return replace(
            self,
            status=OperationStatus.SUCCEEDED,
            result=result,
            completed_at=completed_at,
            updated_at=completed_at,
            result_expires_at=result_expires_at,
            tombstone_expires_at=tombstone_expires_at,
            **associations,
        )

    def mark_failed(
        self,
        *,
        error: OperationError,
        completed_at: datetime,
        result_expires_at: datetime,
        tombstone_expires_at: datetime,
    ) -> Operation:
        """Return this running Operation with a redacted terminal failure."""
        if self.status is not OperationStatus.RUNNING:
            raise ValueError(INVALID_OPERATION_TRANSITION_MESSAGE)
        return replace(
            self,
            status=OperationStatus.FAILED,
            error=error,
            completed_at=completed_at,
            updated_at=completed_at,
            result_expires_at=result_expires_at,
            tombstone_expires_at=tombstone_expires_at,
        )

    def mark_interrupted(
        self,
        *,
        error: OperationError,
        completed_at: datetime,
        result_expires_at: datetime,
        tombstone_expires_at: datetime,
    ) -> Operation:
        """Return queued or running work as interrupted without inferring success."""
        if self.status not in ACTIVE_OPERATION_STATUSES:
            raise ValueError(INVALID_OPERATION_TRANSITION_MESSAGE)
        return replace(
            self,
            status=OperationStatus.INTERRUPTED,
            error=error,
            completed_at=completed_at,
            updated_at=completed_at,
            result_expires_at=result_expires_at,
            tombstone_expires_at=tombstone_expires_at,
        )

    def _validate_time_order(self) -> None:
        if self.updated_at < self.requested_at:
            raise ValueError(INVALID_OPERATION_TIME_ORDER_MESSAGE)
        if self.started_at is not None and self.started_at < self.requested_at:
            raise ValueError(INVALID_OPERATION_TIME_ORDER_MESSAGE)
        self._validate_completion_time_order()
        self._validate_expiry_time_order()

    def _validate_completion_time_order(self) -> None:
        if self.completed_at is None:
            return
        starts_after_completion = self.started_at is not None and self.completed_at < self.started_at
        if self.completed_at < self.requested_at or starts_after_completion or self.updated_at < self.completed_at:
            raise ValueError(INVALID_OPERATION_TIME_ORDER_MESSAGE)

    def _validate_expiry_time_order(self) -> None:
        if self.result_expires_at is not None and (
            self.completed_at is None or self.result_expires_at < self.completed_at
        ):
            raise ValueError(INVALID_OPERATION_TIME_ORDER_MESSAGE)
        if self.tombstone_expires_at is not None and (
            self.result_expires_at is None or self.tombstone_expires_at < self.result_expires_at
        ):
            raise ValueError(INVALID_OPERATION_TIME_ORDER_MESSAGE)

    def _validate_status_fields(self) -> None:
        if self.status is OperationStatus.QUEUED:
            valid = self.started_at is None and self.completed_at is None and self._has_no_terminal_fields()
        elif self.status is OperationStatus.RUNNING:
            valid = self.started_at is not None and self.completed_at is None and self._has_no_terminal_fields()
        elif self.status is OperationStatus.SUCCEEDED:
            valid = (
                self.started_at is not None
                and self.completed_at is not None
                and self.result is not None
                and self.error is None
                and self._has_expiry_fields()
            )
        elif self.status is OperationStatus.FAILED:
            valid = (
                self.started_at is not None
                and self.completed_at is not None
                and self.result is None
                and self.error is not None
                and self._has_expiry_fields()
            )
        else:
            valid = (
                self.completed_at is not None
                and self.result is None
                and self.error is not None
                and self._has_expiry_fields()
            )
        if not valid:
            raise ValueError(INVALID_OPERATION_STATE_MESSAGE)

    def _has_no_terminal_fields(self) -> bool:
        return (
            self.result is None
            and self.error is None
            and self.result_expires_at is None
            and self.tombstone_expires_at is None
        )

    def _has_expiry_fields(self) -> bool:
        return self.result_expires_at is not None and self.tombstone_expires_at is not None

    def _validate_result(self) -> None:
        if self.result is None:
            return
        allowed_results: dict[OperationKind, tuple[type[object], ...]] = {
            OperationKind.ADD_PLAN: (PlanCreatedResult,),
            OperationKind.ORGANIZE_PLAN: (PlanCreatedResult, RegisteredWithoutPlanResult),
            OperationKind.REFRESH_PLAN: (PlanCreatedResult,),
            OperationKind.CHECK: (CheckCompletedResult,),
            OperationKind.APPLY_PLAN: (RunCompletedResult,),
            OperationKind.UNDO_PLAN: (PlanCreatedResult,),
        }
        association_matches = (
            (not isinstance(self.result, PlanCreatedResult) or self.plan_id == self.result.plan_id)
            and (not isinstance(self.result, RegisteredWithoutPlanResult) or self.library_id == self.result.library_id)
            and (not isinstance(self.result, RunCompletedResult) or self.run_id == self.result.run_id)
        )
        if not isinstance(self.result, allowed_results[self.kind]) or not association_matches:
            raise ValueError(INVALID_OPERATION_RESULT_MESSAGE)

    def _validate_error(self) -> None:
        if self.error is None:
            return
        interrupted_error = self.error.code is OperationErrorCode.OPERATION_INTERRUPTED
        if (self.status is OperationStatus.INTERRUPTED) != interrupted_error:
            raise ValueError(INVALID_OPERATION_ERROR_MESSAGE)


@dataclass(frozen=True, slots=True)
class OperationTombstone:
    """Minimal retained identity after a terminal Operation payload expires."""

    operation_id: OperationId
    idempotency_key: UUID
    kind: OperationKind
    request_fingerprint: str
    tombstone_expires_at: datetime

    def __post_init__(self) -> None:
        """Normalize the retained expiry and preserve replay identity."""
        if not self.request_fingerprint:
            raise ValueError(EMPTY_OPERATION_IDENTITY_MESSAGE)
        object.__setattr__(self, "tombstone_expires_at", as_utc(self.tombstone_expires_at))


type OperationLookup = Operation | OperationTombstone
