"""
Summary: Benchmarks add, apply, organize, and clean/READY-plan checks with synthetic tagged audio.
Why: Provides a repeatable end-to-end baseline for performance optimization work.
"""
# ruff: noqa: INP001 -- Standalone developer benchmark, not an importable package.

from __future__ import annotations

import argparse
import subprocess
import sys
from dataclasses import dataclass
from pathlib import Path
from tempfile import TemporaryDirectory
from time import perf_counter
from typing import TYPE_CHECKING, Protocol, cast

from mutagen.flac import FLAC

from omym2.config import (
    BENCHMARK_DEFAULT_FILE_SIZE_BYTES,
    BENCHMARK_DEFAULT_TRACK_COUNT,
    BENCHMARK_DEFAULT_TRACKS_PER_ALBUM,
    BENCHMARK_FILE_WRITE_CHUNK_SIZE_BYTES,
    BENCHMARK_MIN_FILE_SIZE_BYTES,
    BENCHMARK_MIN_TRACK_COUNT,
    BENCHMARK_MIN_TRACKS_PER_ALBUM,
)

if TYPE_CHECKING:
    from collections.abc import Sequence

BENCHMARK_ERROR_EXIT_CODE = 1
CHECK_DIAGNOSTIC_EXIT_CODE = 1
CLI_SUCCESS_EXIT_CODE = 0
CLI_SUCCESS_EXIT_CODES = frozenset({CLI_SUCCESS_EXIT_CODE})
CHECK_DIAGNOSTIC_EXIT_CODES = frozenset({CHECK_DIAGNOSTIC_EXIT_CODE})
FLAC_BYTE_ORDER = "big"
FLAC_CHANNEL_COUNT = 1
FLAC_CHANNEL_COUNT_BITS = 3
FLAC_FRAME_SIZE_FIELDS_BYTES = 6
FLAC_LAST_METADATA_BLOCK_FLAG = 0x80
FLAC_MD5_BYTES = 16
FLAC_SAMPLE_RATE_BITS = 20
FLAC_SAMPLE_RATE_HZ = 8_000
FLAC_SAMPLE_SIZE_BITS = 8
FLAC_SAMPLE_SIZE_FIELD_BITS = 5
FLAC_STREAMINFO_BLOCK_SIZE_SAMPLES = 4_096
FLAC_STREAMINFO_LENGTH_BYTES = 34
FLAC_STREAM_MARKER = b"fLaC"
FLAC_TOTAL_SAMPLES_BITS = 36
INDEX_DISPLAY_OFFSET = 1
OUTPUT_SECONDS_PRECISION = 6
SYNTHETIC_DISC_NUMBER = 1
SYNTHETIC_DISC_TOTAL = 1
SYNTHETIC_MUTATED_GENRE = "OMYM2 Benchmark Changed Genre"
SYNTHETIC_NAME_WIDTH = 6
SYNTHETIC_YEAR = 2026
TEMPORARY_WORKSPACE_PREFIX = "omym2-benchmark-"
ZERO_BYTE = b"\x00"


class BenchmarkError(RuntimeError):
    """Raised when fixture generation or one real CLI stage fails."""


class FlacTagWriter(Protocol):
    """Narrow typed surface used to add tags to a generated FLAC container."""

    def __setitem__(self, key: str, value: str) -> None:
        """Set one Vorbis-comment field."""

    def save(self) -> None:
        """Persist the added FLAC metadata."""


class ParsedArgs(argparse.Namespace):
    """Typed command-line values after argparse validation."""

    def __init__(self) -> None:
        super().__init__()
        self.tracks: int = BENCHMARK_DEFAULT_TRACK_COUNT
        self.file_size_bytes: int = BENCHMARK_DEFAULT_FILE_SIZE_BYTES
        self.tracks_per_album: int = BENCHMARK_DEFAULT_TRACKS_PER_ALBUM
        self.workspace_root: Path | None = None
        self.trust_stat: bool = False


@dataclass(frozen=True, slots=True)
class SyntheticTrack:
    """Metadata and destination for one generated tagged FLAC fixture."""

    path: Path
    title: str
    artist: str
    album: str
    track_number: int
    track_total: int


