"""
Summary: Tests refresh relocation planning.
Why: Protects Plan-centered tag-correction relocation behavior.
"""

from __future__ import annotations

from collections import deque
from dataclasses import dataclass, replace
from datetime import UTC, datetime, timedelta
from typing import TYPE_CHECKING
from uuid import UUID

import pytest

from omym2.adapters.config.default_config import default_app_config
from omym2.config import (
    OPERATION_RESULT_RETENTION_HOURS,
    OPERATION_TOMBSTONE_RETENTION_DAYS,
    PATH_POLICY_DISC_NUMBER_CONDITION_MULTIPLE_DISCS,
    PATH_POLICY_DISC_NUMBER_STYLE_D_PREFIXED,
)
from omym2.domain.models.app_config import AppConfig, PathPolicyConfig
from omym2.domain.models.file_scan_entry import FileScanEntry
from omym2.domain.models.file_snapshot import FileSnapshot
from omym2.domain.models.library import Library, LibraryStatus
from omym2.domain.models.operation import Operation, OperationKind, OperationStatus, PlanCreatedResult
from omym2.domain.models.plan import Plan, PlanStatus, PlanType
from omym2.domain.models.plan_action import ActionStatus, ActionType, PlanActionReason
from omym2.domain.models.track import Track, TrackStatus
from omym2.domain.models.track_metadata import TrackMetadata
from omym2.domain.services.config_fingerprint import calculate_config_fingerprint, calculate_path_policy_fingerprint
from omym2.domain.services.content_fingerprint import calculate_content_fingerprint
from omym2.domain.services.metadata_fingerprint import calculate_metadata_fingerprint
from omym2.features.refresh.dto import CreateRefreshPlanRequest
from omym2.features.refresh.ports import CreateRefreshPlanPorts
from omym2.features.refresh.usecases.create_refresh_plan import (
    AMBIGUOUS_REGISTERED_LIBRARY_MESSAGE,
    NO_REGISTERED_LIBRARY_MESSAGE,
    REFRESH_TARGET_NOT_FOUND_MESSAGE,
    STALE_LIBRARY_MESSAGE,
    CreateRefreshPlanUseCase,
    RefreshLibrarySelectionError,
    RefreshTargetSelectionError,
)
from omym2.shared.ids import ActionId, LibraryId, OperationId, PlanId, TrackId
from tests.fakes.in_memory_repositories import InMemoryUnitOfWork
from tests.fakes.runtime import FixedClock, MappingArtistNameResolver, SequenceIdGenerator

if TYPE_CHECKING:
    from collections.abc import Sequence

    from omym2.features.common_ports import FileSnapshotCaptureRequest, FileSystemPath

ACTION_ID = ActionId(UUID("018f6a4f-3c2d-7b8a-9abc-def01234567b"))
BASE_TIME = datetime(2026, 1, 1, tzinfo=UTC)
CONTENT_HASH = calculate_content_fingerprint(b"audio")
DUPLICATE_ACTION_ID = ActionId(UUID("018f6a4f-3c2d-7b8a-9abc-def01234567c"))
FILE_EXTENSION = ".flac"
FILE_SIZE = 5
INVALID_PATH_TEMPLATE = "{artist}/../{title}"
LIBRARY_ID = LibraryId(UUID("018f6a4f-3c2d-7b8a-9abc-def012345678"))
LIBRARY_ROOT = "/music/library"
NEW_PATH = "Artist/2026_Album/1-02_New-Title.flac"
NEW_D_PREFIXED_PATH = "Artist/2026_Album/D1-02_New-Title.flac"
NEW_PREFERRED_ARTIST_PATH = "Preferred-Artist/2026_Album/1-02_New-Title.flac"
OLD_PATH = "Artist/2026_Album/1-02_Old-Title.flac"
OTHER_LIBRARY_ID = LibraryId(UUID("018f6a4f-3c2d-7b8a-9abc-def012345680"))
OTHER_LIBRARY_ROOT = "/music/other"
PATH_OUTSIDE_LIBRARY_MESSAGE = "outside library"
PLAN_ID = PlanId(UUID("018f6a4f-3c2d-7b8a-9abc-def01234567a"))
OPERATION_ID = OperationId(UUID("018f6a4f-3c2d-7b8a-9abc-def01234568e"))
IDEMPOTENCY_KEY = UUID("018f6a4f-3c2d-7b8a-9abc-def01234568f")
SECOND_NEW_PATH = "Artist/2026_Album/1-03_Second-New.flac"
SECOND_OLD_PATH = "Artist/2026_Album/1-03_Second-Old.flac"
SECOND_TRACK_ID = TrackId(UUID("018f6a4f-3c2d-7b8a-9abc-def012345681"))
TRACK_ID = TrackId(UUID("018f6a4f-3c2d-7b8a-9abc-def012345679"))

