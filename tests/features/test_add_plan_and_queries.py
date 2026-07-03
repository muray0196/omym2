"""
Summary: Tests add Plan and plan query behavior.
Why: Protects reviewed incoming imports before file mutation exists.
"""

from __future__ import annotations

from collections import deque
from dataclasses import dataclass
from datetime import UTC, datetime
from typing import TYPE_CHECKING
from uuid import UUID

import pytest

from omym2.adapters.config.default_config import default_app_config
from omym2.domain.models.app_config import AppConfig, ArtistIdConfig, PathPolicyConfig, PathsConfig
from omym2.domain.models.file_scan_entry import FileScanEntry
from omym2.domain.models.file_snapshot import FileSnapshot
from omym2.domain.models.library import Library, LibraryStatus
from omym2.domain.models.plan import PlanStatus, PlanType
from omym2.domain.models.plan_action import ActionStatus, ActionType, PlanActionReason
from omym2.domain.models.track import Track, TrackStatus
from omym2.domain.models.track_metadata import TrackMetadata
from omym2.domain.services.config_fingerprint import calculate_config_fingerprint, calculate_path_policy_fingerprint
from omym2.domain.services.content_fingerprint import calculate_content_fingerprint
from omym2.domain.services.metadata_fingerprint import calculate_metadata_fingerprint
from omym2.features.add.dto import CreateAddPlanRequest
from omym2.features.add.ports import CreateAddPlanPorts
from omym2.features.add.usecases.create_add_plan import (
    AMBIGUOUS_REGISTERED_LIBRARY_MESSAGE,
    NO_REGISTERED_LIBRARY_MESSAGE,
    STALE_LIBRARY_MESSAGE,
    AddLibrarySelectionError,
    CreateAddPlanUseCase,
)
from omym2.features.plans.dto import GetPlanDetailRequest, ListPlansRequest
from omym2.features.plans.ports import PlanQueryPorts
from omym2.features.plans.usecases.get_plan_detail import GetPlanDetailUseCase
from omym2.features.plans.usecases.list_plans import ListPlansUseCase
from omym2.shared.ids import ActionId, LibraryId, PlanId, TrackId
from tests.fakes.in_memory_repositories import InMemoryUnitOfWork
from tests.fakes.runtime import FixedClock, SequenceIdGenerator

if TYPE_CHECKING:
    from pathlib import Path

    from omym2.features.common_ports import FileSystemPath

ACTION_ID = ActionId(UUID("018f6a4f-3c2d-7b8a-9abc-def01234567b"))
BASE_TIME = datetime(2026, 1, 1, tzinfo=UTC)
CASE_INSENSITIVE_DUPLICATE_TARGET_PATH = "artist/2026_Album/1-02_Title.flac"
CONTENT = b"audio"
CONTENT_HASH = calculate_content_fingerprint(CONTENT)
EXPECTED_CANONICAL_PATH = "Artist/2026_Album/1-02_Title.flac"
FILE_EXTENSION = ".flac"
FILE_SIZE = 5
INCOMING_FILE = "/music/incoming/Title.flac"
INCOMING_ROOT = "/music/incoming"
LIBRARY_ID = LibraryId(UUID("018f6a4f-3c2d-7b8a-9abc-def012345678"))
LIBRARY_ROOT = "/music/library"
LOWERCASE_ARTIST_METADATA = TrackMetadata(
    title="Title",
    artist="artist",
    album="Album",
    year=2026,
    track_number=2,
    disc_number=1,
)
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
OTHER_CONTENT_HASH = calculate_content_fingerprint(b"other audio")
PLAN_ID = PlanId(UUID("018f6a4f-3c2d-7b8a-9abc-def01234567a"))
SECOND_ACTION_ID = ActionId(UUID("018f6a4f-3c2d-7b8a-9abc-def01234567c"))
SECOND_INCOMING_FILE = "/music/incoming/Title2.flac"
SECOND_LIBRARY_ID = LibraryId(UUID("018f6a4f-3c2d-7b8a-9abc-def012345680"))
SECOND_LIBRARY_ROOT = "/music/second"
TRACK_ID = TrackId(UUID("018f6a4f-3c2d-7b8a-9abc-def012345679"))