@dataclass(frozen=True, slots=True)
class CommandMeasurement:
    """Wall time and captured output for one fresh CLI process."""

    seconds: float
    stdout: str


@dataclass(frozen=True, slots=True)
class BenchmarkMeasurements:
    """Setup and measured pipeline timings for one synthetic workspace."""

    workspace_parent: Path
    album_count: int
    bootstrap: CommandMeasurement
    fixture_generation_seconds: float
    add: CommandMeasurement
    apply: CommandMeasurement
    organize: CommandMeasurement
    check: CommandMeasurement
    ready_plan_tag_mutation_seconds: float
    ready_plan_creation: CommandMeasurement
    check_ready_plan: CommandMeasurement


def main(argv: Sequence[str] | None = None) -> int:
    """Generate a disposable dataset, run the real CLI stages, and print timings."""
    args = _parse_args(argv)
    try:
        measurements = _run_benchmark(args)
    except (BenchmarkError, OSError) as error:
        _write_line(sys.stderr, f"benchmark failed: {error}")
        return BENCHMARK_ERROR_EXIT_CODE

    _write_results(args, measurements)
    return 0


def _parse_args(argv: Sequence[str] | None) -> ParsedArgs:
    parser = argparse.ArgumentParser(
        description="Benchmark OMYM2's real add/apply/organize/check CLI pipeline on synthetic tagged FLAC files."
    )
    _ = parser.add_argument(
        "--tracks",
        type=_track_count,
        default=BENCHMARK_DEFAULT_TRACK_COUNT,
        help=f"number of synthetic tracks (default: {BENCHMARK_DEFAULT_TRACK_COUNT})",
    )
    _ = parser.add_argument(
        "--file-size-bytes",
        type=_file_size_bytes,
        default=BENCHMARK_DEFAULT_FILE_SIZE_BYTES,
        help=f"exact size of each synthetic file (default: {BENCHMARK_DEFAULT_FILE_SIZE_BYTES})",
    )
    _ = parser.add_argument(
        "--tracks-per-album",
        type=_tracks_per_album,
        default=BENCHMARK_DEFAULT_TRACKS_PER_ALBUM,
        help=f"album shape as tracks per album (default: {BENCHMARK_DEFAULT_TRACKS_PER_ALBUM})",
    )
    _ = parser.add_argument(
        "--workspace-root",
        type=Path,
        help="existing directory under which the disposable benchmark workspace is created",
    )
    _ = parser.add_argument(
        "--trust-stat",
        action="store_true",
        help="opt into organize, refresh, and check stat-baseline fast paths",
    )
    return parser.parse_args(argv, namespace=ParsedArgs())


def _track_count(raw_value: str) -> int:
    return _integer_at_least(raw_value, BENCHMARK_MIN_TRACK_COUNT)


def _tracks_per_album(raw_value: str) -> int:
    return _integer_at_least(raw_value, BENCHMARK_MIN_TRACKS_PER_ALBUM)


def _integer_at_least(raw_value: str, minimum: int) -> int:
    try:
        value = int(raw_value)
    except ValueError as error:
        message = "value must be an integer"
        raise argparse.ArgumentTypeError(message) from error
    if value < minimum:
        message = f"value must be at least {minimum}"
        raise argparse.ArgumentTypeError(message)
    return value


def _file_size_bytes(raw_value: str) -> int:
    value = _integer_at_least(raw_value, BENCHMARK_MIN_TRACK_COUNT)
    if value < BENCHMARK_MIN_FILE_SIZE_BYTES:
        message = f"value must be at least {BENCHMARK_MIN_FILE_SIZE_BYTES} bytes"
        raise argparse.ArgumentTypeError(message)
    return value


