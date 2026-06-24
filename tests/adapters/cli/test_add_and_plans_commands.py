"""
Summary: Tests add and plans CLI command behavior.
Why: Verifies add Plan creation, inspection, and apply orchestration.
"""

from __future__ import annotations

import sys
from datetime import UTC, datetime
from io import StringIO
from typing import TYPE_CHECKING, override
from uuid import UUID

from omym2.adapters.cli.main import main
from omym2.adapters.config.application_paths import default_application_paths
from omym2.adapters.config.default_config import default_app_config
from omym2.adapters.db.sqlite.unit_of_work import SQLiteUnitOfWork
from omym2.adapters.metadata.mutagen_reader import MutagenMetadataReader
from omym2.domain.models.file_event import FileEventStatus
from omym2.domain.models.library import Library, LibraryStatus
from omym2.domain.models.plan import PlanStatus, PlanType
from omym2.domain.models.plan_action import ActionStatus, ActionType
from omym2.domain.models.run import RunStatus
from omym2.domain.models.track_metadata import TrackMetadata
from omym2.domain.services.config_fingerprint import calculate_path_policy_fingerprint
from omym2.shared.ids import LibraryId

if TYPE_CHECKING:
    from pathlib import Path

    import pytest

    from omym2.features.common_ports import FileSystemPath

AUDIO_CONTENT = b"fake audio bytes"
BASE_TIME = datetime(2026, 1, 1, tzinfo=UTC)
EXPECTED_CANONICAL_PATH = "Artist/2026_Album/1-02_Title.flac"
ERROR_EXIT_CODE = 1
LIBRARY_ID = LibraryId(UUID("018f6a4f-3c2d-7b8a-9abc-def012345678"))
SUCCESS_EXIT_CODE = 0
TITLE = "Title"
TRACK_ALBUM = "Album"
TRACK_ARTIST = "Artist"
UNEXPECTED_STDIN_READ_MESSAGE = "stdin should not be read"
YEAR = 2026


