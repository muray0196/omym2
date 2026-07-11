"""
Summary: Tests the synthetic end-to-end pipeline benchmark script.
Why: Keeps its CLI contract and real application pathway executable as the codebase evolves.
"""

from __future__ import annotations

import re
import subprocess
import sys
from pathlib import Path

from omym2.config import (
    BENCHMARK_MIN_FILE_SIZE_BYTES,
    BENCHMARK_MIN_TRACK_COUNT,
    BENCHMARK_MIN_TRACKS_PER_ALBUM,
    BENCHMARK_MUTATION_SENTINEL_BYTES,
)
from scripts import benchmark_pipeline

PROJECT_ROOT_NOT_FOUND_MESSAGE = "Unable to locate project root from test file."
SCRIPT_RELATIVE_PATH = "scripts/benchmark_pipeline.py"


def test_benchmark_tag_mutation_forces_file_size_mismatch(tmp_path: Path) -> None:
    """Tag mutation always invalidates a trusted size baseline, even on coarse-timestamp filesystems."""
    library_root = tmp_path / "library"
    library_root.mkdir()
    track = benchmark_pipeline.SyntheticTrack(
        path=library_root / "track.flac",
        title="Track",
        artist="Artist",
        album="Album",
        track_number=BENCHMARK_MIN_TRACK_COUNT,
        track_total=BENCHMARK_MIN_TRACK_COUNT,
    )
    benchmark_pipeline._write_synthetic_flac(  # pyright: ignore[reportPrivateUsage]  # noqa: SLF001 -- directly covers benchmark fixture setup.
        track,
        BENCHMARK_MIN_FILE_SIZE_BYTES,
    )
    baseline_size = track.path.stat().st_size

    benchmark_pipeline._mutate_path_neutral_tags(  # pyright: ignore[reportPrivateUsage]  # noqa: SLF001 -- directly covers benchmark setup behavior.
        library_root,
        BENCHMARK_MIN_TRACK_COUNT,
    )

    assert track.path.stat().st_size == baseline_size + BENCHMARK_MUTATION_SENTINEL_BYTES


def test_benchmark_pipeline_runs_real_cli_stages_at_minimum_dataset_boundary() -> None:
    """One minimum-sized tagged fixture completes every measured public CLI stage."""
    result = _run_script(
        "--tracks",
        str(BENCHMARK_MIN_TRACK_COUNT),
        "--file-size-bytes",
        str(BENCHMARK_MIN_FILE_SIZE_BYTES),
        "--tracks-per-album",
        str(BENCHMARK_MIN_TRACKS_PER_ALBUM),
    )

    assert result.returncode == 0, result.stderr
    assert f"tracks={BENCHMARK_MIN_TRACK_COUNT}" in result.stdout
    assert f"file_size_bytes={BENCHMARK_MIN_FILE_SIZE_BYTES}" in result.stdout
    assert f"tracks_per_album={BENCHMARK_MIN_TRACKS_PER_ALBUM}" in result.stdout
    assert f"albums={BENCHMARK_MIN_TRACK_COUNT}" in result.stdout
    assert "trust_stat=false" in result.stdout
    for setup in ("bootstrap", "fixture_generation", "ready_plan_tag_mutation", "ready_plan_creation"):
        assert re.search(rf"^setup\.{setup}_seconds=\d+\.\d+$", result.stdout, flags=re.MULTILINE)
    for stage in (
        "add",
        "apply",
        "organize",
        "check",
        "check_ready_plan",
        "measured_total",
        "extended_measured_total",
    ):
        assert re.search(rf"^stage\.{stage}_seconds=\d+\.\d+$", result.stdout, flags=re.MULTILINE)


def test_benchmark_pipeline_forces_trust_stat_fallback_after_mutation() -> None:
    """A deterministic size mutation exercises every opted-in workflow and its full-capture fallback."""
    result = _run_script(
        "--tracks",
        str(BENCHMARK_MIN_TRACK_COUNT),
        "--file-size-bytes",
        str(BENCHMARK_MIN_FILE_SIZE_BYTES),
        "--tracks-per-album",
        str(BENCHMARK_MIN_TRACKS_PER_ALBUM),
        "--trust-stat",
    )

    assert result.returncode == 0, result.stderr
    assert "trust_stat=true" in result.stdout


def test_benchmark_pipeline_rejects_non_positive_track_count() -> None:
    """A dataset with fewer than one track is rejected before creating a workspace."""
    invalid_track_count = BENCHMARK_MIN_TRACK_COUNT - 1

    result = _run_script("--tracks", str(invalid_track_count))

    assert result.returncode != 0
    assert f"value must be at least {BENCHMARK_MIN_TRACK_COUNT}" in result.stderr


def _run_script(*args: str) -> subprocess.CompletedProcess[str]:
    return subprocess.run(  # noqa: S603 -- fixed argv invokes this repo's own benchmark script.
        (sys.executable, SCRIPT_RELATIVE_PATH, *args),
        cwd=_project_root(),
        capture_output=True,
        text=True,
        check=False,
    )


def _project_root() -> Path:
    current_file = Path(__file__).resolve()
    for parent in current_file.parents:
        if (parent / "pyproject.toml").is_file():
            return parent
    raise RuntimeError(PROJECT_ROOT_NOT_FOUND_MESSAGE)
