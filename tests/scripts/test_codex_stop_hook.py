"""
Summary: Tests the repo-local Codex Stop validation hook.
Why: Keeps completion blocking, change detection, and loop prevention reliable.
"""

from __future__ import annotations

import json
import os
import shutil
import subprocess
import sys
from pathlib import Path
from typing import cast

import pytest

from scripts import codex_stop_hook

SUCCESS_EXIT_CODE = 0
BLOCK_EXIT_CODE = 2
GIT_FAILURE_EXIT_CODE = 128
HOOK_SCRIPT = Path(__file__).parents[2] / "scripts/codex_stop_hook.py"
HOOK_CONFIG = Path(__file__).parents[2] / ".codex/hooks.json"
HOOK_MARKER_ENVIRONMENT_VARIABLE = "OMYM2_CODEX_HOOK_TEST_MARKER"
HOOK_EXIT_CODE_ENVIRONMENT_VARIABLE = "OMYM2_CODEX_HOOK_TEST_EXIT_CODE"
QUALITY_GATE_STDOUT = "quality gate stdout"
QUALITY_GATE_STDERR = "quality gate stderr"
EXPECTED_REVALIDATION_RUNS = 2


def test_hook_config_registers_exactly_one_synchronous_stop_handler() -> None:
    """The repo-local config uses only the supported single Stop command shape."""
    raw_config = cast("object", json.loads(HOOK_CONFIG.read_text(encoding="utf-8")))
    assert isinstance(raw_config, dict)
    config = cast("dict[str, object]", raw_config)

    assert set(config) == {"hooks"}
    raw_hooks = config["hooks"]
    assert isinstance(raw_hooks, dict)
    hooks = cast("dict[str, object]", raw_hooks)
    assert set(hooks) == {"Stop"}
    raw_groups = hooks["Stop"]
    assert isinstance(raw_groups, list)
    groups = cast("list[object]", raw_groups)
    assert len(groups) == 1
    raw_group = groups[0]
    assert isinstance(raw_group, dict)
    group = cast("dict[str, object]", raw_group)
    assert set(group) == {"hooks"}
    raw_handlers = group["hooks"]
    assert isinstance(raw_handlers, list)
    handlers = cast("list[object]", raw_handlers)
    assert len(handlers) == 1
    assert handlers[0] == {
        "type": "command",
        "command": "python3 scripts/codex_stop_hook.py",
        "timeout": 150,
        "async": False,
        "statusMessage": "Running OMYM2 completion checks",
    }


def test_clean_repository_skips_validation(tmp_path: Path) -> None:
    """A repository matching origin/main does not spend time on the full gate."""
    repository, marker = _repository(tmp_path)

    result = _run_hook(repository, marker=marker)

    assert result.returncode == SUCCESS_EXIT_CODE
    assert not marker.exists()


def test_committed_changes_relative_to_origin_main_trigger_validation(tmp_path: Path) -> None:
    """A branch commit after the merge base is treated as repository work."""
    repository, marker = _repository(tmp_path)
    _write(repository / "tracked.txt", "committed change\n")
    _git(repository, "add", "tracked.txt")
    _git(repository, "commit", "-m", "change")

    result = _run_hook(repository, marker=marker)

    assert result.returncode == SUCCESS_EXIT_CODE
    assert _marker_runs(marker) == 1


def test_staged_changes_trigger_validation(tmp_path: Path) -> None:
    """Index-only work invokes the final quality gate."""
    repository, marker = _repository(tmp_path)
    _write(repository / "tracked.txt", "staged change\n")
    _git(repository, "add", "tracked.txt")

    result = _run_hook(repository, marker=marker)

    assert result.returncode == SUCCESS_EXIT_CODE
    assert _marker_runs(marker) == 1


def test_unstaged_changes_trigger_validation(tmp_path: Path) -> None:
    """Tracked working-tree edits invoke the final quality gate."""
    repository, marker = _repository(tmp_path)
    _write(repository / "tracked.txt", "unstaged change\n")

    result = _run_hook(repository, marker=marker)

    assert result.returncode == SUCCESS_EXIT_CODE
    assert _marker_runs(marker) == 1


def test_untracked_files_trigger_validation(tmp_path: Path) -> None:
    """Untracked repository content invokes the final quality gate."""
    repository, marker = _repository(tmp_path)
    _write(repository / "untracked.txt", "new work\n")

    result = _run_hook(repository, marker=marker)

    assert result.returncode == SUCCESS_EXIT_CODE
    assert _marker_runs(marker) == 1


def test_unresolved_origin_main_triggers_validation(tmp_path: Path) -> None:
    """Missing origin/main fails conservatively by running the gate."""
    repository, marker = _repository(tmp_path, configure_origin=False)

    result = _run_hook(repository, marker=marker)

    assert result.returncode == SUCCESS_EXIT_CODE
    assert _marker_runs(marker) == 1


