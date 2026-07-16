"""
Summary: Tests durable failed-companion recovery classification.
Why: Prevents retries from weakening provenance or stranding retained sources.
"""

from __future__ import annotations

from dataclasses import dataclass, replace
from datetime import UTC, datetime, timedelta

import pytest

from omym2.domain.models.companion_asset import (
    CompanionAsset,
    CompanionAssetKind,
    CompanionAssetStatus,
)
from omym2.domain.models.file_event import FileEvent, FileEventStatus, FileEventType
from omym2.domain.models.plan import Plan, PlanStatus, PlanType
from omym2.domain.models.plan_action import (
    ActionStatus,
    ActionType,
    PlanAction,
    PlanActionDependency,
    PlanActionReason,
)
from omym2.domain.models.run import Run, RunStatus
from omym2.domain.models.track import Track, TrackStatus
from omym2.domain.models.track_metadata import TrackMetadata
from omym2.domain.services.companion_recovery import (
    CompanionRecoveryEvidence,
    find_recoverable_companions,
)
from omym2.shared.ids import (
    ActionId,
    CompanionAssetId,
    LibraryId,
    PlanId,
    RunId,
    TrackId,
    new_action_id,
    new_companion_asset_id,
    new_event_id,
    new_library_id,
    new_plan_id,
    new_run_id,
    new_track_id,
)

BASE_TIME = datetime(2026, 7, 16, tzinfo=UTC)
CONTENT_HASH = "companion-content"
INCOMING_ROOT = "/incoming"
LIBRARY_ROOT = "/library"
ORIGINAL_AUDIO_TARGET = "Artist/Album/Song.flac"
ORIGINAL_COMPANION_TARGET = "Artist/Album/Song.lrc"
RELOCATED_AUDIO_PATH = "Renamed/Album/Song.flac"
RELOCATED_COMPANION_TARGET = "Renamed/Album/Song.lrc"
SOURCE_PATH = f"{INCOMING_ROOT}/Album/Song.lrc"


def test_recovery_targets_active_track_location_after_later_relocation() -> None:
    """Original success proves Track identity while its current path selects the retry target."""
    fixture = _base_add_failure(track_path=RELOCATED_AUDIO_PATH)

    recoveries = find_recoverable_companions(fixture.evidence)

    assert len(recoveries) == 1
    recovery = recoveries[0]
    assert recovery.source_root == INCOMING_ROOT
    assert recovery.source_path == SOURCE_PATH
    assert recovery.target_path == RELOCATED_COMPANION_TARGET
    assert recovery.owner_track_id == fixture.track_id
    assert recovery.companion_asset_id == fixture.companion_asset_id


def test_refresh_failure_targets_relocated_active_track() -> None:
    """A Library-relative Refresh failure remains recoverable through Organize after relocation."""
    fixture = _base_refresh_failure(track_path=RELOCATED_AUDIO_PATH)

    recoveries = find_recoverable_companions(fixture.evidence)

    assert len(recoveries) == 1
    recovery = recoveries[0]
    assert recovery.source_plan_type is PlanType.REFRESH
    assert recovery.source_root is None
    assert recovery.source_path == "Old/Album/Song.lrc"
    assert recovery.target_path == RELOCATED_COMPANION_TARGET


def test_refresh_failure_allows_completed_prior_asset_history() -> None:
    """Stable asset identity may have succeeded history completed before the failed anchor Plan."""
    fixture = _base_refresh_failure(track_path=RELOCATED_AUDIO_PATH)
    prior_plan_id = new_plan_id()
    prior_action_id = new_action_id()
    prior_run_id = new_run_id()
    prior_plan = _plan(
        prior_plan_id,
        fixture.library_id,
        PlanType.ORGANIZE,
        PlanStatus.APPLIED,
        source_root=None,
        created_at=BASE_TIME - timedelta(minutes=10),
    )
    prior_action = PlanAction(
        action_id=prior_action_id,
        plan_id=prior_plan_id,
        library_id=fixture.library_id,
        track_id=fixture.track_id,
        action_type=ActionType.MOVE_LYRICS,
        source_path="Older/Album/Song.lrc",
        target_path="Old/Album/Song.lrc",
        content_hash_at_plan=CONTENT_HASH,
        metadata_hash_at_plan=None,
        status=ActionStatus.APPLIED,
        reason=None,
        sort_order=1,
        companion_asset_id=fixture.companion_asset_id,
        owner_action_id=None,
    )
    prior_run = Run(
        run_id=prior_run_id,
        plan_id=prior_plan_id,
        library_id=fixture.library_id,
        status=RunStatus.SUCCEEDED,
        started_at=BASE_TIME - timedelta(minutes=9),
        completed_at=BASE_TIME - timedelta(minutes=8),
    )
    prior_event = _event(
        prior_run_id,
        fixture.library_id,
        prior_action_id,
        FileEventType.MOVE_LYRICS_FILE,
        "Older/Album/Song.lrc",
        "Old/Album/Song.lrc",
        FileEventStatus.SUCCEEDED,
        companion_asset_id=fixture.companion_asset_id,
        started_at=BASE_TIME - timedelta(minutes=9),
    )
    evidence = replace(
        fixture.evidence,
        plans=(prior_plan, *fixture.evidence.plans),
        actions=(prior_action, *fixture.evidence.actions),
        runs=(prior_run, *fixture.evidence.runs),
        events=(prior_event, *fixture.evidence.events),
    )

    recoveries = find_recoverable_companions(evidence)

    assert len(recoveries) == 1
    assert recoveries[0].source_plan_type is PlanType.REFRESH