OLD_METADATA = TrackMetadata(
    title="Old Title",
    artist="Artist",
    album="Album",
    year=2026,
    track_number=2,
    disc_number=1,
)
NEW_METADATA = TrackMetadata(
    title="New Title",
    artist="Artist",
    album="Album",
    year=2026,
    track_number=2,
    disc_number=1,
)
SECOND_NEW_METADATA = TrackMetadata(
    title="Second New",
    artist="Artist",
    album="Album",
    year=2026,
    track_number=3,
    disc_number=1,
)
PEER_METADATA = TrackMetadata(
    title="Peer",
    artist="Artist",
    album="Album",
    year=2026,
    track_number=5,
    disc_number=2,
)
MISSING_ARTIST_METADATA = TrackMetadata(
    title="New Title",
    album="Album",
    year=2026,
    track_number=2,
    disc_number=1,
)


def test_refresh_records_existing_track_id_for_relocation_after_metadata_change() -> None:
    """A tag correction relocation keeps the existing Track identity."""
    uow = _uow_with_library_and_tracks(_track())
    source_path = _absolute(OLD_PATH)
    ports, snapshot_reader = _ports(
        uow,
        {source_path: _snapshot(source_path, NEW_METADATA)},
        SequenceIdGenerator(plan_ids=deque((PLAN_ID,)), action_ids=deque((ACTION_ID,))),
    )

    plan = CreateRefreshPlanUseCase(ports).execute(CreateRefreshPlanRequest(trust_stat=False, track_id=TRACK_ID))

    assert snapshot_reader.captured_paths == [source_path]
    assert plan.plan_type == PlanType.REFRESH
    assert plan.status == PlanStatus.READY
    assert plan.config_hash == calculate_config_fingerprint(default_app_config())
    assert plan.library_root_at_plan == LIBRARY_ROOT
    assert plan.summary["action_count"] == "1"
    assert plan.summary["move_actions"] == "1"
    action = plan.actions[0]
    assert action.track_id == TRACK_ID
    assert action.source_path == OLD_PATH
    assert action.target_path == NEW_PATH
    assert action.status == ActionStatus.PLANNED
    assert action.reason is None
    assert action.content_hash_at_plan == CONTENT_HASH
    assert action.metadata_hash_at_plan == calculate_metadata_fingerprint(NEW_METADATA)
    assert uow.plans.get(PLAN_ID) == plan
    assert uow.plan_actions.get(ACTION_ID) == action
    assert uow.tracks.get(TRACK_ID) == _track()


def test_refresh_operation_success_commits_the_created_plan_result() -> None:
    """Orchestrated Refresh links its success to the reviewed Plan it commits."""
    uow = _uow_with_library_and_tracks(_track())
    uow.operations.save(_running_operation())
    source_path = _absolute(OLD_PATH)
    ports, _ = _ports(
        uow,
        {source_path: _snapshot(source_path, NEW_METADATA)},
        SequenceIdGenerator(plan_ids=deque((PLAN_ID,)), action_ids=deque((ACTION_ID,))),
    )

    plan = CreateRefreshPlanUseCase(ports).execute(
        CreateRefreshPlanRequest(trust_stat=False, track_id=TRACK_ID, operation_id=OPERATION_ID)
    )

    terminal = uow.operations.lookup(OPERATION_ID)
    assert isinstance(terminal, Operation)
    assert terminal.status is OperationStatus.SUCCEEDED
    assert terminal.result == PlanCreatedResult(plan.plan_id)
    assert terminal.plan_id == plan.plan_id
    assert terminal.result_expires_at == BASE_TIME + timedelta(hours=OPERATION_RESULT_RETENTION_HOURS)
    assert terminal.tombstone_expires_at == BASE_TIME + timedelta(days=OPERATION_TOMBSTONE_RETENTION_DAYS)
    assert uow.plans.get(plan.plan_id) == plan


