"""
Summary: Tests refresh CLI command behavior.
Why: Verifies refresh Plan creation and apply orchestration.
"""

from __future__ import annotations

import sys
from datetime import UTC, datetime
from io import StringIO
from typing import TYPE_CHECKING, cast
from uuid import UUID

from omym2.adapters.cli.commands.refresh import RefreshCommandDependencies, run_refresh_command
from omym2.adapters.config.application_paths import default_application_paths
from omym2.adapters.config.default_config import default_app_config
from omym2.adapters.db.sqlite.unit_of_work import SQLiteUnitOfWork
from omym2.adapters.metadata.mutagen_reader import MutagenMetadataReader
from omym2.domain.models.file_event import FileEventStatus
from omym2.domain.models.library import Library, LibraryStatus
from omym2.domain.models.plan import Plan, PlanStatus, PlanType
from omym2.domain.models.plan_action import ActionStatus
from omym2.domain.models.run import RunStatus
from omym2.domain.models.track import Track, TrackStatus
from omym2.domain.models.track_metadata import TrackMetadata
from omym2.domain.services.config_fingerprint import calculate_path_policy_fingerprint
from omym2.domain.services.content_fingerprint import calculate_content_fingerprint
from omym2.domain.services.metadata_fingerprint import calculate_metadata_fingerprint
from omym2.features.refresh.dto import CreateRefreshPlanRequest
from omym2.platform.cli_entry_point import run_cli as main
from omym2.shared.ids import LibraryId, PlanId, TrackId

if TYPE_CHECKING:
    from pathlib import Path

    import pytest

    from omym2.features.apply.ports import ApplyPlanPorts
    from omym2.features.common_ports import FileSystemPath
    from omym2.features.refresh.ports import CreateRefreshPlanPorts

