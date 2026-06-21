"""
Summary: Defines apply execution attempts.
Why: Records Plan application outcome separately from planned work.
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum
from typing import TYPE_CHECKING

from omym2.shared.time import as_utc

if TYPE_CHECKING:
    from datetime import datetime

    from omym2.shared.ids import LibraryId, PlanId, RunId


class RunStatus(StrEnum):
    """Supported Run statuses."""

    RUNNING = "running"
    SUCCEEDED = "succeeded"
    PARTIAL_FAILED = "partial_failed"
    FAILED = "failed"


@dataclass(frozen=True, slots=True)
class Run:
    """Execution attempt for applying a Plan."""

    run_id: RunId
    plan_id: PlanId
    library_id: LibraryId
    status: RunStatus
    started_at: datetime
    completed_at: datetime | None = None
    error_summary: str | None = None

    def __post_init__(self) -> None:
        """Normalize timestamps used by history and diagnostics."""
        object.__setattr__(self, "started_at", as_utc(self.started_at))
        if self.completed_at is not None:
            object.__setattr__(self, "completed_at", as_utc(self.completed_at))

    def mark_succeeded(self, completed_at: datetime) -> Run:
        """Return this Run as succeeded."""
        return self._with_completion(RunStatus.SUCCEEDED, completed_at, None)

    def mark_partial_failed(self, completed_at: datetime, error_summary: str) -> Run:
        """Return this Run as partially failed."""
        return self._with_completion(RunStatus.PARTIAL_FAILED, completed_at, error_summary)

    def mark_failed(self, completed_at: datetime, error_summary: str) -> Run:
        """Return this Run as failed."""
        return self._with_completion(RunStatus.FAILED, completed_at, error_summary)

    def _with_completion(self, status: RunStatus, completed_at: datetime, error_summary: str | None) -> Run:
        return Run(
            run_id=self.run_id,
            plan_id=self.plan_id,
            library_id=self.library_id,
            status=status,
            started_at=self.started_at,
            completed_at=completed_at,
            error_summary=error_summary,
        )