def test_refresh_projects_shared_artist_name_resolution_without_updating_raw_track_state() -> None:
    """Refresh records resolver output while leaving the managed Track untouched."""
    config = AppConfig()
    path_policy_hash = calculate_path_policy_fingerprint(
        config.path_policy,
        config.artist_ids,
        config.metadata.album_year_resolution,
        config.artist_names,
    )
    track = _track()
    uow = InMemoryUnitOfWork()
    uow.libraries.save(_library(path_policy_hash=path_policy_hash))
    uow.tracks.save(track)
    source_path = _absolute(OLD_PATH)
    ports, _ = _ports(
        uow,
        {source_path: _snapshot(source_path, NEW_METADATA)},
        SequenceIdGenerator(plan_ids=deque((PLAN_ID,)), action_ids=deque((ACTION_ID,))),
        options=PortOptions(config=config, resolved_names={"Artist": "Preferred Artist"}),
    )

    plan = CreateRefreshPlanUseCase(ports).execute(CreateRefreshPlanRequest(trust_stat=False, track_id=TRACK_ID))

    assert plan.actions[0].target_path == NEW_PREFERRED_ARTIST_PATH
    assert plan.actions[0].metadata_hash_at_plan == calculate_metadata_fingerprint(NEW_METADATA)
    assert uow.tracks.get(TRACK_ID) == track
    assert isinstance(ports.artist_name_resolver, MappingArtistNameResolver)
    assert ports.artist_name_resolver.calls == [("Artist", None)]


def test_refresh_renders_disc_number_from_active_peer_context() -> None:
    """Refresh infers multi-disc context from active tracks and fresh snapshots."""
    config = AppConfig(
        path_policy=PathPolicyConfig(
            disc_number_style=PATH_POLICY_DISC_NUMBER_STYLE_D_PREFIXED,
            disc_number_condition=PATH_POLICY_DISC_NUMBER_CONDITION_MULTIPLE_DISCS,
        )
    )
    uow = InMemoryUnitOfWork()
    uow.libraries.save(
        _library(path_policy_hash=calculate_path_policy_fingerprint(config.path_policy, config.artist_ids))
    )
    uow.tracks.save(_track())
    uow.tracks.save(
        _track(
            SECOND_TRACK_ID,
            "Artist/2026_Album/D2-05_Peer.flac",
            metadata=PEER_METADATA,
        )
    )
    source_path = _absolute(OLD_PATH)
    ports, _ = _ports(
        uow,
        {source_path: _snapshot(source_path, NEW_METADATA)},
        SequenceIdGenerator(plan_ids=deque((PLAN_ID,)), action_ids=deque((ACTION_ID,))),
        options=PortOptions(config=config),
    )

    plan = CreateRefreshPlanUseCase(ports).execute(CreateRefreshPlanRequest(trust_stat=False, track_id=TRACK_ID))

    assert plan.actions[0].target_path == NEW_D_PREFIXED_PATH


def test_refresh_persists_zero_action_plan_when_canonical_path_is_unchanged() -> None:
    """Refresh observes unchanged metadata without updating Track state."""
    track = _track(current_path=NEW_PATH, metadata=NEW_METADATA)
    uow = _uow_with_library_and_tracks(track)
    source_path = _absolute(NEW_PATH)
    ports, _ = _ports(
        uow,
        {source_path: _snapshot(source_path, NEW_METADATA)},
        SequenceIdGenerator(plan_ids=deque((PLAN_ID,))),
    )

    plan = CreateRefreshPlanUseCase(ports).execute(CreateRefreshPlanRequest(trust_stat=False, track_id=TRACK_ID))

    assert plan.actions == ()
    assert plan.summary["action_count"] == "0"
    assert uow.plan_actions.records == {}
    assert uow.plans.get(PLAN_ID) == plan
    assert uow.tracks.get(TRACK_ID) == track


def test_refresh_trust_stat_skips_full_capture_for_matching_unique_track() -> None:
    """Opted-in refresh reuses a complete baseline for one unambiguous active path."""
    track = replace(
        _track(current_path=NEW_PATH, metadata=NEW_METADATA),
        size=FILE_SIZE,
        mtime=BASE_TIME,
    )
    uow = _uow_with_library_and_tracks(track)
    source_path = _absolute(NEW_PATH)
    ports, snapshot_reader = _ports(
        uow,
        {},
        SequenceIdGenerator(plan_ids=deque((PLAN_ID,))),
        options=PortOptions(stat_entries={source_path: _stat_entry(source_path)}),
    )

    plan = CreateRefreshPlanUseCase(ports).execute(CreateRefreshPlanRequest(trust_stat=True, track_id=TRACK_ID))

    assert plan.actions == ()
    assert snapshot_reader.captured_paths == []
    assert uow.tracks.get(TRACK_ID) == track


