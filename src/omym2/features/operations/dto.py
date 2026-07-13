"""
Summary: Defines durable Operation feature requests and outcomes.
Why: Keeps platform orchestration independent from SQLite and HTTP representations.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from uuid import UUID

    from omym2.domain.models.operation import OperationError, OperationKind, OperationLookup, OperationResult
    from omym2.shared.ids import LibraryId, OperationId, PlanId, RunId


@dataclass(frozen=True, slots=True)
class ReserveOperationRequest:
    """Validated canonical request identity awaiting durable reservation."""

    kind: OperationKind
    idempotency_key: UUID
    request_fingerprint: str
    library_id: LibraryId | None = None
    plan_id: PlanId | None = None
    run_id: RunId | None = None


@dataclass(frozen=True, slots=True)
class ReserveOperationResult:
    """New reservation or exact retained replay classification."""

    lookup: OperationLookup
    is_new: bool


@dataclass(frozen=True, slots=True)
class FinishOperationRequest:
    """Exactly one typed result or redacted error for running work."""

    operation_id: OperationId
    result: OperationResult | None = None
    error: OperationError | None = None


class OperationNotFoundError(LookupError):
    """Raised when a durable Operation identity was never retained."""


class OperationExpiredError(LookupError):
    """Raised when only an idempotency tombstone remains."""


class OperationLifecycleError(RuntimeError):
    """Raised when orchestration observes an impossible lifecycle transition."""