def test_add_command_creates_plan_and_plans_command_displays_it(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """add creates a Plan that plans list/detail can inspect."""
    app_paths = default_application_paths(tmp_path)
    library_root = tmp_path / "library"
    incoming_root = tmp_path / "incoming"
    audio_path = incoming_root / "Title.flac"
    library_root.mkdir()
    incoming_root.mkdir()
    _ = audio_path.write_bytes(AUDIO_CONTENT)
    _register_library(app_paths.database_file, str(library_root))
    add_stdout = StringIO()
    add_stderr = StringIO()

    def read(self: MutagenMetadataReader, path: FileSystemPath) -> TrackMetadata:
        del self
        assert path == audio_path
        return TrackMetadata(
            title=TITLE,
            artist=TRACK_ARTIST,
            album=TRACK_ALBUM,
            year=YEAR,
            track_number=2,
            disc_number=1,
        )

    monkeypatch.setattr(MutagenMetadataReader, "read", read)
    monkeypatch.setattr(sys, "stdin", UnreadableInput())

    add_exit_code = main(
        ["add", str(incoming_root)],
        stdout=add_stdout,
        stderr=add_stderr,
        config_path=app_paths.config_file,
        database_path=app_paths.database_file,
    )

    assert add_exit_code == SUCCESS_EXIT_CODE
    assert "Add plan created:" in add_stdout.getvalue()
    assert "actions: 1" in add_stdout.getvalue()
    assert add_stderr.getvalue() == ""

    with SQLiteUnitOfWork(app_paths.database_file) as uow:
        plans = uow.plans.list_by_library(LIBRARY_ID)
        assert len(plans) == 1
        plan = plans[0]
        actions = uow.plan_actions.list_by_plan(plan.plan_id)
        assert plan.plan_type == PlanType.ADD
        assert len(actions) == 1
        assert actions[0].action_type == ActionType.MOVE
        assert actions[0].status == ActionStatus.PLANNED
        assert actions[0].target_path == EXPECTED_CANONICAL_PATH

    list_stdout = StringIO()
    list_stderr = StringIO()
    list_exit_code = main(
        ["plans"],
        stdout=list_stdout,
        stderr=list_stderr,
        database_path=app_paths.database_file,
    )

    assert list_exit_code == SUCCESS_EXIT_CODE
    assert str(plan.plan_id) in list_stdout.getvalue()
    assert "type=add" in list_stdout.getvalue()
    assert list_stderr.getvalue() == ""

    detail_stdout = StringIO()
    detail_stderr = StringIO()
    detail_exit_code = main(
        ["plans", str(plan.plan_id)],
        stdout=detail_stdout,
        stderr=detail_stderr,
        database_path=app_paths.database_file,
    )

    assert detail_exit_code == SUCCESS_EXIT_CODE
    assert f"plan_id: {plan.plan_id}" in detail_stdout.getvalue()
    assert f"target_path: {EXPECTED_CANONICAL_PATH}" in detail_stdout.getvalue()
    assert detail_stderr.getvalue() == ""


def test_apply_command_applies_existing_plan(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """apply executes a reviewed Plan created by add."""
    app_paths = default_application_paths(tmp_path)
    library_root = tmp_path / "library"
    incoming_root = tmp_path / "incoming"
    audio_path = incoming_root / "Title.flac"
    library_root.mkdir()
    incoming_root.mkdir()
    _ = audio_path.write_bytes(AUDIO_CONTENT)
    _register_library(app_paths.database_file, str(library_root))

    def read(self: MutagenMetadataReader, path: FileSystemPath) -> TrackMetadata:
        del self
        assert path == audio_path
        return TrackMetadata(
            title=TITLE,
            artist=TRACK_ARTIST,
            album=TRACK_ALBUM,
            year=YEAR,
            track_number=2,
            disc_number=1,
        )

    monkeypatch.setattr(MutagenMetadataReader, "read", read)

    add_exit_code = main(
        ["add", str(incoming_root)],
        stdout=StringIO(),
        stderr=StringIO(),
        config_path=app_paths.config_file,
        database_path=app_paths.database_file,
    )
    assert add_exit_code == SUCCESS_EXIT_CODE

    with SQLiteUnitOfWork(app_paths.database_file) as uow:
        plan = uow.plans.list_by_library(LIBRARY_ID)[0]

    apply_stdout = StringIO()
    apply_stderr = StringIO()
    apply_exit_code = main(
        ["apply", str(plan.plan_id), "--yes"],
        stdout=apply_stdout,
        stderr=apply_stderr,
        database_path=app_paths.database_file,
    )

    assert apply_exit_code == SUCCESS_EXIT_CODE
    assert "Apply run completed:" in apply_stdout.getvalue()
    assert "status: succeeded" in apply_stdout.getvalue()
    assert apply_stderr.getvalue() == ""
    assert not audio_path.exists()
    assert library_root.joinpath(*EXPECTED_CANONICAL_PATH.split("/")).is_file()

    with SQLiteUnitOfWork(app_paths.database_file) as uow:
        applied_plan = uow.plans.get(plan.plan_id)
        assert applied_plan is not None
        assert applied_plan.status == PlanStatus.APPLIED
        runs = uow.runs.list_by_plan(plan.plan_id)
        assert len(runs) == 1
        assert runs[0].status == RunStatus.SUCCEEDED
        events = uow.file_events.list_by_run(runs[0].run_id)
        assert len(events) == 1
        assert events[0].status == FileEventStatus.SUCCEEDED
        tracks = uow.tracks.list_by_library(LIBRARY_ID)
        assert len(tracks) == 1
        assert tracks[0].current_path == EXPECTED_CANONICAL_PATH


def test_apply_latest_applies_most_recent_ready_plan(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """apply latest resolves the newest ready Plan before execution."""
    app_paths = default_application_paths(tmp_path)
    library_root = tmp_path / "library"
    incoming_root = tmp_path / "incoming"
    audio_path = incoming_root / "Title.flac"
    library_root.mkdir()
    incoming_root.mkdir()
    _ = audio_path.write_bytes(AUDIO_CONTENT)
    _register_library(app_paths.database_file, str(library_root))

    def read(self: MutagenMetadataReader, path: FileSystemPath) -> TrackMetadata:
        del self
        assert path == audio_path
        return TrackMetadata(
            title=TITLE,
            artist=TRACK_ARTIST,
            album=TRACK_ALBUM,
            year=YEAR,
            track_number=2,
            disc_number=1,
        )

    monkeypatch.setattr(MutagenMetadataReader, "read", read)
    monkeypatch.setattr(sys, "stdin", StringIO("y\n"))

    add_exit_code = main(
        ["add", str(incoming_root)],
        stdout=StringIO(),
        stderr=StringIO(),
        config_path=app_paths.config_file,
        database_path=app_paths.database_file,
    )
    assert add_exit_code == SUCCESS_EXIT_CODE

    apply_stdout = StringIO()
    apply_stderr = StringIO()
    apply_exit_code = main(
        ["apply", "latest"],
        stdout=apply_stdout,
        stderr=apply_stderr,
        database_path=app_paths.database_file,
    )

    assert apply_exit_code == SUCCESS_EXIT_CODE
    assert "status: succeeded" in apply_stdout.getvalue()
    assert apply_stderr.getvalue() == ""
    assert library_root.joinpath(*EXPECTED_CANONICAL_PATH.split("/")).is_file()


def test_apply_command_reports_invalid_plan_id() -> None:
    """apply reports invalid Plan IDs without a traceback."""
    stdout = StringIO()
    stderr = StringIO()

    exit_code = main(["apply", "not-a-plan"], stdout=stdout, stderr=stderr)

    assert exit_code == ERROR_EXIT_CODE
    assert stdout.getvalue() == ""
    assert "Invalid Plan ID." in stderr.getvalue()


def test_apply_latest_reports_no_ready_plan(tmp_path: Path) -> None:
    """apply latest reports a clear message when no ready Plan exists."""
    app_paths = default_application_paths(tmp_path)
    stdout = StringIO()
    stderr = StringIO()

    exit_code = main(
        ["apply", "latest"],
        stdout=stdout,
        stderr=stderr,
        database_path=app_paths.database_file,
    )

    assert exit_code == ERROR_EXIT_CODE
    assert stdout.getvalue() == ""
    assert "No ready Plan exists." in stderr.getvalue()


def test_add_command_apply_creates_and_applies_plan(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """add --apply creates an add Plan and applies it in one command."""
    app_paths = default_application_paths(tmp_path)
    library_root = tmp_path / "library"
    incoming_root = tmp_path / "incoming"
    audio_path = incoming_root / "Title.flac"
    library_root.mkdir()
    incoming_root.mkdir()
    _ = audio_path.write_bytes(AUDIO_CONTENT)
    _register_library(app_paths.database_file, str(library_root))
    stdout = StringIO()
    stderr = StringIO()

    def read(self: MutagenMetadataReader, path: FileSystemPath) -> TrackMetadata:
        del self
        assert path == audio_path
        return TrackMetadata(
            title=TITLE,
            artist=TRACK_ARTIST,
            album=TRACK_ALBUM,
            year=YEAR,
            track_number=2,
            disc_number=1,
        )

    monkeypatch.setattr(MutagenMetadataReader, "read", read)

    exit_code = main(
        ["add", str(incoming_root), "--apply", "--yes"],
        stdout=stdout,
        stderr=stderr,
        config_path=app_paths.config_file,
        database_path=app_paths.database_file,
    )

    assert exit_code == SUCCESS_EXIT_CODE
    assert "Add plan created:" in stdout.getvalue()
    assert "Apply run completed:" in stdout.getvalue()
    assert stderr.getvalue() == ""
    assert not audio_path.exists()
    assert library_root.joinpath(*EXPECTED_CANONICAL_PATH.split("/")).is_file()

    with SQLiteUnitOfWork(app_paths.database_file) as uow:
        plans = uow.plans.list_by_library(LIBRARY_ID)
        assert len(plans) == 1
        assert plans[0].status == PlanStatus.APPLIED


class UnreadableInput(StringIO):
    """Input stream that fails if a command unexpectedly prompts."""

    @override
    def readline(self, size: int = -1) -> str:
        """Raise when a --yes command tries to read confirmation."""
        del size
        raise AssertionError(UNEXPECTED_STDIN_READ_MESSAGE)


def _register_library(database_file: Path, library_root: str) -> None:
    with SQLiteUnitOfWork(database_file) as uow:
        uow.libraries.save(
            Library(
                library_id=LIBRARY_ID,
                root_path=library_root,
                path_policy_hash=calculate_path_policy_fingerprint(default_app_config().path_policy),
                registered_at=BASE_TIME,
                status=LibraryStatus.REGISTERED,
                created_at=BASE_TIME,
                updated_at=BASE_TIME,
            )
        )
        uow.commit()
