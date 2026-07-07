"""
Summary: Tests inspect CLI command behavior.
Why: Verifies read-only inspection through the public entry point.
"""

from __future__ import annotations

from io import StringIO
from typing import TYPE_CHECKING

from omym2.adapters.metadata.mutagen_reader import MutagenMetadataReader
from omym2.config import CONFIG_FILE_NAME
from omym2.domain.models.track_metadata import TrackMetadata
from omym2.domain.services.content_fingerprint import calculate_content_fingerprint
from omym2.platform.cli_entry_point import run_cli as main

if TYPE_CHECKING:
    from pathlib import Path

    import pytest

    from omym2.features.common_ports import FileSystemPath

AUDIO_CONTENT = b"fake audio bytes"
AUDIO_FILE_NAME = "song.flac"
CONFIG_DIRECTORY_NAME = "config"
EXPECTED_CANONICAL_PATH = "Artist/2026_Album/1-02_Title.flac"
SUCCESS_EXIT_CODE = 0
TITLE = "Title"
TRACK_ALBUM = "Album"
TRACK_ARTIST = "Artist"
USAGE_EXIT_CODE = 2
YEAR = 2026


def test_inspect_command_prints_snapshot_and_canonical_path(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """inspect prints metadata, content hash, metadata hash, and canonical path."""
    audio_path = tmp_path / AUDIO_FILE_NAME
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
        ["inspect", str(audio_path)],
        stdout=stdout,
        stderr=stderr,
        config_path=tmp_path / CONFIG_DIRECTORY_NAME / CONFIG_FILE_NAME,
    )

    output = stdout.getvalue()
    assert exit_code == SUCCESS_EXIT_CODE
    assert stderr.getvalue() == ""
    assert f"path: {audio_path}" in output
    assert f"content_hash: {calculate_content_fingerprint(AUDIO_CONTENT)}" in output
    assert f"canonical_path: {EXPECTED_CANONICAL_PATH}" in output
    assert f"  title: {TITLE}" in output


def test_inspect_command_reports_usage_for_wrong_argument_count() -> None:
    """inspect requires exactly one file argument."""
    stdout = StringIO()
    stderr = StringIO()

    exit_code = main(["inspect"], stdout=stdout, stderr=stderr)

    assert exit_code == USAGE_EXIT_CODE
    assert stdout.getvalue() == ""
    assert "Usage: omym2 inspect <file>" in stderr.getvalue()
