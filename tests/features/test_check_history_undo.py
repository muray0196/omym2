"""
Summary: Tests check, history, and undo behavior.
Why: Protects diagnostics and recovery without direct file mutation.
"""

from __future__ import annotations

from collections import deque
from dataclasses import replace
from datetime import UTC, datetime, timedelta
from typing import TYPE_CHECKING
from uuid import UUID

import pytest

from omym2.adapters.config.default_config import default_app_config
from omym2.domain.models.check_issue import CheckIssue, CheckIssueGrouping, CheckIssueType
from omym2.domain.models.file_event import FileEvent, FileEventStatus, FileEventType
from omym2.domain.models.file_scan_entry import FileScanEntry
from omym2.domain.models.file_snapshot import FileSnapshot
from omym2.domain.models.library import Library, LibraryStatus
from omym2.domain.models.plan import Plan, PlanStatus, PlanType
from omym2.domain.models.plan_action import ActionStatus, ActionType, PlanAction, PlanActionReason
from omym2.domain.models.run import Run, RunStatus
from omym2.domain.models.track import Track, TrackStatus
from omym2.domain.models.track_metadata import TrackMetadata
from omym2.domain.services.config_fingerprint import calculate_config_fingerprint, calculate_path_policy_fingerprint
from omym2.features.apply.dto import ApplyOptions, ApplyPlanRequest
from omym2.features.apply.ports import ApplyPlanPorts
from omym2.features.apply.usecases.apply_plan import ApplyPlanUseCase
from omym2.features.check.dto import (
    CheckIssueFacetsRequest,
    CheckLibraryRequest,
    GroupCheckIssuesRequest,
    ListCheckIssuesRequest,
)
from omym2.features.check.ports import CheckLibraryPorts, CheckQueryPorts
from omym2.features.check.usecases.check_library import CheckLibraryUseCase
from omym2.features.check.usecases.get_check_issue_facets import GetCheckIssueFacetsUseCase
from omym2.features.check.usecases.group_check_issues import GroupCheckIssuesUseCase
from omym2.features.check.usecases.list_check_issues import ListCheckIssuesUseCase
from omym2.features.history.dto import GetRunHeaderRequest, ListRunEventsRequest, ListRunsRequest
from omym2.features.history.ports import HistoryPorts
from omym2.features.history.usecases.get_run_header import GetRunHeaderUseCase
from omym2.features.history.usecases.list_run_events import ListRunEventsUseCase
from omym2.features.history.usecases.list_runs import ListRunsUseCase
from omym2.features.undo.dto import CreateUndoPlanRequest
from omym2.features.undo.ports import CreateUndoPlanPorts
from omym2.features.undo.usecases.create_undo_plan import (
    RUN_NOT_TERMINAL_MESSAGE,
    RUN_REFRESH_METADATA_UNSUPPORTED_MESSAGE,
    CreateUndoPlanUseCase,
    UndoPlanError,
)
from omym2.shared.ids import ActionId, CheckRunId, EventId, LibraryId, PlanId, RunId, TrackId
from tests.fakes.in_memory_repositories import InMemoryUnitOfWork
from tests.fakes.runtime import FixedClock, SequenceIdGenerator

if TYPE_CHECKING:
    from collections.abc import Sequence

    from omym2.domain.models.app_config import AppConfig
    from omym2.features.common_ports import FileSnapshotCaptureRequest, FileSystemPath

ACTION_ID = ActionId(UUID("018f6a4f-3c2d-7b8a-9abc-def01234567b"))
BASE_TIME = datetime(2026, 1, 1, tzinfo=UTC)
CHECK_RUN_ID = CheckRunId(UUID("018f6a4f-3c2d-7b8a-9abc-def01234568b"))
SECOND_CHECK_RUN_ID = CheckRunId(UUID("018f6a4f-3c2d-7b8a-9abc-def01234568c"))
CHANGED_CONTENT_HASH = "changed-content"
CHANGED_METADATA_HASH = "changed-metadata"
CONFIG_HASH = calculate_config_fingerprint(default_app_config())
CONTENT_HASH = "content"
DUPLICATE_ACTION_ID = ActionId(UUID("018f6a4f-3c2d-7b8a-9abc-def01234567c"))
EVENT_ID = EventId(UUID("018f6a4f-3c2d-7b8a-9abc-def01234567e"))
EXTERNAL_SOURCE_PATH = "/incoming/Imported.flac"
FILE_EXTENSION = ".flac"
FILE_SIZE = 5
LIBRARY_ID = LibraryId(UUID("018f6a4f-3c2d-7b8a-9abc-def012345678"))
LIBRARY_ROOT = "/music/library"
SECOND_LIBRARY_ID = LibraryId(UUID("018f6a4f-3c2d-7b8a-9abc-def01234568d"))
SECOND_LIBRARY_ROOT = "/music/second-library"
METADATA_HASH = "metadata"
PLAN_ID = PlanId(UUID("018f6a4f-3c2d-7b8a-9abc-def01234567a"))
RELOCATED_PATH = "Relocated/Imported.flac"
RESTORE_PATH = "Restore/Imported.flac"
RUN_ID = RunId(UUID("018f6a4f-3c2d-7b8a-9abc-def01234567d"))
SECOND_ACTION_ID = ActionId(UUID("018f6a4f-3c2d-7b8a-9abc-def012345680"))
SECOND_EVENT_ID = EventId(UUID("018f6a4f-3c2d-7b8a-9abc-def012345681"))
SECOND_PLAN_ID = PlanId(UUID("018f6a4f-3c2d-7b8a-9abc-def012345682"))
SECOND_RUN_ID = RunId(UUID("018f6a4f-3c2d-7b8a-9abc-def012345683"))
SECOND_SOURCE_PATH = "Original/Title2.flac"
SECOND_TRACK_ID = TrackId(UUID("018f6a4f-3c2d-7b8a-9abc-def012345684"))
SOURCE_PATH = "Original/Title.flac"
TARGET_PATH = "Artist/2026_Album/1-02_Title.flac"
THIRD_EVENT_ID = EventId(UUID("018f6a4f-3c2d-7b8a-9abc-def01234568a"))
TRACK_ID = TrackId(UUID("018f6a4f-3c2d-7b8a-9abc-def012345679"))
UNDO_PLAN_ID = PlanId(UUID("018f6a4f-3c2d-7b8a-9abc-def012345685"))
UNDO_ACTION_ID = ActionId(UUID("018f6a4f-3c2d-7b8a-9abc-def012345686"))
UNDO_SECOND_ACTION_ID = ActionId(UUID("018f6a4f-3c2d-7b8a-9abc-def012345687"))
UNDO_RUN_ID = RunId(UUID("018f6a4f-3c2d-7b8a-9abc-def012345688"))
UNDO_EVENT_ID = EventId(UUID("018f6a4f-3c2d-7b8a-9abc-def012345689"))
UNMANAGED_PATH = "Loose/Copy.flac"

METADATA = TrackMetadata(title="Title", artist="Artist", album="Album", year=2026, track_number=2, disc_number=1)


