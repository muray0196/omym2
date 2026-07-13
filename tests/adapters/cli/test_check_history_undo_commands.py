"""
Summary: Tests check, history, and undo CLI commands.
Why: Verifies check, history, and undo through the public CLI entry point.
"""

from __future__ import annotations

import sys
from datetime import UTC, datetime
from io import StringIO
from typing import TYPE_CHECKING
from uuid import UUID

from omym2.adapters.cli.commands.check import CheckCommandDependencies, run_check_command
from omym2.adapters.config.application_paths import ApplicationPaths, default_application_paths
from omym2.adapters.config.default_config import default_app_config
from omym2.adapters.db.sqlite.unit_of_work import SQLiteUnitOfWork
from omym2.adapters.metadata.mutagen_reader import MutagenMetadataReader
from omym2.domain.models.file_event import FileEvent, FileEventStatus, FileEventType
from omym2.domain.models.library import Library, LibraryStatus
from omym2.domain.models.plan import Plan, PlanStatus, PlanType
from omym2.domain.models.plan_action import ActionStatus, ActionType, PlanAction
from omym2.domain.models.run import Run, RunStatus
from omym2.domain.models.track import Track, TrackStatus
from omym2.domain.models.track_metadata import TrackMetadata
from omym2.domain.services.config_fingerprint import calculate_config_fingerprint, calculate_path_policy_fingerprint
from omym2.domain.services.content_fingerprint import calculate_content_fingerprint
from omym2.domain.services.metadata_fingerprint import calculate_metadata_fingerprint
from omym2.features.check.dto import CheckLibraryRequest, CheckLibraryResult
from omym2.platform.cli_entry_point import run_cli as main
from omym2.shared.ids import ActionId, EventId, LibraryId, PlanId, RunId, TrackId
from omym2.shared.pagination import PageRequest

if TYPE_CHECKING:
    from pathlib import Path

    import pytest

    from omym2.features.common_ports import FileSystemPath

AUDIO_CONTENT = b"fake audio bytes"
BASE_TIME = datetime(2026, 1, 1, tzinfo=UTC)
ERROR_EXIT_CODE = 1
EXTERNAL_SOURCE = "incoming/Imported.flac"
LIBRARY_ID = LibraryId(UUID("018f6a4f-3c2d-7b8a-9abc-def012345678"))
PLAN_ID = PlanId(UUID("018f6a4f-3c2d-7b8a-9abc-def01234567a"))
ACTION_ID = ActionId(UUID("018f6a4f-3c2d-7b8a-9abc-def01234567b"))
RUN_ID = RunId(UUID("018f6a4f-3c2d-7b8a-9abc-def01234567d"))
EVENT_ID = EventId(UUID("018f6a4f-3c2d-7b8a-9abc-def01234567e"))
SUCCESS_EXIT_CODE = 0
TARGET_PATH = "Artist/2026_Album/1-02_Title.flac"
TRACK_ID = TrackId(UUID("018f6a4f-3c2d-7b8a-9abc-def012345679"))

METADATA = TrackMetadata(title="Title", artist="Artist", album="Album", year=2026, track_number=2, disc_number=1)
CONTENT_HASH = calculate_content_fingerprint(AUDIO_CONTENT)
METADATA_HASH = calculate_metadata_fingerprint(METADATA)


def test_check_command_passes_trust_stat_to_request() -> None:
    """check forwards the explicit trust-stat opt-in to its usecase request."""
    captured_requests: list[CheckLibraryRequest] = []

    class CapturingCheckLibraryUseCase:
        """Usecase test double that records the inbound request."""

        def __init__(self, ports: object) -> None:
            """Accept the injected ports without using them."""
            del ports

        def execute(self, request: CheckLibraryRequest) -> CheckLibraryResult:
            """Capture the request and return a clean check result."""
            captured_requests.append(request)
            return CheckLibraryResult(issues=(), checked_at=BASE_TIME)

    dependencies = CheckCommandDependencies(check_library=CapturingCheckLibraryUseCase(object()).execute)
    stdout = StringIO()
    stderr = StringIO()

    default_exit_code = run_check_command(
        [],
        stdout,
        stderr,
        dependencies,
    )
    trusted_exit_code = run_check_command(
        ["--trust-stat"],
        stdout,
        stderr,
        dependencies,
    )

    assert default_exit_code == SUCCESS_EXIT_CODE
    assert trusted_exit_code == SUCCESS_EXIT_CODE
    assert captured_requests == [
        CheckLibraryRequest(trust_stat=False),
        CheckLibraryRequest(trust_stat=True),
    ]
    assert stdout.getvalue() == "No issues.\nNo issues.\n"
    assert stderr.getvalue() == ""


