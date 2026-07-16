"""
Summary: Tests add Plan and plan query behavior.
Why: Protects reviewed incoming imports before file mutation exists.
"""

from __future__ import annotations

from collections import deque
from dataclasses import dataclass, replace
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import TYPE_CHECKING
from uuid import UUID

import pytest

from omym2.adapters.config.default_config import default_app_config
from omym2.adapters.fs.file_presence import FilesystemFilePresence
from omym2.adapters.fs.source_inventory_reader import FilesystemSourceInventoryReader
from omym2.config import (
    DEFAULT_UNPROCESSED_DIRECTORY,
    DEFAULT_UNPROCESSED_RESULT_PREVIEW_LIMIT,
    OPERATION_RESULT_RETENTION_HOURS,
    OPERATION_TOMBSTONE_RETENTION_DAYS,
    PATH_POLICY_DISC_NUMBER_CONDITION_MULTIPLE_DISCS,
    PATH_POLICY_DISC_NUMBER_STYLE_D_PREFIXED,
)
from omym2.domain.models.app_config import (
    AppConfig,
    ArtistIdConfig,
    ArtistNameConfig,
    CompanionsConfig,
    PathPolicyConfig,
    PathsConfig,
    UnprocessedConfig,
)
from omym2.domain.models.file_event import FileEvent, FileEventStatus, FileEventType
from omym2.domain.models.file_scan_entry import FileScanEntry
from omym2.domain.models.file_snapshot import FileContentSnapshot, FileSnapshot, FilesystemIdentity
from omym2.domain.models.library import Library, LibraryStatus
from omym2.domain.models.operation import Operation, OperationKind, OperationStatus, PlanCreatedResult
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
from omym2.domain.services.config_fingerprint import calculate_config_fingerprint, calculate_path_policy_fingerprint
from omym2.domain.services.content_fingerprint import calculate_content_fingerprint
from omym2.domain.services.metadata_fingerprint import calculate_metadata_fingerprint
from omym2.features.add.dto import CreateAddPlanRequest
from omym2.features.add.ports import CreateAddPlanPorts
from omym2.features.add.usecases.create_add_plan import (
    AMBIGUOUS_REGISTERED_LIBRARY_MESSAGE,
    ARTIST_NAME_RECONCILIATION_REQUIRED_MESSAGE,
    NO_REGISTERED_LIBRARY_MESSAGE,
    SELECTED_LIBRARY_NOT_FOUND_MESSAGE,
    SOURCE_INSIDE_LIBRARY_MESSAGE,
    STALE_LIBRARY_MESSAGE,
    AddLibraryReconciliationRequiredError,
    AddLibrarySelectionError,
    AddSourceSelectionError,
    CreateAddPlanUseCase,
)
from omym2.features.common_ports import (
    FileObservationChangedError,
    FileObservationInvalidPathError,
    SourceInventoryEntry,
    SourceInventoryRequest,
)
from omym2.features.plans.dto import GetPlanHeaderRequest, ListPlanActionsRequest, ListPlansRequest
from omym2.features.plans.ports import PlanQueryPorts
from omym2.features.plans.usecases.get_plan_header import GetPlanHeaderUseCase
from omym2.features.plans.usecases.list_plan_actions import ListPlanActionsUseCase
from omym2.features.plans.usecases.list_plans import ListPlansUseCase
from omym2.shared.ids import (
    ActionId,
    CompanionAssetId,
    EventId,
    LibraryId,
    OperationId,
    PlanId,
    RunId,
    TrackId,
)
from tests.fakes.file_observation import MappingFileContentSnapshotReader, StaticSourceInventoryReader
from tests.fakes.in_memory_repositories import InMemoryUnitOfWork
from tests.fakes.runtime import FixedClock, MappingArtistNameResolver, SequenceIdGenerator

if TYPE_CHECKING:
    from collections.abc import Sequence

    from omym2.features.common_ports import FileSnapshotCaptureRequest, FileSystemPath

ACTION_ID = ActionId(UUID("018f6a4f-3c2d-7b8a-9abc-def01234567b"))
COMPANION_ASSET_ID = CompanionAssetId(UUID("018f6a4f-3c2d-7b8a-9abc-def012345689"))
BASE_TIME = datetime(2026, 1, 1, tzinfo=UTC)
CASE_INSENSITIVE_DUPLICATE_TARGET_PATH = "artist/2026_Album/1-02_Title.flac"
CONTENT = b"audio"
CONTENT_HASH = calculate_content_fingerprint(CONTENT)
EXPECTED_CANONICAL_PATH = "Artist/2026_Album/1-02_Title.flac"
EXPECTED_D_PREFIXED_PATH = "Artist/2026_Album/D1-02_Title.flac"
EXPECTED_PREFERRED_ARTIST_PATH = "Preferred-Artist/2026_Album/1-02_Title.flac"
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
PEER_METADATA = TrackMetadata(
    title="Peer",
    artist="Artist",
    album="Album",
    year=2026,
    track_number=5,
    disc_number=2,
)
PLAN_ID = PlanId(UUID("018f6a4f-3c2d-7b8a-9abc-def01234567a"))
OPERATION_ID = OperationId(UUID("018f6a4f-3c2d-7b8a-9abc-def01234568e"))
IDEMPOTENCY_KEY = UUID("018f6a4f-3c2d-7b8a-9abc-def01234568f")
SECOND_ACTION_ID = ActionId(UUID("018f6a4f-3c2d-7b8a-9abc-def01234567c"))
SECOND_DUPLICATE_TRACK_PATH = "Artist/2026_Album/1-05_Title-Copy.flac"
SECOND_INCOMING_FILE = "/music/incoming/Title2.flac"
SECOND_LIBRARY_ID = LibraryId(UUID("018f6a4f-3c2d-7b8a-9abc-def012345680"))
SECOND_LIBRARY_ROOT = "/music/second"
SECOND_TRACK_ID = TrackId(UUID("018f6a4f-3c2d-7b8a-9abc-def012345681"))
THIRD_ACTION_ID = ActionId(UUID("018f6a4f-3c2d-7b8a-9abc-def01234567d"))
FOURTH_ACTION_ID = ActionId(UUID("018f6a4f-3c2d-7b8a-9abc-def01234567e"))
THIRD_INCOMING_FILE = "/music/incoming/Title3.flac"
TRACK_ID = TrackId(UUID("018f6a4f-3c2d-7b8a-9abc-def012345679"))
YEAR_1998 = 1998
YEAR_2002 = 2002
YEAR_2004 = 2004


def test_add_refuses_when_no_registered_library_can_be_selected() -> None:
    """Add does not guess a Library before organize registration."""
    uow = InMemoryUnitOfWork()
    ports, _, _ = _ports(uow, (), {}, SequenceIdGenerator())

    with pytest.raises(AddLibrarySelectionError, match=NO_REGISTERED_LIBRARY_MESSAGE):
        _ = CreateAddPlanUseCase(ports).execute(CreateAddPlanRequest(source_path=INCOMING_ROOT))

    assert uow.plans.records == {}
    assert uow.rollback_count == 1


def test_add_operation_success_commits_the_created_plan_result() -> None:
    """Orchestrated Add succeeds with the exact Plan created in its transaction."""
    uow = InMemoryUnitOfWork()
    uow.libraries.save(_library(LIBRARY_ID, LIBRARY_ROOT))
    uow.operations.save(_running_operation(OperationKind.ADD_PLAN))
    ports, _, _ = _ports(
        uow,
        (_entry(INCOMING_FILE),),
        {INCOMING_FILE: _snapshot(INCOMING_FILE, METADATA, CONTENT_HASH)},
        SequenceIdGenerator(plan_ids=deque((PLAN_ID,)), action_ids=deque((ACTION_ID,))),
    )

    plan = CreateAddPlanUseCase(ports).execute(
        CreateAddPlanRequest(source_path=INCOMING_ROOT, operation_id=OPERATION_ID)
    )

    terminal = uow.operations.lookup(OPERATION_ID)
    assert isinstance(terminal, Operation)
    assert terminal.status is OperationStatus.SUCCEEDED
    assert terminal.result == PlanCreatedResult(plan.plan_id)
    assert terminal.plan_id == plan.plan_id
    assert terminal.completed_at == BASE_TIME
    assert terminal.result_expires_at == BASE_TIME + timedelta(hours=OPERATION_RESULT_RETENTION_HOURS)
    assert terminal.tombstone_expires_at == BASE_TIME + timedelta(days=OPERATION_TOMBSTONE_RETENTION_DAYS)
    assert uow.plans.get(plan.plan_id) == plan


def test_add_rejects_nonrunning_operation_without_creating_plan() -> None:
    """An invalid orchestration lifecycle rolls back before Plan persistence."""
    uow = InMemoryUnitOfWork()
    uow.libraries.save(_library(LIBRARY_ID, LIBRARY_ROOT))
    queued = Operation.queued(
        operation_id=OPERATION_ID,
        kind=OperationKind.ADD_PLAN,
        idempotency_key=IDEMPOTENCY_KEY,
        request_fingerprint="add-request",
        requested_at=BASE_TIME,
        library_id=LIBRARY_ID,
    )
    uow.operations.save(queued)
    ports, scanner, _ = _ports(uow, (), {}, SequenceIdGenerator())

    with pytest.raises(RuntimeError):
        _ = CreateAddPlanUseCase(ports).execute(
            CreateAddPlanRequest(source_path=INCOMING_ROOT, operation_id=OPERATION_ID)
        )

    assert scanner.scanned_roots == []
    assert uow.plans.records == {}
    assert uow.operations.lookup(OPERATION_ID) == queued
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