def test_check_reports_db_filesystem_plan_and_pending_event_issues() -> None:
    """check reports drift and commits its own findings without mutating other repositories."""
    uow = InMemoryUnitOfWork()
    uow.libraries.save(_library())
    uow.tracks.save(_track(canonical_path=RESTORE_PATH))
    uow.plans.save(_plan())
    uow.plan_actions.save(_source_action())
    uow.runs.save(_run())
    uow.file_events.save(_pending_event())
    scanner = StaticScanner(
        (
            _scan_entry(_absolute(TARGET_PATH)),
            _scan_entry(_absolute(UNMANAGED_PATH)),
        )
    )
    snapshots = MappingSnapshotReader(
        {
            _absolute(TARGET_PATH): _snapshot(_absolute(TARGET_PATH), CHANGED_CONTENT_HASH, CHANGED_METADATA_HASH),
        }
    )
    content_hasher = MappingContentHasher({_absolute(UNMANAGED_PATH): CONTENT_HASH})

    result = CheckLibraryUseCase(_check_ports(uow, scanner, snapshots, content_hasher=content_hasher)).execute(
        CheckLibraryRequest(trust_stat=False)
    )

    assert {
        CheckIssueType.CONTENT_HASH_CHANGED,
        CheckIssueType.METADATA_HASH_CHANGED,
        CheckIssueType.CURRENT_PATH_DIFFERS_FROM_CANONICAL_PATH,
        CheckIssueType.UNMANAGED_FILE_EXISTS,
        CheckIssueType.DUPLICATE_CANDIDATE,
        CheckIssueType.PLAN_SOURCE_CHANGED,
        CheckIssueType.PENDING_FILE_EVENT_EXISTS,
    } <= {issue.issue_type for issue in result.issues}
    assert result.checked_at == BASE_TIME
    assert uow.commit_count == 1
    assert uow.tracks.get(TRACK_ID) is not None
    assert uow.libraries.get(LIBRARY_ID) is not None
    assert _absolute(UNMANAGED_PATH) not in snapshots.captured_paths
    assert content_hasher.calculated_paths == [_absolute(UNMANAGED_PATH)]


def test_check_keeps_unmanaged_issue_when_file_vanishes_before_hashing() -> None:
    """A vanished unmanaged candidate is still reported unmanaged without a duplicate issue."""
    uow = InMemoryUnitOfWork()
    uow.libraries.save(_library())
    unmanaged_path = _absolute(UNMANAGED_PATH)
    content_hasher = MappingContentHasher({}, missing_paths={unmanaged_path})

    result = CheckLibraryUseCase(
        _check_ports(
            uow,
            StaticScanner((_scan_entry(unmanaged_path),)),
            MappingSnapshotReader({}),
            content_hasher=content_hasher,
        )
    ).execute(CheckLibraryRequest(trust_stat=False))

    assert tuple(issue.issue_type for issue in result.issues) == (CheckIssueType.UNMANAGED_FILE_EXISTS,)
    assert content_hasher.calculated_paths == [unmanaged_path]


def test_check_reuses_managed_snapshot_for_ready_plan_source_without_reordering_issues() -> None:
    """Managed-track and READY-plan diagnostics share one snapshot while retaining phase order."""
    uow = InMemoryUnitOfWork()
    uow.libraries.save(_library())
    uow.tracks.save(_track())
    uow.plans.save(_plan())
    uow.plan_actions.save(_source_action())
    managed_path = _absolute(TARGET_PATH)
    snapshots = MappingSnapshotReader({managed_path: _snapshot(managed_path, CHANGED_CONTENT_HASH, METADATA_HASH)})

    result = CheckLibraryUseCase(_check_ports(uow, StaticScanner(()), snapshots)).execute(
        CheckLibraryRequest(trust_stat=False)
    )

    assert tuple(issue.issue_type for issue in result.issues) == (
        CheckIssueType.CONTENT_HASH_CHANGED,
        CheckIssueType.PLAN_SOURCE_CHANGED,
    )
    assert snapshots.captured_paths == [managed_path]


def test_check_trust_stat_skips_full_capture_and_reuses_ready_plan_snapshot() -> None:
    """Opted-in check shares one trusted managed observation with READY-Plan diagnostics."""
    track = replace(_track(), size=FILE_SIZE, mtime=BASE_TIME)
    uow = InMemoryUnitOfWork()
    uow.libraries.save(_library())
    uow.tracks.save(track)
    uow.plans.save(_plan())
    uow.plan_actions.save(_source_action())
    managed_path = _absolute(TARGET_PATH)
    snapshots = MappingSnapshotReader({})

    result = CheckLibraryUseCase(_check_ports(uow, StaticScanner((_scan_entry(managed_path),)), snapshots)).execute(
        CheckLibraryRequest(trust_stat=True)
    )

    assert result.issues == ()
    assert snapshots.captured_paths == []
    assert uow.tracks.get(TRACK_ID) == track


def test_check_trust_stat_full_captures_mismatching_baseline() -> None:
    """A mismatching scan observation falls back to a full snapshot during check."""
    track = replace(_track(), size=FILE_SIZE, mtime=BASE_TIME)
    uow = InMemoryUnitOfWork()
    uow.libraries.save(_library())
    uow.tracks.save(track)
    managed_path = _absolute(TARGET_PATH)
    changed_entry = FileScanEntry(
        path=managed_path,
        size=FILE_SIZE + 1,
        mtime=BASE_TIME,
        file_extension=FILE_EXTENSION,
    )
    snapshots = MappingSnapshotReader({managed_path: _snapshot(managed_path, CHANGED_CONTENT_HASH, METADATA_HASH)})

    result = CheckLibraryUseCase(_check_ports(uow, StaticScanner((changed_entry,)), snapshots)).execute(
        CheckLibraryRequest(trust_stat=True)
    )

    assert tuple(issue.issue_type for issue in result.issues) == (CheckIssueType.CONTENT_HASH_CHANGED,)
    assert snapshots.captured_paths == [managed_path]
    assert uow.tracks.get(TRACK_ID) == track


def test_check_trust_stat_full_captures_duplicate_active_path() -> None:
    """Duplicate active Track paths cannot seed Track-derived snapshot memo entries."""
    uow = InMemoryUnitOfWork()
    uow.libraries.save(_library())
    uow.tracks.save(replace(_track(), size=FILE_SIZE, mtime=BASE_TIME))
    uow.tracks.save(
        replace(
            _track(track_id=SECOND_TRACK_ID),
            size=FILE_SIZE,
            mtime=BASE_TIME,
            content_hash=CHANGED_CONTENT_HASH,
        )
    )
    managed_path = _absolute(TARGET_PATH)
    snapshots = MappingSnapshotReader({managed_path: _snapshot(managed_path)})

    result = CheckLibraryUseCase(_check_ports(uow, StaticScanner((_scan_entry(managed_path),)), snapshots)).execute(
        CheckLibraryRequest(trust_stat=True)
    )

    assert snapshots.captured_paths == [managed_path]
    assert tuple(issue.track_id for issue in result.issues) == (SECOND_TRACK_ID,)