def test_add_refuses_when_no_registered_library_can_be_selected() -> None:
    """Add does not guess a Library before organize registration."""
    uow = InMemoryUnitOfWork()
    ports, _, _ = _ports(uow, (), {}, SequenceIdGenerator())

    with pytest.raises(AddLibrarySelectionError, match=NO_REGISTERED_LIBRARY_MESSAGE):
        _ = CreateAddPlanUseCase(ports).execute(CreateAddPlanRequest(source_path=INCOMING_ROOT))

    assert uow.plans.records == {}
    assert uow.rollback_count == 1


def test_add_refuses_ambiguous_registered_library_selection() -> None:
    """Add requires exactly one registered Library in the MVP."""
    uow = InMemoryUnitOfWork()
    uow.libraries.save(_library(LIBRARY_ID, LIBRARY_ROOT))
    uow.libraries.save(_library(SECOND_LIBRARY_ID, SECOND_LIBRARY_ROOT))
    ports, _, _ = _ports(uow, (), {}, SequenceIdGenerator())

    with pytest.raises(AddLibrarySelectionError, match=AMBIGUOUS_REGISTERED_LIBRARY_MESSAGE):
        _ = CreateAddPlanUseCase(ports).execute(CreateAddPlanRequest(source_path=INCOMING_ROOT))

    assert uow.plans.records == {}


def test_add_refuses_stale_path_policy_registration() -> None:
    """Add requires organize registration under the current PathPolicy."""
    uow = InMemoryUnitOfWork()
    uow.libraries.save(_library(LIBRARY_ID, LIBRARY_ROOT, path_policy_hash="old-path-policy-hash"))
    ports, _, _ = _ports(uow, (), {}, SequenceIdGenerator())

    with pytest.raises(AddLibrarySelectionError, match=STALE_LIBRARY_MESSAGE):
        _ = CreateAddPlanUseCase(ports).execute(CreateAddPlanRequest(source_path=INCOMING_ROOT))

    assert uow.plans.records == {}


def test_add_refuses_registration_stale_after_artist_id_entries_change() -> None:
    """A real artist_ids.entries change makes the registered fingerprint stale.

    Unlike test_add_refuses_stale_path_policy_registration (which injects a
    fake literal hash), this proves the real fingerprint wiring: a Library
    registered under one ArtistIdConfig is rejected once artist_ids.entries
    changes, because the template renders {artist_id}.
    """
    path_policy = PathPolicyConfig(template="{artist_id}/{title}")
    registered_artist_ids = ArtistIdConfig(entries={"Artist": "ART1"})
    registered_hash = calculate_path_policy_fingerprint(path_policy, registered_artist_ids)
    uow = InMemoryUnitOfWork()
    uow.libraries.save(_library(LIBRARY_ID, LIBRARY_ROOT, path_policy_hash=registered_hash))
    changed_artist_ids = ArtistIdConfig(entries={"Artist": "ART2"})
    config = AppConfig(path_policy=path_policy, artist_ids=changed_artist_ids)
    ports, _, _ = _ports(uow, (), {}, SequenceIdGenerator(), options=PortOptions(config=config))

    with pytest.raises(AddLibrarySelectionError, match=STALE_LIBRARY_MESSAGE):
        _ = CreateAddPlanUseCase(ports).execute(CreateAddPlanRequest(source_path=INCOMING_ROOT))

    assert uow.plans.records == {}