def test_refresh_trust_stat_full_captures_mismatching_baseline() -> None:
    """A stat mismatch falls back to a fresh full snapshot in opted-in refresh."""
    track = replace(
        _track(current_path=NEW_PATH, metadata=NEW_METADATA),
        size=FILE_SIZE,
        mtime=BASE_TIME,
    )
    uow = _uow_with_library_and_tracks(track)
    source_path = _absolute(NEW_PATH)
    ports, snapshot_reader = _ports(
        uow,
        {source_path: _snapshot(source_path, NEW_METADATA)},
        SequenceIdGenerator(plan_ids=deque((PLAN_ID,))),
        options=PortOptions(stat_entries={source_path: _stat_entry(source_path, size=FILE_SIZE + 1)}),
    )

    plan = CreateRefreshPlanUseCase(ports).execute(CreateRefreshPlanRequest(trust_stat=True, track_id=TRACK_ID))

    assert plan.actions == ()
    assert snapshot_reader.captured_paths == [source_path]


def test_refresh_trust_stat_full_captures_duplicate_active_path() -> None:
    """Duplicate active Track paths cannot derive a shared synthetic snapshot."""
    first = replace(_track(), size=FILE_SIZE, mtime=BASE_TIME)
    second = replace(_track(SECOND_TRACK_ID, OLD_PATH), size=FILE_SIZE, mtime=BASE_TIME)
    uow = _uow_with_library_and_tracks(first, second)
    source_path = _absolute(OLD_PATH)
    ports, snapshot_reader = _ports(
        uow,
        {source_path: _snapshot(source_path, NEW_METADATA)},
        SequenceIdGenerator(
            plan_ids=deque((PLAN_ID,)),
            action_ids=deque((ACTION_ID, DUPLICATE_ACTION_ID)),
        ),
        options=PortOptions(stat_entries={source_path: _stat_entry(source_path)}),
    )

    _ = CreateRefreshPlanUseCase(ports).execute(CreateRefreshPlanRequest(trust_stat=True, include_all=True))

    assert snapshot_reader.captured_paths == [source_path, source_path]


def test_refresh_plans_metadata_action_when_hashes_change_without_relocation() -> None:
    """A metadata-only tag edit is persisted through apply as a reviewed action."""
    metadata_same_path = TrackMetadata(
        title="New Title",
        artist="Artist",
        album="Album",
        year=2026,
        track_number=2,
        disc_number=1,
    )
    unchanged_path = NEW_PATH
    uow = _uow_with_library_and_tracks(_track(current_path=unchanged_path, metadata=OLD_METADATA))
    source_path = _absolute(unchanged_path)
    ports, _ = _ports(
        uow,
        {source_path: _snapshot(source_path, metadata_same_path)},
        SequenceIdGenerator(plan_ids=deque((PLAN_ID,)), action_ids=deque((ACTION_ID,))),
    )

    plan = CreateRefreshPlanUseCase(ports).execute(CreateRefreshPlanRequest(trust_stat=False, track_id=TRACK_ID))

    assert plan.summary["action_count"] == "1"
    assert plan.summary["move_actions"] == "0"
    assert plan.summary["metadata_actions"] == "1"
    action = plan.actions[0]
    assert action.action_type == ActionType.REFRESH_METADATA
    assert action.source_path == unchanged_path
    assert action.target_path == unchanged_path
    assert action.status == ActionStatus.PLANNED
    assert action.metadata_hash_at_plan == calculate_metadata_fingerprint(metadata_same_path)


def test_refresh_selects_exact_file_target() -> None:
    """An exact Library file target refreshes only that managed Track."""
    uow = _uow_with_library_and_tracks(_track(), _track(SECOND_TRACK_ID, SECOND_OLD_PATH))
    source_path = _absolute(OLD_PATH)
    ports, _ = _ports(
        uow,
        {source_path: _snapshot(source_path, NEW_METADATA)},
        SequenceIdGenerator(plan_ids=deque((PLAN_ID,)), action_ids=deque((ACTION_ID,))),
    )

    plan = CreateRefreshPlanUseCase(ports).execute(CreateRefreshPlanRequest(trust_stat=False, target_path=source_path))

    assert len(plan.actions) == 1
    assert plan.actions[0].source_path == OLD_PATH
    assert plan.actions[0].track_id == TRACK_ID


def test_refresh_selects_directory_target_prefix() -> None:
    """A Library directory target refreshes managed Tracks below that prefix."""
    uow = _uow_with_library_and_tracks(_track(), _track(SECOND_TRACK_ID, SECOND_OLD_PATH))
    ports, _ = _ports(
        uow,
        {
            _absolute(OLD_PATH): _snapshot(_absolute(OLD_PATH), NEW_METADATA),
            _absolute(SECOND_OLD_PATH): _snapshot(_absolute(SECOND_OLD_PATH), SECOND_NEW_METADATA),
        },
        SequenceIdGenerator(
            plan_ids=deque((PLAN_ID,)),
            action_ids=deque((ACTION_ID, DUPLICATE_ACTION_ID)),
        ),
    )

    plan = CreateRefreshPlanUseCase(ports).execute(
        CreateRefreshPlanRequest(trust_stat=False, target_path=_absolute("Artist/2026_Album"))
    )

    assert tuple(action.source_path for action in plan.actions) == (OLD_PATH, SECOND_OLD_PATH)
    assert tuple(action.target_path for action in plan.actions) == (NEW_PATH, SECOND_NEW_PATH)