def test_check_memoizes_missing_managed_snapshot_for_ready_plan_source() -> None:
    """A missing managed source is observed once and reused by both diagnostic phases."""
    uow = InMemoryUnitOfWork()
    uow.libraries.save(_library())
    uow.tracks.save(_track())
    uow.plans.save(_plan())
    uow.plan_actions.save(_source_action())
    managed_path = _absolute(TARGET_PATH)
    snapshots = MappingSnapshotReader({}, missing_paths={managed_path})

    result = CheckLibraryUseCase(_check_ports(uow, StaticScanner(()), snapshots)).execute(
        CheckLibraryRequest(trust_stat=False)
    )

    assert tuple(issue.issue_type for issue in result.issues) == (
        CheckIssueType.DB_FILE_MISSING,
        CheckIssueType.PLAN_SOURCE_CHANGED,
    )
    assert snapshots.captured_paths == [managed_path]


def test_check_reports_missing_file_and_library_state() -> None:
    """check reports missing DB files and non-current Library states."""
    uow = InMemoryUnitOfWork()
    uow.libraries.save(_library(status=LibraryStatus.BLOCKED, path_policy_hash="old-policy"))
    uow.tracks.save(_track())
    snapshots = MappingSnapshotReader({}, missing_paths={_absolute(TARGET_PATH)})

    result = CheckLibraryUseCase(_check_ports(uow, StaticScanner(()), snapshots)).execute(
        CheckLibraryRequest(trust_stat=False)
    )

    assert CheckIssueType.DB_FILE_MISSING in {issue.issue_type for issue in result.issues}
    assert CheckIssueType.LIBRARY_BLOCKED in {issue.issue_type for issue in result.issues}
    assert CheckIssueType.LIBRARY_STALE in {issue.issue_type for issue in result.issues}


def test_check_orders_pending_event_issues_by_run_start_then_sequence() -> None:
    """check emits pending-event issues per Run in start order and per event in sequence order."""
    uow = InMemoryUnitOfWork()
    uow.libraries.save(_library())
    uow.runs.save(_run())
    uow.runs.save(_run(run_id=SECOND_RUN_ID, plan_id=SECOND_PLAN_ID, started_at=BASE_TIME + timedelta(minutes=1)))
    uow.file_events.save(_pending_event(event_id=SECOND_EVENT_ID, target_path=RESTORE_PATH, sequence_no=2))
    uow.file_events.save(_pending_event(event_id=THIRD_EVENT_ID, run_id=SECOND_RUN_ID, target_path=SECOND_SOURCE_PATH))
    uow.file_events.save(_pending_event())

    result = CheckLibraryUseCase(_check_ports(uow, StaticScanner(()), MappingSnapshotReader({}))).execute(
        CheckLibraryRequest(trust_stat=False)
    )

    pending_issues = tuple(
        issue for issue in result.issues if issue.issue_type == CheckIssueType.PENDING_FILE_EVENT_EXISTS
    )
    assert tuple((issue.plan_id, issue.path) for issue in pending_issues) == (
        (PLAN_ID, TARGET_PATH),
        (PLAN_ID, RESTORE_PATH),
        (SECOND_PLAN_ID, SECOND_SOURCE_PATH),
    )


def test_check_replaces_prior_run_findings_wholesale_on_recheck() -> None:
    """A second check for one Library replaces its persisted CheckRun and CheckIssues entirely."""
    uow = InMemoryUnitOfWork()
    uow.libraries.save(_library(status=LibraryStatus.BLOCKED, path_policy_hash="old-policy"))
    uow.tracks.save(_track())
    dirty_snapshots = MappingSnapshotReader({}, missing_paths={_absolute(TARGET_PATH)})
    first_id_generator = SequenceIdGenerator(check_run_ids=deque((CHECK_RUN_ID,)))

    first = CheckLibraryUseCase(
        _check_ports(uow, StaticScanner(()), dirty_snapshots, id_generator=first_id_generator)
    ).execute(CheckLibraryRequest(trust_stat=False))

    first_run = uow.check_runs.latest(LIBRARY_ID)
    assert first_run is not None
    assert first_run.check_run_id == CHECK_RUN_ID
    assert first_run.total_count == len(first.issues) > 0
    assert len(uow.check_issues.records) == len(first.issues)

    uow.libraries.save(_library())  # Library becomes registered with the current path policy hash.
    clean_snapshots = MappingSnapshotReader({_absolute(TARGET_PATH): _snapshot(_absolute(TARGET_PATH))})
    second_id_generator = SequenceIdGenerator(check_run_ids=deque((SECOND_CHECK_RUN_ID,)))

    second = CheckLibraryUseCase(
        _check_ports(uow, StaticScanner(()), clean_snapshots, id_generator=second_id_generator)
    ).execute(CheckLibraryRequest(trust_stat=False))

    assert second.issues == ()
    second_run = uow.check_runs.latest(LIBRARY_ID)
    assert second_run is not None
    assert second_run.check_run_id == SECOND_CHECK_RUN_ID
    assert second_run.total_count == 0
    assert len(uow.check_issues.records) == 0


def test_check_query_usecases_read_persisted_findings_and_resolve_checked_at() -> None:
    """List/facet/group usecases read persisted CheckIssues and resolve checked_at per scope."""
    uow = InMemoryUnitOfWork()
    uow.libraries.save(_library())
    uow.libraries.save(_library(library_id=SECOND_LIBRARY_ID, root_path=SECOND_LIBRARY_ROOT))
    dirty_snapshots = MappingSnapshotReader({}, missing_paths={_absolute(TARGET_PATH)})
    uow.tracks.save(_track())

    _ = CheckLibraryUseCase(
        CheckLibraryPorts(
            uow=uow,
            file_scanner=StaticScanner(()),
            file_snapshot_reader=dirty_snapshots,
            file_content_hasher=MappingContentHasher({}),
            config_store=StaticConfigStore(),
            path_resolver=SimplePathResolver(),
            clock=FixedClock(BASE_TIME),
            id_generator=SequenceIdGenerator(check_run_ids=deque((CHECK_RUN_ID,))),
        )
    ).execute(CheckLibraryRequest(trust_stat=False, library_id=LIBRARY_ID))
    _ = CheckLibraryUseCase(
        CheckLibraryPorts(
            uow=uow,
            file_scanner=StaticScanner(()),
            file_snapshot_reader=MappingSnapshotReader({}),
            file_content_hasher=MappingContentHasher({}),
            config_store=StaticConfigStore(),
            path_resolver=SimplePathResolver(),
            clock=FixedClock(BASE_TIME + timedelta(days=1)),
            id_generator=SequenceIdGenerator(check_run_ids=deque((SECOND_CHECK_RUN_ID,))),
        )
    ).execute(CheckLibraryRequest(trust_stat=False, library_id=SECOND_LIBRARY_ID))

    query_ports = CheckQueryPorts(uow)
    per_library = ListCheckIssuesUseCase(query_ports).execute(ListCheckIssuesRequest(library_id=LIBRARY_ID))
    other_library = ListCheckIssuesUseCase(query_ports).execute(ListCheckIssuesRequest(library_id=SECOND_LIBRARY_ID))
    aggregate = ListCheckIssuesUseCase(query_ports).execute(ListCheckIssuesRequest())
    facets = GetCheckIssueFacetsUseCase(query_ports).execute(CheckIssueFacetsRequest())
    groups = GroupCheckIssuesUseCase(query_ports).execute(GroupCheckIssuesRequest())

    assert len(per_library.page.items) > 0
    assert per_library.checked_at == BASE_TIME
    assert other_library.page.items == ()
    assert other_library.checked_at == BASE_TIME + timedelta(days=1)
    assert aggregate.page.total == per_library.page.total
    assert aggregate.checked_at == BASE_TIME  # minimum across both Libraries' latest check runs
    assert facets.checked_at == BASE_TIME
    assert facets.total == per_library.page.total
    assert sum(group.count for group in groups.items) == per_library.page.total


