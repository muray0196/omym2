"""
Summary: Tests read-only Run capability projection.
Why: Keeps Undo visibility derived from durable evidence rather than status strings alone.
"""

from __future__ import annotations

from datetime import UTC, datetime
from uuid import UUID

from omym2.domain.models.file_event import FileEvent, FileEventStatus, FileEventType
from omym2.domain.models.plan import Plan, PlanStatus, PlanType
from omym2.domain.models.plan_action import ActionStatus, ActionType, PlanAction
from omym2.domain.models.run import Run, RunStatus
from omym2.features.history.dto import GetRunHeaderRequest, RunCapabilityReason
from omym2.features.history.ports import HistoryPorts
from omym2.features.history.usecases.get_run_detail import GetRunDetailUseCase
from omym2.shared.ids import ActionId, EventId, LibraryId, PlanId, RunId
from tests.fakes.in_memory_repositories import InMemoryUnitOfWork

NOW = datetime(2026, 7, 13, tzinfo=UTC)
LIBRARY_ID = LibraryId(UUID("018f6a4f-3c2d-7b8a-9abc-def012345611"))
PLAN_ID = PlanId(UUID("018f6a4f-3c2d-7b8a-9abc-def012345612"))
ACTION_ID = ActionId(UUID("018f6a4f-3c2d-7b8a-9abc-def012345613"))
SECOND_ACTION_ID = ActionId(UUID("018f6a4f-3c2d-7b8a-9abc-def012345616"))
RUN_ID = RunId(UUID("018f6a4f-3c2d-7b8a-9abc-def012345614"))
EVENT_ID = EventId(UUID("018f6a4f-3c2d-7b8a-9abc-def012345615"))


def test_run_detail_allows_undo_only_with_terminal_succeeded_file_event() -> None:
    """A terminal Run with confirmed mutation evidence is Undo-capable."""
    uow = _history_uow(ActionType.MOVE, FileEventStatus.SUCCEEDED)

    result = GetRunDetailUseCase(HistoryPorts(uow)).execute(GetRunHeaderRequest(run_id=RUN_ID))

    assert result.capabilities.can_create_undo is True
    assert result.capabilities.disabled_reasons == ()
    assert uow.commit_count == 0


def test_run_detail_reports_refresh_and_pending_evidence_reasons() -> None:
    """Refresh metadata and an unknown mutation outcome independently disable Undo."""
    uow = _history_uow(ActionType.REFRESH_METADATA, FileEventStatus.PENDING)

    result = GetRunDetailUseCase(HistoryPorts(uow)).execute(GetRunHeaderRequest(run_id=RUN_ID))

    assert result.capabilities.can_create_undo is False
    assert result.capabilities.disabled_reasons == (
        RunCapabilityReason.UNDO_REFRESH_METADATA_UNSUPPORTED,
        RunCapabilityReason.PENDING_FILE_EVENT_REQUIRES_REVIEW,
        RunCapabilityReason.NOTHING_TO_UNDO,
    )


def _history_uow(action_type: ActionType, event_status: FileEventStatus) -> InMemoryUnitOfWork:
    uow = InMemoryUnitOfWork()
    uow.plans.save(
        Plan(
            plan_id=PLAN_ID,
            library_id=LIBRARY_ID,
            plan_type=PlanType.REFRESH,
            status=PlanStatus.APPLIED,
            created_at=NOW,
            config_hash="config",
            library_root_at_plan="/music/library",
            summary={},
            actions=(),
        )
    )
    uow.plan_actions.save(
        PlanAction(
            action_id=ACTION_ID,
            plan_id=PLAN_ID,
            library_id=LIBRARY_ID,
            track_id=None,
            action_type=action_type,
            source_path="Artist/Track.flac",
            target_path="Artist/Track.flac",
            content_hash_at_plan="content",
            metadata_hash_at_plan="metadata",
            status=ActionStatus.APPLIED,
            reason=None,
            sort_order=1,
        )
    )
    uow.runs.save(
        Run(
            run_id=RUN_ID,
            plan_id=PLAN_ID,
            library_id=LIBRARY_ID,
            status=RunStatus.SUCCEEDED,
            started_at=NOW,
            completed_at=NOW,
        )
    )
    event_action_id = ACTION_ID
    if action_type is ActionType.REFRESH_METADATA:
        event_action_id = SECOND_ACTION_ID
        uow.plan_actions.save(
            PlanAction(
                action_id=SECOND_ACTION_ID,
                plan_id=PLAN_ID,
                library_id=LIBRARY_ID,
                track_id=None,
                action_type=ActionType.MOVE,
                source_path="Source/Track.flac",
                target_path="Artist/Track.flac",
                content_hash_at_plan="content",
                metadata_hash_at_plan="metadata",
                status=ActionStatus.FAILED,
                reason=None,
                sort_order=2,
            )
        )
    uow.file_events.save(
        FileEvent(
            event_id=EVENT_ID,
            library_id=LIBRARY_ID,
            run_id=RUN_ID,
            plan_action_id=event_action_id,
            event_type=FileEventType.MOVE_FILE,
            source_path="Source/Track.flac",
            target_path="Artist/Track.flac",
            status=event_status,
            started_at=NOW,
            completed_at=None if event_status is FileEventStatus.PENDING else NOW,
            error_code=None,
            error_message=None,
            sequence_no=1,
        )
    )
    return uow