def test_add_registration_survives_artist_id_change_when_template_unused() -> None:
    """artist_ids.entries changes do not stale a Library whose template ignores {artist_id}.

    Positive control for test_add_refuses_registration_stale_after_artist_id_entries_change:
    the path policy fingerprint intentionally omits artist_ids when the
    template never renders {artist_id}, so registration must still succeed.
    """
    path_policy = PathPolicyConfig(template="{artist}/{title}")
    registered_artist_ids = ArtistIdConfig(entries={"Artist": "ART1"})
    registered_hash = calculate_path_policy_fingerprint(path_policy, registered_artist_ids)
    uow = InMemoryUnitOfWork()
    uow.libraries.save(_library(LIBRARY_ID, LIBRARY_ROOT, path_policy_hash=registered_hash))
    changed_artist_ids = ArtistIdConfig(entries={"Artist": "ART2"})
    config = AppConfig(path_policy=path_policy, artist_ids=changed_artist_ids)
    ports, _, _ = _ports(
        uow,
        (_entry(INCOMING_FILE),),
        {INCOMING_FILE: _snapshot(INCOMING_FILE, METADATA, CONTENT_HASH)},
        SequenceIdGenerator(plan_ids=deque((PLAN_ID,)), action_ids=deque((ACTION_ID,))),
        options=PortOptions(config=config),
    )

    plan = CreateAddPlanUseCase(ports).execute(CreateAddPlanRequest(source_path=INCOMING_ROOT))

    assert plan.status == PlanStatus.READY
    assert plan.library_id == LIBRARY_ID
    assert plan.actions[0].action_type == ActionType.MOVE
    assert plan.actions[0].reason is None


def test_add_uses_configured_incoming_and_persists_move_action() -> None:
    """A new incoming file creates a reviewed add move action."""
    uow = InMemoryUnitOfWork()
    uow.libraries.save(_library(LIBRARY_ID, LIBRARY_ROOT))
    config = AppConfig(paths=PathsConfig(incoming=INCOMING_ROOT))
    ports, scanner, snapshot_reader = _ports(
        uow,
        (_entry(INCOMING_FILE),),
        {INCOMING_FILE: _snapshot(INCOMING_FILE, METADATA, CONTENT_HASH)},
        SequenceIdGenerator(plan_ids=deque((PLAN_ID,)), action_ids=deque((ACTION_ID,))),
        options=PortOptions(config=config),
    )

    plan = CreateAddPlanUseCase(ports).execute(CreateAddPlanRequest())

    assert scanner.scanned_roots == [INCOMING_ROOT]
    assert snapshot_reader.captured_paths == [INCOMING_FILE]
    assert plan.plan_type == PlanType.ADD
    assert plan.status == PlanStatus.READY
    assert plan.config_hash == calculate_config_fingerprint(config)
    assert plan.library_root_at_plan == LIBRARY_ROOT
    assert plan.summary["action_count"] == "1"
    action = plan.actions[0]
    assert action.action_type == ActionType.MOVE
    assert action.status == ActionStatus.PLANNED
    assert action.reason is None
    assert action.source_path == INCOMING_FILE
    assert action.target_path == EXPECTED_CANONICAL_PATH
    assert action.track_id is None
    assert action.content_hash_at_plan == CONTENT_HASH
    assert uow.plans.get(PLAN_ID) == plan
    assert uow.plan_actions.get(ACTION_ID) == action
    assert uow.tracks.list_by_library(LIBRARY_ID) == ()
    assert uow.commit_count == 1