def test_check_query_usecases_resolve_checked_at_none_when_never_checked() -> None:
    """checked_at is null for a Library (or the aggregate scope) that has never been checked."""
    uow = InMemoryUnitOfWork()
    uow.libraries.save(_library())
    query_ports = CheckQueryPorts(uow)

    per_library = ListCheckIssuesUseCase(query_ports).execute(ListCheckIssuesRequest(library_id=LIBRARY_ID))
    aggregate = ListCheckIssuesUseCase(query_ports).execute(ListCheckIssuesRequest())
    facets = GetCheckIssueFacetsUseCase(query_ports).execute(CheckIssueFacetsRequest())

    assert per_library.page.items == ()
    assert per_library.checked_at is None
    assert aggregate.page.items == ()
    assert aggregate.checked_at is None
    assert facets.checked_at is None


def test_check_query_usecases_group_and_drill_down_without_loading_all_issues() -> None:
    """Check browse usecases expose the same grouping keys and member filters through their ports."""
    uow = InMemoryUnitOfWork()
    uow.libraries.save(_library())
    uow.check_issues.save_many(
        CHECK_RUN_ID,
        (
            CheckIssue(
                issue_type=CheckIssueType.DB_FILE_MISSING,
                library_id=LIBRARY_ID,
                path="Aimer/Album/01.flac",
            ),
            CheckIssue(
                issue_type=CheckIssueType.DB_FILE_MISSING,
                library_id=LIBRARY_ID,
                path="Aimer/Album/02.flac",
            ),
            CheckIssue(
                issue_type=CheckIssueType.METADATA_HASH_CHANGED,
                library_id=LIBRARY_ID,
                path="Aimer/Other/03.flac",
            ),
        ),
    )
    ports = CheckQueryPorts(uow)

    groups = GroupCheckIssuesUseCase(ports).execute(
        GroupCheckIssuesRequest(grouping=CheckIssueGrouping.SUGGESTED_COMMAND)
    )
    members = ListCheckIssuesUseCase(ports).execute(
        ListCheckIssuesRequest(
            grouping=CheckIssueGrouping.PATH_ROOT,
            group_key="Aimer/",
        )
    )

    assert [(group.key, group.label, group.count) for group in groups.items] == [("refresh", "omym2 refresh <file>", 3)]
    assert groups.items[0].common_path_root == "Aimer/"
    assert [issue.path for issue in members.page.items] == [
        "Aimer/Album/01.flac",
        "Aimer/Album/02.flac",
        "Aimer/Other/03.flac",
    ]


def test_history_lists_runs_newest_first_and_loads_detail() -> None:
    """history usecases query Runs and FileEvents through repositories."""
    uow = InMemoryUnitOfWork()
    uow.libraries.save(_library())
    uow.runs.save(_run(started_at=BASE_TIME))
    uow.runs.save(_run(run_id=SECOND_RUN_ID, started_at=BASE_TIME + timedelta(minutes=1)))
    uow.file_events.save(_event())
    ports = HistoryPorts(uow)

    runs = ListRunsUseCase(ports).execute(ListRunsRequest())
    header = GetRunHeaderUseCase(ports).execute(GetRunHeaderRequest(RUN_ID))
    events = ListRunEventsUseCase(ports).execute(ListRunEventsRequest(run_id=RUN_ID))

    assert tuple(run.run_id for run in runs.items) == (SECOND_RUN_ID, RUN_ID)
    assert header.run_id == RUN_ID
    assert tuple(event.event_id for event in events.items) == (EVENT_ID,)


def test_undo_creates_plan_from_succeeded_events_in_reverse_order() -> None:
    """undo reverses succeeded FileEvents and preserves external restore targets."""
    uow = _uow_with_applied_run()
    id_generator = SequenceIdGenerator(
        plan_ids=deque((UNDO_PLAN_ID,)),
        action_ids=deque((UNDO_ACTION_ID, UNDO_SECOND_ACTION_ID)),
    )
    ports = _undo_ports(uow, id_generator=id_generator)

    plan = CreateUndoPlanUseCase(ports).execute(CreateUndoPlanRequest(RUN_ID))

    assert plan.plan_type == PlanType.UNDO
    assert plan.status == PlanStatus.READY
    assert plan.summary["action_count"] == "2"
    assert tuple(action.source_path for action in plan.actions) == (TARGET_PATH, RESTORE_PATH)
    assert tuple(action.target_path for action in plan.actions) == (EXTERNAL_SOURCE_PATH, SOURCE_PATH)
    assert tuple(action.track_id for action in plan.actions) == (TRACK_ID, SECOND_TRACK_ID)
    assert all(action.status == ActionStatus.PLANNED for action in plan.actions)
    assert uow.plans.get(UNDO_PLAN_ID) == plan


def test_undo_rejects_refresh_metadata_only_run_without_creating_empty_plan() -> None:
    """undo rejects DB-only refresh history because no reversible FileEvents exist."""
    uow = InMemoryUnitOfWork()
    uow.libraries.save(_library())
    uow.tracks.save(_track())
    uow.plans.save(_plan(status=PlanStatus.APPLIED))
    uow.plan_actions.save(
        replace(_source_action(), action_type=ActionType.REFRESH_METADATA, status=ActionStatus.APPLIED)
    )
    uow.runs.save(_run(status=RunStatus.SUCCEEDED))
    ports = _undo_ports(uow, id_generator=SequenceIdGenerator(plan_ids=deque((UNDO_PLAN_ID,))))

    with pytest.raises(UndoPlanError, match=RUN_REFRESH_METADATA_UNSUPPORTED_MESSAGE):
        _ = CreateUndoPlanUseCase(ports).execute(CreateUndoPlanRequest(RUN_ID))

    assert uow.plans.get(UNDO_PLAN_ID) is None