def test_add_uses_explicit_library_selection_when_multiple_libraries_exist() -> None:
    """Web callers can select one stable Library ID without relying on list order."""
    uow = InMemoryUnitOfWork()
    uow.libraries.save(_library(LIBRARY_ID, LIBRARY_ROOT))
    uow.libraries.save(_library(SECOND_LIBRARY_ID, SECOND_LIBRARY_ROOT))
    ports, _, _ = _ports(
        uow,
        (_entry(INCOMING_FILE),),
        {INCOMING_FILE: _snapshot(INCOMING_FILE, METADATA, CONTENT_HASH)},
        SequenceIdGenerator(plan_ids=deque((PLAN_ID,)), action_ids=deque((ACTION_ID,))),
    )

    plan = CreateAddPlanUseCase(ports).execute(
        CreateAddPlanRequest(source_path=INCOMING_ROOT, library_id=SECOND_LIBRARY_ID)
    )

    assert plan.library_id == SECOND_LIBRARY_ID
    assert plan.library_root_at_plan == SECOND_LIBRARY_ROOT


def test_add_rejects_unknown_explicit_library_selection() -> None:
    """An opaque Library ID must resolve before scanning or Plan persistence."""
    uow = InMemoryUnitOfWork()
    uow.libraries.save(_library(LIBRARY_ID, LIBRARY_ROOT))
    ports, scanner, _ = _ports(uow, (), {}, SequenceIdGenerator())

    with pytest.raises(AddLibrarySelectionError, match=SELECTED_LIBRARY_NOT_FOUND_MESSAGE):
        _ = CreateAddPlanUseCase(ports).execute(
            CreateAddPlanRequest(source_path=INCOMING_ROOT, library_id=SECOND_LIBRARY_ID)
        )

    assert scanner.scanned_roots == []
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


def test_add_projects_shared_artist_name_resolution_only_into_the_recorded_target() -> None:
    """Add uses the shared resolver while keeping snapshot metadata raw."""
    config = AppConfig()
    path_policy_hash = calculate_path_policy_fingerprint(
        config.path_policy,
        config.artist_ids,
        config.metadata.album_year_resolution,
        config.artist_names,
    )
    uow = InMemoryUnitOfWork()
    uow.libraries.save(_library(LIBRARY_ID, LIBRARY_ROOT, path_policy_hash=path_policy_hash))
    ports, _, _ = _ports(
        uow,
        (_entry(INCOMING_FILE),),
        {INCOMING_FILE: _snapshot(INCOMING_FILE, METADATA, CONTENT_HASH)},
        SequenceIdGenerator(plan_ids=deque((PLAN_ID,)), action_ids=deque((ACTION_ID,))),
        options=PortOptions(config=config, resolved_names={"Artist": "Preferred Artist"}),
    )

    plan = CreateAddPlanUseCase(ports).execute(CreateAddPlanRequest(source_path=INCOMING_ROOT))

    action = plan.actions[0]
    assert action.target_path == EXPECTED_PREFERRED_ARTIST_PATH
    assert action.metadata_hash_at_plan == calculate_metadata_fingerprint(METADATA)
    assert action.artist_name_diagnostics is not None
    assert action.artist_name_diagnostics.artist.source_name == "Artist"
    assert action.artist_name_diagnostics.artist.resolved_name == "Preferred Artist"
    assert action.artist_name_diagnostics.album_artist.source_name is None
    assert action.artist_name_diagnostics.album_artist.resolved_name is None
    assert METADATA.artist == "Artist"
    assert isinstance(ports.artist_name_resolver, MappingArtistNameResolver)
    assert ports.artist_name_resolver.calls == [("Artist", None)]


def test_add_refuses_resolved_source_key_that_would_mix_existing_library_paths() -> None:
    """Add normalizes source keys before deciding that an active Track needs organize."""
    existing_metadata = TrackMetadata(
        title="Existing",
        artist=" Artist ",
        album="Album",
        year=2026,
        track_number=1,
        disc_number=1,
    )
    uow = InMemoryUnitOfWork()
    uow.libraries.save(_library(LIBRARY_ID, LIBRARY_ROOT))
    uow.tracks.save(
        _track(
            OTHER_CONTENT_HASH,
            "Artist/2026_Album/1-01_Existing.flac",
            metadata=existing_metadata,
        )
    )
    ports, _, _ = _ports(
        uow,
        (_entry(INCOMING_FILE),),
        {INCOMING_FILE: _snapshot(INCOMING_FILE, METADATA, CONTENT_HASH)},
        SequenceIdGenerator(),
        options=PortOptions(resolved_names={"Artist": "Preferred Artist"}),
    )

    with pytest.raises(
        AddLibraryReconciliationRequiredError,
        match=ARTIST_NAME_RECONCILIATION_REQUIRED_MESSAGE,
    ):
        _ = CreateAddPlanUseCase(ports).execute(CreateAddPlanRequest(source_path=INCOMING_ROOT))

    assert uow.plans.records == {}
    assert uow.plan_actions.records == {}
    assert isinstance(ports.artist_name_resolver, MappingArtistNameResolver)
    assert ports.artist_name_resolver.calls == [("Artist", None)]


def test_add_allows_resolved_artist_name_after_existing_tracks_are_reconciled() -> None:
    """A matching active Track already at its resolved target does not block Add."""
    existing_metadata = TrackMetadata(
        title="Existing",
        artist="Artist",
        album="Album",
        year=2026,
        track_number=1,
        disc_number=1,
    )
    uow = InMemoryUnitOfWork()
    uow.libraries.save(_library(LIBRARY_ID, LIBRARY_ROOT))
    uow.tracks.save(
        _track(
            OTHER_CONTENT_HASH,
            "Preferred-Artist/2026_Album/1-01_Existing.flac",
            metadata=existing_metadata,
        )
    )
    ports, _, _ = _ports(
        uow,
        (_entry(INCOMING_FILE),),
        {INCOMING_FILE: _snapshot(INCOMING_FILE, METADATA, CONTENT_HASH)},
        SequenceIdGenerator(plan_ids=deque((PLAN_ID,)), action_ids=deque((ACTION_ID,))),
        options=PortOptions(resolved_names={"Artist": "Preferred Artist"}),
    )

    plan = CreateAddPlanUseCase(ports).execute(CreateAddPlanRequest(source_path=INCOMING_ROOT))

    assert plan.actions[0].target_path == EXPECTED_PREFERRED_ARTIST_PATH


def test_add_honors_an_existing_tracks_exact_artist_name_preference() -> None:
    """An exact preference outranks a provider result shared by normalized source key."""
    existing_metadata = TrackMetadata(
        title="Existing",
        artist=" Artist ",
        album="Album",
        year=2026,
        track_number=1,
        disc_number=1,
    )
    config = AppConfig(
        artist_names=ArtistNameConfig(preferences={" Artist ": "Existing Preferred"}),
    )
    path_policy_hash = calculate_path_policy_fingerprint(
        config.path_policy,
        config.artist_ids,
        config.metadata.album_year_resolution,
        config.artist_names,
    )
    uow = InMemoryUnitOfWork()
    uow.libraries.save(_library(LIBRARY_ID, LIBRARY_ROOT, path_policy_hash=path_policy_hash))
    uow.tracks.save(
        _track(
            OTHER_CONTENT_HASH,
            "Existing-Preferred/2026_Album/1-01_Existing.flac",
            metadata=existing_metadata,
        )
    )
    ports, _, _ = _ports(
        uow,
        (_entry(INCOMING_FILE),),
        {INCOMING_FILE: _snapshot(INCOMING_FILE, METADATA, CONTENT_HASH)},
        SequenceIdGenerator(plan_ids=deque((PLAN_ID,)), action_ids=deque((ACTION_ID,))),
        options=PortOptions(
            config=config,
            resolved_names={"Artist": "Provider Preferred"},
        ),
    )

    plan = CreateAddPlanUseCase(ports).execute(CreateAddPlanRequest(source_path=INCOMING_ROOT))

    assert plan.actions[0].target_path == "Provider-Preferred/2026_Album/1-02_Title.flac"


def test_add_does_not_spread_an_incoming_exact_preference_across_a_normalized_key() -> None:
    """An exact incoming preference does not rename a distinct existing raw value."""
    existing_metadata = TrackMetadata(
        title="Existing",
        artist=" Artist ",
        album="Album",
        year=2026,
        track_number=1,
        disc_number=1,
    )
    config = AppConfig(
        artist_names=ArtistNameConfig(preferences={"Artist": "Incoming Preferred"}),
    )
    path_policy_hash = calculate_path_policy_fingerprint(
        config.path_policy,
        config.artist_ids,
        config.metadata.album_year_resolution,
        config.artist_names,
    )
    uow = InMemoryUnitOfWork()
    uow.libraries.save(_library(LIBRARY_ID, LIBRARY_ROOT, path_policy_hash=path_policy_hash))
    uow.tracks.save(
        _track(
            OTHER_CONTENT_HASH,
            "Artist/2026_Album/1-01_Existing.flac",
            metadata=existing_metadata,
        )
    )
    ports, _, _ = _ports(
        uow,
        (_entry(INCOMING_FILE),),
        {INCOMING_FILE: _snapshot(INCOMING_FILE, METADATA, CONTENT_HASH)},
        SequenceIdGenerator(plan_ids=deque((PLAN_ID,)), action_ids=deque((ACTION_ID,))),
        options=PortOptions(config=config),
    )

    plan = CreateAddPlanUseCase(ports).execute(CreateAddPlanRequest(source_path=INCOMING_ROOT))

    assert plan.actions[0].target_path == "Incoming-Preferred/2026_Album/1-02_Title.flac"


