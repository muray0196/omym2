"""
Summary: Tests organize CLI command behavior.
Why: Verifies Library registration and organize apply orchestration.
"""

from __future__ import annotations

import sys
from datetime import UTC, datetime
from io import StringIO
from typing import TYPE_CHECKING, cast
from uuid import UUID

from omym2.adapters.cli.commands.organize import OrganizeCommandDependencies, run_organize_command
from omym2.adapters.config.application_paths import default_application_paths
from omym2.adapters.db.sqlite.unit_of_work import SQLiteUnitOfWork
from omym2.adapters.metadata.mutagen_reader import MutagenMetadataReader
from omym2.domain.models.file_event import FileEventStatus
from omym2.domain.models.library import Library, LibraryStatus
from omym2.domain.models.plan import PlanStatus
from omym2.domain.models.run import RunStatus
from omym2.domain.models.track_metadata import TrackMetadata
from omym2.features.organize.dto import CreateOrganizePlanRequest, OrganizeLibraryResult
from omym2.platform.cli_entry_point import run_cli as main
from omym2.shared.ids import LibraryId

if TYPE_CHECKING:
    from pathlib import Path

    import pytest

    from omym2.features.apply.ports import ApplyPlanPorts
    from omym2.features.common_ports import FileSystemPath

AUDIO_CONTENT = b"fake audio bytes"
BASE_TIME = datetime(2026, 1, 1, tzinfo=UTC)
CONFIG_HASH = "config-hash"
EXPECTED_CANONICAL_PATH = "Artist/2026_Album/1-02_Title.flac"
LIBRARY_ID = LibraryId(UUID("018f6a4f-3c2d-7b8a-9abc-def012345678"))
NORMALIZED_LIBRARY_ROOT = "normalized:library"
RAW_LIBRARY_ROOT = "library"
SUCCESS_EXIT_CODE = 0
TITLE = "Title"
TRACK_ALBUM = "Album"
TRACK_ARTIST = "Artist"
USAGE_EXIT_CODE = 2
YEAR = 2026


def test_organize_command_passes_normalized_library_root_and_trust_stat_to_request() -> None:
    """organize forwards normalized Library-root and trust-stat values."""
    captured_requests: list[CreateOrganizePlanRequest] = []

    class CapturingCreateOrganizePlanUseCase:
        """Usecase test double that records the inbound request."""

        def __init__(self, ports: object) -> None:
            """Accept the injected ports without using them."""
            del ports

        def execute(self, request: CreateOrganizePlanRequest) -> OrganizeLibraryResult:
            """Capture the request and return a clean registration result."""
            captured_requests.append(request)
            return OrganizeLibraryResult(
                library=_library(NORMALIZED_LIBRARY_ROOT),
                plan=None,
                actions=(),
                track_count=0,
            )

    stdout = StringIO()
    stderr = StringIO()

    default_exit_code = run_organize_command(
        ["--library", RAW_LIBRARY_ROOT],
        stdout,
        stderr,
        OrganizeCommandDependencies(
            create_organize_plan=CapturingCreateOrganizePlanUseCase(object()).execute,
            apply_plan_ports_factory=_stub_apply_plan_ports,
            normalize_library_root=lambda path: f"normalized:{path}",
        ),
    )
    trusted_exit_code = run_organize_command(
        ["--library", RAW_LIBRARY_ROOT, "--trust-stat"],
        stdout,
        stderr,
        OrganizeCommandDependencies(
            create_organize_plan=CapturingCreateOrganizePlanUseCase(object()).execute,
            apply_plan_ports_factory=_stub_apply_plan_ports,
            normalize_library_root=lambda path: f"normalized:{path}",
        ),
    )

    assert default_exit_code == SUCCESS_EXIT_CODE
    assert trusted_exit_code == SUCCESS_EXIT_CODE
    assert captured_requests == [
        CreateOrganizePlanRequest(
            trust_stat=False,
            library_root=NORMALIZED_LIBRARY_ROOT,
        ),
        CreateOrganizePlanRequest(
            trust_stat=True,
            library_root=NORMALIZED_LIBRARY_ROOT,
        ),
    ]