def test_undo_rejects_run_that_includes_refresh_metadata_even_with_file_events() -> None:
    """undo rejects mixed refresh history instead of creating an incomplete file-only plan."""
    uow = _uow_with_applied_run(second_event=False)
    uow.plan_actions.save(
        replace(
            _source_action(action_id=UNDO_ACTION_ID),
            action_type=ActionType.REFRESH_METADATA,
            status=ActionStatus.APPLIED,
        )
    )
    ports = _undo_ports(
        uow,
        id_generator=SequenceIdGenerator(plan_ids=deque((UNDO_PLAN_ID,)), action_ids=deque((UNDO_ACTION_ID,))),
    )

    with pytest.raises(UndoPlanError, match=RUN_REFRESH_METADATA_UNSUPPORTED_MESSAGE):
        _ = CreateUndoPlanUseCase(ports).execute(CreateUndoPlanRequest(RUN_ID))

    assert uow.plans.get(UNDO_PLAN_ID) is None


def test_undo_rejects_running_run_before_planning_from_partial_history() -> None:
    """undo rejects in-progress Runs before reading a stale FileEvent snapshot."""
    uow = _uow_with_applied_run(second_event=False)
    uow.runs.save(_run(status=RunStatus.RUNNING))
    ports = _undo_ports(
        uow,
        id_generator=SequenceIdGenerator(plan_ids=deque((UNDO_PLAN_ID,)), action_ids=deque((UNDO_ACTION_ID,))),
    )

    with pytest.raises(UndoPlanError, match=RUN_NOT_TERMINAL_MESSAGE):
        _ = CreateUndoPlanUseCase(ports).execute(CreateUndoPlanRequest(RUN_ID))

    assert uow.plans.get(UNDO_PLAN_ID) is None


@pytest.mark.parametrize("run_status", [RunStatus.FAILED, RunStatus.PARTIAL_FAILED])
def test_undo_allows_terminal_unsuccessful_runs_with_succeeded_file_events(run_status: RunStatus) -> None:
    """undo can still reverse confirmed file moves from terminal unsuccessful Runs."""
    uow = _uow_with_applied_run(second_event=False)
    uow.runs.save(_run(status=run_status))
    ports = _undo_ports(
        uow,
        id_generator=SequenceIdGenerator(plan_ids=deque((UNDO_PLAN_ID,)), action_ids=deque((UNDO_ACTION_ID,))),
    )

    plan = CreateUndoPlanUseCase(ports).execute(CreateUndoPlanRequest(RUN_ID))

    assert len(plan.actions) == 1
    assert plan.actions[0].status == ActionStatus.PLANNED


def test_apply_persists_generated_track_id_on_add_action_for_later_undo() -> None:
    """Apply stores the new Track identity on the action referenced by FileEvent."""
    uow = InMemoryUnitOfWork()
    uow.libraries.save(_library())
    uow.plans.save(_plan(status=PlanStatus.READY))
    uow.plan_actions.save(_source_action(source_path=EXTERNAL_SOURCE_PATH, target_path=TARGET_PATH, track_id=None))
    ports = ApplyPlanPorts(
        uow=uow,
        file_mover=RecordingFileMover(),
        file_snapshot_reader=MappingSnapshotReader({EXTERNAL_SOURCE_PATH: _snapshot(EXTERNAL_SOURCE_PATH)}),
        path_resolver=SimplePathResolver(),
        clock=FixedClock(BASE_TIME),
        id_generator=SequenceIdGenerator(
            run_ids=deque((RUN_ID,)),
            event_ids=deque((EVENT_ID,)),
            track_ids=deque((TRACK_ID,)),
        ),
    )

    _ = ApplyPlanUseCase(ports).execute(ApplyPlanRequest(PLAN_ID, options=ApplyOptions(yes=True)))

    action = uow.plan_actions.get(ACTION_ID)
    assert action is not None
    assert action.track_id == TRACK_ID


def test_undo_uses_current_track_path_for_import_after_track_moved() -> None:
    """Undo resolves durable Track identity instead of replaying stale FileEvent target paths."""
    uow = InMemoryUnitOfWork()
    uow.libraries.save(_library())
    uow.tracks.save(_track(current_path=RESTORE_PATH))
    uow.tracks.save(_track(track_id=SECOND_TRACK_ID, current_path=TARGET_PATH))
    uow.plans.save(_plan(status=PlanStatus.APPLIED))
    uow.plan_actions.save(_source_action(source_path=EXTERNAL_SOURCE_PATH, target_path=TARGET_PATH, track_id=TRACK_ID))
    uow.runs.save(_run(status=RunStatus.SUCCEEDED))
    uow.file_events.save(_event(source_path=EXTERNAL_SOURCE_PATH, target_path=TARGET_PATH))
    ports = _undo_ports(
        uow,
        id_generator=SequenceIdGenerator(plan_ids=deque((UNDO_PLAN_ID,)), action_ids=deque((UNDO_ACTION_ID,))),
    )

    plan = CreateUndoPlanUseCase(ports).execute(CreateUndoPlanRequest(RUN_ID))

    assert plan.actions[0].source_path == RESTORE_PATH
    assert plan.actions[0].target_path == EXTERNAL_SOURCE_PATH
    assert plan.actions[0].track_id == TRACK_ID
    assert plan.actions[0].status == ActionStatus.PLANNED


def test_undo_resolves_tracks_by_path_when_no_source_action_has_track_id() -> None:
    """Undo resolves Track identity from Library paths for every event of a Run
    whose recorded plan actions all lack track_id."""
    uow = InMemoryUnitOfWork()
    uow.libraries.save(_library())
    uow.tracks.save(_track())
    uow.tracks.save(_track(track_id=SECOND_TRACK_ID, current_path=RESTORE_PATH))
    uow.plans.save(_plan(status=PlanStatus.APPLIED))
    uow.plan_actions.save(_source_action(track_id=None))
    uow.plan_actions.save(_source_action(action_id=SECOND_ACTION_ID, track_id=None))
    uow.runs.save(_run(status=RunStatus.SUCCEEDED))
    uow.file_events.save(_event(source_path=SOURCE_PATH, target_path=RESTORE_PATH, plan_action_id=ACTION_ID))
    uow.file_events.save(
        _event(
            event_id=SECOND_EVENT_ID,
            source_path=SECOND_SOURCE_PATH,
            target_path=TARGET_PATH,
            plan_action_id=SECOND_ACTION_ID,
            sequence_no=2,
        )
    )
    ports = _undo_ports(
        uow,
        id_generator=SequenceIdGenerator(
            plan_ids=deque((UNDO_PLAN_ID,)),
            action_ids=deque((UNDO_ACTION_ID, UNDO_SECOND_ACTION_ID)),
        ),
    )

    plan = CreateUndoPlanUseCase(ports).execute(CreateUndoPlanRequest(RUN_ID))

    assert tuple(action.track_id for action in plan.actions) == (TRACK_ID, SECOND_TRACK_ID)
    assert tuple(action.source_path for action in plan.actions) == (TARGET_PATH, RESTORE_PATH)
    assert tuple(action.target_path for action in plan.actions) == (SECOND_SOURCE_PATH, SOURCE_PATH)
    assert all(action.status == ActionStatus.PLANNED for action in plan.actions)