def test_refresh_all_selects_all_active_tracks() -> None:
    """--all style refresh ignores removed Tracks and keeps active ones."""
    removed_track = _track(
        TrackId(UUID("018f6a4f-3c2d-7b8a-9abc-def012345682")),
        "Removed/Track.flac",
        status=TrackStatus.REMOVED,
    )
    uow = _uow_with_library_and_tracks(_track(), _track(SECOND_TRACK_ID, SECOND_OLD_PATH), removed_track)
    ports, _ = _ports(
        uow,
        {
            _absolute(OLD_PATH): _snapshot(_absolute(OLD_PATH), NEW_METADATA),
            _absolute(SECOND_OLD_PATH): _snapshot(_absolute(SECOND_OLD_PATH), SECOND_NEW_METADATA),
        },
        SequenceIdGenerator(
            plan_ids=deque((PLAN_ID,)),
            action_ids=deque((ACTION_ID, DUPLICATE_ACTION_ID)),
        ),
    )

    plan = CreateRefreshPlanUseCase(ports).execute(CreateRefreshPlanRequest(trust_stat=False, include_all=True))

    assert plan.summary["action_count"] == "2"
    assert tuple(action.track_id for action in plan.actions) == (TRACK_ID, SECOND_TRACK_ID)


def test_refresh_resolves_latest_album_year_across_selected_album_group() -> None:
    """Refresh uses a single effective album year for mixed-year tracks."""
    older_metadata = _album_track_metadata(title="Song 1", year=1998, track_number=1)
    latest_metadata = _album_track_metadata(title="Song 2", year=2004, track_number=2)
    older_path = "Artist/1998_Album/1-01_Song-1.flac"
    latest_path = "Artist/2004_Album/1-02_Song-2.flac"
    uow = _uow_with_library_and_tracks(
        _track(current_path=older_path, metadata=older_metadata),
        _track(SECOND_TRACK_ID, latest_path, metadata=latest_metadata),
    )
    ports, _ = _ports(
        uow,
        {
            _absolute(older_path): _snapshot(_absolute(older_path), older_metadata),
            _absolute(latest_path): _snapshot(_absolute(latest_path), latest_metadata),
        },
        SequenceIdGenerator(plan_ids=deque((PLAN_ID,)), action_ids=deque((ACTION_ID,))),
    )

    plan = CreateRefreshPlanUseCase(ports).execute(CreateRefreshPlanRequest(trust_stat=False, include_all=True))

    assert plan.summary["action_count"] == "1"
    action = plan.actions[0]
    assert action.track_id == TRACK_ID
    assert action.source_path == older_path
    assert action.target_path == "Artist/2004_Album/1-01_Song-1.flac"
    assert uow.tracks.get(TRACK_ID) == _track(current_path=older_path, metadata=older_metadata)


def test_refresh_refuses_when_no_registered_library_can_be_selected() -> None:
    """Refresh does not guess a Library before registration."""
    ports, _ = _ports(InMemoryUnitOfWork(), {}, SequenceIdGenerator())

    with pytest.raises(RefreshLibrarySelectionError, match=NO_REGISTERED_LIBRARY_MESSAGE):
        _ = CreateRefreshPlanUseCase(ports).execute(CreateRefreshPlanRequest(trust_stat=False, include_all=True))


def test_refresh_refuses_ambiguous_registered_libraries() -> None:
    """Refresh requires one registered Library unless a Library ID is supplied."""
    uow = _uow_with_library_and_tracks(_track())
    uow.libraries.save(_library(OTHER_LIBRARY_ID, OTHER_LIBRARY_ROOT))
    ports, _ = _ports(uow, {}, SequenceIdGenerator())

    with pytest.raises(RefreshLibrarySelectionError, match=AMBIGUOUS_REGISTERED_LIBRARY_MESSAGE):
        _ = CreateRefreshPlanUseCase(ports).execute(CreateRefreshPlanRequest(trust_stat=False, include_all=True))