def _run_benchmark(args: ParsedArgs) -> BenchmarkMeasurements:
    workspace_root = _validated_workspace_root(args.workspace_root)
    with TemporaryDirectory(prefix=TEMPORARY_WORKSPACE_PREFIX, dir=workspace_root) as temporary_directory:
        workspace = Path(temporary_directory)
        library_root = workspace / "library"
        incoming_root = workspace / "incoming"
        library_root.mkdir()
        incoming_root.mkdir()

        bootstrap = _measure_cli(workspace, "bootstrap", ("organize", "--library", str(library_root)))
        _require_output("bootstrap", bootstrap, f"tracks: {0}")

        generation_started = perf_counter()
        album_count = _generate_library(
            incoming_root,
            track_count=args.tracks,
            file_size_bytes=args.file_size_bytes,
            tracks_per_album=args.tracks_per_album,
        )
        fixture_generation_seconds = perf_counter() - generation_started

        add = _measure_cli(workspace, "add", ("add", str(incoming_root)))
        _require_output("add", add, f"move_actions: {args.tracks}")
        _require_output("add", add, f"blocked_actions: {0}")

        apply = _measure_cli(workspace, "apply", ("apply", "latest", "--yes"))
        _require_output("apply", apply, "status: succeeded")
        _verify_applied_files(incoming_root, library_root, args.tracks)

        organize = _measure_cli(
            workspace,
            "organize",
            ("organize", "--library", str(library_root), *_trust_stat_args(args)),
        )
        _require_output("organize", organize, f"tracks: {args.tracks}")

        check = _measure_cli(workspace, "check", ("check", *_trust_stat_args(args)))
        _require_output("check", check, "No issues.")

        tag_mutation_started = perf_counter()
        _mutate_path_neutral_tags(library_root, args.tracks)
        ready_plan_tag_mutation_seconds = perf_counter() - tag_mutation_started

        ready_plan_creation = _measure_cli(
            workspace,
            "ready_plan_creation",
            ("refresh", "--all", *_trust_stat_args(args)),
        )
        _require_output("ready_plan_creation", ready_plan_creation, f"actions: {args.tracks}")
        _require_output("ready_plan_creation", ready_plan_creation, f"move_actions: {0}")
        _require_output("ready_plan_creation", ready_plan_creation, f"blocked_actions: {0}")

        check_ready_plan = _measure_cli(
            workspace,
            "check_ready_plan",
            ("check", *_trust_stat_args(args)),
            accepted_exit_codes=CHECK_DIAGNOSTIC_EXIT_CODES,
        )
        _require_output_line_count(
            "check_ready_plan",
            check_ready_plan,
            "content_hash_changed ",
            args.tracks,
        )
        _require_output_line_count(
            "check_ready_plan",
            check_ready_plan,
            "metadata_hash_changed ",
            args.tracks,
        )

        return BenchmarkMeasurements(
            workspace_parent=workspace.parent,
            album_count=album_count,
            bootstrap=bootstrap,
            fixture_generation_seconds=fixture_generation_seconds,
            add=add,
            apply=apply,
            organize=organize,
            check=check,
            ready_plan_tag_mutation_seconds=ready_plan_tag_mutation_seconds,
            ready_plan_creation=ready_plan_creation,
            check_ready_plan=check_ready_plan,
        )


def _trust_stat_args(args: ParsedArgs) -> tuple[str, ...]:
    return ("--trust-stat",) if args.trust_stat else ()


def _validated_workspace_root(workspace_root: Path | None) -> Path | None:
    if workspace_root is None:
        return None
    resolved_root = workspace_root.expanduser().resolve(strict=False)
    if not resolved_root.is_dir():
        message = f"workspace root is not an existing directory: {resolved_root}"
        raise BenchmarkError(message)
    return resolved_root


def _generate_library(
    incoming_root: Path,
    *,
    track_count: int,
    file_size_bytes: int,
    tracks_per_album: int,
) -> int:
    album_count = len(range(0, track_count, tracks_per_album))
    for track_index in range(track_count):
        album_index, index_in_album = divmod(track_index, tracks_per_album)
        remaining_tracks = track_count - album_index * tracks_per_album
        track_total = min(tracks_per_album, remaining_tracks)
        display_track_index = track_index + INDEX_DISPLAY_OFFSET
        display_album_index = album_index + INDEX_DISPLAY_OFFSET
        display_track_number = index_in_album + INDEX_DISPLAY_OFFSET
        track = SyntheticTrack(
            path=incoming_root / f"track_{display_track_index:0{SYNTHETIC_NAME_WIDTH}d}.flac",
            title=f"Track {display_track_index:0{SYNTHETIC_NAME_WIDTH}d}",
            artist=f"Artist {display_album_index:0{SYNTHETIC_NAME_WIDTH}d}",
            album=f"Album {display_album_index:0{SYNTHETIC_NAME_WIDTH}d}",
            track_number=display_track_number,
            track_total=track_total,
        )
        _write_synthetic_flac(track, file_size_bytes)
    return album_count


