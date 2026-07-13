"""
Summary: Projects one Run with backend-authoritative Undo availability.
Why: Keeps History controls from inferring permission from Run status alone.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING

from omym2.domain.models.file_event import FileEventStatus
from omym2.domain.models.plan import PlanStatus
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
    from omym2.domain.models.plan import Plan
    from omym2.domain.models.plan_action import PlanAction
    from omym2.features.history.dto import GetRunHeaderRequest
    from omym2.features.history.ports import HistoryPorts
    from omym2.shared.ids import ActionId, LibraryId, RunId


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
            prior_undo_plans = tuple(uow.plans.list_by_source_run(run.run_id))
            prior_undo_evidence = tuple(
                _PriorUndoEvidence(
                    plan=plan,
                    actions_by_id={action.action_id: action for action in uow.plan_actions.list_by_plan(plan.plan_id)},
                    events=tuple(
                        event
                        for undo_run in uow.runs.list_by_plan(plan.plan_id)
                        for event in uow.file_events.list_by_run(undo_run.run_id)
                    ),
                )
                for plan in prior_undo_plans
            )

        disabled_reasons = _undo_disabled_reasons(
            _SourceUndoEvidence(
                run_status=run.status,
                run_id=run.run_id,
                library_id=run.library_id,
                actions=actions,
                events=events,
            ),
            prior_undo_evidence,
        )
        return RunDetailResult(
            run=run,
            capabilities=RunCapabilitiesResult(
                can_create_undo=not disabled_reasons,
                disabled_reasons=disabled_reasons,
            ),
        )


def _undo_disabled_reasons(
    source: _SourceUndoEvidence,
    prior_undo_evidence: Sequence[_PriorUndoEvidence],
) -> tuple[RunCapabilityReason, ...]:
    """Return stable Undo refusal reasons ordered from lifecycle to evidence."""
    reasons: list[RunCapabilityReason] = []
    source_actions_by_id = {action.action_id: action for action in source.actions}
    reversible_event_ids = {
        event.event_id
        for event in source.events
        if event.status is FileEventStatus.SUCCEEDED
        and event.run_id == source.run_id
        and event.library_id == source.library_id
        and (source_action := source_actions_by_id.get(event.plan_action_id)) is not None
        and source_action.library_id == source.library_id
        and source_action.action_type is ActionType.MOVE
    }
    reversed_event_ids = {
        action.reverses_event_id
        for evidence in prior_undo_evidence
        for event in evidence.events
        if event.status is FileEventStatus.SUCCEEDED
        and event.library_id == source.library_id
        and (action := evidence.actions_by_id.get(event.plan_action_id)) is not None
        and action.library_id == source.library_id
        and action.reverses_event_id is not None
    }
    already_undone_or_in_progress = any(
        evidence.plan.status in {PlanStatus.APPLYING, PlanStatus.APPLIED} for evidence in prior_undo_evidence
    )
    if source.run_status is RunStatus.RUNNING:
        reasons.append(RunCapabilityReason.RUN_NOT_TERMINAL)
    if any(action.action_type is ActionType.REFRESH_METADATA for action in source.actions):
        reasons.append(RunCapabilityReason.UNDO_REFRESH_METADATA_UNSUPPORTED)
    if any(event.status is FileEventStatus.PENDING for event in source.events) or any(
        event.status is FileEventStatus.PENDING for evidence in prior_undo_evidence for event in evidence.events
    ):
        reasons.append(RunCapabilityReason.PENDING_FILE_EVENT_REQUIRES_REVIEW)
    if not already_undone_or_in_progress and not reversible_event_ids.difference(reversed_event_ids):
        reasons.append(RunCapabilityReason.NOTHING_TO_UNDO)
    if already_undone_or_in_progress:
        reasons.append(RunCapabilityReason.ALREADY_UNDONE_OR_IN_PROGRESS)
    return tuple(reasons)


@dataclass(frozen=True, slots=True)
class _SourceUndoEvidence:
    """Persisted action/event evidence for the source Run."""

    run_status: RunStatus
    run_id: RunId
    library_id: LibraryId
    actions: tuple[PlanAction, ...]
    events: tuple[FileEvent, ...]


@dataclass(frozen=True, slots=True)
class _PriorUndoEvidence:
    """Persisted Plan/action/event evidence for one prior Undo attempt."""

    plan: Plan
    actions_by_id: dict[ActionId, PlanAction]
    events: tuple[FileEvent, ...]