def test_check_command_reports_missing_db_file(tmp_path: Path) -> None:
    """check reports missing managed files and exits nonzero."""
    app_paths = default_application_paths(tmp_path)
    library_root = tmp_path / "library"
    library_root.mkdir()
    _register_library_state(app_paths.database_file, str(library_root), _track())
    stdout = StringIO()
    stderr = StringIO()

    exit_code = main(
        ["check"],
        stdout=stdout,
        stderr=stderr,
        config_path=app_paths.config_file,
        database_path=app_paths.database_file,
    )

    assert exit_code == ERROR_EXIT_CODE
    assert "db_file_missing" in stdout.getvalue()
    assert stderr.getvalue() == ""

    with SQLiteUnitOfWork(app_paths.database_file) as uow:
        check_run = uow.check_runs.latest(LIBRARY_ID)
        assert check_run is not None
        assert check_run.total_count > 0
        persisted_page = uow.check_issues.query_page(LIBRARY_ID, issue_type=None, page=PageRequest())
        assert any(issue.issue_type.value == "db_file_missing" for issue in persisted_page.items)


def test_history_command_lists_runs(tmp_path: Path) -> None:
    """history lists apply Runs through the CLI."""
    app_paths = default_application_paths(tmp_path)
    library_root = tmp_path / "library"
    library_root.mkdir()
    _register_library_state(app_paths.database_file, str(library_root), _track())
    _save_run_history(app_paths.database_file)
    stdout = StringIO()
    stderr = StringIO()

    exit_code = main(["history"], stdout=stdout, stderr=stderr, database_path=app_paths.database_file)

    assert exit_code == SUCCESS_EXIT_CODE
    assert str(RUN_ID) in stdout.getvalue()
    assert "status=succeeded" in stdout.getvalue()
    assert stderr.getvalue() == ""


