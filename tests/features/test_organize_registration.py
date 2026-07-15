"""
Summary: Tests organize registration behavior.
Why: Protects Library registration and review-plan creation before apply exists.
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
from omym2.domain.models.operation import (
    Operation,
    OperationKind,
    OperationStatus,
    PlanCreatedResult,
    RegisteredWithoutPlanResult,
)
from omym2.domain.models.plan import PlanStatus, PlanType
from omym2.domain.models.plan_action import ActionStatus, PlanActionReason
from omym2.domain.models.track import Track, TrackStatus
from omym2.domain.models.track_metadata import TrackMetadata
from omym2.domain.services.config_fingerprint import calculate_config_fingerprint, calculate_path_policy_fingerprint
from omym2.domain.services.content_fingerprint import calculate_content_fingerprint
from omym2.domain.services.metadata_fingerprint import calculate_metadata_fingerprint
from omym2.features.organize.dto import CreateOrganizePlanRequest
from omym2.features.organize.ports import CreateOrganizePlanPorts
from omym2.features.organize.usecases.create_organize_plan import (
    AMBIGUOUS_LIBRARY_SELECTION_MESSAGE,
    NO_LIBRARY_SELECTION_MESSAGE,
    UNREGISTERED_PATH_MESSAGE,
    CreateOrganizePlanUseCase,
    OrganizeLibrarySelectionError,
)
from omym2.shared.ids import ActionId, LibraryId, OperationId, PlanId, TrackId
from tests.fakes.in_memory_repositories import InMemoryUnitOfWork
from tests.fakes.runtime import FixedClock, MappingArtistNameResolver, SequenceIdGenerator

if TYPE_CHECKING:
    from collections.abc import Sequence

    from omym2.features.common_ports import FileSnapshotCaptureRequest, FileSystemPath

ACTION_ID = ActionId(UUID("018f6a4f-3c2d-7b8a-9abc-def01234567b"))
BASE_TIME = datetime(2026, 1, 1, tzinfo=UTC)
CONTENT = b"audio"
CONTENT_HASH = calculate_content_fingerprint(CONTENT)
EXPECTED_CANONICAL_PATH = "Artist/2026_Album/1-02_Title.flac"
EXPECTED_D_PREFIXED_PATH = "Artist/2026_Album/D1-02_Title.flac"
EXPECTED_PREFERRED_ARTIST_PATH = "Preferred-Artist/2026_Album/1-02_Title.flac"
EXPECTED_SECOND_D_PREFIXED_PATH = "Artist/2026_Album/D2-03_Second-Title.flac"
FILE_EXTENSION = ".flac"
FILE_SIZE = 5
LIBRARY_ID = LibraryId(UUID("018f6a4f-3c2d-7b8a-9abc-def012345678"))
LIBRARY_ROOT = "/music/library"
METADATA = TrackMetadata(
    title="Title",
    artist="Artist",
    album="Album",
    year=2026,
    track_number=2,
    disc_number=1,
)
MISSING_ARTIST_METADATA = TrackMetadata(
    title="Title",
    album="Album",
    year=2026,
    track_number=2,
    disc_number=1,
)
MISPLACED_PATH = "Unsorted/Title.flac"
PLAN_ID = PlanId(UUID("018f6a4f-3c2d-7b8a-9abc-def01234567a"))
OPERATION_ID = OperationId(UUID("018f6a4f-3c2d-7b8a-9abc-def01234568e"))
IDEMPOTENCY_KEY = UUID("018f6a4f-3c2d-7b8a-9abc-def01234568f")
SECOND_ACTION_ID = ActionId(UUID("018f6a4f-3c2d-7b8a-9abc-def01234567c"))
SECOND_LIBRARY_ID = LibraryId(UUID("018f6a4f-3c2d-7b8a-9abc-def012345680"))
SECOND_LIBRARY_ROOT = "/music/other"
SECOND_TRACK_ID = TrackId(UUID("018f6a4f-3c2d-7b8a-9abc-def012345681"))
THIRD_ACTION_ID = ActionId(UUID("018f6a4f-3c2d-7b8a-9abc-def01234567d"))
THIRD_TRACK_ID = TrackId(UUID("018f6a4f-3c2d-7b8a-9abc-def012345682"))
SECOND_METADATA = TrackMetadata(
    title="Second Title",
    artist="Artist",
    album="Album",
    year=2026,
    track_number=3,
    disc_number=2,
)
TRACK_ID = TrackId(UUID("018f6a4f-3c2d-7b8a-9abc-def012345679"))
UNREGISTERED_LIBRARY_ROOT = "/music/new"
PATH_OUTSIDE_LIBRARY_MESSAGE = "outside library"

CANONICAL_ABSOLUTE_PATH = f"{LIBRARY_ROOT}/{EXPECTED_CANONICAL_PATH}"
MISPLACED_ABSOLUTE_PATH = f"{LIBRARY_ROOT}/{MISPLACED_PATH}"


def test_organize_registers_clean_library_without_mutation_plan() -> None:
    """A clean first Library is registered and tracked without creating a Plan."""
    uow = InMemoryUnitOfWork()
    entry = _entry(CANONICAL_ABSOLUTE_PATH)
    ports, scanner, snapshot_reader = _ports(
        uow,
        (entry,),
        {CANONICAL_ABSOLUTE_PATH: _snapshot(CANONICAL_ABSOLUTE_PATH, METADATA)},
        SequenceIdGenerator(library_ids=deque((LIBRARY_ID,)), track_ids=deque((TRACK_ID,))),
    )

    result = CreateOrganizePlanUseCase(ports).execute(
        CreateOrganizePlanRequest(trust_stat=False, library_root=LIBRARY_ROOT)
    )

    assert scanner.scanned_roots == [LIBRARY_ROOT]
    assert snapshot_reader.captured_paths == [CANONICAL_ABSOLUTE_PATH]
    assert result.plan is None
    assert result.actions == ()
    assert result.track_count == 1
    assert result.library.status == LibraryStatus.REGISTERED
    assert result.library.registered_at == BASE_TIME
    assert result.library.path_policy_hash == calculate_path_policy_fingerprint(
        default_app_config().path_policy,
        default_app_config().artist_ids,
    )
    assert uow.libraries.get(LIBRARY_ID) == result.library
    track = uow.tracks.get(TRACK_ID)
    assert track is not None
    assert track.current_path == EXPECTED_CANONICAL_PATH
    assert track.canonical_path == EXPECTED_CANONICAL_PATH
    assert track.content_hash == CONTENT_HASH
    assert track.size == FILE_SIZE
    assert track.mtime == BASE_TIME
    assert uow.plans.list_by_library(LIBRARY_ID) == ()
    assert uow.commit_count == 1


def test_organize_operation_success_records_clean_registration_result() -> None:
    """A clean orchestrated registration links its Library and persisted Track count."""
    uow = InMemoryUnitOfWork()
    uow.operations.save(_running_operation())
    ports, _, _ = _ports(
        uow,
        (_entry(CANONICAL_ABSOLUTE_PATH),),
        {CANONICAL_ABSOLUTE_PATH: _snapshot(CANONICAL_ABSOLUTE_PATH, METADATA)},
        SequenceIdGenerator(library_ids=deque((LIBRARY_ID,)), track_ids=deque((TRACK_ID,))),
    )

    result = CreateOrganizePlanUseCase(ports).execute(
        CreateOrganizePlanRequest(trust_stat=False, library_root=LIBRARY_ROOT, operation_id=OPERATION_ID)
    )

    terminal = uow.operations.lookup(OPERATION_ID)
    assert isinstance(terminal, Operation)
    assert terminal.status is OperationStatus.SUCCEEDED
    assert terminal.result == RegisteredWithoutPlanResult(result.library.library_id, result.track_count)
    assert terminal.library_id == result.library.library_id
    assert terminal.result_expires_at == BASE_TIME + timedelta(hours=OPERATION_RESULT_RETENTION_HOURS)
    assert terminal.tombstone_expires_at == BASE_TIME + timedelta(days=OPERATION_TOMBSTONE_RETENTION_DAYS)


def test_organize_trust_stat_skips_full_capture_for_matching_active_track() -> None:
    """Opted-in organize reconstructs a snapshot only from a complete matching baseline."""
    uow = InMemoryUnitOfWork()
    uow.libraries.save(_library(LIBRARY_ID, LIBRARY_ROOT))
    uow.tracks.save(_track(size=FILE_SIZE, mtime=BASE_TIME))
    ports, _, snapshot_reader = _ports(
        uow,
        (_entry(CANONICAL_ABSOLUTE_PATH),),
        {},
        SequenceIdGenerator(),
    )

    result = CreateOrganizePlanUseCase(ports).execute(
        CreateOrganizePlanRequest(trust_stat=True, library_root=LIBRARY_ROOT)
    )

    assert snapshot_reader.captured_paths == []
    assert result.plan is None
    assert result.track_count == 1
    assert uow.tracks.get(TRACK_ID) is not None


def test_organize_trust_stat_preserves_unique_active_track_when_removed_track_shares_path() -> None:
    """Stat trust and persistence select the same unique active Track identity."""
    uow = InMemoryUnitOfWork()
    uow.libraries.save(_library(LIBRARY_ID, LIBRARY_ROOT))
    active_track = _track(size=FILE_SIZE, mtime=BASE_TIME)
    removed_track = replace(
        _track(track_id=SECOND_TRACK_ID, size=FILE_SIZE, mtime=BASE_TIME),
        status=TrackStatus.REMOVED,
    )
    uow.tracks.save(active_track)
    uow.tracks.save(removed_track)
    ports, _, snapshot_reader = _ports(
        uow,
        (_entry(CANONICAL_ABSOLUTE_PATH),),
        {},
        SequenceIdGenerator(),
    )

    result = CreateOrganizePlanUseCase(ports).execute(
        CreateOrganizePlanRequest(trust_stat=True, library_root=LIBRARY_ROOT)
    )

    assert snapshot_reader.captured_paths == []
    assert result.plan is None
    persisted_active_track = uow.tracks.get(TRACK_ID)
    assert persisted_active_track is not None
    assert persisted_active_track.status == TrackStatus.ACTIVE
    assert uow.tracks.get(SECOND_TRACK_ID) == removed_track


def test_organize_trust_stat_full_captures_track_without_complete_baseline() -> None:
    """An opted-in organize still hashes when an existing Track has no verified baseline."""
    uow = InMemoryUnitOfWork()
    uow.libraries.save(_library(LIBRARY_ID, LIBRARY_ROOT))
    uow.tracks.save(_track())
    ports, _, snapshot_reader = _ports(
        uow,
        (_entry(CANONICAL_ABSOLUTE_PATH),),
        {CANONICAL_ABSOLUTE_PATH: _snapshot(CANONICAL_ABSOLUTE_PATH, METADATA)},
        SequenceIdGenerator(),
    )

    _ = CreateOrganizePlanUseCase(ports).execute(CreateOrganizePlanRequest(trust_stat=True, library_root=LIBRARY_ROOT))

    assert snapshot_reader.captured_paths == [CANONICAL_ABSOLUTE_PATH]


def test_organize_trust_stat_full_captures_duplicate_active_path() -> None:
    """Ambiguous duplicate active Track paths are never eligible for stat trust."""
    uow = InMemoryUnitOfWork()
    uow.libraries.save(_library(LIBRARY_ID, LIBRARY_ROOT))
    uow.tracks.save(_track(size=FILE_SIZE, mtime=BASE_TIME))
    uow.tracks.save(_track(track_id=SECOND_TRACK_ID, size=FILE_SIZE, mtime=BASE_TIME))
    ports, _, snapshot_reader = _ports(
        uow,
        (_entry(CANONICAL_ABSOLUTE_PATH),),
        {CANONICAL_ABSOLUTE_PATH: _snapshot(CANONICAL_ABSOLUTE_PATH, METADATA)},
        SequenceIdGenerator(),
    )

    _ = CreateOrganizePlanUseCase(ports).execute(CreateOrganizePlanRequest(trust_stat=True, library_root=LIBRARY_ROOT))

    assert snapshot_reader.captured_paths == [CANONICAL_ABSOLUTE_PATH]


def test_organize_creates_plan_for_misplaced_library_file() -> None:
    """A misplaced Library file creates a reviewed organize move action."""
    uow = InMemoryUnitOfWork()
    ports, _, _ = _ports(
        uow,
        (_entry(MISPLACED_ABSOLUTE_PATH),),
        {MISPLACED_ABSOLUTE_PATH: _snapshot(MISPLACED_ABSOLUTE_PATH, METADATA)},
        SequenceIdGenerator(
            library_ids=deque((LIBRARY_ID,)),
            track_ids=deque((TRACK_ID,)),
            plan_ids=deque((PLAN_ID,)),
            action_ids=deque((ACTION_ID,)),
        ),
    )

    result = CreateOrganizePlanUseCase(ports).execute(
        CreateOrganizePlanRequest(trust_stat=False, library_root=LIBRARY_ROOT)
    )

    plan = result.plan
    assert plan is not None
    assert plan.plan_type == PlanType.ORGANIZE
    assert plan.status == PlanStatus.READY
    assert plan.config_hash == calculate_config_fingerprint(default_app_config())
    assert result.library.status == LibraryStatus.UNREGISTERED
    assert result.library.registered_at is None
    action = result.actions[0]
    assert action.status == ActionStatus.PLANNED
    assert action.reason is None
    assert action.source_path == MISPLACED_PATH
    assert action.target_path == EXPECTED_CANONICAL_PATH
    assert action.track_id == TRACK_ID
    assert action.content_hash_at_plan == CONTENT_HASH
    assert uow.plan_actions.get(ACTION_ID) == action
    track = uow.tracks.get(TRACK_ID)
    assert track is not None
    assert track.current_path == MISPLACED_PATH
    assert track.canonical_path == EXPECTED_CANONICAL_PATH


def test_organize_operation_success_records_created_plan_result() -> None:
    """An orchestrated misplaced scan links the reviewed Plan committed with success."""
    uow = InMemoryUnitOfWork()
    uow.operations.save(_running_operation())
    ports, _, _ = _ports(
        uow,
        (_entry(MISPLACED_ABSOLUTE_PATH),),
        {MISPLACED_ABSOLUTE_PATH: _snapshot(MISPLACED_ABSOLUTE_PATH, METADATA)},
        SequenceIdGenerator(
            library_ids=deque((LIBRARY_ID,)),
            track_ids=deque((TRACK_ID,)),
            plan_ids=deque((PLAN_ID,)),
            action_ids=deque((ACTION_ID,)),
        ),
    )

    result = CreateOrganizePlanUseCase(ports).execute(
        CreateOrganizePlanRequest(trust_stat=False, library_root=LIBRARY_ROOT, operation_id=OPERATION_ID)
    )

    assert result.plan is not None
    terminal = uow.operations.lookup(OPERATION_ID)
    assert isinstance(terminal, Operation)
    assert terminal.status is OperationStatus.SUCCEEDED
    assert terminal.result == PlanCreatedResult(result.plan.plan_id)
    assert terminal.plan_id == result.plan.plan_id


def test_organize_projects_shared_artist_name_resolution_while_storing_raw_metadata() -> None:
    """Organize reconciles resolver output without replacing persisted tag metadata."""
    config = AppConfig()
    uow = InMemoryUnitOfWork()
    ports, _, _ = _ports(
        uow,
        (_entry(MISPLACED_ABSOLUTE_PATH),),
        {MISPLACED_ABSOLUTE_PATH: _snapshot(MISPLACED_ABSOLUTE_PATH, METADATA)},
        SequenceIdGenerator(
            library_ids=deque((LIBRARY_ID,)),
            track_ids=deque((TRACK_ID,)),
            plan_ids=deque((PLAN_ID,)),
            action_ids=deque((ACTION_ID,)),
        ),
        options=PortOptions(config=config, resolved_names={"Artist": "Preferred Artist"}),
    )

    result = CreateOrganizePlanUseCase(ports).execute(
        CreateOrganizePlanRequest(trust_stat=False, library_root=LIBRARY_ROOT)
    )

    assert result.actions[0].target_path == EXPECTED_PREFERRED_ARTIST_PATH
    track = uow.tracks.get(TRACK_ID)
    assert track is not None
    assert track.canonical_path == EXPECTED_PREFERRED_ARTIST_PATH
    assert track.metadata == METADATA
    assert isinstance(ports.artist_name_resolver, MappingArtistNameResolver)
    assert ports.artist_name_resolver.calls == [("Artist", None)]


def test_organize_resolves_latest_album_year_across_scanned_album_group() -> None:
    """Organize renders one effective album year while storing raw track years."""
    first_path = f"{LIBRARY_ROOT}/Unsorted/Song 1.flac"
    second_path = f"{LIBRARY_ROOT}/Unsorted/Song 2.flac"
    third_path = f"{LIBRARY_ROOT}/Unsorted/Song 3.flac"
    first_metadata = _album_track_metadata(title="Song 1", year=1998, track_number=1)
    second_metadata = _album_track_metadata(title="Song 2", year=2002, track_number=2)
    third_metadata = _album_track_metadata(title="Song 3", year=2004, track_number=3)
    uow = InMemoryUnitOfWork()
    ports, _, _ = _ports(
        uow,
        (_entry(first_path), _entry(second_path), _entry(third_path)),
        {
            first_path: _snapshot(first_path, first_metadata),
            second_path: _snapshot(second_path, second_metadata),
            third_path: _snapshot(third_path, third_metadata),
        },
        SequenceIdGenerator(
            library_ids=deque((LIBRARY_ID,)),
            track_ids=deque((TRACK_ID, SECOND_TRACK_ID, THIRD_TRACK_ID)),
            plan_ids=deque((PLAN_ID,)),
            action_ids=deque((ACTION_ID, SECOND_ACTION_ID, THIRD_ACTION_ID)),
        ),
    )

    result = CreateOrganizePlanUseCase(ports).execute(
        CreateOrganizePlanRequest(trust_stat=False, library_root=LIBRARY_ROOT)
    )

    assert tuple(action.target_path for action in result.actions) == (
        "Artist/2004_Album/1-01_Song-1.flac",
        "Artist/2004_Album/1-02_Song-2.flac",
        "Artist/2004_Album/1-03_Song-3.flac",
    )
    tracks = uow.tracks.list_by_library(LIBRARY_ID)
    assert tuple(track.metadata.year for track in tracks) == (1998, 2002, 2004)
    assert tuple(track.canonical_path for track in tracks) == tuple(action.target_path for action in result.actions)


def test_organize_renders_disc_numbers_when_scanned_album_is_multi_disc() -> None:
    """Organize infers multi-disc context from scanned snapshots before rendering."""
    first_path = f"{LIBRARY_ROOT}/Unsorted/Disc1.flac"
    second_path = f"{LIBRARY_ROOT}/Unsorted/Disc2.flac"
    config = AppConfig(
        path_policy=PathPolicyConfig(
            disc_number_style=PATH_POLICY_DISC_NUMBER_STYLE_D_PREFIXED,
            disc_number_condition=PATH_POLICY_DISC_NUMBER_CONDITION_MULTIPLE_DISCS,
        )
    )
    uow = InMemoryUnitOfWork()
    ports, _, _ = _ports(
        uow,
        (_entry(first_path), _entry(second_path)),
        {
            first_path: _snapshot(first_path, METADATA),
            second_path: _snapshot(second_path, SECOND_METADATA),
        },
        SequenceIdGenerator(
            library_ids=deque((LIBRARY_ID,)),
            track_ids=deque((TRACK_ID, TrackId(UUID("018f6a4f-3c2d-7b8a-9abc-def012345682")))),
            plan_ids=deque((PLAN_ID,)),
            action_ids=deque((ACTION_ID, ActionId(UUID("018f6a4f-3c2d-7b8a-9abc-def012345683")))),
        ),
        options=PortOptions(config=config),
    )

    result = CreateOrganizePlanUseCase(ports).execute(
        CreateOrganizePlanRequest(trust_stat=False, library_root=LIBRARY_ROOT)
    )

    assert tuple(action.target_path for action in result.actions) == (
        EXPECTED_D_PREFIXED_PATH,
        EXPECTED_SECOND_D_PREFIXED_PATH,
    )


def test_organize_blocks_missing_required_metadata() -> None:
    """Missing required metadata creates a blocked review action."""
    uow = InMemoryUnitOfWork()
    ports, _, _ = _ports(
        uow,
        (_entry(MISPLACED_ABSOLUTE_PATH),),
        {MISPLACED_ABSOLUTE_PATH: _snapshot(MISPLACED_ABSOLUTE_PATH, MISSING_ARTIST_METADATA)},
        SequenceIdGenerator(
            library_ids=deque((LIBRARY_ID,)),
            plan_ids=deque((PLAN_ID,)),
            action_ids=deque((ACTION_ID,)),
        ),
    )

    result = CreateOrganizePlanUseCase(ports).execute(
        CreateOrganizePlanRequest(trust_stat=False, library_root=LIBRARY_ROOT)
    )

    assert result.library.status == LibraryStatus.BLOCKED
    assert result.track_count == 0
    action = result.actions[0]
    assert action.status == ActionStatus.BLOCKED
    assert action.reason == PlanActionReason.MISSING_REQUIRED_METADATA
    assert action.source_path == MISPLACED_PATH
    assert action.target_path is None
    assert action.track_id is None
    assert uow.tracks.list_by_library(LIBRARY_ID) == ()


def test_organize_blocks_missing_source_after_scan() -> None:
    """A file missing during snapshot capture becomes a source_missing block."""
    uow = InMemoryUnitOfWork()
    ports, _, snapshot_reader = _ports(
        uow,
        (_entry(MISPLACED_ABSOLUTE_PATH),),
        {},
        SequenceIdGenerator(
            library_ids=deque((LIBRARY_ID,)),
            plan_ids=deque((PLAN_ID,)),
            action_ids=deque((ACTION_ID,)),
        ),
        options=PortOptions(missing_paths={MISPLACED_ABSOLUTE_PATH}),
    )

    result = CreateOrganizePlanUseCase(ports).execute(
        CreateOrganizePlanRequest(trust_stat=False, library_root=LIBRARY_ROOT)
    )

    assert snapshot_reader.captured_paths == [MISPLACED_ABSOLUTE_PATH]
    assert result.library.status == LibraryStatus.BLOCKED
    action = result.actions[0]
    assert action.status == ActionStatus.BLOCKED
    assert action.reason == PlanActionReason.SOURCE_MISSING
    assert action.source_path == MISPLACED_PATH
    assert action.target_path is None
    assert action.content_hash_at_plan is None


def test_organize_blocks_invalid_path_with_library_relative_source() -> None:
    """Invalid scanned Library entries still store source paths relative to the Library root."""
    invalid_absolute_path = f"{LIBRARY_ROOT}/Linked/Outside.flac"
    uow = InMemoryUnitOfWork()
    ports, _, snapshot_reader = _ports(
        uow,
        (_entry(invalid_absolute_path),),
        {},
        SequenceIdGenerator(
            library_ids=deque((LIBRARY_ID,)),
            plan_ids=deque((PLAN_ID,)),
            action_ids=deque((ACTION_ID,)),
        ),
    )
    assert isinstance(ports.path_resolver, SimplePathResolver)
    ports.path_resolver.invalid_paths.add(invalid_absolute_path)

    result = CreateOrganizePlanUseCase(ports).execute(
        CreateOrganizePlanRequest(trust_stat=False, library_root=LIBRARY_ROOT)
    )

    assert snapshot_reader.captured_paths == []
    assert result.library.status == LibraryStatus.BLOCKED
    action = result.actions[0]
    assert action.status == ActionStatus.BLOCKED
    assert action.reason == PlanActionReason.INVALID_PATH
    assert action.source_path == "Linked/Outside.flac"
    assert action.target_path is None
    assert action.content_hash_at_plan is None


def test_organize_blocks_target_conflict_without_overwriting() -> None:
    """A misplaced file targeting an occupied canonical path is blocked."""
    uow = InMemoryUnitOfWork()
    ports, _, _ = _ports(
        uow,
        (_entry(CANONICAL_ABSOLUTE_PATH), _entry(MISPLACED_ABSOLUTE_PATH)),
        {
            CANONICAL_ABSOLUTE_PATH: _snapshot(CANONICAL_ABSOLUTE_PATH, METADATA),
            MISPLACED_ABSOLUTE_PATH: _snapshot(MISPLACED_ABSOLUTE_PATH, METADATA),
        },
        SequenceIdGenerator(
            library_ids=deque((LIBRARY_ID,)),
            track_ids=deque((TRACK_ID,)),
            plan_ids=deque((PLAN_ID,)),
            action_ids=deque((ACTION_ID,)),
        ),
    )

    result = CreateOrganizePlanUseCase(ports).execute(
        CreateOrganizePlanRequest(trust_stat=False, library_root=LIBRARY_ROOT)
    )

    assert result.library.status == LibraryStatus.BLOCKED
    assert result.track_count == 1
    action = result.actions[0]
    assert action.status == ActionStatus.BLOCKED
    assert action.reason == PlanActionReason.TARGET_EXISTS
    assert action.source_path == MISPLACED_PATH
    assert action.target_path == EXPECTED_CANONICAL_PATH
    assert action.track_id is None


def test_plain_organize_refuses_when_no_library_can_be_selected() -> None:
    """Plain organize does not guess a Library path."""
    ports, _, _ = _ports(InMemoryUnitOfWork(), (), {}, SequenceIdGenerator())

    with pytest.raises(OrganizeLibrarySelectionError, match=NO_LIBRARY_SELECTION_MESSAGE):
        _ = CreateOrganizePlanUseCase(ports).execute(CreateOrganizePlanRequest(trust_stat=False))


def test_plain_organize_refuses_ambiguous_library_selection() -> None:
    """Plain organize requires exactly one known Library."""
    uow = InMemoryUnitOfWork()
    uow.libraries.save(_library(LIBRARY_ID, LIBRARY_ROOT))
    uow.libraries.save(_library(SECOND_LIBRARY_ID, SECOND_LIBRARY_ROOT))
    ports, _, _ = _ports(uow, (), {}, SequenceIdGenerator())

    with pytest.raises(OrganizeLibrarySelectionError, match=AMBIGUOUS_LIBRARY_SELECTION_MESSAGE):
        _ = CreateOrganizePlanUseCase(ports).execute(CreateOrganizePlanRequest(trust_stat=False))


def test_organize_refuses_unregistered_path_when_library_exists() -> None:
    """An unregistered root is not silently treated as a second Library."""
    uow = InMemoryUnitOfWork()
    uow.libraries.save(_library(LIBRARY_ID, LIBRARY_ROOT))
    ports, _, _ = _ports(uow, (), {}, SequenceIdGenerator())

    with pytest.raises(OrganizeLibrarySelectionError, match=UNREGISTERED_PATH_MESSAGE):
        _ = CreateOrganizePlanUseCase(ports).execute(
            CreateOrganizePlanRequest(trust_stat=False, library_root=UNREGISTERED_LIBRARY_ROOT)
        )


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


class StaticFileScanner:
    """FileScanner fake returning predetermined scan entries."""

    def __init__(self, entries: tuple[FileScanEntry, ...]) -> None:
        """Store scan entries and expose scan calls for assertions."""
        self._entries: tuple[FileScanEntry, ...] = entries
        self.scanned_roots: list[FileSystemPath] = []

    def scan(self, root: FileSystemPath) -> tuple[FileScanEntry, ...]:
        """Return configured scan entries."""
        self.scanned_roots.append(root)
        return self._entries


class MappingSnapshotReader:
    """FileSnapshotReader fake keyed by path."""

    def __init__(self, snapshots: dict[str, FileSnapshot], missing_paths: set[str] | None = None) -> None:
        """Store snapshots and optional paths that disappear after scan."""
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
        """Capture requests serially while preserving observations and order."""
        snapshots: list[FileSnapshot | None] = []
        for request in requests:
            try:
                snapshots.append(self.capture(request.path))
            except FileNotFoundError:
                snapshots.append(None)
        return tuple(snapshots)


class SimplePathResolver:
    """PathResolver fake for absolute paths under one root."""

    def __init__(self) -> None:
        """Store paths that should be treated as outside the Library after resolution."""
        self.invalid_paths: set[str] = set()

    def resolve_library_path(self, library_root: FileSystemPath, library_relative_path: str) -> str:
        """Join root and relative path without touching the real filesystem."""
        return f"{str(library_root).rstrip('/')}/{library_relative_path}"

    def relative_to_library(self, library_root: FileSystemPath, path: FileSystemPath) -> str:
        """Return a Library-relative path for test absolute paths."""
        root = str(library_root).rstrip("/")
        path_text = str(path)
        if path_text in self.invalid_paths:
            raise ValueError(PATH_OUTSIDE_LIBRARY_MESSAGE)
        expected_prefix = f"{root}/"
        if not path_text.startswith(expected_prefix):
            raise ValueError(PATH_OUTSIDE_LIBRARY_MESSAGE)
        return path_text.removeprefix(expected_prefix)


@dataclass(frozen=True, slots=True)
class PortOptions:
    """Optional fake settings for CreateOrganizePlanPorts."""

    config: AppConfig | None = None
    missing_paths: set[str] | None = None
    resolved_names: dict[str, str] | None = None


def _ports(
    uow: InMemoryUnitOfWork,
    entries: tuple[FileScanEntry, ...],
    snapshots: dict[str, FileSnapshot],
    id_generator: SequenceIdGenerator,
    *,
    options: PortOptions | None = None,
) -> tuple[CreateOrganizePlanPorts, StaticFileScanner, MappingSnapshotReader]:
    port_options = PortOptions() if options is None else options
    scanner = StaticFileScanner(entries)
    snapshot_reader = MappingSnapshotReader(snapshots, port_options.missing_paths)
    ports = CreateOrganizePlanPorts(
        uow=uow,
        file_scanner=scanner,
        file_snapshot_reader=snapshot_reader,
        config_store=StaticConfigStore(port_options.config),
        artist_name_resolver=MappingArtistNameResolver(port_options.resolved_names or {}),
        path_resolver=SimplePathResolver(),
        clock=FixedClock(BASE_TIME),
        id_generator=id_generator,
    )
    return ports, scanner, snapshot_reader


def _entry(path: str) -> FileScanEntry:
    return FileScanEntry(path=path, size=FILE_SIZE, mtime=BASE_TIME, file_extension=FILE_EXTENSION)


def _track(
    *,
    track_id: TrackId = TRACK_ID,
    size: int | None = None,
    mtime: datetime | None = None,
) -> Track:
    return Track(
        track_id=track_id,
        library_id=LIBRARY_ID,
        current_path=EXPECTED_CANONICAL_PATH,
        canonical_path=EXPECTED_CANONICAL_PATH,
        content_hash=CONTENT_HASH,
        metadata_hash=calculate_metadata_fingerprint(METADATA),
        size=size,
        mtime=mtime,
        metadata=METADATA,
        status=TrackStatus.ACTIVE,
        first_seen_at=BASE_TIME,
        last_seen_at=BASE_TIME,
        updated_at=BASE_TIME,
    )


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


def _library(library_id: LibraryId, root_path: str) -> Library:
    return Library(
        library_id=library_id,
        root_path=root_path,
        path_policy_hash="old-path-policy-hash",
        registered_at=BASE_TIME,
        status=LibraryStatus.REGISTERED,
        created_at=BASE_TIME,
        updated_at=BASE_TIME,
    )


def _running_operation() -> Operation:
    return Operation.queued(
        operation_id=OPERATION_ID,
        kind=OperationKind.ORGANIZE_PLAN,
        idempotency_key=IDEMPOTENCY_KEY,
        request_fingerprint="organize-request",
        requested_at=BASE_TIME,
    ).mark_running(BASE_TIME)


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