def test_add_does_not_require_reconciliation_for_a_duplicate_skip() -> None:
    """A resolved duplicate is not imported and therefore cannot create mixed naming."""
    uow = InMemoryUnitOfWork()
    uow.libraries.save(_library(LIBRARY_ID, LIBRARY_ROOT))
    uow.tracks.save(_track(CONTENT_HASH, EXPECTED_CANONICAL_PATH))
    ports, _, _ = _ports(
        uow,
        (_entry(INCOMING_FILE),),
        {INCOMING_FILE: _snapshot(INCOMING_FILE, METADATA, CONTENT_HASH)},
        SequenceIdGenerator(plan_ids=deque((PLAN_ID,)), action_ids=deque((ACTION_ID,))),
        options=PortOptions(resolved_names={"Artist": "Preferred Artist"}),
    )

    plan = CreateAddPlanUseCase(ports).execute(CreateAddPlanRequest(source_path=INCOMING_ROOT))

    action = plan.actions[0]
    assert action.action_type is ActionType.SKIP
    assert action.reason is PlanActionReason.DUPLICATE_HASH


def test_add_excludes_duplicate_skip_from_reconciliation_disc_context() -> None:
    """A skipped disc-two duplicate cannot make a reconciled Track appear stale."""
    config = AppConfig(
        path_policy=PathPolicyConfig(
            disc_number_style=PATH_POLICY_DISC_NUMBER_STYLE_D_PREFIXED,
            disc_number_condition=PATH_POLICY_DISC_NUMBER_CONDITION_MULTIPLE_DISCS,
        )
    )
    existing_metadata = TrackMetadata(
        title="Existing",
        artist="Artist",
        album="Album",
        year=2026,
        track_number=1,
        disc_number=1,
    )
    known_duplicate_metadata = TrackMetadata(
        title="Known duplicate",
        artist="Other Artist",
        album="Other Album",
        year=YEAR_2002,
        track_number=1,
        disc_number=1,
    )
    skipped_duplicate_metadata = TrackMetadata(
        title="Skipped duplicate",
        artist="Artist",
        album="Album",
        year=2026,
        track_number=3,
        disc_number=2,
    )
    duplicate_content_hash = calculate_content_fingerprint(b"duplicate audio")
    path_policy_hash = calculate_path_policy_fingerprint(
        config.path_policy,
        config.artist_ids,
        config.metadata.album_year_resolution,
        config.artist_names,
    )
    uow = InMemoryUnitOfWork()
    uow.libraries.save(_library(LIBRARY_ID, LIBRARY_ROOT, path_policy_hash=path_policy_hash))
    uow.tracks.save(
        _track(
            OTHER_CONTENT_HASH,
            "Preferred-Artist/2026_Album/01_Existing.flac",
            metadata=existing_metadata,
        )
    )
    uow.tracks.save(
        _track(
            duplicate_content_hash,
            "Other-Artist/2002_Other-Album/01_Known-duplicate.flac",
            track_id=SECOND_TRACK_ID,
            metadata=known_duplicate_metadata,
        )
    )
    ports, _, _ = _ports(
        uow,
        (_entry(INCOMING_FILE), _entry(SECOND_INCOMING_FILE)),
        {
            INCOMING_FILE: _snapshot(INCOMING_FILE, METADATA, CONTENT_HASH),
            SECOND_INCOMING_FILE: _snapshot(
                SECOND_INCOMING_FILE,
                skipped_duplicate_metadata,
                duplicate_content_hash,
            ),
        },
        SequenceIdGenerator(
            plan_ids=deque((PLAN_ID,)),
            action_ids=deque((ACTION_ID, SECOND_ACTION_ID)),
        ),
        options=PortOptions(
            config=config,
            resolved_names={"Artist": "Preferred Artist"},
        ),
    )

    plan = CreateAddPlanUseCase(ports).execute(CreateAddPlanRequest(source_path=INCOMING_ROOT))

    move_action, duplicate_action = plan.actions
    assert move_action.action_type is ActionType.MOVE
    assert move_action.reason is None
    assert duplicate_action.action_type is ActionType.SKIP
    assert duplicate_action.reason is PlanActionReason.DUPLICATE_HASH


def test_add_does_not_require_reconciliation_for_a_blocked_target() -> None:
    """A blocked resolved move cannot introduce mixed naming into the Library."""
    uow = InMemoryUnitOfWork()
    uow.libraries.save(_library(LIBRARY_ID, LIBRARY_ROOT))
    uow.tracks.save(_track(OTHER_CONTENT_HASH, EXPECTED_CANONICAL_PATH))
    ports, _, _ = _ports(
        uow,
        (_entry(INCOMING_FILE),),
        {INCOMING_FILE: _snapshot(INCOMING_FILE, METADATA, CONTENT_HASH)},
        SequenceIdGenerator(plan_ids=deque((PLAN_ID,)), action_ids=deque((ACTION_ID,))),
        options=PortOptions(
            existing_files={f"{LIBRARY_ROOT}/{EXPECTED_PREFERRED_ARTIST_PATH}"},
            resolved_names={"Artist": "Preferred Artist"},
        ),
    )

    plan = CreateAddPlanUseCase(ports).execute(CreateAddPlanRequest(source_path=INCOMING_ROOT))

    action = plan.actions[0]
    assert action.status is ActionStatus.BLOCKED
    assert action.reason is PlanActionReason.TARGET_EXISTS


def test_add_does_not_reconcile_names_against_removed_tracks() -> None:
    """Removed Track naming does not constrain a new active import path."""
    uow = InMemoryUnitOfWork()
    uow.libraries.save(_library(LIBRARY_ID, LIBRARY_ROOT))
    uow.tracks.save(
        _track(
            OTHER_CONTENT_HASH,
            EXPECTED_CANONICAL_PATH,
            status=TrackStatus.REMOVED,
        )
    )
    ports, _, _ = _ports(
        uow,
        (_entry(INCOMING_FILE),),
        {INCOMING_FILE: _snapshot(INCOMING_FILE, METADATA, CONTENT_HASH)},
        SequenceIdGenerator(plan_ids=deque((PLAN_ID,)), action_ids=deque((ACTION_ID,))),
        options=PortOptions(resolved_names={"Artist": "Preferred Artist"}),
    )

    plan = CreateAddPlanUseCase(ports).execute(CreateAddPlanRequest(source_path=INCOMING_ROOT))

    assert plan.actions[0].target_path == EXPECTED_PREFERRED_ARTIST_PATH


def test_add_does_not_reconcile_names_when_the_template_ignores_artist_fields() -> None:
    """Resolved names do not gate Add when they cannot change managed paths."""
    config = AppConfig(path_policy=PathPolicyConfig(template="{album}/{track}_{title}"))
    path_policy_hash = calculate_path_policy_fingerprint(
        config.path_policy,
        config.artist_ids,
        config.metadata.album_year_resolution,
        config.artist_names,
    )
    uow = InMemoryUnitOfWork()
    uow.libraries.save(_library(LIBRARY_ID, LIBRARY_ROOT, path_policy_hash=path_policy_hash))
    uow.tracks.save(_track(OTHER_CONTENT_HASH, "unrelated/current.flac"))
    ports, _, _ = _ports(
        uow,
        (_entry(INCOMING_FILE),),
        {INCOMING_FILE: _snapshot(INCOMING_FILE, METADATA, CONTENT_HASH)},
        SequenceIdGenerator(plan_ids=deque((PLAN_ID,)), action_ids=deque((ACTION_ID,))),
        options=PortOptions(config=config, resolved_names={"Artist": "Preferred Artist"}),
    )

    plan = CreateAddPlanUseCase(ports).execute(CreateAddPlanRequest(source_path=INCOMING_ROOT))

    assert plan.actions[0].target_path == "Album/02_Title.flac"


