"""
Summary: Implements the inspect CLI command.
Why: Exposes read-only metadata, hash, and canonical path checks to users.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from omym2.adapters.cli.commands.output import write_line, write_usage, write_validation_errors
from omym2.features.common_ports import ConfigStoreValidationError, MetadataReadError
from omym2.features.inspect.dto import InspectFileRequest, InspectFileResult
from omym2.features.inspect.usecases.inspect_file import InspectFileUseCase

if TYPE_CHECKING:
    from collections.abc import Sequence
    from typing import TextIO

    from omym2.domain.models.track_metadata import TrackMetadata
    from omym2.features.inspect.ports import InspectFilePorts

ERROR_EXIT_CODE = 1
INSPECT_USAGE_MESSAGE = "Usage: omym2 inspect <file>"
MISSING_VALUE_TEXT = "-"
SUCCESS_EXIT_CODE = 0
USAGE_EXIT_CODE = 2


def run_inspect_command(
    args: Sequence[str],
    stdout: TextIO,
    stderr: TextIO,
    ports: InspectFilePorts,
) -> int:
    """Run inspect for one file and return a process exit code."""
    if len(args) != 1:
        write_usage(stderr, INSPECT_USAGE_MESSAGE)
        return USAGE_EXIT_CODE

    try:
        result = InspectFileUseCase(ports).execute(InspectFileRequest(path=args[0]))
    except ConfigStoreValidationError as exc:
        write_validation_errors(stderr, exc.errors)
        return ERROR_EXIT_CODE
    except MetadataReadError as exc:
        write_line(stderr, f"Metadata read error: {exc}")
        return ERROR_EXIT_CODE
    except OSError as exc:
        write_line(stderr, f"Inspect I/O error: {exc}")
        return ERROR_EXIT_CODE

    _write_result(stdout, result)
    return SUCCESS_EXIT_CODE


def _write_result(stdout: TextIO, result: InspectFileResult) -> None:
    snapshot = result.snapshot
    lines = [
        f"path: {snapshot.path}",
        f"size: {snapshot.size}",
        f"mtime: {snapshot.mtime.isoformat()}",
        f"file_extension: {snapshot.file_extension}",
        f"content_hash: {snapshot.content_hash}",
        f"metadata_hash: {snapshot.metadata_hash}",
    ]
    if result.canonical_path is None:
        lines.append(f"canonical_path_error: {_format_value(result.canonical_path_error)}")
    else:
        lines.append(f"canonical_path: {result.canonical_path}")

    lines.extend(_metadata_lines(snapshot.metadata))
    _ = stdout.write("\n".join(lines) + "\n")


def _metadata_lines(metadata: TrackMetadata) -> list[str]:
    return [
        "metadata:",
        f"  title: {_format_value(metadata.title)}",
        f"  artist: {_format_value(metadata.artist)}",
        f"  album: {_format_value(metadata.album)}",
        f"  album_artist: {_format_value(metadata.album_artist)}",
        f"  genre: {_format_value(metadata.genre)}",
        f"  year: {_format_value(metadata.year)}",
        f"  track_number: {_format_value(metadata.track_number)}",
        f"  track_total: {_format_value(metadata.track_total)}",
        f"  disc_number: {_format_value(metadata.disc_number)}",
        f"  disc_total: {_format_value(metadata.disc_total)}",
    ]


def _format_value(value: object | None) -> str:
    if value is None:
        return MISSING_VALUE_TEXT
    return str(value)