def test_undo_blocks_occupied_restore_destination() -> None:
    """undo records target conflicts instead of overwriting destinations."""
    uow = _uow_with_applied_run(second_event=False)
    occupied_target = _absolute(SOURCE_PATH)
    ports = _undo_ports(
        uow,
        id_generator=SequenceIdGenerator(plan_ids=deque((UNDO_PLAN_ID,)), action_ids=deque((UNDO_ACTION_ID,))),
        file_presence=StaticFilePresence({occupied_target}),
    )

    plan = CreateUndoPlanUseCase(ports).execute(CreateUndoPlanRequest(RUN_ID))

    assert len(plan.actions) == 1
    assert plan.actions[0].status == ActionStatus.BLOCKED
    assert plan.actions[0].reason == PlanActionReason.TARGET_EXISTS


def test_apply_external_undo_restore_marks_track_removed() -> None:
    """Applying an external restore never stores the external path on Track."""
    uow = InMemoryUnitOfWork()
    uow.libraries.save(_library())
    uow.tracks.save(_track())
    uow.plans.save(_plan(status=PlanStatus.APPLIED))
    uow.plan_actions.save(_source_action(source_path=EXTERNAL_SOURCE_PATH, target_path=TARGET_PATH, track_id=TRACK_ID))
    uow.runs.save(_run(status=RunStatus.SUCCEEDED))
    uow.file_events.save(_event(source_path=EXTERNAL_SOURCE_PATH, target_path=TARGET_PATH))
    uow.plans.save(_plan(plan_id=UNDO_PLAN_ID, plan_type=PlanType.UNDO, status=PlanStatus.READY))
    uow.plan_actions.save(
        _source_action(
            action_id=UNDO_ACTION_ID,
            plan_id=UNDO_PLAN_ID,
            source_path=TARGET_PATH,
            target_path=EXTERNAL_SOURCE_PATH,
            track_id=TRACK_ID,
        )
    )
    mover = RecordingFileMover()
    ports = ApplyPlanPorts(
        uow=uow,
        file_mover=mover,
        file_snapshot_reader=MappingSnapshotReader({_absolute(TARGET_PATH): _snapshot(_absolute(TARGET_PATH))}),
        path_resolver=SimplePathResolver(),
        clock=FixedClock(BASE_TIME),
        id_generator=SequenceIdGenerator(run_ids=deque((UNDO_RUN_ID,)), event_ids=deque((UNDO_EVENT_ID,))),
    )

    run = ApplyPlanUseCase(ports).execute(ApplyPlanRequest(UNDO_PLAN_ID, options=ApplyOptions(yes=True)))

    assert run is not None
    assert run.status == RunStatus.SUCCEEDED
    assert mover.moves == [(_absolute(TARGET_PATH), EXTERNAL_SOURCE_PATH)]
    track = uow.tracks.get(TRACK_ID)
    assert track is not None
    assert track.status == TrackStatus.REMOVED
    assert track.current_path == TARGET_PATH


def test_apply_rejects_absolute_target_on_non_undo_plan() -> None:
    """A corrupted non-undo action cannot move a Library file outside its root."""
    uow = InMemoryUnitOfWork()
    uow.libraries.save(_library())
    uow.tracks.save(_track())
    uow.plans.save(_plan(status=PlanStatus.READY))
    uow.plan_actions.save(_source_action(source_path=TARGET_PATH, target_path=EXTERNAL_SOURCE_PATH, track_id=TRACK_ID))
    mover = RecordingFileMover()
    ports = ApplyPlanPorts(
        uow=uow,
        file_mover=mover,
        file_snapshot_reader=MappingSnapshotReader({_absolute(TARGET_PATH): _snapshot(_absolute(TARGET_PATH))}),
        path_resolver=SimplePathResolver(),
        clock=FixedClock(BASE_TIME),
        id_generator=SequenceIdGenerator(run_ids=deque((RUN_ID,))),
    )

    run = ApplyPlanUseCase(ports).execute(ApplyPlanRequest(PLAN_ID, options=ApplyOptions(yes=True)))

    assert run is not None
    assert run.status == RunStatus.FAILED
    assert mover.moves == []
    action = uow.plan_actions.get(ACTION_ID)
    assert action is not None
    assert action.status == ActionStatus.FAILED
    assert action.reason == PlanActionReason.INVALID_PATH


def test_undo_blocks_absolute_target_not_matching_source_action() -> None:
    """Corrupted event history cannot create an unverified external restore."""
    uow = _uow_with_applied_run(second_event=False)
    uow.file_events.save(_event(source_path=EXTERNAL_SOURCE_PATH, target_path=RESTORE_PATH))
    ports = _undo_ports(
        uow,
        id_generator=SequenceIdGenerator(plan_ids=deque((UNDO_PLAN_ID,)), action_ids=deque((UNDO_ACTION_ID,))),
    )

    plan = CreateUndoPlanUseCase(ports).execute(CreateUndoPlanRequest(RUN_ID))

    assert plan.actions[0].status == ActionStatus.BLOCKED
    assert plan.actions[0].reason == PlanActionReason.INVALID_PATH


def test_apply_external_undo_restore_succeeds_after_in_library_relocation() -> None:
    """External restore stays verified after the imported Track moved inside the Library."""
    uow = InMemoryUnitOfWork()
    uow.libraries.save(_library())
    uow.tracks.save(_track(current_path=RELOCATED_PATH))
    uow.plans.save(_plan(status=PlanStatus.APPLIED))
    uow.plan_actions.save(_source_action(source_path=EXTERNAL_SOURCE_PATH, target_path=TARGET_PATH, track_id=TRACK_ID))
    uow.runs.save(_run(status=RunStatus.SUCCEEDED))
    uow.file_events.save(_event(source_path=EXTERNAL_SOURCE_PATH, target_path=TARGET_PATH))
    undo_plan = CreateUndoPlanUseCase(
        _undo_ports(
            uow,
            id_generator=SequenceIdGenerator(plan_ids=deque((UNDO_PLAN_ID,)), action_ids=deque((UNDO_ACTION_ID,))),
        )
    ).execute(CreateUndoPlanRequest(RUN_ID))

    assert undo_plan.actions[0].status == ActionStatus.PLANNED
    assert undo_plan.actions[0].source_path == RELOCATED_PATH

    mover = RecordingFileMover()
    ports = ApplyPlanPorts(
        uow=uow,
        file_mover=mover,
        file_snapshot_reader=MappingSnapshotReader({_absolute(RELOCATED_PATH): _snapshot(_absolute(RELOCATED_PATH))}),
        path_resolver=SimplePathResolver(),
        clock=FixedClock(BASE_TIME),
        id_generator=SequenceIdGenerator(run_ids=deque((UNDO_RUN_ID,)), event_ids=deque((UNDO_EVENT_ID,))),
    )

    run = ApplyPlanUseCase(ports).execute(ApplyPlanRequest(UNDO_PLAN_ID, options=ApplyOptions(yes=True)))

    assert run is not None
    assert run.status == RunStatus.SUCCEEDED
    assert mover.moves == [(_absolute(RELOCATED_PATH), EXTERNAL_SOURCE_PATH)]
    track = uow.tracks.get(TRACK_ID)
    assert track is not None
    assert track.status == TrackStatus.REMOVED
    assert track.current_path == RELOCATED_PATH