def test_refresh_refuses_stale_path_policy_registration() -> None:
    """Refresh requires registration under the current PathPolicy."""
    uow = InMemoryUnitOfWork()
    uow.libraries.save(_library(path_policy_hash="old-path-policy-hash"))
    uow.tracks.save(_track())
    ports, _ = _ports(uow, {}, SequenceIdGenerator())

    with pytest.raises(RefreshLibrarySelectionError, match=STALE_LIBRARY_MESSAGE):
        _ = CreateRefreshPlanUseCase(ports).execute(CreateRefreshPlanRequest(trust_stat=False, include_all=True))


def test_refresh_refuses_unmatched_target() -> None:
    """A target path must select at least one active managed Track."""
    uow = _uow_with_library_and_tracks(_track())
    ports, _ = _ports(uow, {}, SequenceIdGenerator())

    with pytest.raises(RefreshTargetSelectionError, match=REFRESH_TARGET_NOT_FOUND_MESSAGE):
        _ = CreateRefreshPlanUseCase(ports).execute(
            CreateRefreshPlanRequest(trust_stat=False, target_path=_absolute("Missing"))
        )


def test_refresh_blocks_missing_source() -> None:
    """A missing managed source becomes a blocked refresh action."""
    source_path = _absolute(OLD_PATH)
    plan = _single_action_plan({}, missing_paths={source_path})

    action = plan.actions[0]
    assert action.status == ActionStatus.BLOCKED
    assert action.reason == PlanActionReason.SOURCE_MISSING
    assert action.source_path == OLD_PATH
    assert action.target_path is None
    assert action.track_id == TRACK_ID


def test_refresh_blocks_missing_required_metadata() -> None:
    """Missing required refreshed metadata blocks relocation planning."""
    source_path = _absolute(OLD_PATH)
    plan = _single_action_plan({source_path: _snapshot(source_path, MISSING_ARTIST_METADATA)})

    action = plan.actions[0]
    assert action.status == ActionStatus.BLOCKED
    assert action.reason == PlanActionReason.MISSING_REQUIRED_METADATA
    assert action.target_path is None


def test_refresh_blocks_invalid_generated_target() -> None:
    """Invalid generated Library paths are stored as blocked actions."""
    source_path = _absolute(OLD_PATH)
    config = AppConfig(path_policy=PathPolicyConfig(template=INVALID_PATH_TEMPLATE, sanitize=False))
    plan = _single_action_plan({source_path: _snapshot(source_path, NEW_METADATA)}, config=config)

    action = plan.actions[0]
    assert action.status == ActionStatus.BLOCKED
    assert action.reason == PlanActionReason.INVALID_PATH
    assert action.target_path is None


def test_refresh_blocks_duplicate_planned_targets() -> None:
    """Two refreshed Tracks may not plan the same destination."""
    other_old_path = "Other/1-03_Second Old.flac"
    uow = _uow_with_library_and_tracks(_track(), _track(SECOND_TRACK_ID, other_old_path))
    ports, _ = _ports(
        uow,
        {
            _absolute(OLD_PATH): _snapshot(_absolute(OLD_PATH), NEW_METADATA),
            _absolute(other_old_path): _snapshot(_absolute(other_old_path), NEW_METADATA),
        },
        SequenceIdGenerator(
            plan_ids=deque((PLAN_ID,)),
            action_ids=deque((ACTION_ID, DUPLICATE_ACTION_ID)),
        ),
    )

    plan = CreateRefreshPlanUseCase(ports).execute(CreateRefreshPlanRequest(trust_stat=False, include_all=True))

    assert tuple(action.status for action in plan.actions) == (ActionStatus.BLOCKED, ActionStatus.BLOCKED)
    assert tuple(action.reason for action in plan.actions) == (
        PlanActionReason.TARGET_EXISTS,
        PlanActionReason.TARGET_EXISTS,
    )


def test_refresh_blocks_db_target_conflict() -> None:
    """A refreshed Track may not target another managed Track's current path."""
    uow = _uow_with_library_and_tracks(_track(), _track(SECOND_TRACK_ID, NEW_PATH, metadata=NEW_METADATA))
    source_path = _absolute(OLD_PATH)
    ports, _ = _ports(
        uow,
        {source_path: _snapshot(source_path, NEW_METADATA)},
        SequenceIdGenerator(plan_ids=deque((PLAN_ID,)), action_ids=deque((ACTION_ID,))),
    )

    plan = CreateRefreshPlanUseCase(ports).execute(CreateRefreshPlanRequest(trust_stat=False, track_id=TRACK_ID))

    action = plan.actions[0]
    assert action.status == ActionStatus.BLOCKED
    assert action.reason == PlanActionReason.TARGET_EXISTS
    assert action.target_path == NEW_PATH