def test_undo_command_creates_external_restore_plan(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """undo creates a reviewed Plan that can restore an imported file externally."""
    app_paths, library_root, incoming_file = _setup_applied_add_history(tmp_path)
    stdout = StringIO()
    stderr = StringIO()
    _patch_metadata_reader(monkeypatch)

    exit_code = main(["undo", str(RUN_ID)], stdout=stdout, stderr=stderr, database_path=app_paths.database_file)

    assert exit_code == SUCCESS_EXIT_CODE
    assert "Undo plan created:" in stdout.getvalue()
    assert "actions: 1" in stdout.getvalue()
    assert stderr.getvalue() == ""

    with SQLiteUnitOfWork(app_paths.database_file) as uow:
        undo_plans = [plan for plan in uow.plans.list_by_library(LIBRARY_ID) if plan.plan_type == PlanType.UNDO]
        assert len(undo_plans) == 1
        actions = uow.plan_actions.list_by_plan(undo_plans[0].plan_id)
        assert len(actions) == 1
        assert actions[0].source_path == TARGET_PATH
        assert actions[0].target_path == str(incoming_file)
        assert actions[0].status == ActionStatus.PLANNED
    assert library_root.joinpath(*TARGET_PATH.split("/")).is_file()


def test_undo_apply_restores_external_file_and_marks_track_removed(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """undo --apply uses apply and records removed Track state after external restore."""
    app_paths, library_root, incoming_file = _setup_applied_add_history(tmp_path)
    stdout = StringIO()
    stderr = StringIO()
    _patch_metadata_reader(monkeypatch)
    monkeypatch.setattr(sys, "stdin", StringIO("y\n"))

    exit_code = main(
        ["undo", str(RUN_ID), "--apply"], stdout=stdout, stderr=stderr, database_path=app_paths.database_file
    )

    assert exit_code == SUCCESS_EXIT_CODE
    assert "Undo plan created:" in stdout.getvalue()
    assert "Apply run completed:" in stdout.getvalue()
    assert stderr.getvalue() == ""
    assert incoming_file.is_file()
    assert not library_root.joinpath(*TARGET_PATH.split("/")).exists()

    with SQLiteUnitOfWork(app_paths.database_file) as uow:
        undo_plan = next(plan for plan in uow.plans.list_by_library(LIBRARY_ID) if plan.plan_type == PlanType.UNDO)
        assert undo_plan.status == PlanStatus.APPLIED
        track = uow.tracks.get(TRACK_ID)
        assert track is not None
        assert track.status == TrackStatus.REMOVED
        assert track.current_path == TARGET_PATH


def _setup_applied_add_history(tmp_path: Path) -> tuple[ApplicationPaths, Path, Path]:
    app_paths = default_application_paths(tmp_path)
    library_root = tmp_path / "library"
    incoming_root = tmp_path / "incoming"
    library_root.mkdir()
    incoming_root.mkdir()
    library_file = _write_audio_file(library_root, TARGET_PATH)
    incoming_file = incoming_root / "Imported.flac"
    _register_library_state(app_paths.database_file, str(library_root), _track())
    _save_run_history(app_paths.database_file, source_path=str(incoming_file), target_path=TARGET_PATH)
    assert library_file.is_file()
    assert not incoming_file.exists()
    return app_paths, library_root, incoming_file


def _register_library_state(database_file: Path, library_root: str, track: Track) -> None:
    with SQLiteUnitOfWork(database_file) as uow:
        uow.libraries.save(_library(library_root))
        uow.tracks.save(track)
        uow.commit()


def _save_run_history(
    database_file: Path,
    *,
    source_path: str = EXTERNAL_SOURCE,
    target_path: str = TARGET_PATH,
) -> None:
    with SQLiteUnitOfWork(database_file) as uow:
        uow.plans.save(_plan())
        uow.plan_actions.save(_action(source_path=source_path, target_path=target_path))
        uow.runs.save(_run())
        uow.file_events.save(_event(source_path=source_path, target_path=target_path))
        uow.commit()


def _write_audio_file(root: Path, relative_path: str) -> Path:
    path = root.joinpath(*relative_path.split("/"))
    path.parent.mkdir(parents=True, exist_ok=True)
    _ = path.write_bytes(AUDIO_CONTENT)
    return path


def _patch_metadata_reader(monkeypatch: pytest.MonkeyPatch) -> None:
    def read(self: MutagenMetadataReader, path: FileSystemPath) -> TrackMetadata:
        del self, path
        return METADATA

    monkeypatch.setattr(MutagenMetadataReader, "read", read)


def _library(library_root: str) -> Library:
    return Library(
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


def _track() -> Track:
    return Track(
        track_id=TRACK_ID,
        library_id=LIBRARY_ID,
        current_path=TARGET_PATH,
        canonical_path=TARGET_PATH,
        content_hash=CONTENT_HASH,
        metadata_hash=METADATA_HASH,
        metadata=METADATA,
        size=None,
        mtime=None,
        status=TrackStatus.ACTIVE,
        first_seen_at=BASE_TIME,
        last_seen_at=BASE_TIME,
        updated_at=BASE_TIME,
    )


def _plan() -> Plan:
    return Plan(
        plan_id=PLAN_ID,
        library_id=LIBRARY_ID,
        plan_type=PlanType.ADD,
        status=PlanStatus.APPLIED,
        created_at=BASE_TIME,
        config_hash=calculate_config_fingerprint(default_app_config()),
        library_root_at_plan="/unused",
        summary={"action_count": "1"},
    )


def _action(*, source_path: str, target_path: str) -> PlanAction:
    return PlanAction(
        action_id=ACTION_ID,
        plan_id=PLAN_ID,
        library_id=LIBRARY_ID,
        track_id=TRACK_ID,
        action_type=ActionType.MOVE,
        source_path=source_path,
        target_path=target_path,
        content_hash_at_plan=CONTENT_HASH,
        metadata_hash_at_plan=METADATA_HASH,
        status=ActionStatus.APPLIED,
        reason=None,
        sort_order=1,
    )


def _run() -> Run:
    return Run(
        run_id=RUN_ID,
        plan_id=PLAN_ID,
        library_id=LIBRARY_ID,
        status=RunStatus.SUCCEEDED,
        started_at=BASE_TIME,
        completed_at=BASE_TIME,
    )


def _event(*, source_path: str, target_path: str) -> FileEvent:
    return FileEvent(
        event_id=EVENT_ID,
        library_id=LIBRARY_ID,
        run_id=RUN_ID,
        plan_action_id=ACTION_ID,
        event_type=FileEventType.MOVE_FILE,
        source_path=source_path,
        target_path=target_path,
        status=FileEventStatus.SUCCEEDED,
        started_at=BASE_TIME,
        completed_at=BASE_TIME,
        error_code=None,
        error_message=None,
        sequence_no=1,
    )