def test_apply_rejects_external_restore_not_matching_track_current_path() -> None:
    """A corrupted restore source cannot move an unrelated Library file outside."""
    uow = InMemoryUnitOfWork()
    uow.libraries.save(_library())
    uow.tracks.save(_track())
    uow.plans.save(_plan(status=PlanStatus.APPLIED))
    uow.plan_actions.save(_source_action(source_path=EXTERNAL_SOURCE_PATH, target_path=TARGET_PATH, track_id=TRACK_ID))
    uow.runs.save(_run(status=RunStatus.SUCCEEDED))
    uow.file_events.save(_event(source_path=EXTERNAL_SOURCE_PATH, target_path=TARGET_PATH))
    uow.plans.save(_plan(plan_id=UNDO_PLAN_ID, plan_type=PlanType.UNDO, status=PlanStatus.READY))
    uow.plan_actions.save(
        _source_action(
            action_id=UNDO_ACTION_ID,
            plan_id=UNDO_PLAN_ID,
            source_path=RESTORE_PATH,
            target_path=EXTERNAL_SOURCE_PATH,
            track_id=TRACK_ID,
        )
    )
    mover = RecordingFileMover()
    ports = ApplyPlanPorts(
        uow=uow,
        file_mover=mover,
        file_snapshot_reader=MappingSnapshotReader({_absolute(RESTORE_PATH): _snapshot(_absolute(RESTORE_PATH))}),
        path_resolver=SimplePathResolver(),
        clock=FixedClock(BASE_TIME),
        id_generator=SequenceIdGenerator(run_ids=deque((UNDO_RUN_ID,))),
    )

    run = ApplyPlanUseCase(ports).execute(ApplyPlanRequest(UNDO_PLAN_ID, options=ApplyOptions(yes=True)))

    assert run is not None
    assert run.status == RunStatus.FAILED
    assert mover.moves == []
    action = uow.plan_actions.get(UNDO_ACTION_ID)
    assert action is not None
    assert action.status == ActionStatus.FAILED
    assert action.reason == PlanActionReason.INVALID_PATH


class StaticConfigStore:
    """ConfigStore fake returning one AppConfig."""

    def __init__(self, config: AppConfig | None = None) -> None:
        """Store the config returned by load."""
        self._config: AppConfig = default_app_config() if config is None else config

    def load(self) -> AppConfig:
        """Return the configured AppConfig."""
        return self._config

    def save(self, config: AppConfig) -> None:
        """Replace the configured AppConfig."""
        self._config = config


class StaticScanner:
    """FileScanner fake returning fixed entries."""

    def __init__(self, entries: tuple[FileScanEntry, ...]) -> None:
        """Store scan entries."""
        self._entries: tuple[FileScanEntry, ...] = entries

    def scan(self, root: FileSystemPath) -> tuple[FileScanEntry, ...]:
        """Return fixed entries without touching the filesystem."""
        del root
        return self._entries


class MappingSnapshotReader:
    """FileSnapshotReader fake keyed by filesystem path text."""

    def __init__(self, snapshots: dict[str, FileSnapshot], *, missing_paths: set[str] | None = None) -> None:
        """Store snapshots and paths that should appear missing."""
        self._snapshots: dict[str, FileSnapshot] = snapshots
        self._missing_paths: set[str] = set() if missing_paths is None else set(missing_paths)
        self.captured_paths: list[str] = []

    def capture(self, path: FileSystemPath) -> FileSnapshot:
        """Return the configured snapshot for a path."""
        path_text = str(path)
        self.captured_paths.append(path_text)
        if path_text in self._missing_paths:
            raise FileNotFoundError(path_text)
        return self._snapshots[path_text]

    def capture_many(
        self,
        requests: Sequence[FileSnapshotCaptureRequest],
    ) -> tuple[FileSnapshot | None, ...]:
        """Capture requests serially while recording memo-visible path reads."""
        snapshots: list[FileSnapshot | None] = []
        for request in requests:
            try:
                snapshots.append(self.capture(request.path))
            except FileNotFoundError:
                snapshots.append(None)
        return tuple(snapshots)


class MappingContentHasher:
    """FileContentHasher fake keyed by filesystem path text."""

    def __init__(self, hashes: dict[str, str], *, missing_paths: set[str] | None = None) -> None:
        """Store hashes and paths that should disappear before hashing."""
        self._hashes: dict[str, str] = hashes
        self._missing_paths: set[str] = set() if missing_paths is None else set(missing_paths)
        self.calculated_paths: list[str] = []

    def calculate(self, path: FileSystemPath) -> str:
        """Return the configured hash for a path."""
        path_text = str(path)
        self.calculated_paths.append(path_text)
        if path_text in self._missing_paths:
            raise FileNotFoundError(path_text)
        return self._hashes[path_text]


class StaticFilePresence:
    """FilePresence fake keyed by path text."""

    def __init__(self, existing_paths: set[str] | None = None) -> None:
        """Store paths reported as present."""
        self._existing_paths: set[str] = set() if existing_paths is None else set(existing_paths)

    def exists(self, path: FileSystemPath) -> bool:
        """Return whether the path is configured as present."""
        return str(path) in self._existing_paths


class SimplePathResolver:
    """PathResolver fake joining Library roots and logical paths."""

    def resolve_library_path(self, library_root: FileSystemPath, library_relative_path: str) -> str:
        """Return a filesystem path for a Library-relative path."""
        return f"{str(library_root).rstrip('/')}/{library_relative_path}"

    def relative_to_library(self, library_root: FileSystemPath, path: FileSystemPath) -> str:
        """Return a lexical Library-relative path."""
        return str(path).removeprefix(f"{str(library_root).rstrip('/')}/")


class RecordingFileMover:
    """FileMover fake that records moves."""

    def __init__(self) -> None:
        """Initialize recorded moves."""
        self.moves: list[tuple[str, str]] = []

    def move(
        self,
        source: FileSystemPath,
        target: FileSystemPath,
        *,
        target_root: FileSystemPath | None = None,
    ) -> None:
        """Record one move."""
        del target_root
        self.moves.append((str(source), str(target)))


def _check_ports(
    uow: InMemoryUnitOfWork,
    scanner: StaticScanner,
    snapshot_reader: MappingSnapshotReader,
    *,
    content_hasher: MappingContentHasher | None = None,
    id_generator: SequenceIdGenerator | None = None,
) -> CheckLibraryPorts:
    return CheckLibraryPorts(
        uow=uow,
        file_scanner=scanner,
        file_snapshot_reader=snapshot_reader,
        file_content_hasher=MappingContentHasher({}) if content_hasher is None else content_hasher,
        config_store=StaticConfigStore(),
        path_resolver=SimplePathResolver(),
        clock=FixedClock(BASE_TIME),
        id_generator=SequenceIdGenerator(check_run_ids=deque((CHECK_RUN_ID,)))
        if id_generator is None
        else id_generator,
    )


