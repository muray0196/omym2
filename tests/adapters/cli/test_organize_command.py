"""
Summary: Tests organize CLI command behavior.
Why: Verifies Phase 7 registration through the public entry point.
"""

from __future__ import annotations

from io import StringIO
from typing import TYPE_CHECKING

from omym2.adapters.cli.main import main
from omym2.adapters.config.application_paths import default_application_paths
from omym2.adapters.db.sqlite.unit_of_work import SQLiteUnitOfWork
from omym2.adapters.metadata.mutagen_reader import MutagenMetadataReader
from omym2.domain.models.library import LibraryStatus
from omym2.domain.models.track_metadata import TrackMetadata

if TYPE_CHECKING:
    from pathlib import Path

    import pytest

    from omym2.features.common_ports import FileSystemPath

AUDIO_CONTENT = b"fake audio bytes"
EXPECTED_CANONICAL_PATH = "Artist/2026_Album/1-02_Title.flac"
ERROR_EXIT_CODE = 1
SUCCESS_EXIT_CODE = 0
TITLE = "Title"
TRACK_ALBUM = "Album"
TRACK_ARTIST = "Artist"
USAGE_EXIT_CODE = 2
YEAR = 2026


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
    assert "Usage: omym2 organize [--library PATH]" in stderr.getvalue()


def test_organize_command_defers_apply_orchestration() -> None:
    """organize --apply is explicitly outside Phase 7."""
    stdout = StringIO()
    stderr = StringIO()

    exit_code = main(["organize", "--apply"], stdout=stdout, stderr=stderr)

    assert exit_code == ERROR_EXIT_CODE
    assert stdout.getvalue() == ""
    assert "deferred until the apply vertical slice" in stderr.getvalue()