def test_organize_command_registers_clean_library(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """organize --library registers a clean Library and stores Track state."""
    app_paths = default_application_paths(tmp_path)
    library_root = tmp_path / "library"
    audio_path = library_root / "Artist" / "2026_Album" / "1-02_Title.flac"
    audio_path.parent.mkdir(parents=True)
    _ = audio_path.write_bytes(AUDIO_CONTENT)
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
        ["organize", "--library", str(library_root)],
        stdout=stdout,
        stderr=stderr,
        config_path=app_paths.config_file,
        database_path=app_paths.database_file,
    )

    assert exit_code == SUCCESS_EXIT_CODE
    assert "Library registered:" in stdout.getvalue()
    assert "tracks: 1" in stdout.getvalue()
    assert stderr.getvalue() == ""

    with SQLiteUnitOfWork(app_paths.database_file) as uow:
        libraries = uow.libraries.list_all()
        assert len(libraries) == 1
        library = libraries[0]
        assert library.root_path == str(library_root.resolve(strict=False))
        assert library.status == LibraryStatus.REGISTERED
        tracks = uow.tracks.list_by_library(library.library_id)
        assert len(tracks) == 1
        assert tracks[0].current_path == EXPECTED_CANONICAL_PATH
        assert tracks[0].canonical_path == EXPECTED_CANONICAL_PATH
        assert uow.plans.list_by_library(library.library_id) == ()


def test_organize_command_reports_usage_for_wrong_argument_count() -> None:
    """organize --library requires a path value."""
    stdout = StringIO()
    stderr = StringIO()

    exit_code = main(["organize", "--library"], stdout=stdout, stderr=stderr)

    assert exit_code == USAGE_EXIT_CODE
    assert stdout.getvalue() == ""
    assert "Usage: omym2 organize [--library PATH] [--apply] [--trust-stat]" in stderr.getvalue()


def test_organize_command_reports_usage_when_library_path_is_an_option() -> None:
    """organize --library rejects another option in place of its path."""
    stdout = StringIO()
    stderr = StringIO()

    exit_code = main(["organize", "--library", "--trust-stat"], stdout=stdout, stderr=stderr)

    assert exit_code == USAGE_EXIT_CODE
    assert stdout.getvalue() == ""
    assert "Usage: omym2 organize [--library PATH] [--apply] [--trust-stat]" in stderr.getvalue()


def test_organize_command_apply_moves_file_and_registers_library(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """organize --apply creates and applies an organize Plan."""
    app_paths = default_application_paths(tmp_path)
    library_root = tmp_path / "library"
    audio_path = library_root / "Unsorted" / "Title.flac"
    target_path = library_root.joinpath(*EXPECTED_CANONICAL_PATH.split("/"))
    audio_path.parent.mkdir(parents=True)
    _ = audio_path.write_bytes(AUDIO_CONTENT)
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
    monkeypatch.setattr(sys, "stdin", StringIO("y\n"))

    exit_code = main(
        ["organize", "--library", str(library_root), "--apply"],
        stdout=stdout,
        stderr=stderr,
        config_path=app_paths.config_file,
        database_path=app_paths.database_file,
    )

    assert exit_code == SUCCESS_EXIT_CODE
    assert "Organize plan created:" in stdout.getvalue()
    assert "Apply run completed:" in stdout.getvalue()
    assert stderr.getvalue() == ""
    assert not audio_path.exists()
    assert target_path.is_file()

    with SQLiteUnitOfWork(app_paths.database_file) as uow:
        libraries = uow.libraries.list_all()
        assert len(libraries) == 1
        library = libraries[0]
        assert library.status == LibraryStatus.REGISTERED
        plans = uow.plans.list_by_library(library.library_id)
        assert len(plans) == 1
        assert plans[0].status == PlanStatus.APPLIED
        runs = uow.runs.list_by_plan(plans[0].plan_id)
        assert len(runs) == 1
        assert runs[0].status == RunStatus.SUCCEEDED
        events = uow.file_events.list_by_run(runs[0].run_id)
        assert len(events) == 1
        assert events[0].status == FileEventStatus.SUCCEEDED
        tracks = uow.tracks.list_by_library(library.library_id)
        assert len(tracks) == 1
        assert tracks[0].current_path == EXPECTED_CANONICAL_PATH


def _library(root_path: str) -> Library:
    return Library(
        library_id=LIBRARY_ID,
        root_path=root_path,
        path_policy_hash=CONFIG_HASH,
        registered_at=BASE_TIME,
        status=LibraryStatus.REGISTERED,
        created_at=BASE_TIME,
        updated_at=BASE_TIME,
    )


def _stub_apply_plan_ports() -> ApplyPlanPorts:
    return cast("ApplyPlanPorts", object())