def test_equivalent_failed_recovery_retry_preserves_original_anchor() -> None:
    """A later failed companion-only retry remains recoverable through the original owner evidence."""
    fixture = _base_add_failure(track_path=RELOCATED_AUDIO_PATH)
    evidence = _with_retry(
        fixture,
        plan_status=PlanStatus.FAILED,
        action_status=ActionStatus.FAILED,
        with_failed_event=True,
    )

    recoveries = find_recoverable_companions(evidence)

    assert len(recoveries) == 1
    assert recoveries[0].source_plan_id == fixture.anchor_plan_id
    assert recoveries[0].target_path == RELOCATED_COMPANION_TARGET


@pytest.mark.parametrize("plan_status", [PlanStatus.READY, PlanStatus.APPLYING])
def test_active_retry_suppresses_duplicate_replanning(plan_status: PlanStatus) -> None:
    """An active Plan that already owns the stable asset ID suppresses another retry."""
    fixture = _base_add_failure()
    evidence = _with_retry(
        fixture,
        plan_status=plan_status,
        action_status=ActionStatus.PLANNED,
        with_failed_event=False,
    )

    assert find_recoverable_companions(evidence) == ()


@pytest.mark.parametrize("plan_status", [PlanStatus.CANCELLED, PlanStatus.EXPIRED, PlanStatus.APPLIED])
def test_nonexecuted_terminal_retry_does_not_consume_anchor(plan_status: PlanStatus) -> None:
    """Cancelled, expired, or terminal blocked attempts leave the failed anchor reusable."""
    fixture = _base_add_failure()
    evidence = _with_retry(
        fixture,
        plan_status=plan_status,
        action_status=ActionStatus.BLOCKED,
        with_failed_event=False,
    )

    assert len(find_recoverable_companions(evidence)) == 1


def test_failed_retry_without_definitive_event_fails_closed() -> None:
    """A FAILED retry without its durable failed event requires manual review."""
    fixture = _base_add_failure()
    evidence = _with_retry(
        fixture,
        plan_status=PlanStatus.FAILED,
        action_status=ActionStatus.FAILED,
        with_failed_event=False,
    )

    assert find_recoverable_companions(evidence) == ()


@dataclass(frozen=True, slots=True)
class _FailureFixture:
    """IDs and evidence shared by retry-chain tests."""

    evidence: CompanionRecoveryEvidence
    anchor_plan_id: PlanId
    library_id: LibraryId
    track_id: TrackId
    companion_asset_id: CompanionAssetId