def test_add_plan_resolves_latest_album_year_across_incoming_album_group() -> None:
    """Add renders one effective album year without changing raw snapshots."""
    first_metadata = _album_track_metadata(title="Song 1", year=YEAR_1998, track_number=1)
    second_metadata = _album_track_metadata(title="Song 2", year=YEAR_2002, track_number=2)
    third_metadata = _album_track_metadata(title="Song 3", year=YEAR_2004, track_number=3)
    uow = InMemoryUnitOfWork()
    uow.libraries.save(_library(LIBRARY_ID, LIBRARY_ROOT))
    ports, _, _ = _ports(
        uow,
        (_entry(INCOMING_FILE), _entry(SECOND_INCOMING_FILE), _entry(THIRD_INCOMING_FILE)),
        {
            INCOMING_FILE: _snapshot(INCOMING_FILE, first_metadata, calculate_content_fingerprint(b"audio-1")),
            SECOND_INCOMING_FILE: _snapshot(
                SECOND_INCOMING_FILE,
                second_metadata,
                calculate_content_fingerprint(b"audio-2"),
            ),
            THIRD_INCOMING_FILE: _snapshot(
                THIRD_INCOMING_FILE,
                third_metadata,
                calculate_content_fingerprint(b"audio-3"),
            ),
        },
        SequenceIdGenerator(
            plan_ids=deque((PLAN_ID,)),
            action_ids=deque((ACTION_ID, SECOND_ACTION_ID, THIRD_ACTION_ID)),
        ),
    )

    plan = CreateAddPlanUseCase(ports).execute(CreateAddPlanRequest(source_path=INCOMING_ROOT))

    assert tuple(action.target_path for action in plan.actions) == (
        "Artist/2004_Album/1-01_Song-1.flac",
        "Artist/2004_Album/1-02_Song-2.flac",
        "Artist/2004_Album/1-03_Song-3.flac",
    )
    assert first_metadata.year == YEAR_1998
    assert second_metadata.year == YEAR_2002
    assert third_metadata.year == YEAR_2004


def test_add_plan_ignores_removed_tracks_when_resolving_album_year() -> None:
    """Removed Library tracks do not influence effective add target years."""
    active_metadata = _album_track_metadata(title="Active", year=YEAR_2002, track_number=1)
    removed_metadata = _album_track_metadata(title="Removed", year=YEAR_2004, track_number=2)
    incoming_metadata = _album_track_metadata(title="Incoming", year=YEAR_1998, track_number=3)
    uow = InMemoryUnitOfWork()
    uow.libraries.save(_library(LIBRARY_ID, LIBRARY_ROOT))
    uow.tracks.save(
        _track(
            calculate_content_fingerprint(b"active"),
            "Artist/2002_Album/1-01_Active.flac",
            metadata=active_metadata,
        )
    )
    uow.tracks.save(
        _track(
            calculate_content_fingerprint(b"removed"),
            "Artist/2004_Album/1-02_Removed.flac",
            track_id=SECOND_TRACK_ID,
            metadata=removed_metadata,
            status=TrackStatus.REMOVED,
        )
    )
    ports, _, _ = _ports(
        uow,
        (_entry(INCOMING_FILE),),
        {INCOMING_FILE: _snapshot(INCOMING_FILE, incoming_metadata, CONTENT_HASH)},
        SequenceIdGenerator(plan_ids=deque((PLAN_ID,)), action_ids=deque((ACTION_ID,))),
    )

    plan = CreateAddPlanUseCase(ports).execute(CreateAddPlanRequest(source_path=INCOMING_ROOT))

    assert plan.actions[0].target_path == "Artist/2002_Album/1-03_Incoming.flac"
    assert incoming_metadata.year == YEAR_1998


def test_add_renders_disc_number_from_existing_library_peer_context() -> None:
    """Add infers multi-disc context from active Library tracks plus incoming snapshots."""
    config = AppConfig(
        path_policy=PathPolicyConfig(
            disc_number_style=PATH_POLICY_DISC_NUMBER_STYLE_D_PREFIXED,
            disc_number_condition=PATH_POLICY_DISC_NUMBER_CONDITION_MULTIPLE_DISCS,
        )
    )
    uow = InMemoryUnitOfWork()
    uow.libraries.save(
        _library(
            LIBRARY_ID,
            LIBRARY_ROOT,
            path_policy_hash=calculate_path_policy_fingerprint(config.path_policy, config.artist_ids),
        )
    )
    uow.tracks.save(
        _track(
            OTHER_CONTENT_HASH,
            "Artist/2026_Album/D2-05_Peer.flac",
            track_id=SECOND_TRACK_ID,
            metadata=PEER_METADATA,
        )
    )
    ports, _, _ = _ports(
        uow,
        (_entry(INCOMING_FILE),),
        {INCOMING_FILE: _snapshot(INCOMING_FILE, METADATA, CONTENT_HASH)},
        SequenceIdGenerator(plan_ids=deque((PLAN_ID,)), action_ids=deque((ACTION_ID,))),
        options=PortOptions(config=config),
    )

    plan = CreateAddPlanUseCase(ports).execute(CreateAddPlanRequest(source_path=INCOMING_ROOT))

    assert plan.actions[0].target_path == EXPECTED_D_PREFIXED_PATH


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


def test_add_plan_duplicate_skip_references_first_track_in_list_order() -> None:
    """A duplicate skip references the first matching Track in repository list
    order (current_path, then track_id)."""
    uow = InMemoryUnitOfWork()
    uow.libraries.save(_library(LIBRARY_ID, LIBRARY_ROOT))
    uow.tracks.save(_track(CONTENT_HASH, EXPECTED_CANONICAL_PATH))
    uow.tracks.save(_track(CONTENT_HASH, SECOND_DUPLICATE_TRACK_PATH, track_id=SECOND_TRACK_ID))
    ports, _, _ = _ports(
        uow,
        (_entry(INCOMING_FILE),),
        {INCOMING_FILE: _snapshot(INCOMING_FILE, METADATA, CONTENT_HASH)},
        SequenceIdGenerator(plan_ids=deque((PLAN_ID,)), action_ids=deque((ACTION_ID,))),
    )

    plan = CreateAddPlanUseCase(ports).execute(CreateAddPlanRequest(source_path=INCOMING_ROOT))

    action = plan.actions[0]
    assert action.action_type == ActionType.SKIP
    assert action.reason == PlanActionReason.DUPLICATE_HASH
    assert action.track_id == TRACK_ID


def test_add_plan_ignores_removed_track_for_duplicate_hash() -> None:
    """A REMOVED Library track's content hash no longer skips incoming imports."""
    uow = InMemoryUnitOfWork()
    uow.libraries.save(_library(LIBRARY_ID, LIBRARY_ROOT))
    uow.tracks.save(_track(CONTENT_HASH, SECOND_DUPLICATE_TRACK_PATH, status=TrackStatus.REMOVED))
    ports, _, _ = _ports(
        uow,
        (_entry(INCOMING_FILE),),
        {INCOMING_FILE: _snapshot(INCOMING_FILE, METADATA, CONTENT_HASH)},
        SequenceIdGenerator(plan_ids=deque((PLAN_ID,)), action_ids=deque((ACTION_ID,))),
    )

    plan = CreateAddPlanUseCase(ports).execute(CreateAddPlanRequest(source_path=INCOMING_ROOT))

    action = plan.actions[0]
    assert action.action_type == ActionType.MOVE
    assert action.status == ActionStatus.PLANNED
    assert action.reason is None
    assert action.target_path == EXPECTED_CANONICAL_PATH


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


def test_add_plan_ignores_removed_track_current_path_for_target_conflict() -> None:
    """A REMOVED Library track's current path no longer blocks incoming targets."""
    uow = InMemoryUnitOfWork()
    uow.libraries.save(_library(LIBRARY_ID, LIBRARY_ROOT))
    uow.tracks.save(_track(OTHER_CONTENT_HASH, EXPECTED_CANONICAL_PATH, status=TrackStatus.REMOVED))
    ports, _, _ = _ports(
        uow,
        (_entry(INCOMING_FILE),),
        {INCOMING_FILE: _snapshot(INCOMING_FILE, METADATA, CONTENT_HASH)},
        SequenceIdGenerator(plan_ids=deque((PLAN_ID,)), action_ids=deque((ACTION_ID,))),
    )

    plan = CreateAddPlanUseCase(ports).execute(CreateAddPlanRequest(source_path=INCOMING_ROOT))

    action = plan.actions[0]
    assert action.action_type == ActionType.MOVE
    assert action.status == ActionStatus.PLANNED
    assert action.reason is None
    assert action.target_path == EXPECTED_CANONICAL_PATH


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
        filesystem_identity=None,
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

    plans_page = ListPlansUseCase(query_ports).execute(ListPlansRequest())
    header = GetPlanHeaderUseCase(query_ports).execute(GetPlanHeaderRequest(PLAN_ID))
    actions_page = ListPlanActionsUseCase(query_ports).execute(ListPlanActionsRequest(plan_id=PLAN_ID))

    assert plans_page.items == (plan,)
    assert header == plan
    assert actions_page.items == plan.actions


def test_add_plans_unique_lyrics_after_audio_with_durable_owner_dependency() -> None:
    """An enabled unique lyric is reviewed after its owner and creates no premature asset row."""
    lyrics_path = f"{INCOMING_ROOT}/Title.lrc"
    uow = InMemoryUnitOfWork()
    uow.libraries.save(_library(LIBRARY_ID, LIBRARY_ROOT))
    ports, _, _ = _ports(
        uow,
        (_entry(INCOMING_FILE),),
        {INCOMING_FILE: _snapshot(INCOMING_FILE, METADATA, CONTENT_HASH)},
        SequenceIdGenerator(
            plan_ids=deque((PLAN_ID,)),
            action_ids=deque((ACTION_ID, SECOND_ACTION_ID)),
            companion_asset_ids=deque((COMPANION_ASSET_ID,)),
        ),
        options=PortOptions(
            config=_companion_enabled_config(),
            inventory_entries=(
                SourceInventoryEntry(path=INCOMING_FILE, relative_path="Title.flac"),
                SourceInventoryEntry(path=lyrics_path, relative_path="Title.lrc"),
            ),
            content_results={lyrics_path: _content_snapshot(lyrics_path)},
        ),
    )

    plan = CreateAddPlanUseCase(ports).execute(CreateAddPlanRequest(INCOMING_ROOT))

    assert [action.action_type for action in plan.actions] == [ActionType.MOVE, ActionType.MOVE_LYRICS]
    owner, lyrics = plan.actions
    assert plan.source_root_at_plan == INCOMING_ROOT
    assert lyrics.owner_action_id == owner.action_id
    assert lyrics.companion_asset_id == COMPANION_ASSET_ID
    assert lyrics.source_path == lyrics_path
    assert lyrics.target_path == EXPECTED_CANONICAL_PATH.removesuffix(".flac") + ".lrc"
    assert lyrics.content_hash_at_plan == "companion-hash"
    assert uow.plan_action_dependencies.list_by_action(lyrics.action_id) == (
        PlanActionDependency(
            plan_id=PLAN_ID,
            action_id=lyrics.action_id,
            depends_on_action_id=owner.action_id,
        ),
    )
    assert uow.companion_assets.records == {}


