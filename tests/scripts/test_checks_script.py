"""
Summary: Tests path-aware routing in the repository quality wrapper.
Why: Keeps Codex completion checks focused without weakening CI gates.
"""

from __future__ import annotations

import os
import shutil
import subprocess
from pathlib import Path

import pytest

CHECKS_SCRIPT = Path(__file__).parents[2] / "scripts/checks.sh"
SUCCESS_EXIT_CODE = 0


@pytest.mark.parametrize(
    ("changed_path", "expected_commands", "excluded_commands"),
    [
        (
            "docs/guide.md",
            ("uv:run pytest tests/docs -q",),
            ("npm:", "uv:run pytest -q"),
        ),
        (
            "src/omym2/domain/example.py",
            ("uv:run ruff check .", "uv:run pytest -q"),
            ("npm:", "uv:run pytest tests/docs -q"),
        ),
        (
            "web/src/example.ts",
            ("npm:run api:check", "npm:run test:unit", "uv:run python scripts/web/audit_web_static.py"),
            ("uv:run pytest -q", "uv:run pytest tests/docs -q"),
        ),
        (
            "src/omym2/adapters/web/example.py",
            ("npm:run api:check", "uv:run pytest -q"),
            ("uv:run pytest tests/docs -q",),
        ),
    ],
)
def test_completion_routes_changed_paths_to_focused_gate_groups(
    tmp_path: Path,
    changed_path: str,
    expected_commands: tuple[str, ...],
    excluded_commands: tuple[str, ...],
) -> None:
    """Each changed area runs only its relevant local completion groups."""
    repository, command_log, environment = _repository(tmp_path)
    _write(repository / changed_path, "changed\n")

    result = subprocess.run(  # noqa: S603 -- Fixed repository script is exercised with controlled fake tools.
        (str(repository / "scripts/checks.sh"), "completion"),
        cwd=repository,
        capture_output=True,
        text=True,
        check=False,
        env=environment,
    )

    assert result.returncode == SUCCESS_EXIT_CODE, result.stderr
    commands = command_log.read_text(encoding="utf-8")
    for expected_command in expected_commands:
        assert expected_command in commands
    for excluded_command in excluded_commands:
        assert excluded_command not in commands


def test_completion_runs_all_groups_when_origin_main_is_unavailable(tmp_path: Path) -> None:
    """Missing comparison history conservatively selects every completion group."""
    repository, command_log, environment = _repository(tmp_path, configure_origin=False)

    result = subprocess.run(  # noqa: S603 -- Fixed repository script is exercised with controlled fake tools.
        (str(repository / "scripts/checks.sh"), "completion"),
        cwd=repository,
        capture_output=True,
        text=True,
        check=False,
        env=environment,
    )

    assert result.returncode == SUCCESS_EXIT_CODE, result.stderr
    commands = command_log.read_text(encoding="utf-8")
    assert "uv:run pytest tests/docs -q" in commands
    assert "npm:run api:check" in commands
    assert "uv:run pytest -q" in commands


def test_completion_routes_deleted_files_to_their_gate_group(tmp_path: Path) -> None:
    """Deleting a tracked file still selects checks for its former area."""
    repository, command_log, environment = _repository(tmp_path)
    tracked_web_file = repository / "web/.keep"
    tracked_web_file.unlink()

    result = subprocess.run(  # noqa: S603 -- Fixed repository script is exercised with controlled fake tools.
        (str(repository / "scripts/checks.sh"), "completion"),
        cwd=repository,
        capture_output=True,
        text=True,
        check=False,
        env=environment,
    )

    assert result.returncode == SUCCESS_EXIT_CODE, result.stderr
    commands = command_log.read_text(encoding="utf-8")
    assert "npm:run api:check" in commands
    assert "uv:run pytest -q" not in commands


def _repository(tmp_path: Path, *, configure_origin: bool = True) -> tuple[Path, Path, dict[str, str]]:
    repository = tmp_path / "repository"
    repository.mkdir()
    _git(repository, "init", "--initial-branch=main")
    _git(repository, "config", "user.email", "checks-script@example.invalid")
    _git(repository, "config", "user.name", "Checks Script Test")
    checks_script = repository / "scripts/checks.sh"
    checks_script.parent.mkdir()
    _ = shutil.copy2(CHECKS_SCRIPT, checks_script)
    checks_script.chmod(0o755)
    _write(repository / "baseline.txt", "baseline\n")
    _write(repository / "web/.keep", "fixture\n")
    _git(repository, "add", ".")
    _git(repository, "commit", "-m", "baseline")
    if configure_origin:
        _git(repository, "update-ref", "refs/remotes/origin/main", "HEAD")

    command_log = tmp_path / "commands.log"
    fake_bin = tmp_path / "bin"
    fake_bin.mkdir()
    for command_name in ("npm", "uv"):
        executable = fake_bin / command_name
        _write(
            executable,
            f'#!/bin/sh\nprintf \'{command_name}:%s\\n\' "$*" >> "$OMYM2_CHECK_COMMAND_LOG"\n',
        )
        executable.chmod(0o755)
    environment = os.environ.copy()
    environment["OMYM2_CHECK_COMMAND_LOG"] = str(command_log)
    environment["PATH"] = f"{fake_bin}{os.pathsep}{environment['PATH']}"
    return repository, command_log, environment


def _write(path: Path, content: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    _ = path.write_text(content, encoding="utf-8")


def _git(repository: Path, *arguments: str) -> None:
    git_executable = shutil.which("git")
    assert git_executable is not None
    result = subprocess.run(  # noqa: S603 -- Tests invoke fixed Git commands against a temporary repository.
        (git_executable, *arguments),
        cwd=repository,
        capture_output=True,
        text=True,
        check=False,
    )
    assert result.returncode == SUCCESS_EXIT_CODE, result.stderr