def _base_add_failure(*, track_path: str = ORIGINAL_AUDIO_TARGET) -> _FailureFixture:
    library_id = new_library_id()
    track_id = new_track_id()
    plan_id = new_plan_id()
    run_id = new_run_id()
    audio_action_id = new_action_id()
    companion_action_id = new_action_id()
    companion_asset_id = new_companion_asset_id()
    plan = _plan(
        plan_id,
        library_id,
        PlanType.ADD,
        PlanStatus.PARTIAL_FAILED,
        source_root=INCOMING_ROOT,
    )
    audio_action = _audio_action(audio_action_id, plan_id, library_id, track_id)
    companion_action = _companion_action(
        companion_action_id,
        plan_id,
        library_id,
        companion_asset_id,
        status=ActionStatus.FAILED,
        track_id=None,
        owner_action_id=audio_action_id,
        target_path=ORIGINAL_COMPANION_TARGET,
    )
    run = _run(run_id, plan_id, library_id, RunStatus.PARTIAL_FAILED)
    evidence = CompanionRecoveryEvidence(
        plans=(plan,),
        actions=(audio_action, companion_action),
        dependencies=(
            PlanActionDependency(
                plan_id=plan_id,
                action_id=companion_action_id,
                depends_on_action_id=audio_action_id,
            ),
        ),
        runs=(run,),
        events=(
            _event(
                run_id,
                library_id,
                audio_action_id,
                FileEventType.MOVE_FILE,
                f"{INCOMING_ROOT}/Album/Song.flac",
                ORIGINAL_AUDIO_TARGET,
                FileEventStatus.SUCCEEDED,
            ),
            _event(
                run_id,
                library_id,
                companion_action_id,
                FileEventType.MOVE_LYRICS_FILE,
                SOURCE_PATH,
                ORIGINAL_COMPANION_TARGET,
                FileEventStatus.FAILED,
                companion_asset_id=companion_asset_id,
            ),
        ),
        tracks=(_track(track_id, library_id, track_path),),
        companion_assets=(),
    )
    return _FailureFixture(
        evidence,
        anchor_plan_id=plan_id,
        library_id=library_id,
        track_id=track_id,
        companion_asset_id=companion_asset_id,
    )


def _base_refresh_failure(*, track_path: str) -> _FailureFixture:
    fixture = _base_add_failure(track_path=track_path)
    plan = replace(
        fixture.evidence.plans[0],
        plan_type=PlanType.REFRESH,
        source_root_at_plan=None,
    )
    audio_action = replace(
        fixture.evidence.actions[0],
        source_path="Old/Album/Song.flac",
    )
    companion_action = replace(
        fixture.evidence.actions[1],
        source_path="Old/Album/Song.lrc",
    )
    audio_event = replace(
        fixture.evidence.events[0],
        source_path="Old/Album/Song.flac",
    )
    companion_event = replace(
        fixture.evidence.events[1],
        source_path="Old/Album/Song.lrc",
    )
    asset = CompanionAsset(
        companion_asset_id=fixture.companion_asset_id,
        library_id=fixture.library_id,
        kind=CompanionAssetKind.LYRICS,
        owner_track_id=fixture.track_id,
        current_path="Old/Album/Song.lrc",
        canonical_path=ORIGINAL_COMPANION_TARGET,
        content_hash=CONTENT_HASH,
        size=None,
        mtime=None,
        status=CompanionAssetStatus.ACTIVE,
        first_seen_at=BASE_TIME,
        last_seen_at=BASE_TIME,
        updated_at=BASE_TIME,
    )
    return replace(
        fixture,
        evidence=replace(
            fixture.evidence,
            plans=(plan,),
            actions=(audio_action, companion_action),
            events=(audio_event, companion_event),
            companion_assets=(asset,),
        ),
    )


def _with_retry(
    fixture: _FailureFixture,
    *,
    plan_status: PlanStatus,
    action_status: ActionStatus,
    with_failed_event: bool,
) -> CompanionRecoveryEvidence:
    plan_id = new_plan_id()
    run_id = new_run_id()
    action_id = new_action_id()
    retry_plan = _plan(
        plan_id,
        fixture.library_id,
        PlanType.ADD,
        plan_status,
        source_root=INCOMING_ROOT,
        created_at=BASE_TIME + timedelta(minutes=10),
    )
    retry_action = _companion_action(
        action_id,
        plan_id,
        fixture.library_id,
        fixture.companion_asset_id,
        status=action_status,
        track_id=fixture.track_id,
        owner_action_id=None,
        target_path=RELOCATED_COMPANION_TARGET,
    )
    retry_run = replace(
        _run(run_id, plan_id, fixture.library_id, RunStatus.FAILED),
        started_at=BASE_TIME + timedelta(minutes=11),
        completed_at=BASE_TIME + timedelta(minutes=12),
    )
    retry_events = (
        (
            _event(
                run_id,
                fixture.library_id,
                action_id,
                FileEventType.MOVE_LYRICS_FILE,
                SOURCE_PATH,
                RELOCATED_COMPANION_TARGET,
                FileEventStatus.FAILED,
                companion_asset_id=fixture.companion_asset_id,
                started_at=BASE_TIME + timedelta(minutes=11),
            ),
        )
        if with_failed_event
        else ()
    )
    return replace(
        fixture.evidence,
        plans=(*fixture.evidence.plans, retry_plan),
        actions=(*fixture.evidence.actions, retry_action),
        runs=(*fixture.evidence.runs, retry_run),
        events=(*fixture.evidence.events, *retry_events),
    )