def _undo_ports(
    uow: InMemoryUnitOfWork,
    *,
    id_generator: SequenceIdGenerator,
    file_presence: StaticFilePresence | None = None,
) -> CreateUndoPlanPorts:
    snapshots = {
        _absolute(TARGET_PATH): _snapshot(_absolute(TARGET_PATH)),
        _absolute(RELOCATED_PATH): _snapshot(_absolute(RELOCATED_PATH)),
        _absolute(RESTORE_PATH): _snapshot(_absolute(RESTORE_PATH)),
    }
    return CreateUndoPlanPorts(
        uow=uow,
        file_snapshot_reader=MappingSnapshotReader(snapshots),
        file_presence=StaticFilePresence() if file_presence is None else file_presence,
        path_resolver=SimplePathResolver(),
        clock=FixedClock(BASE_TIME),
        id_generator=id_generator,
    )


def _uow_with_applied_run(*, second_event: bool = True) -> InMemoryUnitOfWork:
    uow = InMemoryUnitOfWork()
    uow.libraries.save(_library())
    uow.tracks.save(_track())
    uow.tracks.save(_track(track_id=SECOND_TRACK_ID, current_path=RESTORE_PATH))
    uow.plans.save(_plan(status=PlanStatus.APPLIED))
    uow.plan_actions.save(_source_action(track_id=SECOND_TRACK_ID))
    uow.plan_actions.save(
        _source_action(
            action_id=SECOND_ACTION_ID,
            source_path=EXTERNAL_SOURCE_PATH,
            target_path=TARGET_PATH,
            track_id=TRACK_ID,
        )
    )
    uow.runs.save(_run(status=RunStatus.SUCCEEDED))
    uow.file_events.save(_event(source_path=SOURCE_PATH, target_path=RESTORE_PATH, plan_action_id=ACTION_ID))
    if second_event:
        uow.file_events.save(
            _event(
                event_id=SECOND_EVENT_ID,
                source_path=EXTERNAL_SOURCE_PATH,
                target_path=TARGET_PATH,
                plan_action_id=SECOND_ACTION_ID,
                sequence_no=2,
            )
        )
    return uow


def _library(
    *,
    library_id: LibraryId = LIBRARY_ID,
    root_path: str = LIBRARY_ROOT,
    status: LibraryStatus = LibraryStatus.REGISTERED,
    path_policy_hash: str | None = None,
) -> Library:
    return Library(
        library_id=library_id,
        root_path=root_path,
        path_policy_hash=calculate_path_policy_fingerprint(
            default_app_config().path_policy,
            default_app_config().artist_ids,
        )
        if path_policy_hash is None
        else path_policy_hash,
        registered_at=BASE_TIME,
        status=status,
        created_at=BASE_TIME,
        updated_at=BASE_TIME,
    )


def _track(
    *,
    track_id: TrackId = TRACK_ID,
    current_path: str = TARGET_PATH,
    canonical_path: str = TARGET_PATH,
    status: TrackStatus = TrackStatus.ACTIVE,
) -> Track:
    return Track(
        track_id=track_id,
        library_id=LIBRARY_ID,
        current_path=current_path,
        canonical_path=canonical_path,
        content_hash=CONTENT_HASH,
        metadata_hash=METADATA_HASH,
        size=None,
        mtime=None,
        metadata=METADATA,
        status=status,
        first_seen_at=BASE_TIME,
        last_seen_at=BASE_TIME,
        updated_at=BASE_TIME,
    )


def _plan(
    *,
    plan_id: PlanId = PLAN_ID,
    plan_type: PlanType = PlanType.ADD,
    status: PlanStatus = PlanStatus.READY,
) -> Plan:
    return Plan(
        plan_id=plan_id,
        library_id=LIBRARY_ID,
        plan_type=plan_type,
        status=status,
        created_at=BASE_TIME,
        config_hash=CONFIG_HASH,
        library_root_at_plan=LIBRARY_ROOT,
        summary={"action_count": "1"},
    )


def _source_action(
    *,
    action_id: ActionId = ACTION_ID,
    plan_id: PlanId = PLAN_ID,
    source_path: str = TARGET_PATH,
    target_path: str = RESTORE_PATH,
    track_id: TrackId | None = TRACK_ID,
) -> PlanAction:
    return PlanAction(
        action_id=action_id,
        plan_id=plan_id,
        library_id=LIBRARY_ID,
        track_id=track_id,
        action_type=ActionType.MOVE,
        source_path=source_path,
        target_path=target_path,
        content_hash_at_plan=CONTENT_HASH,
        metadata_hash_at_plan=METADATA_HASH,
        status=ActionStatus.PLANNED,
        reason=None,
        sort_order=1,
    )


def _run(
    *,
    run_id: RunId = RUN_ID,
    plan_id: PlanId = PLAN_ID,
    status: RunStatus = RunStatus.RUNNING,
    started_at: datetime = BASE_TIME,
) -> Run:
    return Run(
        run_id=run_id,
        plan_id=plan_id,
        library_id=LIBRARY_ID,
        status=status,
        started_at=started_at,
    )


def _event(
    *,
    event_id: EventId = EVENT_ID,
    source_path: str = SOURCE_PATH,
    target_path: str = TARGET_PATH,
    plan_action_id: ActionId = ACTION_ID,
    sequence_no: int = 1,
) -> FileEvent:
    return FileEvent(
        event_id=event_id,
        library_id=LIBRARY_ID,
        run_id=RUN_ID,
        plan_action_id=plan_action_id,
        event_type=FileEventType.MOVE_FILE,
        source_path=source_path,
        target_path=target_path,
        status=FileEventStatus.SUCCEEDED,
        started_at=BASE_TIME,
        completed_at=BASE_TIME,
        error_code=None,
        error_message=None,
        sequence_no=sequence_no,
    )


def _pending_event(
    *,
    event_id: EventId = EVENT_ID,
    run_id: RunId = RUN_ID,
    target_path: str = TARGET_PATH,
    sequence_no: int = 1,
) -> FileEvent:
    return FileEvent(
        event_id=event_id,
        library_id=LIBRARY_ID,
        run_id=run_id,
        plan_action_id=ACTION_ID,
        event_type=FileEventType.MOVE_FILE,
        source_path=SOURCE_PATH,
        target_path=target_path,
        status=FileEventStatus.PENDING,
        started_at=BASE_TIME,
        completed_at=None,
        error_code=None,
        error_message=None,
        sequence_no=sequence_no,
    )


def _scan_entry(path: str) -> FileScanEntry:
    return FileScanEntry(path=path, size=FILE_SIZE, mtime=BASE_TIME, file_extension=FILE_EXTENSION)


def _snapshot(
    path: str,
    content_hash: str = CONTENT_HASH,
    metadata_hash: str = METADATA_HASH,
) -> FileSnapshot:
    return FileSnapshot(
        path=path,
        size=FILE_SIZE,
        mtime=BASE_TIME,
        file_extension=FILE_EXTENSION,
        content_hash=content_hash,
        metadata_hash=metadata_hash,
        metadata=METADATA,
        captured_at=BASE_TIME,
    )


def _absolute(relative_path: str) -> str:
    return f"{LIBRARY_ROOT}/{relative_path}"