AUDIO_CONTENT = b"fake audio bytes"
BASE_TIME = datetime(2026, 1, 1, tzinfo=UTC)
CONFIG_HASH = "config-hash"
CONTENT_HASH = calculate_content_fingerprint(AUDIO_CONTENT)
ERROR_EXIT_CODE = 1
LIBRARY_ID = LibraryId(UUID("018f6a4f-3c2d-7b8a-9abc-def012345678"))
LIBRARY_ROOT = "/library"
NORMALIZED_TARGET_PATH = "normalized:target.flac"
NEW_PATH = "Artist/2026_Album/1-02_New-Title.flac"
OLD_PATH = "Artist/2026_Album/1-02_Old-Title.flac"
PLAN_ID = PlanId(UUID("018f6a4f-3c2d-7b8a-9abc-def012345680"))
RAW_TARGET_PATH = "target.flac"
SECOND_NEW_PATH = "Artist/2026_Album/1-03_Second-New.flac"
SECOND_OLD_PATH = "Artist/2026_Album/1-03_Second-Old.flac"
SECOND_TRACK_ID = TrackId(UUID("018f6a4f-3c2d-7b8a-9abc-def012345681"))
SUCCESS_EXIT_CODE = 0
TRACK_ID = TrackId(UUID("018f6a4f-3c2d-7b8a-9abc-def012345679"))
UNEXPECTED_METADATA_PATH_MESSAGE = "unexpected metadata path"
USAGE_EXIT_CODE = 2

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
SECOND_OLD_METADATA = TrackMetadata(
    title="Second Old",
    artist="Artist",
    album="Album",
    year=2026,
    track_number=3,
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


def test_refresh_command_passes_normalized_target_path_and_trust_stat_to_request(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """refresh forwards normalized target and trust-stat values."""
    captured_requests: list[CreateRefreshPlanRequest] = []

    class CapturingCreateRefreshPlanUseCase:
        """Usecase test double that records the inbound request."""

        def __init__(self, ports: object) -> None:
            """Accept the injected ports without using them."""
            del ports

        def execute(self, request: CreateRefreshPlanRequest) -> Plan:
            """Capture the request and return an empty refresh Plan."""
            captured_requests.append(request)
            return _empty_plan()

    monkeypatch.setattr(
        "omym2.adapters.cli.commands.refresh.CreateRefreshPlanUseCase", CapturingCreateRefreshPlanUseCase
    )
    stdout = StringIO()
    stderr = StringIO()

    default_exit_code = run_refresh_command(
        [RAW_TARGET_PATH],
        stdout,
        stderr,
        RefreshCommandDependencies(
            create_refresh_plan_ports_factory=_stub_create_refresh_plan_ports,
            apply_plan_ports_factory=_stub_apply_plan_ports,
            normalize_target_path=lambda path: f"normalized:{path}",
        ),
    )
    trusted_exit_code = run_refresh_command(
        [RAW_TARGET_PATH, "--trust-stat"],
        stdout,
        stderr,
        RefreshCommandDependencies(
            create_refresh_plan_ports_factory=_stub_create_refresh_plan_ports,
            apply_plan_ports_factory=_stub_apply_plan_ports,
            normalize_target_path=lambda path: f"normalized:{path}",
        ),
    )

    assert default_exit_code == SUCCESS_EXIT_CODE
    assert trusted_exit_code == SUCCESS_EXIT_CODE
    assert captured_requests == [
        CreateRefreshPlanRequest(
            trust_stat=False,
            target_path=NORMALIZED_TARGET_PATH,
            include_all=False,
        ),
        CreateRefreshPlanRequest(
            trust_stat=True,
            target_path=NORMALIZED_TARGET_PATH,
            include_all=False,
        ),
    ]


def test_refresh_command_creates_plan_for_managed_file(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """refresh <file> creates a relocation Plan for a managed Track."""
    app_paths = default_application_paths(tmp_path)
    library_root = tmp_path / "library"
    old_file = _write_audio_file(library_root, OLD_PATH)
    _register_library_and_tracks(app_paths.database_file, str(library_root), _track())
    stdout = StringIO()
    stderr = StringIO()

    def read(self: MutagenMetadataReader, path: FileSystemPath) -> TrackMetadata:
        del self
        assert path == old_file
        return NEW_METADATA

    monkeypatch.setattr(MutagenMetadataReader, "read", read)

    exit_code = main(
        ["refresh", str(old_file)],
        stdout=stdout,
        stderr=stderr,
        config_path=app_paths.config_file,
        database_path=app_paths.database_file,
    )

    assert exit_code == SUCCESS_EXIT_CODE
    assert "Refresh plan created:" in stdout.getvalue()
    assert "actions: 1" in stdout.getvalue()
    assert stderr.getvalue() == ""

    with SQLiteUnitOfWork(app_paths.database_file) as uow:
        plans = uow.plans.list_by_library(LIBRARY_ID)
        assert len(plans) == 1
        plan = plans[0]
        actions = uow.plan_actions.list_by_plan(plan.plan_id)
        assert plan.plan_type == PlanType.REFRESH
        assert plan.status == PlanStatus.READY
        assert len(actions) == 1
        assert actions[0].track_id == TRACK_ID
        assert actions[0].source_path == OLD_PATH
        assert actions[0].target_path == NEW_PATH
        assert actions[0].status == ActionStatus.PLANNED


def test_refresh_command_apply_moves_file_and_preserves_track_id(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """refresh --apply uses the existing apply path for relocation."""
    app_paths = default_application_paths(tmp_path)
    library_root = tmp_path / "library"
    old_file = _write_audio_file(library_root, OLD_PATH)
    target_file = library_root.joinpath(*NEW_PATH.split("/"))
    _register_library_and_tracks(app_paths.database_file, str(library_root), _track())
    stdout = StringIO()
    stderr = StringIO()

    def read(self: MutagenMetadataReader, path: FileSystemPath) -> TrackMetadata:
        del self
        assert path == old_file
        return NEW_METADATA

    monkeypatch.setattr(MutagenMetadataReader, "read", read)
    monkeypatch.setattr(sys, "stdin", StringIO("y\n"))

    exit_code = main(
        ["refresh", str(old_file), "--apply"],
        stdout=stdout,
        stderr=stderr,
        config_path=app_paths.config_file,
        database_path=app_paths.database_file,
    )

    assert exit_code == SUCCESS_EXIT_CODE
    assert "Refresh plan created:" in stdout.getvalue()
    assert "Apply run completed:" in stdout.getvalue()
    assert stderr.getvalue() == ""
    assert not old_file.exists()
    assert target_file.is_file()

    with SQLiteUnitOfWork(app_paths.database_file) as uow:
        plans = uow.plans.list_by_library(LIBRARY_ID)
        assert len(plans) == 1
        assert plans[0].status == PlanStatus.APPLIED
        runs = uow.runs.list_by_plan(plans[0].plan_id)
        assert len(runs) == 1
        assert runs[0].status == RunStatus.SUCCEEDED
        events = uow.file_events.list_by_run(runs[0].run_id)
        assert len(events) == 1
        assert events[0].status == FileEventStatus.SUCCEEDED
        tracks = uow.tracks.list_by_library(LIBRARY_ID)
        assert len(tracks) == 1
        assert tracks[0].track_id == TRACK_ID
        assert tracks[0].current_path == NEW_PATH


def test_refresh_command_apply_persists_metadata_only_refresh_without_file_event(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """refresh --apply updates Track snapshots when canonical path is unchanged."""
    app_paths = default_application_paths(tmp_path)
    library_root = tmp_path / "library"
    managed_file = _write_audio_file(library_root, NEW_PATH)
    _register_library_and_tracks(
        app_paths.database_file,
        str(library_root),
        _track(current_path=NEW_PATH, metadata=OLD_METADATA),
    )
    stdout = StringIO()
    stderr = StringIO()

    def read(self: MutagenMetadataReader, path: FileSystemPath) -> TrackMetadata:
        del self
        assert path == managed_file
        return NEW_METADATA

    monkeypatch.setattr(MutagenMetadataReader, "read", read)
    monkeypatch.setattr(sys, "stdin", StringIO("y\n"))

    exit_code = main(
        ["refresh", str(managed_file), "--apply"],
        stdout=stdout,
        stderr=stderr,
        config_path=app_paths.config_file,
        database_path=app_paths.database_file,
    )

    assert exit_code == SUCCESS_EXIT_CODE
    assert managed_file.is_file()

    with SQLiteUnitOfWork(app_paths.database_file) as uow:
        plans = uow.plans.list_by_library(LIBRARY_ID)
        assert len(plans) == 1
        assert plans[0].status == PlanStatus.APPLIED
        actions = uow.plan_actions.list_by_plan(plans[0].plan_id)
        assert len(actions) == 1
        assert actions[0].status == ActionStatus.APPLIED
        runs = uow.runs.list_by_plan(plans[0].plan_id)
        assert len(runs) == 1
        assert runs[0].status == RunStatus.SUCCEEDED
        assert uow.file_events.list_by_run(runs[0].run_id) == ()
        refreshed_track = uow.tracks.get(TRACK_ID)
        assert refreshed_track is not None
        assert refreshed_track.current_path == NEW_PATH
        assert refreshed_track.metadata_hash == calculate_metadata_fingerprint(NEW_METADATA)


def test_refresh_all_command_selects_all_managed_active_tracks(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """refresh --all creates actions for all active managed Tracks."""
    app_paths = default_application_paths(tmp_path)
    library_root = tmp_path / "library"
    first_file = _write_audio_file(library_root, OLD_PATH)
    second_file = _write_audio_file(library_root, SECOND_OLD_PATH)
    _register_library_and_tracks(
        app_paths.database_file,
        str(library_root),
        _track(),
        _track(SECOND_TRACK_ID, SECOND_OLD_PATH, metadata=SECOND_OLD_METADATA),
    )
    stdout = StringIO()
    stderr = StringIO()

    def read(self: MutagenMetadataReader, path: FileSystemPath) -> TrackMetadata:
        del self
        if path == first_file:
            return NEW_METADATA
        if path == second_file:
            return SECOND_NEW_METADATA
        raise AssertionError(UNEXPECTED_METADATA_PATH_MESSAGE)

    monkeypatch.setattr(MutagenMetadataReader, "read", read)

    exit_code = main(
        ["refresh", "--all"],
        stdout=stdout,
        stderr=stderr,
        config_path=app_paths.config_file,
        database_path=app_paths.database_file,
    )

    assert exit_code == SUCCESS_EXIT_CODE
    assert "actions: 2" in stdout.getvalue()
    assert stderr.getvalue() == ""

    with SQLiteUnitOfWork(app_paths.database_file) as uow:
        plans = uow.plans.list_by_library(LIBRARY_ID)
        actions = uow.plan_actions.list_by_plan(plans[0].plan_id)
        assert tuple(action.target_path for action in actions) == (NEW_PATH, SECOND_NEW_PATH)


def test_refresh_command_reports_usage_for_invalid_arguments(tmp_path: Path) -> None:
    """refresh accepts exactly one target selector."""
    stdout = StringIO()
    stderr = StringIO()

    exit_code = main(["refresh", "--all", str(tmp_path)], stdout=stdout, stderr=stderr)

    assert exit_code == USAGE_EXIT_CODE
    assert stdout.getvalue() == ""
    assert "Usage: omym2 refresh (<file|dir>|--all) [--apply] [--trust-stat]" in stderr.getvalue()


def test_refresh_command_reports_unmatched_target(tmp_path: Path) -> None:
    """Unmanaged targets are reported without a traceback."""
    app_paths = default_application_paths(tmp_path)
    library_root = tmp_path / "library"
    unmatched_file = library_root / "missing.flac"
    _register_library_and_tracks(app_paths.database_file, str(library_root), _track())
    stdout = StringIO()
    stderr = StringIO()

    exit_code = main(
        ["refresh", str(unmatched_file)],
        stdout=stdout,
        stderr=stderr,
        config_path=app_paths.config_file,
        database_path=app_paths.database_file,
    )

    assert exit_code == ERROR_EXIT_CODE
    assert stdout.getvalue() == ""
    assert "Refresh target does not match any managed active Track." in stderr.getvalue()


def _write_audio_file(library_root: Path, library_relative_path: str) -> Path:
    audio_path = library_root.joinpath(*library_relative_path.split("/"))
    audio_path.parent.mkdir(parents=True, exist_ok=True)
    _ = audio_path.write_bytes(AUDIO_CONTENT)
    return audio_path


def _register_library_and_tracks(database_file: Path, library_root: str, *tracks: Track) -> None:
    with SQLiteUnitOfWork(database_file) as uow:
        uow.libraries.save(
            Library(
                library_id=LIBRARY_ID,
                root_path=library_root,
                path_policy_hash=calculate_path_policy_fingerprint(
                    default_app_config().path_policy,
                    default_app_config().artist_ids,
                ),
                registered_at=BASE_TIME,
                status=LibraryStatus.REGISTERED,
                created_at=BASE_TIME,
                updated_at=BASE_TIME,
            )
        )
        for track in tracks:
            uow.tracks.save(track)
        uow.commit()


def _empty_plan() -> Plan:
    return Plan(
        plan_id=PLAN_ID,
        library_id=LIBRARY_ID,
        plan_type=PlanType.REFRESH,
        status=PlanStatus.READY,
        created_at=BASE_TIME,
        config_hash=CONFIG_HASH,
        library_root_at_plan=LIBRARY_ROOT,
    )


def _stub_create_refresh_plan_ports() -> CreateRefreshPlanPorts:
    return cast("CreateRefreshPlanPorts", object())


def _stub_apply_plan_ports() -> ApplyPlanPorts:
    return cast("ApplyPlanPorts", object())


def _track(
    track_id: TrackId = TRACK_ID,
    current_path: str = OLD_PATH,
    *,
    metadata: TrackMetadata = OLD_METADATA,
) -> Track:
    return Track(
        track_id=track_id,
        library_id=LIBRARY_ID,
        current_path=current_path,
        canonical_path=current_path,
        content_hash=CONTENT_HASH,
        metadata_hash=calculate_metadata_fingerprint(metadata),
        metadata=metadata,
        size=None,
        mtime=None,
        status=TrackStatus.ACTIVE,
        first_seen_at=BASE_TIME,
        last_seen_at=BASE_TIME,
        updated_at=BASE_TIME,
    )