def _write_synthetic_flac(track: SyntheticTrack, file_size_bytes: int) -> None:
    _ = track.path.write_bytes(_minimal_flac_bytes())
    audio = cast("FlacTagWriter", FLAC(track.path))
    audio["title"] = track.title
    audio["artist"] = track.artist
    audio["albumartist"] = track.artist
    audio["album"] = track.album
    audio["date"] = str(SYNTHETIC_YEAR)
    audio["tracknumber"] = f"{track.track_number}/{track.track_total}"
    audio["discnumber"] = f"{SYNTHETIC_DISC_NUMBER}/{SYNTHETIC_DISC_TOTAL}"
    audio.save()

    current_size = track.path.stat().st_size
    if current_size > file_size_bytes:
        message = (
            f"generated FLAC metadata exceeds requested file size for {track.path.name}: "
            f"{current_size} > {file_size_bytes}"
        )
        raise BenchmarkError(message)
    _append_payload(track.path, file_size_bytes - current_size)


def _minimal_flac_bytes() -> bytes:
    stream_info = FLAC_STREAMINFO_BLOCK_SIZE_SAMPLES.to_bytes(2, FLAC_BYTE_ORDER) * 2
    stream_info += bytes(FLAC_FRAME_SIZE_FIELDS_BYTES)
    sample_rate_shift = FLAC_CHANNEL_COUNT_BITS + FLAC_SAMPLE_SIZE_FIELD_BITS + FLAC_TOTAL_SAMPLES_BITS
    channel_count_shift = FLAC_SAMPLE_SIZE_FIELD_BITS + FLAC_TOTAL_SAMPLES_BITS
    sample_size_shift = FLAC_TOTAL_SAMPLES_BITS
    packed_audio_properties = (
        FLAC_SAMPLE_RATE_HZ << sample_rate_shift
        | (FLAC_CHANNEL_COUNT - INDEX_DISPLAY_OFFSET) << channel_count_shift
        | (FLAC_SAMPLE_SIZE_BITS - INDEX_DISPLAY_OFFSET) << sample_size_shift
    )
    stream_info += packed_audio_properties.to_bytes(
        (FLAC_SAMPLE_RATE_BITS + FLAC_CHANNEL_COUNT_BITS + FLAC_SAMPLE_SIZE_FIELD_BITS + FLAC_TOTAL_SAMPLES_BITS) // 8,
        FLAC_BYTE_ORDER,
    )
    stream_info += bytes(FLAC_MD5_BYTES)
    block_header = bytes((FLAC_LAST_METADATA_BLOCK_FLAG, 0, 0, FLAC_STREAMINFO_LENGTH_BYTES))
    return FLAC_STREAM_MARKER + block_header + stream_info


def _append_payload(path: Path, byte_count: int) -> None:
    chunk = ZERO_BYTE * BENCHMARK_FILE_WRITE_CHUNK_SIZE_BYTES
    remaining = byte_count
    with path.open("ab") as output:
        while remaining > 0:
            write_size = min(remaining, len(chunk))
            _ = output.write(chunk[:write_size])
            remaining -= write_size


def _mutate_path_neutral_tags(library_root: Path, expected_count: int) -> None:
    library_files = tuple(sorted(library_root.rglob("*.flac")))
    if len(library_files) != expected_count:
        message = f"tag mutation found {len(library_files)} Library files; expected {expected_count}"
        raise BenchmarkError(message)
    for path in library_files:
        audio = cast("FlacTagWriter", FLAC(path))
        audio["genre"] = SYNTHETIC_MUTATED_GENRE
        audio.save()