def test_add_normalizes_configured_relative_incoming_source(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Configured relative Incoming paths are stored as absolute external sources."""
    incoming_file = tmp_path / "Incoming" / "Title.flac"
    expected_incoming_root = str((tmp_path / "Incoming").resolve(strict=False))
    expected_source_path = str(incoming_file.resolve(strict=False))
    uow = InMemoryUnitOfWork()
    uow.libraries.save(_library(LIBRARY_ID, LIBRARY_ROOT))
    ports, scanner, _ = _ports(
        uow,
        (_entry(expected_source_path),),
        {expected_source_path: _snapshot(expected_source_path, METADATA, CONTENT_HASH)},
        SequenceIdGenerator(plan_ids=deque((PLAN_ID,)), action_ids=deque((ACTION_ID,))),
        options=PortOptions(config=AppConfig(paths=PathsConfig(incoming="Incoming"))),
    )
    monkeypatch.chdir(tmp_path)

    plan = CreateAddPlanUseCase(ports).execute(CreateAddPlanRequest())

    assert scanner.scanned_roots == [expected_incoming_root]
    assert plan.actions[0].source_path == expected_source_path


def test_add_plan_skips_duplicate_hash() -> None:
    """Incoming content already known to the Library is recorded as a skip."""
    uow = InMemoryUnitOfWork()
    uow.libraries.save(_library(LIBRARY_ID, LIBRARY_ROOT))
    uow.tracks.save(_track(CONTENT_HASH, EXPECTED_CANONICAL_PATH))
    ports, _, _ = _ports(
        uow,
        (_entry(INCOMING_FILE),),
        {INCOMING_FILE: _snapshot(INCOMING_FILE, METADATA, CONTENT_HASH)},
        SequenceIdGenerator(plan_ids=deque((PLAN_ID,)), action_ids=deque((ACTION_ID,))),
    )

    plan = CreateAddPlanUseCase(ports).execute(CreateAddPlanRequest(source_path=INCOMING_ROOT))

    action = plan.actions[0]
    assert action.action_type == ActionType.SKIP
    assert action.status == ActionStatus.PLANNED
    assert action.reason == PlanActionReason.DUPLICATE_HASH
    assert action.track_id == TRACK_ID
    assert action.target_path == EXPECTED_CANONICAL_PATH
    assert plan.summary["skip_actions"] == "1"


def test_add_plan_blocks_missing_required_metadata() -> None:
    """Missing required incoming metadata creates a blocked action."""
    uow = InMemoryUnitOfWork()
    uow.libraries.save(_library(LIBRARY_ID, LIBRARY_ROOT))
    ports, _, _ = _ports(
        uow,
        (_entry(INCOMING_FILE),),
        {INCOMING_FILE: _snapshot(INCOMING_FILE, MISSING_ARTIST_METADATA, CONTENT_HASH)},
        SequenceIdGenerator(plan_ids=deque((PLAN_ID,)), action_ids=deque((ACTION_ID,))),
    )

    plan = CreateAddPlanUseCase(ports).execute(CreateAddPlanRequest(source_path=INCOMING_ROOT))

    action = plan.actions[0]
    assert action.action_type == ActionType.MOVE
    assert action.status == ActionStatus.BLOCKED
    assert action.reason == PlanActionReason.MISSING_REQUIRED_METADATA
    assert action.target_path is None
    assert plan.summary["blocked_actions"] == "1"


def test_add_plan_detects_target_conflict() -> None:
    """Incoming files do not overwrite known Library targets."""
    uow = InMemoryUnitOfWork()
    uow.libraries.save(_library(LIBRARY_ID, LIBRARY_ROOT))
    uow.tracks.save(_track(OTHER_CONTENT_HASH, EXPECTED_CANONICAL_PATH))
    ports, _, _ = _ports(
        uow,
        (_entry(INCOMING_FILE),),
        {INCOMING_FILE: _snapshot(INCOMING_FILE, METADATA, CONTENT_HASH)},
        SequenceIdGenerator(plan_ids=deque((PLAN_ID,)), action_ids=deque((ACTION_ID,))),
    )

    plan = CreateAddPlanUseCase(ports).execute(CreateAddPlanRequest(source_path=INCOMING_ROOT))

    action = plan.actions[0]
    assert action.action_type == ActionType.MOVE
    assert action.status == ActionStatus.BLOCKED
    assert action.reason == PlanActionReason.TARGET_EXISTS
    assert action.target_path == EXPECTED_CANONICAL_PATH
    assert plan.summary["blocked_actions"] == "1"


def test_add_plan_blocks_existing_untracked_target_file() -> None:
    """Incoming files do not overwrite Library files missing from the DB."""
    target_filesystem_path = f"{LIBRARY_ROOT}/{EXPECTED_CANONICAL_PATH}"
    uow = InMemoryUnitOfWork()
    uow.libraries.save(_library(LIBRARY_ID, LIBRARY_ROOT))
    ports, _, _ = _ports(
        uow,
        (_entry(INCOMING_FILE),),
        {INCOMING_FILE: _snapshot(INCOMING_FILE, METADATA, CONTENT_HASH)},
        SequenceIdGenerator(plan_ids=deque((PLAN_ID,)), action_ids=deque((ACTION_ID,))),
        options=PortOptions(existing_files={target_filesystem_path}),
    )

    plan = CreateAddPlanUseCase(ports).execute(CreateAddPlanRequest(source_path=INCOMING_ROOT))

    action = plan.actions[0]
    assert action.action_type == ActionType.MOVE
    assert action.status == ActionStatus.BLOCKED
    assert action.reason == PlanActionReason.TARGET_EXISTS
    assert action.target_path == EXPECTED_CANONICAL_PATH


def test_add_plan_blocks_source_changed_after_scan() -> None:
    """Incoming files changed between scan and snapshot are not planned for move."""
    changed_snapshot = FileSnapshot(
        path=INCOMING_FILE,
        size=FILE_SIZE + 1,
        mtime=BASE_TIME,
        file_extension=FILE_EXTENSION,
        content_hash=CONTENT_HASH,
        metadata_hash=calculate_metadata_fingerprint(METADATA),
        metadata=METADATA,
        captured_at=BASE_TIME,
    )
    uow = InMemoryUnitOfWork()
    uow.libraries.save(_library(LIBRARY_ID, LIBRARY_ROOT))
    ports, _, _ = _ports(
        uow,
        (_entry(INCOMING_FILE),),
        {INCOMING_FILE: changed_snapshot},
        SequenceIdGenerator(plan_ids=deque((PLAN_ID,)), action_ids=deque((ACTION_ID,))),
    )

    plan = CreateAddPlanUseCase(ports).execute(CreateAddPlanRequest(source_path=INCOMING_ROOT))

    action = plan.actions[0]
    assert action.action_type == ActionType.MOVE
    assert action.status == ActionStatus.BLOCKED
    assert action.reason == PlanActionReason.SOURCE_CHANGED
    assert action.target_path is None
    assert action.content_hash_at_plan == CONTENT_HASH
    assert plan.summary["blocked_actions"] == "1"


def test_add_plan_currently_allows_case_insensitive_duplicate_targets() -> None:
    """Characterizes current behavior: two incoming files whose canonical target
    paths differ only by case are both planned as MOVE with no TARGET_EXISTS
    block, because target comparison is an exact string match. Exact-match
    target comparison is the intended current contract; this does not protect
    case-insensitive filesystems.
    """
    uow = InMemoryUnitOfWork()
    uow.libraries.save(_library(LIBRARY_ID, LIBRARY_ROOT))
    ports, _, _ = _ports(
        uow,
        (_entry(INCOMING_FILE), _entry(SECOND_INCOMING_FILE)),
        {
            INCOMING_FILE: _snapshot(INCOMING_FILE, METADATA, CONTENT_HASH),
            SECOND_INCOMING_FILE: _snapshot(SECOND_INCOMING_FILE, LOWERCASE_ARTIST_METADATA, OTHER_CONTENT_HASH),
        },
        SequenceIdGenerator(plan_ids=deque((PLAN_ID,)), action_ids=deque((ACTION_ID, SECOND_ACTION_ID))),
    )

    plan = CreateAddPlanUseCase(ports).execute(CreateAddPlanRequest(source_path=INCOMING_ROOT))

    first_action, second_action = plan.actions
    assert first_action.target_path == EXPECTED_CANONICAL_PATH
    assert second_action.target_path == CASE_INSENSITIVE_DUPLICATE_TARGET_PATH
    assert first_action.action_type == ActionType.MOVE
    assert second_action.action_type == ActionType.MOVE
    assert first_action.status == ActionStatus.PLANNED
    assert second_action.status == ActionStatus.PLANNED
    assert first_action.reason is None
    assert second_action.reason is None


def test_plans_list_and_detail_usecases_return_recorded_actions() -> None:
    """Plan query usecases expose persisted Plan headers and actions."""
    uow = InMemoryUnitOfWork()
    uow.libraries.save(_library(LIBRARY_ID, LIBRARY_ROOT))
    add_ports, _, _ = _ports(
        uow,
        (_entry(INCOMING_FILE),),
        {INCOMING_FILE: _snapshot(INCOMING_FILE, METADATA, CONTENT_HASH)},
        SequenceIdGenerator(plan_ids=deque((PLAN_ID,)), action_ids=deque((ACTION_ID,))),
    )
    plan = CreateAddPlanUseCase(add_ports).execute(CreateAddPlanRequest(source_path=INCOMING_ROOT))
    query_ports = PlanQueryPorts(uow=uow)

    plans = ListPlansUseCase(query_ports).execute(ListPlansRequest())
    detail = GetPlanDetailUseCase(query_ports).execute(GetPlanDetailRequest(PLAN_ID))

    assert plans == (plan,)
    assert detail.plan == plan
    assert detail.actions == plan.actions


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

    def __init__(self, snapshots: dict[str, FileSnapshot]) -> None:
        """Store snapshots by source path."""
        self._snapshots: dict[str, FileSnapshot] = snapshots
        self.captured_paths: list[FileSystemPath] = []

    def capture(self, path: FileSystemPath) -> FileSnapshot:
        """Return the configured snapshot for a source path."""
        self.captured_paths.append(path)
        return self._snapshots[str(path)]


class StaticFilePresence:
    """FilePresence fake keyed by path text."""

    def __init__(self, existing_files: set[str] | None = None) -> None:
        """Store paths that should be reported as present."""
        self._existing_files: set[str] = set() if existing_files is None else set(existing_files)
        self.checked_paths: list[FileSystemPath] = []

    def exists(self, path: FileSystemPath) -> bool:
        """Return whether path was configured as present."""
        self.checked_paths.append(path)
        return str(path) in self._existing_files


class SimplePathResolver:
    """PathResolver fake for Library target paths."""

    def resolve_library_path(self, library_root: FileSystemPath, library_relative_path: str) -> str:
        """Join root and Library-relative path for tests."""
        return f"{str(library_root).rstrip('/')}/{library_relative_path}"

    def relative_to_library(self, library_root: FileSystemPath, path: FileSystemPath) -> str:
        """Return a lexical Library-relative path for protocol completeness."""
        root = str(library_root).rstrip("/")
        return str(path).removeprefix(f"{root}/")


@dataclass(frozen=True, slots=True)
class PortOptions:
    """Optional fake settings for CreateAddPlanPorts."""

    config: AppConfig | None = None
    existing_files: set[str] | None = None


def _ports(
    uow: InMemoryUnitOfWork,
    entries: tuple[FileScanEntry, ...],
    snapshots: dict[str, FileSnapshot],
    id_generator: SequenceIdGenerator,
    *,
    options: PortOptions | None = None,
) -> tuple[CreateAddPlanPorts, StaticFileScanner, MappingSnapshotReader]:
    port_options = PortOptions() if options is None else options
    scanner = StaticFileScanner(entries)
    snapshot_reader = MappingSnapshotReader(snapshots)
    ports = CreateAddPlanPorts(
        uow=uow,
        file_scanner=scanner,
        file_snapshot_reader=snapshot_reader,
        file_presence=StaticFilePresence(port_options.existing_files),
        config_store=StaticConfigStore(port_options.config),
        path_resolver=SimplePathResolver(),
        clock=FixedClock(BASE_TIME),
        id_generator=id_generator,
    )
    return ports, scanner, snapshot_reader


def _entry(path: str) -> FileScanEntry:
    return FileScanEntry(path=path, size=FILE_SIZE, mtime=BASE_TIME, file_extension=FILE_EXTENSION)


def _snapshot(path: str, metadata: TrackMetadata, content_hash: str) -> FileSnapshot:
    return FileSnapshot(
        path=path,
        size=FILE_SIZE,
        mtime=BASE_TIME,
        file_extension=FILE_EXTENSION,
        content_hash=content_hash,
        metadata_hash=calculate_metadata_fingerprint(metadata),
        metadata=metadata,
        captured_at=BASE_TIME,
    )


def _library(library_id: LibraryId, root_path: str, path_policy_hash: str | None = None) -> Library:
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


def _track(content_hash: str, current_path: str) -> Track:
    return Track(
        track_id=TRACK_ID,
        library_id=LIBRARY_ID,
        current_path=current_path,
        canonical_path=current_path,
        content_hash=content_hash,
        metadata_hash=calculate_metadata_fingerprint(METADATA),
        metadata=METADATA,
        status=TrackStatus.ACTIVE,
        first_seen_at=BASE_TIME,
        last_seen_at=BASE_TIME,
        updated_at=BASE_TIME,
    )
