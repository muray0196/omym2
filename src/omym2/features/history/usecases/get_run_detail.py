"""
Summary: Projects one Run with backend-authoritative Undo availability.
Why: Keeps History controls from inferring permission from Run status alone.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING

from omym2.domain.models.file_event import FileEventStatus
from omym2.domain.models.plan_action import ActionType
from omym2.domain.models.run import RunStatus
from omym2.features.history.dto import (
    RunCapabilitiesResult,
    RunCapabilityReason,
    RunDetailResult,
)
from omym2.features.history.usecases.get_run_header import RUN_NOT_FOUND_MESSAGE, RunNotFoundError

if TYPE_CHECKING:
    from collections.abc import Sequence

    from omym2.domain.models.file_event import FileEvent
    from omym2.domain.models.plan_action import PlanAction
    from omym2.features.history.dto import GetRunHeaderRequest
    from omym2.features.history.ports import HistoryPorts


@dataclass(frozen=True, slots=True)
class GetRunDetailUseCase:
    """Load one Run and calculate its current Undo capability snapshot."""

    ports: HistoryPorts

    def execute(self, request: GetRunHeaderRequest) -> RunDetailResult:
        """Return one Run detail without mutating history or reading the filesystem."""
        with self.ports.uow as uow:
            run = uow.runs.get(request.run_id)
            if run is None:
                raise RunNotFoundError(RUN_NOT_FOUND_MESSAGE)
            actions = tuple(uow.plan_actions.list_by_plan(run.plan_id))
            events = tuple(uow.file_events.list_by_run(run.run_id))

        disabled_reasons = _undo_disabled_reasons(run.status, actions, events)
        return RunDetailResult(
            run=run,
            capabilities=RunCapabilitiesResult(
                can_create_undo=not disabled_reasons,
                disabled_reasons=disabled_reasons,
            ),
        )


def _undo_disabled_reasons(
    run_status: RunStatus,
    actions: Sequence[PlanAction],
    events: Sequence[FileEvent],
) -> tuple[RunCapabilityReason, ...]:
    """Return stable Undo refusal reasons ordered from lifecycle to evidence."""
    reasons: list[RunCapabilityReason] = []
    if run_status is RunStatus.RUNNING:
        reasons.append(RunCapabilityReason.RUN_NOT_TERMINAL)
    if any(action.action_type is ActionType.REFRESH_METADATA for action in actions):
        reasons.append(RunCapabilityReason.UNDO_REFRESH_METADATA_UNSUPPORTED)
    if any(event.status is FileEventStatus.PENDING for event in events):
        reasons.append(RunCapabilityReason.PENDING_FILE_EVENT_REQUIRES_REVIEW)
    if not any(event.status is FileEventStatus.SUCCEEDED for event in events):
        reasons.append(RunCapabilityReason.NOTHING_TO_UNDO)
    return tuple(reasons)
