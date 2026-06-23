"""
Summary: Tests add and plans CLI command behavior.
Why: Verifies Phase 8 Plan creation through the public entry point.
"""

from __future__ import annotations

from datetime import UTC, datetime
from io import StringIO
from typing import TYPE_CHECKING
from uuid import UUID

from omym2.adapters.cli.main import main
from omym2.adapters.config.application_paths import default_application_paths
from omym2.adapters.config.default_config import default_app_config
from omym2.adapters.db.sqlite.unit_of_work import SQLiteUnitOfWork
from omym2.adapters.metadata.mutagen_reader import MutagenMetadataReader
from omym2.domain.models.library import Library, LibraryStatus
from omym2.domain.models.plan import PlanType
from omym2.domain.models.plan_action import ActionStatus, ActionType
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


def test_add_command_defers_apply_orchestration() -> None:
    """add --apply remains outside Phase 8."""
    stdout = StringIO()
    stderr = StringIO()

    exit_code = main(["add", "--apply"], stdout=stdout, stderr=stderr)

    assert exit_code == ERROR_EXIT_CODE
    assert stdout.getvalue() == ""
    assert "deferred until the apply vertical slice" in stderr.getvalue()


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