def _measure_cli(
    workspace: Path,
    stage: str,
    args: Sequence[str],
    *,
    accepted_exit_codes: frozenset[int] = CLI_SUCCESS_EXIT_CODES,
) -> CommandMeasurement:
    started = perf_counter()
    completed = subprocess.run(  # noqa: S603 -- fixed interpreter runs this repo's public module entry point.
        (sys.executable, "-m", "omym2", *args),
        cwd=workspace,
        capture_output=True,
        text=True,
        check=False,
    )
    seconds = perf_counter() - started
    if completed.returncode not in accepted_exit_codes:
        details = completed.stderr.strip() or completed.stdout.strip() or "no command output"
        message = f"{stage} exited {completed.returncode}: {details}"
        raise BenchmarkError(message)
    return CommandMeasurement(seconds=seconds, stdout=completed.stdout)


def _require_output(stage: str, measurement: CommandMeasurement, expected: str) -> None:
    if expected not in measurement.stdout:
        message = f"{stage} did not report expected output {expected!r}: {measurement.stdout.strip()}"
        raise BenchmarkError(message)


def _require_output_line_count(
    stage: str,
    measurement: CommandMeasurement,
    line_prefix: str,
    expected_count: int,
) -> None:
    actual_count = sum(line.startswith(line_prefix) for line in measurement.stdout.splitlines())
    if actual_count != expected_count:
        message = f"{stage} reported {actual_count} {line_prefix.strip()} lines; expected {expected_count}"
        raise BenchmarkError(message)


def _verify_applied_files(incoming_root: Path, library_root: Path, expected_count: int) -> None:
    incoming_count = sum(1 for _path in incoming_root.rglob("*.flac"))
    library_count = sum(1 for _path in library_root.rglob("*.flac"))
    if incoming_count != 0 or library_count != expected_count:
        message = (
            "apply produced an unexpected file count: "
            f"incoming={incoming_count}, library={library_count}, expected_library={expected_count}"
        )
        raise BenchmarkError(message)


def _write_results(args: ParsedArgs, measurements: BenchmarkMeasurements) -> None:
    _write_line(
        sys.stdout,
        " ".join(
            (
                "benchmark",
                f"tracks={args.tracks}",
                f"file_size_bytes={args.file_size_bytes}",
                f"tracks_per_album={args.tracks_per_album}",
                f"albums={measurements.album_count}",
                f"trust_stat={str(args.trust_stat).lower()}",
                f"workspace_root={measurements.workspace_parent}",
            )
        ),
    )
    _write_seconds("setup.bootstrap_seconds", measurements.bootstrap.seconds)
    _write_seconds("setup.fixture_generation_seconds", measurements.fixture_generation_seconds)
    _write_seconds("stage.add_seconds", measurements.add.seconds)
    _write_seconds("stage.apply_seconds", measurements.apply.seconds)
    _write_seconds("stage.organize_seconds", measurements.organize.seconds)
    _write_seconds("stage.check_seconds", measurements.check.seconds)
    _write_seconds("setup.ready_plan_tag_mutation_seconds", measurements.ready_plan_tag_mutation_seconds)
    _write_seconds("setup.ready_plan_creation_seconds", measurements.ready_plan_creation.seconds)
    _write_seconds("stage.check_ready_plan_seconds", measurements.check_ready_plan.seconds)
    measured_total = (
        measurements.add.seconds
        + measurements.apply.seconds
        + measurements.organize.seconds
        + measurements.check.seconds
    )
    _write_seconds("stage.measured_total_seconds", measured_total)
    _write_seconds(
        "stage.extended_measured_total_seconds",
        measured_total + measurements.check_ready_plan.seconds,
    )


def _write_seconds(label: str, seconds: float) -> None:
    _write_line(sys.stdout, f"{label}={seconds:.{OUTPUT_SECONDS_PRECISION}f}")


def _write_line(stream: object, text: str) -> None:
    writer = getattr(stream, "write", None)
    if not callable(writer):
        message = "output stream must provide write()"
        raise TypeError(message)
    _ = writer(f"{text}\n")


if __name__ == "__main__":
    raise SystemExit(main())