def test_add_replans_failed_lyrics_without_rescanning_moved_audio() -> None:
    """Exact retained Add history creates one companion-only retry with stable identity."""
    failed_run_id = RunId(UUID("018f6a4f-3c2d-7b8a-9abc-def012345691"))
    audio_event_id = EventId(UUID("018f6a4f-3c2d-7b8a-9abc-def012345692"))
    companion_event_id = EventId(UUID("018f6a4f-3c2d-7b8a-9abc-def012345693"))
    recovery_plan_id = PlanId(UUID("018f6a4f-3c2d-7b8a-9abc-def012345694"))
    lyrics_path = f"{INCOMING_ROOT}/Title.lrc"
    lyrics_target = EXPECTED_CANONICAL_PATH.removesuffix(".flac") + ".lrc"
    uow = InMemoryUnitOfWork()
    uow.libraries.save(_library(LIBRARY_ID, LIBRARY_ROOT))
    uow.tracks.save(_track(CONTENT_HASH, EXPECTED_CANONICAL_PATH))
    failed_plan = Plan(
        plan_id=PLAN_ID,
        library_id=LIBRARY_ID,
        plan_type=PlanType.ADD,
        status=PlanStatus.PARTIAL_FAILED,
        created_at=BASE_TIME,
        config_hash="failed-config",
        library_root_at_plan=LIBRARY_ROOT,
        source_root_at_plan=INCOMING_ROOT,
    )
    audio_action = PlanAction(
        action_id=ACTION_ID,
        plan_id=PLAN_ID,
        library_id=LIBRARY_ID,
        track_id=TRACK_ID,
        action_type=ActionType.MOVE,
        source_path=INCOMING_FILE,
        target_path=EXPECTED_CANONICAL_PATH,
        content_hash_at_plan=CONTENT_HASH,
        metadata_hash_at_plan=calculate_metadata_fingerprint(METADATA),
        status=ActionStatus.APPLIED,
        reason=None,
        sort_order=1,
    )
    failed_lyrics = PlanAction(
        action_id=SECOND_ACTION_ID,
        plan_id=PLAN_ID,
        library_id=LIBRARY_ID,
        track_id=None,
        action_type=ActionType.MOVE_LYRICS,
        source_path=lyrics_path,
        target_path=lyrics_target,
        content_hash_at_plan="companion-hash",
        metadata_hash_at_plan=None,
        status=ActionStatus.FAILED,
        reason=PlanActionReason.TARGET_EXISTS,
        sort_order=2,
        companion_asset_id=COMPANION_ASSET_ID,
        owner_action_id=ACTION_ID,
    )
    failed_run = Run(
        run_id=failed_run_id,
        plan_id=PLAN_ID,
        library_id=LIBRARY_ID,
        status=RunStatus.PARTIAL_FAILED,
        started_at=BASE_TIME,
        completed_at=BASE_TIME + timedelta(minutes=1),
        error_summary="target exists",
    )
    uow.plans.save(failed_plan)
    uow.plan_actions.save(audio_action)
    uow.plan_actions.save(failed_lyrics)
    uow.plan_action_dependencies.save(
        PlanActionDependency(
            plan_id=PLAN_ID,
            action_id=SECOND_ACTION_ID,
            depends_on_action_id=ACTION_ID,
        )
    )
    uow.runs.save(failed_run)
    uow.file_events.save(
        FileEvent(
            event_id=audio_event_id,
            library_id=LIBRARY_ID,
            run_id=failed_run_id,
            plan_action_id=ACTION_ID,
            event_type=FileEventType.MOVE_FILE,
            source_path=INCOMING_FILE,
            target_path=EXPECTED_CANONICAL_PATH,
            status=FileEventStatus.SUCCEEDED,
            started_at=BASE_TIME,
            completed_at=BASE_TIME + timedelta(seconds=10),
            error_code=None,
            error_message=None,
            sequence_no=1,
        )
    )
    uow.file_events.save(
        FileEvent(
            event_id=companion_event_id,
            library_id=LIBRARY_ID,
            run_id=failed_run_id,
            plan_action_id=SECOND_ACTION_ID,
            event_type=FileEventType.MOVE_LYRICS_FILE,
            source_path=lyrics_path,
            target_path=lyrics_target,
            status=FileEventStatus.FAILED,
            started_at=BASE_TIME + timedelta(seconds=20),
            completed_at=BASE_TIME + timedelta(seconds=30),
            error_code=PlanActionReason.TARGET_EXISTS.value,
            error_message="target exists",
            sequence_no=2,
            companion_asset_id=COMPANION_ASSET_ID,
        )
    )
    ports, _, _ = _ports(
        uow,
        (),
        {},
        SequenceIdGenerator(
            plan_ids=deque((recovery_plan_id,)),
            action_ids=deque((THIRD_ACTION_ID,)),
        ),
        options=PortOptions(
            config=_companion_enabled_config(),
            inventory_entries=(SourceInventoryEntry(path=lyrics_path, relative_path="Title.lrc"),),
            content_results={lyrics_path: _content_snapshot(lyrics_path)},
        ),
    )

    plan = CreateAddPlanUseCase(ports).execute(CreateAddPlanRequest(INCOMING_ROOT))

    assert plan.plan_id == recovery_plan_id
    assert len(plan.actions) == 1
    recovery = plan.actions[0]
    assert recovery.action_type is ActionType.MOVE_LYRICS
    assert recovery.track_id == TRACK_ID
    assert recovery.companion_asset_id == COMPANION_ASSET_ID
    assert recovery.owner_action_id is None
    assert recovery.source_path == lyrics_path
    assert recovery.target_path == lyrics_target
    assert uow.plan_action_dependencies.list_by_action(recovery.action_id) == ()


def test_add_blocks_ambiguous_lyrics_and_records_every_candidate_dependency() -> None:
    """Same-stem audio ambiguity remains reviewable and retains both durable dependencies."""
    second_audio = f"{INCOMING_ROOT}/Title.mp3"
    lyrics_path = f"{INCOMING_ROOT}/Title.lrc"
    second_snapshot = replace(
        _snapshot(second_audio, METADATA, OTHER_CONTENT_HASH),
        file_extension=".mp3",
    )
    uow = InMemoryUnitOfWork()
    uow.libraries.save(_library(LIBRARY_ID, LIBRARY_ROOT))
    ports, _, _ = _ports(
        uow,
        (_entry(INCOMING_FILE), replace(_entry(second_audio), file_extension=".mp3")),
        {
            INCOMING_FILE: _snapshot(INCOMING_FILE, METADATA, CONTENT_HASH),
            second_audio: second_snapshot,
        },
        SequenceIdGenerator(
            plan_ids=deque((PLAN_ID,)),
            action_ids=deque((ACTION_ID, SECOND_ACTION_ID, THIRD_ACTION_ID)),
            companion_asset_ids=deque((COMPANION_ASSET_ID,)),
        ),
        options=PortOptions(
            config=_companion_enabled_config(),
            inventory_entries=(SourceInventoryEntry(path=lyrics_path, relative_path="Title.lrc"),),
            content_results={lyrics_path: _content_snapshot(lyrics_path)},
        ),
    )

    plan = CreateAddPlanUseCase(ports).execute(CreateAddPlanRequest(INCOMING_ROOT))

    ambiguous = plan.actions[-1]
    assert ambiguous.action_type is ActionType.MOVE_LYRICS
    assert ambiguous.status is ActionStatus.BLOCKED
    assert ambiguous.reason is PlanActionReason.COMPANION_ASSOCIATION_AMBIGUOUS
    assert ambiguous.owner_action_id is None
    assert {
        dependency.depends_on_action_id
        for dependency in uow.plan_action_dependencies.list_by_action(ambiguous.action_id)
    } == {ACTION_ID, SECOND_ACTION_ID}