def _plan(  # noqa: PLR0913  # Test history fields remain explicit.
    plan_id: PlanId,
    library_id: LibraryId,
    plan_type: PlanType,
    status: PlanStatus,
    *,
    source_root: str | None,
    created_at: datetime = BASE_TIME,
) -> Plan:
    return Plan(
        plan_id=plan_id,
        library_id=library_id,
        plan_type=plan_type,
        status=status,
        created_at=created_at,
        config_hash="config",
        library_root_at_plan=LIBRARY_ROOT,
        source_root_at_plan=source_root,
    )


def _audio_action(
    action_id: ActionId,
    plan_id: PlanId,
    library_id: LibraryId,
    track_id: TrackId,
) -> PlanAction:
    return PlanAction(
        action_id=action_id,
        plan_id=plan_id,
        library_id=library_id,
        track_id=track_id,
        action_type=ActionType.MOVE,
        source_path=f"{INCOMING_ROOT}/Album/Song.flac",
        target_path=ORIGINAL_AUDIO_TARGET,
        content_hash_at_plan="audio-content",
        metadata_hash_at_plan="audio-metadata",
        status=ActionStatus.APPLIED,
        reason=None,
        sort_order=1,
    )


def _companion_action(  # noqa: PLR0913  # Test action evidence remains explicit.
    action_id: ActionId,
    plan_id: PlanId,
    library_id: LibraryId,
    companion_asset_id: CompanionAssetId,
    *,
    status: ActionStatus,
    track_id: TrackId | None,
    owner_action_id: ActionId | None,
    target_path: str,
) -> PlanAction:
    return PlanAction(
        action_id=action_id,
        plan_id=plan_id,
        library_id=library_id,
        track_id=track_id,
        action_type=ActionType.MOVE_LYRICS,
        source_path=SOURCE_PATH,
        target_path=target_path,
        content_hash_at_plan=CONTENT_HASH,
        metadata_hash_at_plan=None,
        status=status,
        reason=(PlanActionReason.TARGET_EXISTS if status is not ActionStatus.PLANNED else None),
        sort_order=2,
        companion_asset_id=companion_asset_id,
        owner_action_id=owner_action_id,
    )


def _run(
    run_id: RunId,
    plan_id: PlanId,
    library_id: LibraryId,
    status: RunStatus,
) -> Run:
    return Run(
        run_id=run_id,
        plan_id=plan_id,
        library_id=library_id,
        status=status,
        started_at=BASE_TIME + timedelta(minutes=1),
        completed_at=BASE_TIME + timedelta(minutes=2),
        error_summary="failed",
    )


def _event(  # noqa: PLR0913  # Test event evidence remains explicit.
    run_id: RunId,
    library_id: LibraryId,
    action_id: ActionId,
    event_type: FileEventType,
    source_path: str,
    target_path: str,
    status: FileEventStatus,
    *,
    companion_asset_id: CompanionAssetId | None = None,
    started_at: datetime | None = None,
) -> FileEvent:
    effective_started_at = BASE_TIME + timedelta(minutes=1) if started_at is None else started_at
    return FileEvent(
        event_id=new_event_id(),
        library_id=library_id,
        run_id=run_id,
        plan_action_id=action_id,
        event_type=event_type,
        source_path=source_path,
        target_path=target_path,
        status=status,
        started_at=effective_started_at,
        completed_at=effective_started_at + timedelta(minutes=1),
        error_code=None if status is FileEventStatus.SUCCEEDED else "target_exists",
        error_message=None if status is FileEventStatus.SUCCEEDED else "failed",
        sequence_no=1,
        companion_asset_id=companion_asset_id,
    )


def _track(track_id: TrackId, library_id: LibraryId, current_path: str) -> Track:
    return Track(
        track_id=track_id,
        library_id=library_id,
        current_path=current_path,
        canonical_path=current_path,
        content_hash="audio-content",
        metadata_hash="audio-metadata",
        size=None,
        mtime=None,
        metadata=TrackMetadata(title="Song", artist="Artist", album="Album"),
        status=TrackStatus.ACTIVE,
        first_seen_at=BASE_TIME,
        last_seen_at=BASE_TIME,
        updated_at=BASE_TIME,
    )