def test_refresh_blocks_filesystem_target_conflict() -> None:
    """A refreshed Track may not target an occupied filesystem path."""
    source_path = _absolute(OLD_PATH)
    plan = _single_action_plan(
        {source_path: _snapshot(source_path, NEW_METADATA)},
        existing_files={_absolute(NEW_PATH)},
    )

    action = plan.actions[0]
    assert action.status == ActionStatus.BLOCKED
    assert action.reason == PlanActionReason.TARGET_EXISTS
    assert action.target_path == NEW_PATH


class StaticConfigStore:
    """ConfigStore fake returning one AppConfig."""

    def __init__(self, config: AppConfig | None = None) -> None:
        """Store the config returned by load."""
        self._config: AppConfig = default_app_config() if config is None else config

    def load(self) -> AppConfig:
        """Return the configured AppConfig."""
        return self._config

    def save(self, config: AppConfig) -> None:
        """Accept saves to satisfy the ConfigStore protocol."""
        del config


class MappingSnapshotReader:
    """FileSnapshotReader fake keyed by filesystem path text."""

    def __init__(self, snapshots: dict[str, FileSnapshot], missing_paths: set[str] | None = None) -> None:
        """Store snapshots and optional paths missing at refresh time."""
        self._snapshots: dict[str, FileSnapshot] = snapshots
        self._missing_paths: set[str] = set() if missing_paths is None else set(missing_paths)
        self.captured_paths: list[FileSystemPath] = []

    def capture(self, path: FileSystemPath) -> FileSnapshot:
        """Return a snapshot or raise FileNotFoundError for vanished files."""
        self.captured_paths.append(path)
        path_key = str(path)
        if path_key in self._missing_paths:
            raise FileNotFoundError(path_key)
        return self._snapshots[path_key]

    def capture_many(
        self,
        requests: Sequence[FileSnapshotCaptureRequest],
    ) -> tuple[FileSnapshot | None, ...]:
        """Capture requests serially while preserving the production batch contract."""
        snapshots: list[FileSnapshot | None] = []
        for request in requests:
            try:
                snapshots.append(self.capture(request.path))
            except FileNotFoundError:
                snapshots.append(None)
        return tuple(snapshots)


class StaticFileStatReader:
    """FileStatReader fake keyed by filesystem path text."""

    def __init__(self, entries: dict[str, FileScanEntry] | None = None) -> None:
        """Store the cheap observations available at refresh time."""
        self._entries: dict[str, FileScanEntry] = {} if entries is None else entries

    def observe(self, path: FileSystemPath) -> FileScanEntry:
        """Return an observation or report that the managed source disappeared."""
        path_text = str(path)
        try:
            return self._entries[path_text]
        except KeyError as exc:
            raise FileNotFoundError(path_text) from exc


class StaticFilePresence:
    """FilePresence fake keyed by path text."""

    def __init__(self, existing_files: set[str] | None = None) -> None:
        """Store paths that should be reported as present."""
        self._existing_files: set[str] = set() if existing_files is None else set(existing_files)

    def exists(self, path: FileSystemPath) -> bool:
        """Return whether path was configured as present."""
        return str(path) in self._existing_files


class SimplePathResolver:
    """PathResolver fake for Library-relative refresh paths."""

    def resolve_library_path(self, library_root: FileSystemPath, library_relative_path: str) -> str:
        """Join root and Library-relative path for tests."""
        return f"{str(library_root).rstrip('/')}/{library_relative_path}"

    def relative_to_library(self, library_root: FileSystemPath, path: FileSystemPath) -> str:
        """Return a Library-relative path for absolute target selections."""
        root = str(library_root).rstrip("/")
        path_text = str(path)
        expected_prefix = f"{root}/"
        if not path_text.startswith(expected_prefix):
            raise ValueError(PATH_OUTSIDE_LIBRARY_MESSAGE)
        return path_text.removeprefix(expected_prefix)


@dataclass(frozen=True, slots=True)
class PortOptions:
    """Optional fake settings for CreateRefreshPlanPorts."""

    config: AppConfig | None = None
    existing_files: set[str] | None = None
    missing_paths: set[str] | None = None
    stat_entries: dict[str, FileScanEntry] | None = None
    resolved_names: dict[str, str] | None = None