def test_add_plans_shared_artwork_once_with_all_audio_dependencies() -> None:
    """One sibling artwork source becomes one action after every audio action."""
    artwork_path = f"{INCOMING_ROOT}/cover.jpg"
    second_metadata = replace(METADATA, title="Title2", track_number=3)
    uow = InMemoryUnitOfWork()
    uow.libraries.save(_library(LIBRARY_ID, LIBRARY_ROOT))
    ports, _, _ = _ports(
        uow,
        (_entry(INCOMING_FILE), _entry(SECOND_INCOMING_FILE)),
        {
            INCOMING_FILE: _snapshot(INCOMING_FILE, METADATA, CONTENT_HASH),
            SECOND_INCOMING_FILE: _snapshot(SECOND_INCOMING_FILE, second_metadata, OTHER_CONTENT_HASH),
        },
        SequenceIdGenerator(
            plan_ids=deque((PLAN_ID,)),
            action_ids=deque((ACTION_ID, SECOND_ACTION_ID, THIRD_ACTION_ID)),
            companion_asset_ids=deque((COMPANION_ASSET_ID,)),
        ),
        options=PortOptions(
            config=_companion_enabled_config(),
            inventory_entries=(SourceInventoryEntry(path=artwork_path, relative_path="cover.jpg"),),
            content_results={artwork_path: _content_snapshot(artwork_path)},
        ),
    )

    plan = CreateAddPlanUseCase(ports).execute(CreateAddPlanRequest(INCOMING_ROOT))

    artwork_actions = [action for action in plan.actions if action.action_type is ActionType.MOVE_ARTWORK]
    assert len(artwork_actions) == 1
    artwork = artwork_actions[0]
    assert artwork.target_path == "Artist/2026_Album/cover.jpg"
    assert {
        dependency.depends_on_action_id for dependency in uow.plan_action_dependencies.list_by_action(artwork.action_id)
    } == {ACTION_ID, SECOND_ACTION_ID}


def test_add_blocks_shared_artwork_when_audio_targets_split_across_parents() -> None:
    """Shared artwork never guesses a target when sibling audio resolves to mixed parents."""
    artwork_path = f"{INCOMING_ROOT}/cover.png"
    second_metadata = replace(METADATA, title="Title2", artist="Other", track_number=3)
    uow = InMemoryUnitOfWork()
    uow.libraries.save(_library(LIBRARY_ID, LIBRARY_ROOT))
    ports, _, _ = _ports(
        uow,
        (_entry(INCOMING_FILE), _entry(SECOND_INCOMING_FILE)),
        {
            INCOMING_FILE: _snapshot(INCOMING_FILE, METADATA, CONTENT_HASH),
            SECOND_INCOMING_FILE: _snapshot(SECOND_INCOMING_FILE, second_metadata, OTHER_CONTENT_HASH),
        },
        SequenceIdGenerator(
            plan_ids=deque((PLAN_ID,)),
            action_ids=deque((ACTION_ID, SECOND_ACTION_ID, THIRD_ACTION_ID)),
            companion_asset_ids=deque((COMPANION_ASSET_ID,)),
        ),
        options=PortOptions(
            config=_companion_enabled_config(),
            inventory_entries=(SourceInventoryEntry(path=artwork_path, relative_path="cover.png"),),
            content_results={artwork_path: _content_snapshot(artwork_path)},
        ),
    )

    plan = CreateAddPlanUseCase(ports).execute(CreateAddPlanRequest(INCOMING_ROOT))

    artwork = plan.actions[-1]
    assert artwork.status is ActionStatus.BLOCKED
    assert artwork.reason is PlanActionReason.COMPANION_ASSOCIATION_AMBIGUOUS
    assert artwork.target_path is None


def test_add_both_collection_features_disabled_skip_source_inventory() -> None:
    """Default Add avoids optional inventory capabilities and companion observations."""
    lyrics_path = f"{INCOMING_ROOT}/Title.lrc"
    uow = InMemoryUnitOfWork()
    uow.libraries.save(_library(LIBRARY_ID, LIBRARY_ROOT))
    ports, _, _ = _ports(
        uow,
        (_entry(INCOMING_FILE),),
        {INCOMING_FILE: _snapshot(INCOMING_FILE, METADATA, CONTENT_HASH)},
        SequenceIdGenerator(plan_ids=deque((PLAN_ID,)), action_ids=deque((ACTION_ID,))),
        options=PortOptions(
            inventory_entries=(SourceInventoryEntry(path=lyrics_path, relative_path="Title.lrc"),),
        ),
    )

    plan = CreateAddPlanUseCase(ports).execute(CreateAddPlanRequest(INCOMING_ROOT))

    assert [action.action_type for action in plan.actions] == [ActionType.MOVE]
    assert isinstance(ports.source_inventory_reader, StaticSourceInventoryReader)
    assert ports.source_inventory_reader.requests == []
    assert isinstance(ports.file_content_snapshot_reader, MappingFileContentSnapshotReader)
    assert ports.file_content_snapshot_reader.captures == []


def test_add_unprocessed_disabled_leaves_an_eligible_leftover_unplanned() -> None:
    """Turning collection off stops new leftover actions and content observations."""
    leftover = f"{INCOMING_ROOT}/notes.txt"
    uow = InMemoryUnitOfWork()
    uow.libraries.save(_library(LIBRARY_ID, LIBRARY_ROOT))
    ports, _, _ = _ports(
        uow,
        (),
        {},
        SequenceIdGenerator(plan_ids=deque((PLAN_ID,))),
        options=PortOptions(
            inventory_entries=(SourceInventoryEntry(path=leftover, relative_path="notes.txt"),),
            content_results={leftover: _content_snapshot(leftover)},
        ),
    )

    plan = CreateAddPlanUseCase(ports).execute(CreateAddPlanRequest(INCOMING_ROOT))

    assert plan.actions == ()
    assert plan.summary["unprocessed_actions"] == "0"
    assert isinstance(ports.file_content_snapshot_reader, MappingFileContentSnapshotReader)
    assert ports.file_content_snapshot_reader.captures == []


@pytest.mark.parametrize(
    ("content_result", "existing_files", "expected_reason"),
    [
        (FileNotFoundError("gone"), None, PlanActionReason.SOURCE_MISSING),
        (FileObservationInvalidPathError("symlink"), None, PlanActionReason.INVALID_PATH),
        (FileObservationChangedError("changed"), None, PlanActionReason.SOURCE_CHANGED),
        (None, {f"{LIBRARY_ROOT}/Artist/2026_Album/1-02_Title.lrc"}, PlanActionReason.TARGET_EXISTS),
    ],
)
def test_add_companion_observation_and_live_collision_fail_closed(
    content_result: BaseException | None,
    existing_files: set[str] | None,
    expected_reason: PlanActionReason,
) -> None:
    """Disappearance, symlink replacement, change, and live collision each block safely."""
    lyrics_path = f"{INCOMING_ROOT}/Title.lrc"
    result = _content_snapshot(lyrics_path) if content_result is None else content_result
    uow = InMemoryUnitOfWork()
    uow.libraries.save(_library(LIBRARY_ID, LIBRARY_ROOT))
    ports, _, _ = _ports(
        uow,
        (_entry(INCOMING_FILE),),
        {INCOMING_FILE: _snapshot(INCOMING_FILE, METADATA, CONTENT_HASH)},
        SequenceIdGenerator(
            plan_ids=deque((PLAN_ID,)),
            action_ids=deque((ACTION_ID, SECOND_ACTION_ID)),
            companion_asset_ids=deque((COMPANION_ASSET_ID,)),
        ),
        options=PortOptions(
            config=_companion_enabled_config(),
            existing_files=existing_files,
            inventory_entries=(SourceInventoryEntry(path=lyrics_path, relative_path="Title.lrc"),),
            content_results={lyrics_path: result},
        ),
    )

    plan = CreateAddPlanUseCase(ports).execute(CreateAddPlanRequest(INCOMING_ROOT))

    companion = plan.actions[-1]
    assert companion.status is ActionStatus.BLOCKED
    assert companion.reason is expected_reason


def test_add_blocks_companion_when_owner_audio_is_blocked() -> None:
    """A companion cannot execute when its owning audio move is already blocked."""
    lyrics_path = f"{INCOMING_ROOT}/Title.lrc"
    uow = InMemoryUnitOfWork()
    uow.libraries.save(_library(LIBRARY_ID, LIBRARY_ROOT))
    ports, _, _ = _ports(
        uow,
        (_entry(INCOMING_FILE),),
        {INCOMING_FILE: _snapshot(INCOMING_FILE, METADATA, CONTENT_HASH)},
        SequenceIdGenerator(
            plan_ids=deque((PLAN_ID,)),
            action_ids=deque((ACTION_ID, SECOND_ACTION_ID)),
            companion_asset_ids=deque((COMPANION_ASSET_ID,)),
        ),
        options=PortOptions(
            config=_companion_enabled_config(),
            existing_files={f"{LIBRARY_ROOT}/{EXPECTED_CANONICAL_PATH}"},
            inventory_entries=(SourceInventoryEntry(path=lyrics_path, relative_path="Title.lrc"),),
            content_results={lyrics_path: _content_snapshot(lyrics_path)},
        ),
    )

    plan = CreateAddPlanUseCase(ports).execute(CreateAddPlanRequest(INCOMING_ROOT))

    owner, companion = plan.actions
    assert owner.reason is PlanActionReason.TARGET_EXISTS
    assert companion.status is ActionStatus.BLOCKED
    assert companion.reason is PlanActionReason.COMPANION_OWNER_BLOCKED