def test_successful_validation_returns_zero(tmp_path: Path) -> None:
    """Changed work may complete after the authoritative gate passes."""
    repository, marker = _repository(tmp_path)
    _write(repository / "tracked.txt", "validated change\n")

    result = _run_hook(repository, marker=marker)

    assert result.returncode == SUCCESS_EXIT_CODE
    assert result.stdout == ""
    assert result.stderr == ""


def test_failed_validation_blocks_with_command_and_diagnostics(tmp_path: Path) -> None:
    """Gate failures become actionable Codex continuation feedback."""
    repository, marker = _repository(tmp_path)
    _write(repository / "tracked.txt", "failing change\n")

    result = _run_hook(repository, marker=marker, gate_exit_code=BLOCK_EXIT_CODE)

    assert result.returncode == BLOCK_EXIT_CODE
    assert "Command: scripts/checks.sh completion" in result.stderr
    assert QUALITY_GATE_STDOUT in result.stderr
    assert QUALITY_GATE_STDERR in result.stderr
    assert "Fix the reported failure" in result.stderr
    assert "Traceback" not in result.stderr


def test_same_successful_fingerprint_skips_duplicate_validation(tmp_path: Path) -> None:
    """An unchanged state that already passed does not rerun the expensive gate."""
    repository, marker = _repository(tmp_path)
    _write(repository / "tracked.txt", "stable validated change\n")

    first = _run_hook(repository, marker=marker)
    second = _run_hook(repository, marker=marker)

    assert first.returncode == SUCCESS_EXIT_CODE
    assert second.returncode == SUCCESS_EXIT_CODE
    assert _marker_runs(marker) == 1


def test_same_failed_fingerprint_does_not_create_stop_loop(tmp_path: Path) -> None:
    """The retry Stop after one unchanged failure reports it without blocking forever."""
    repository, marker = _repository(tmp_path)
    _write(repository / "tracked.txt", "stable failing change\n")

    first = _run_hook(repository, marker=marker, gate_exit_code=BLOCK_EXIT_CODE)
    second = _run_hook(
        repository,
        marker=marker,
        gate_exit_code=BLOCK_EXIT_CODE,
        stop_hook_active=True,
    )

    assert first.returncode == BLOCK_EXIT_CODE
    assert second.returncode == SUCCESS_EXIT_CODE
    assert "still failing" in second.stderr
    assert _marker_runs(marker) == 1


def test_changed_state_after_failure_runs_validation_again(tmp_path: Path) -> None:
    """A new fingerprint invalidates the failed-state loop guard."""
    repository, marker = _repository(tmp_path)
    tracked_file = repository / "tracked.txt"
    _write(tracked_file, "first failing state\n")
    first = _run_hook(repository, marker=marker, gate_exit_code=BLOCK_EXIT_CODE)
    _write(tracked_file, "second failing state\n")

    second = _run_hook(
        repository,
        marker=marker,
        gate_exit_code=BLOCK_EXIT_CODE,
        stop_hook_active=True,
    )

    assert first.returncode == BLOCK_EXIT_CODE
    assert second.returncode == BLOCK_EXIT_CODE
    assert _marker_runs(marker) == EXPECTED_REVALIDATION_RUNS