def _ports(
    uow: InMemoryUnitOfWork,
    snapshots: dict[str, FileSnapshot],
    id_generator: SequenceIdGenerator,
    *,
    options: PortOptions | None = None,
) -> tuple[CreateRefreshPlanPorts, MappingSnapshotReader]:
    port_options = PortOptions() if options is None else options
    snapshot_reader = MappingSnapshotReader(snapshots, port_options.missing_paths)
    ports = CreateRefreshPlanPorts(
        uow=uow,
        file_snapshot_reader=snapshot_reader,
        file_stat_reader=StaticFileStatReader(port_options.stat_entries),
        file_presence=StaticFilePresence(port_options.existing_files),
        config_store=StaticConfigStore(port_options.config),
        artist_name_resolver=MappingArtistNameResolver(port_options.resolved_names or {}),
        path_resolver=SimplePathResolver(),
        clock=FixedClock(BASE_TIME),
        id_generator=id_generator,
    )
    return ports, snapshot_reader


def _single_action_plan(
    snapshots: dict[str, FileSnapshot],
    *,
    config: AppConfig | None = None,
    existing_files: set[str] | None = None,
    missing_paths: set[str] | None = None,
) -> Plan:
    uow = InMemoryUnitOfWork()
    active_config = default_app_config() if config is None else config
    uow.libraries.save(
        _library(
            path_policy_hash=calculate_path_policy_fingerprint(active_config.path_policy, active_config.artist_ids)
        )
    )
    uow.tracks.save(_track())
    ports, _ = _ports(
        uow,
        snapshots,
        SequenceIdGenerator(plan_ids=deque((PLAN_ID,)), action_ids=deque((ACTION_ID,))),
        options=PortOptions(config=config, existing_files=existing_files, missing_paths=missing_paths),
    )
    return CreateRefreshPlanUseCase(ports).execute(CreateRefreshPlanRequest(trust_stat=False, track_id=TRACK_ID))


def _uow_with_library_and_tracks(*tracks: Track) -> InMemoryUnitOfWork:
    uow = InMemoryUnitOfWork()
    uow.libraries.save(_library())
    for track in tracks:
        uow.tracks.save(track)
    return uow


def _library(
    library_id: LibraryId = LIBRARY_ID,
    root_path: str = LIBRARY_ROOT,
    *,
    path_policy_hash: str | None = None,
) -> Library:
    return Library(
        library_id=library_id,
        root_path=root_path,
        path_policy_hash=(
            calculate_path_policy_fingerprint(default_app_config().path_policy, default_app_config().artist_ids)
            if path_policy_hash is None
            else path_policy_hash
        ),
        registered_at=BASE_TIME,
        status=LibraryStatus.REGISTERED,
        created_at=BASE_TIME,
        updated_at=BASE_TIME,
    )


def _track(
    track_id: TrackId = TRACK_ID,
    current_path: str = OLD_PATH,
    *,
    metadata: TrackMetadata = OLD_METADATA,
    status: TrackStatus = TrackStatus.ACTIVE,
) -> Track:
    return Track(
        track_id=track_id,
        library_id=LIBRARY_ID,
        current_path=current_path,
        canonical_path=current_path,
        content_hash=CONTENT_HASH,
        metadata_hash=calculate_metadata_fingerprint(metadata),
        size=None,
        mtime=None,
        metadata=metadata,
        status=status,
        first_seen_at=BASE_TIME,
        last_seen_at=BASE_TIME,
        updated_at=BASE_TIME,
    )


def _running_operation() -> Operation:
    return Operation.queued(
        operation_id=OPERATION_ID,
        kind=OperationKind.REFRESH_PLAN,
        idempotency_key=IDEMPOTENCY_KEY,
        request_fingerprint="refresh-request",
        requested_at=BASE_TIME,
        library_id=LIBRARY_ID,
    ).mark_running(BASE_TIME)


def _snapshot(path: str, metadata: TrackMetadata) -> FileSnapshot:
    return FileSnapshot(
        path=path,
        size=FILE_SIZE,
        mtime=BASE_TIME,
        file_extension=FILE_EXTENSION,
        content_hash=CONTENT_HASH,
        metadata_hash=calculate_metadata_fingerprint(metadata),
        metadata=metadata,
        filesystem_identity=None,
        captured_at=BASE_TIME,
    )


def _stat_entry(path: str, *, size: int = FILE_SIZE) -> FileScanEntry:
    return FileScanEntry(
        path=path,
        size=size,
        mtime=BASE_TIME,
        file_extension=FILE_EXTENSION,
    )


def _absolute(relative_path: str) -> str:
    return f"{LIBRARY_ROOT}/{relative_path}"


def _album_track_metadata(title: str, year: int | None, track_number: int) -> TrackMetadata:
    return TrackMetadata(
        title=title,
        artist="Artist",
        album="Album",
        album_artist="Artist",
        year=year,
        track_number=track_number,
        disc_number=1,
    )