def test_add_rejects_a_source_inside_the_library_before_scanning() -> None:
    """Add never inventories or plans files from inside the managed Library."""
    uow = InMemoryUnitOfWork()
    uow.libraries.save(_library(LIBRARY_ID, LIBRARY_ROOT))
    ports, scanner, _ = _ports(uow, (), {}, SequenceIdGenerator())

    with pytest.raises(AddSourceSelectionError, match=SOURCE_INSIDE_LIBRARY_MESSAGE):
        _ = CreateAddPlanUseCase(ports).execute(CreateAddPlanRequest(f"{LIBRARY_ROOT}/incoming"))

    assert scanner.scanned_roots == []
    assert uow.plans.records == {}


def test_add_treats_every_scanner_entry_as_claimed_and_collects_only_true_leftovers() -> None:
    """A scanner-emitted odd extension remains audio while an un-emitted extension is reviewed."""
    scanner_claimed = f"{INCOMING_ROOT}/scanner-claimed.odd"
    unsupported_leftover = f"{INCOMING_ROOT}/unsupported.leftover"
    scan_entry = replace(_entry(scanner_claimed), file_extension=".odd")
    scan_snapshot = replace(
        _snapshot(scanner_claimed, METADATA, CONTENT_HASH),
        file_extension=".odd",
    )
    uow = InMemoryUnitOfWork()
    uow.libraries.save(_library(LIBRARY_ID, LIBRARY_ROOT))
    ports, _, _ = _ports(
        uow,
        (scan_entry,),
        {scanner_claimed: scan_snapshot},
        SequenceIdGenerator(
            plan_ids=deque((PLAN_ID,)),
            action_ids=deque((ACTION_ID, SECOND_ACTION_ID)),
        ),
        options=PortOptions(
            config=_unprocessed_enabled_config(),
            inventory_entries=(
                SourceInventoryEntry(path=scanner_claimed, relative_path="scanner-claimed.odd"),
                SourceInventoryEntry(path=unsupported_leftover, relative_path="unsupported.leftover"),
            ),
            content_results={unsupported_leftover: _content_snapshot(unsupported_leftover)},
        ),
    )

    plan = CreateAddPlanUseCase(ports).execute(CreateAddPlanRequest(INCOMING_ROOT))

    assert [action.action_type for action in plan.actions] == [
        ActionType.MOVE,
        ActionType.MOVE_UNPROCESSED,
    ]
    assert plan.actions[0].source_path == scanner_claimed
    assert plan.actions[1].source_path == unsupported_leftover
    assert plan.actions[1].target_path == f"{INCOMING_ROOT}/Unprocessed/unsupported.leftover"


def test_add_excludes_blocked_duplicate_and_disabled_companion_claims_from_leftovers() -> None:
    """All audio and companion claims stay excluded regardless of their resulting action status."""
    missing_audio = f"{INCOMING_ROOT}/missing.flac"
    duplicate_audio = f"{INCOMING_ROOT}/duplicate.flac"
    lyrics = f"{INCOMING_ROOT}/missing.lrc"
    leftover = f"{INCOMING_ROOT}/notes.txt"
    uow = InMemoryUnitOfWork()
    uow.libraries.save(_library(LIBRARY_ID, LIBRARY_ROOT))
    uow.tracks.save(_track(CONTENT_HASH, EXPECTED_CANONICAL_PATH))
    ports, _, _ = _ports(
        uow,
        (_entry(missing_audio), _entry(duplicate_audio)),
        {
            missing_audio: replace(
                _snapshot(missing_audio, METADATA, OTHER_CONTENT_HASH),
                size=FILE_SIZE + 1,
            ),
            duplicate_audio: _snapshot(duplicate_audio, METADATA, CONTENT_HASH),
        },
        SequenceIdGenerator(
            plan_ids=deque((PLAN_ID,)),
            action_ids=deque((ACTION_ID, SECOND_ACTION_ID, THIRD_ACTION_ID)),
        ),
        options=PortOptions(
            config=_unprocessed_enabled_config(),
            inventory_entries=(
                SourceInventoryEntry(path=missing_audio, relative_path="missing.flac"),
                SourceInventoryEntry(path=lyrics, relative_path="missing.lrc"),
                SourceInventoryEntry(path=duplicate_audio, relative_path="duplicate.flac"),
                SourceInventoryEntry(path=leftover, relative_path="notes.txt"),
            ),
            content_results={leftover: _content_snapshot(leftover)},
        ),
    )

    plan = CreateAddPlanUseCase(ports).execute(CreateAddPlanRequest(INCOMING_ROOT))

    assert [action.action_type for action in plan.actions] == [
        ActionType.MOVE,
        ActionType.SKIP,
        ActionType.MOVE_UNPROCESSED,
    ]
    assert plan.actions[0].reason is PlanActionReason.SOURCE_CHANGED
    assert plan.actions[1].reason is PlanActionReason.DUPLICATE_HASH
    assert plan.actions[2].source_path == leftover
    assert isinstance(ports.file_content_snapshot_reader, MappingFileContentSnapshotReader)
    assert ports.file_content_snapshot_reader.captures == [(leftover, INCOMING_ROOT)]


def test_add_excludes_nested_library_destination_and_only_specific_internal_paths() -> None:
    """An app-root source keeps ordinary siblings while pruning every owned subtree or log."""
    source_root = "/application"
    library_root = f"{source_root}/library"
    log_file = f"{source_root}/logs/omym2.log"
    ordinary = f"{source_root}/ordinary.txt"
    log_notes = f"{source_root}/logs/omym2.log.notes"
    retained_paths = (ordinary, log_notes)
    excluded_paths = (
        f"{source_root}/config",
        f"{source_root}/data",
        f"{source_root}/custom-config.toml",
        f"{source_root}/custom.sqlite3",
        log_file,
    )
    inventory_paths = (
        *retained_paths,
        f"{library_root}/managed.txt",
        f"{source_root}/Unprocessed/already.txt",
        f"{source_root}/config/config.toml",
        f"{source_root}/data/omym2.sqlite3",
        f"{source_root}/custom-config.toml",
        f"{source_root}/custom.sqlite3",
        log_file,
        f"{log_file}.12",
    )
    uow = InMemoryUnitOfWork()
    uow.libraries.save(_library(LIBRARY_ID, library_root))
    ports, scanner, _ = _ports(
        uow,
        (),
        {},
        SequenceIdGenerator(
            plan_ids=deque((PLAN_ID,)),
            action_ids=deque((ACTION_ID, SECOND_ACTION_ID)),
        ),
        options=PortOptions(
            config=_unprocessed_enabled_config(),
            inventory_entries=tuple(
                SourceInventoryEntry(
                    path=path,
                    relative_path=Path(path).relative_to(source_root).as_posix(),
                )
                for path in inventory_paths
            ),
            content_results={path: _content_snapshot(path) for path in retained_paths},
            internal_excluded_paths=excluded_paths,
            rotating_log_files=(log_file,),
        ),
    )

    plan = CreateAddPlanUseCase(ports).execute(CreateAddPlanRequest(source_root))

    assert {action.source_path for action in plan.actions} == set(retained_paths)
    assert all(action.action_type is ActionType.MOVE_UNPROCESSED for action in plan.actions)
    assert isinstance(ports.source_inventory_reader, StaticSourceInventoryReader)
    assert ports.source_inventory_reader.requests == [
        SourceInventoryRequest(
            root=source_root,
            excluded_roots=(library_root, f"{source_root}/Unprocessed", *excluded_paths),
        )
    ]
    assert scanner.scanned_excluded_roots == [(library_root, f"{source_root}/Unprocessed", *excluded_paths)]


@pytest.mark.parametrize(
    ("directory", "relative_path", "library_root", "internal_paths", "rotating_log_files"),
    [
        ("Review", "docs/file.txt", "/collection/Review/docs", (), ()),
        ("data", "docs/file.txt", LIBRARY_ROOT, ("/collection/data",), ()),
        (
            "logs",
            "omym2.log.7",
            LIBRARY_ROOT,
            ("/collection/logs/omym2.log",),
            ("/collection/logs/omym2.log",),
        ),
    ],
)
def test_add_blocks_unprocessed_targets_overlapping_protected_paths(
    directory: str,
    relative_path: str,
    library_root: str,
    internal_paths: tuple[str, ...],
    rotating_log_files: tuple[str, ...],
) -> None:
    """A reviewed target cannot enter the Library, internal data, or a rotated log path."""
    source_root = "/collection"
    source_path = f"{source_root}/{relative_path}"
    target_path = f"{source_root}/{directory}/{relative_path}"
    uow = InMemoryUnitOfWork()
    uow.libraries.save(_library(LIBRARY_ID, library_root))
    ports, _, _ = _ports(
        uow,
        (),
        {},
        SequenceIdGenerator(plan_ids=deque((PLAN_ID,)), action_ids=deque((ACTION_ID,))),
        options=PortOptions(
            config=_unprocessed_enabled_config(directory=directory),
            inventory_entries=(SourceInventoryEntry(path=source_path, relative_path=relative_path),),
            content_results={source_path: _content_snapshot(source_path)},
            internal_excluded_paths=internal_paths,
            rotating_log_files=rotating_log_files,
        ),
    )

    plan = CreateAddPlanUseCase(ports).execute(CreateAddPlanRequest(source_root))

    action = plan.actions[0]
    assert action.target_path == target_path
    assert action.content_hash_at_plan == "companion-hash"
    assert action.status is ActionStatus.BLOCKED
    assert action.reason is PlanActionReason.INVALID_PATH
    assert isinstance(ports.file_presence, StaticFilePresence)
    assert ports.file_presence.checked_paths == []