def test_timeout_becomes_concise_blocking_failure(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    """A hung quality gate is converted to protocol exit code 2 without a traceback."""
    repository, _marker = _repository(tmp_path)
    _write(repository / "tracked.txt", "timeout state\n")
    original_run_command = codex_stop_hook.run_command

    def timeout_gate(
        command: tuple[str, ...],
        *,
        cwd: Path,
        timeout_seconds: int,
    ) -> subprocess.CompletedProcess[bytes]:
        if tuple(command) == codex_stop_hook.QUALITY_GATE_COMMAND:
            raise subprocess.TimeoutExpired(command, timeout_seconds, output=b"partial diagnostics")
        return original_run_command(command, cwd=cwd, timeout_seconds=timeout_seconds)

    monkeypatch.setattr(codex_stop_hook, "run_command", timeout_gate)
    monkeypatch.chdir(repository)

    exit_code = codex_stop_hook.run_hook(codex_stop_hook.HookPayload(stop_hook_active=False))
    captured = capsys.readouterr()

    assert exit_code == BLOCK_EXIT_CODE
    assert "timed out" in captured.err
    assert "Command: scripts/checks.sh completion" in captured.err
    assert "partial diagnostics" in captured.err
    assert "Traceback" not in captured.err


def test_git_errors_become_concise_blocking_failures(tmp_path: Path) -> None:
    """Running outside a Git repository blocks predictably without a traceback."""
    marker = tmp_path / "marker.txt"

    result = _run_hook(tmp_path, marker=marker)

    assert result.returncode == BLOCK_EXIT_CODE
    assert "git rev-parse --show-toplevel failed" in result.stderr
    assert "Traceback" not in result.stderr


def test_git_subprocess_failure_is_handled_by_main(
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    """A failed Git command returned by the command boundary maps to exit code 2."""

    def fail_git(
        command: tuple[str, ...],
        *,
        cwd: Path,
        timeout_seconds: int,
    ) -> subprocess.CompletedProcess[bytes]:
        del cwd, timeout_seconds
        return subprocess.CompletedProcess(command, GIT_FAILURE_EXIT_CODE, b"", b"fatal: broken repository")

    monkeypatch.setattr(codex_stop_hook, "run_command", fail_git)
    monkeypatch.setattr(
        sys,
        "stdin",
        _StringInput(json.dumps({"hook_event_name": "Stop", "stop_hook_active": False})),
    )

    exit_code = codex_stop_hook.main()
    captured = capsys.readouterr()

    assert exit_code == BLOCK_EXIT_CODE
    assert "fatal: broken repository" in captured.err
    assert "Traceback" not in captured.err


@pytest.mark.parametrize(
    ("payload", "expected_message"),
    [
        ("not-json", "malformed JSON input"),
        (json.dumps([]), "JSON object"),
        (json.dumps({"hook_event_name": "PostToolUse", "stop_hook_active": False}), "must be Stop"),
        (json.dumps({"hook_event_name": "Stop", "stop_hook_active": "false"}), "must be a boolean"),
    ],
)
def test_malformed_hook_input_is_handled_predictably(
    tmp_path: Path,
    payload: str,
    expected_message: str,
) -> None:
    """Invalid protocol input blocks with a stable concise explanation."""
    result = _run_hook(tmp_path, marker=tmp_path / "marker.txt", payload=payload)

    assert result.returncode == BLOCK_EXIT_CODE
    assert expected_message in result.stderr
    assert "Traceback" not in result.stderr


class _StringInput:
    """Minimal stdin replacement for direct main() tests."""

    def __init__(self, value: str) -> None:
        self._value: str = value

    def read(self) -> str:
        """Return the fixed input payload."""
        return self._value


def _repository(tmp_path: Path, *, configure_origin: bool = True) -> tuple[Path, Path]:
    repository = tmp_path / "repository"
    repository.mkdir()
    _git(repository, "init", "--initial-branch=main")
    _git(repository, "config", "user.email", "codex-hook@example.invalid")
    _git(repository, "config", "user.name", "Codex Hook Test")
    _write(repository / "tracked.txt", "baseline\n")
    checks_script = repository / "scripts/checks.sh"
    checks_script_content = "\n".join(
        (
            "#!/bin/sh",
            'test "$1" = "completion" || exit 99',
            f"printf 'run\\n' >> \"${HOOK_MARKER_ENVIRONMENT_VARIABLE}\"",
            f"printf '{QUALITY_GATE_STDOUT}\\n'",
            f"printf '{QUALITY_GATE_STDERR}\\n' >&2",
            f'exit "${{{HOOK_EXIT_CODE_ENVIRONMENT_VARIABLE}:-{SUCCESS_EXIT_CODE}}}"',
            "",
        )
    )
    _write(
        checks_script,
        checks_script_content,
    )
    checks_script.chmod(0o755)
    _git(repository, "add", "tracked.txt", "scripts/checks.sh")
    _git(repository, "commit", "-m", "baseline")
    if configure_origin:
        _git(repository, "update-ref", "refs/remotes/origin/main", "HEAD")
    return repository, tmp_path / "hook-runs.txt"


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


def _run_hook(
    repository: Path,
    *,
    marker: Path,
    gate_exit_code: int = SUCCESS_EXIT_CODE,
    stop_hook_active: bool = False,
    payload: str | None = None,
) -> subprocess.CompletedProcess[str]:
    environment = os.environ.copy()
    environment[HOOK_MARKER_ENVIRONMENT_VARIABLE] = str(marker)
    environment[HOOK_EXIT_CODE_ENVIRONMENT_VARIABLE] = str(gate_exit_code)
    hook_payload = payload or json.dumps(
        {
            "hook_event_name": "Stop",
            "stop_hook_active": stop_hook_active,
            "cwd": "/untrusted/payload/path",
        }
    )
    return subprocess.run(  # noqa: S603 -- Fixed interpreter invokes this repository's own hook script.
        (sys.executable, str(HOOK_SCRIPT)),
        cwd=repository,
        input=hook_payload,
        capture_output=True,
        text=True,
        check=False,
        env=environment,
    )


def _marker_runs(marker: Path) -> int:
    return len(marker.read_text(encoding="utf-8").splitlines())