def test_add_inventory_does_not_turn_a_symlink_into_an_unprocessed_action(tmp_path: Path) -> None:
    """The production inventory's no-symlink contract reaches Add classification unchanged."""
    source_root = tmp_path / "incoming"
    library_root = tmp_path / "library"
    outside = tmp_path / "outside.txt"
    retained = source_root / "retained.txt"
    source_root.mkdir()
    library_root.mkdir()
    _ = outside.write_text("outside", encoding="utf-8")
    _ = retained.write_text("retained", encoding="utf-8")
    (source_root / "linked.txt").symlink_to(outside)
    uow = InMemoryUnitOfWork()
    uow.libraries.save(_library(LIBRARY_ID, str(library_root)))
    ports, _, _ = _ports(
        uow,
        (),
        {},
        SequenceIdGenerator(plan_ids=deque((PLAN_ID,)), action_ids=deque((ACTION_ID,))),
        options=PortOptions(
            config=_unprocessed_enabled_config(),
            content_results={str(retained): _content_snapshot(str(retained))},
        ),
    )
    ports = replace(ports, source_inventory_reader=FilesystemSourceInventoryReader())

    plan = CreateAddPlanUseCase(ports).execute(CreateAddPlanRequest(str(source_root)))

    assert [action.source_path for action in plan.actions] == [str(retained)]


def test_add_blocks_an_unprocessed_target_occupied_by_a_broken_symlink(tmp_path: Path) -> None:
    """Target presence uses lstat semantics so a dangling link is never overwritten."""
    source_root = tmp_path / "incoming"
    library_root = tmp_path / "library"
    source_path = source_root / "notes.txt"
    target_path = source_root / "Unprocessed" / "notes.txt"
    source_root.mkdir()
    library_root.mkdir()
    target_path.parent.mkdir()
    _ = source_path.write_text("notes", encoding="utf-8")
    target_path.symlink_to(tmp_path / "missing-target")
    uow = InMemoryUnitOfWork()
    uow.libraries.save(_library(LIBRARY_ID, str(library_root)))
    ports, _, _ = _ports(
        uow,
        (),
        {},
        SequenceIdGenerator(plan_ids=deque((PLAN_ID,)), action_ids=deque((ACTION_ID,))),
        options=PortOptions(
            config=_unprocessed_enabled_config(),
            inventory_entries=(SourceInventoryEntry(path=str(source_path), relative_path="notes.txt"),),
            content_results={str(source_path): _content_snapshot(str(source_path))},
        ),
    )
    ports = replace(ports, file_presence=FilesystemFilePresence())

    plan = CreateAddPlanUseCase(ports).execute(CreateAddPlanRequest(str(source_root)))

    action = plan.actions[0]
    assert action.status is ActionStatus.BLOCKED
    assert action.reason is PlanActionReason.TARGET_EXISTS
    assert action.target_path == str(target_path)


@pytest.mark.parametrize(
    ("content_result", "expected_reason"),
    [
        (FileNotFoundError("gone"), PlanActionReason.SOURCE_MISSING),
        (FileObservationInvalidPathError("replaced"), PlanActionReason.INVALID_PATH),
        (FileObservationChangedError("changed"), PlanActionReason.SOURCE_CHANGED),
        (OSError("unreadable"), PlanActionReason.SOURCE_CHANGED),
    ],
)
def test_add_blocks_unprocessed_content_snapshot_failures(
    content_result: BaseException,
    expected_reason: PlanActionReason,
) -> None:
    """Missing, invalid, changed, and unreadable leftovers remain visible but blocked."""
    source_path = f"{INCOMING_ROOT}/review.txt"
    uow = InMemoryUnitOfWork()
    uow.libraries.save(_library(LIBRARY_ID, LIBRARY_ROOT))
    ports, _, _ = _ports(
        uow,
        (),
        {},
        SequenceIdGenerator(plan_ids=deque((PLAN_ID,)), action_ids=deque((ACTION_ID,))),
        options=PortOptions(
            config=_unprocessed_enabled_config(),
            inventory_entries=(SourceInventoryEntry(path=source_path, relative_path="review.txt"),),
            content_results={source_path: content_result},
        ),
    )

    plan = CreateAddPlanUseCase(ports).execute(CreateAddPlanRequest(INCOMING_ROOT))

    action = plan.actions[0]
    assert action.action_type is ActionType.MOVE_UNPROCESSED
    assert action.status is ActionStatus.BLOCKED
    assert action.reason is expected_reason
    assert action.content_hash_at_plan is None


def test_add_retains_every_unprocessed_action_beyond_the_preview_limit() -> None:
    """Preview tuning never truncates durable Plan actions or their deterministic order."""
    source_paths = tuple(f"{INCOMING_ROOT}/{name}.txt" for name in ("c", "a", "b"))
    uow = InMemoryUnitOfWork()
    uow.libraries.save(_library(LIBRARY_ID, LIBRARY_ROOT))
    ports, _, _ = _ports(
        uow,
        (),
        {},
        SequenceIdGenerator(
            plan_ids=deque((PLAN_ID,)),
            action_ids=deque((ACTION_ID, SECOND_ACTION_ID, THIRD_ACTION_ID)),
        ),
        options=PortOptions(
            config=_unprocessed_enabled_config(preview_limit=2),
            inventory_entries=tuple(
                SourceInventoryEntry(path=path, relative_path=Path(path).name) for path in source_paths
            ),
            content_results={path: _content_snapshot(path) for path in source_paths},
        ),
    )

    plan = CreateAddPlanUseCase(ports).execute(CreateAddPlanRequest(INCOMING_ROOT))

    assert [Path(action.source_path or "").name for action in plan.actions] == ["a.txt", "b.txt", "c.txt"]
    assert plan.summary["action_count"] == "3"
    assert plan.summary["move_actions"] == "3"
    assert plan.summary["unprocessed_actions"] == "3"
    assert plan.summary["unprocessed_preview_limit"] == "2"


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
        self.scanned_excluded_roots: list[tuple[FileSystemPath, ...]] = []

    def scan(
        self,
        root: FileSystemPath,
        *,
        excluded_roots: tuple[FileSystemPath, ...] = (),
    ) -> tuple[FileScanEntry, ...]:
        """Return configured scan entries."""
        self.scanned_roots.append(root)
        self.scanned_excluded_roots.append(excluded_roots)
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
    resolved_names: dict[str, str] | None = None
    inventory_entries: tuple[SourceInventoryEntry, ...] | None = None
    content_results: dict[str, FileContentSnapshot | BaseException] | None = None
    internal_excluded_paths: tuple[FileSystemPath, ...] = ()
    rotating_log_files: tuple[FileSystemPath, ...] = ()


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
        file_content_snapshot_reader=MappingFileContentSnapshotReader(port_options.content_results or {}),
        source_inventory_reader=StaticSourceInventoryReader(port_options.inventory_entries or ()),
        file_presence=StaticFilePresence(port_options.existing_files),
        config_store=StaticConfigStore(port_options.config),
        artist_name_resolver=MappingArtistNameResolver(port_options.resolved_names or {}),
        path_resolver=SimplePathResolver(),
        clock=FixedClock(BASE_TIME),
        id_generator=id_generator,
        internal_excluded_paths=port_options.internal_excluded_paths,
        rotating_log_files=port_options.rotating_log_files,
    )
    return ports, scanner, snapshot_reader


def _companion_enabled_config() -> AppConfig:
    return replace(default_app_config(), companions=CompanionsConfig(enabled=True))


def _unprocessed_enabled_config(
    *,
    directory: str = DEFAULT_UNPROCESSED_DIRECTORY,
    preview_limit: int = DEFAULT_UNPROCESSED_RESULT_PREVIEW_LIMIT,
) -> AppConfig:
    return replace(
        default_app_config(),
        unprocessed=UnprocessedConfig(
            enabled=True,
            directory=directory,
            result_preview_limit=preview_limit,
        ),
    )


def _content_snapshot(path: str) -> FileContentSnapshot:
    return FileContentSnapshot(
        path=path,
        size=FILE_SIZE,
        mtime=BASE_TIME,
        content_hash="companion-hash",
        filesystem_identity=FilesystemIdentity(1, 2, FILE_SIZE, 3, 4),
        captured_at=BASE_TIME,
    )


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
        filesystem_identity=None,
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


def _track(
    content_hash: str,
    current_path: str,
    *,
    track_id: TrackId = TRACK_ID,
    metadata: TrackMetadata = METADATA,
    status: TrackStatus = TrackStatus.ACTIVE,
) -> Track:
    return Track(
        track_id=track_id,
        library_id=LIBRARY_ID,
        current_path=current_path,
        canonical_path=current_path,
        content_hash=content_hash,
        metadata_hash=calculate_metadata_fingerprint(metadata),
        size=None,
        mtime=None,
        metadata=metadata,
        status=status,
        first_seen_at=BASE_TIME,
        last_seen_at=BASE_TIME,
        updated_at=BASE_TIME,
    )


def _running_operation(kind: OperationKind) -> Operation:
    return Operation.queued(
        operation_id=OPERATION_ID,
        kind=kind,
        idempotency_key=IDEMPOTENCY_KEY,
        request_fingerprint="add-request",
        requested_at=BASE_TIME,
        library_id=LIBRARY_ID,
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
