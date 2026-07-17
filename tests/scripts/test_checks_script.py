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

from scripts import config
from scripts.config import CHECKS_FAILURE_DIAGNOSTIC_MAX_BYTES

CHECKS_SCRIPT = Path(__file__).parents[2] / "scripts/checks.sh"
CHECK_OUTPUT_SCRIPT = CHECKS_SCRIPT.with_name("check_output.py")
SCRIPT_CONFIG = CHECKS_SCRIPT.with_name("config.py")
SUCCESS_EXIT_CODE = 0
FAKE_FAILURE_EXIT_CODE = 7
DIAGNOSTIC_OVERFLOW_BYTES = 200
DOCS_COMMAND = "uv:run pytest tests/docs -q"


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


def test_ci_only_modes_skip_gate_groups_owned_by_parallel_jobs(tmp_path: Path) -> None:
    """CI-only modes retain their evidence while avoiding aggregate gate duplication."""
    repository, command_log, environment = _repository(tmp_path)
    wheel = repository / "build/evidence/omym2.whl"
    _write(wheel, "wheel")

    e2e_result = subprocess.run(  # noqa: S603 -- Fixed script runs with controlled fake tools.
        (str(repository / "scripts/checks.sh"), "e2e-ci"),
        cwd=repository,
        capture_output=True,
        text=True,
        check=False,
        env=environment,
    )

    assert e2e_result.returncode == SUCCESS_EXIT_CODE, e2e_result.stderr
    e2e_commands = command_log.read_text(encoding="utf-8")
    assert e2e_commands.count("npm run test:e2e") == config.CI_E2E_PROFILE_COUNT
    assert "npm:run api:check" not in e2e_commands
    assert "npm:run build" not in e2e_commands

    command_log.unlink()
    performance_result = subprocess.run(  # noqa: S603 -- Fixed script runs with controlled fake tools.
        (str(repository / "scripts/checks.sh"), "performance-ci", str(wheel)),
        cwd=repository,
        capture_output=True,
        text=True,
        check=False,
        env=environment,
    )

    assert performance_result.returncode == SUCCESS_EXIT_CODE, performance_result.stderr
    performance_commands = command_log.read_text(encoding="utf-8")
    assert f"uv:run python scripts/web/build_web_evidence.py --performance-wheel {wheel}" in performance_commands
    assert "--run-performance" not in performance_commands


def test_ci_workflow_reuses_expensive_gate_outputs() -> None:
    """CI topology keeps full evidence while removing redundant aggregate work."""
    workflow = (Path(__file__).parents[2] / ".github/workflows/ci.yml").read_text(encoding="utf-8")

    assert "api-client:" in workflow
    assert "scripts/checks.sh e2e-ci" in workflow
    assert "scripts/checks.sh performance-ci" in workflow
    assert "windows-runtime-boundaries:" in workflow
    assert "needs: [scope, package-evidence]" in workflow
    assert "python scripts/ci_scope.py" in workflow


def test_successful_mode_discards_gate_output_and_reports_only_pass(tmp_path: Path) -> None:
    """Successful tools cannot flood the caller's context."""
    repository, _command_log, environment = _repository(tmp_path)
    environment["OMYM2_CHECK_FAKE_OUTPUT"] = "unneeded successful diagnostics"

    result = subprocess.run(  # noqa: S603 -- Fixed repository script is exercised with controlled fake tools.
        (str(repository / "scripts/checks.sh"), "docs"),
        cwd=repository,
        capture_output=True,
        text=True,
        check=False,
        env=environment,
    )

    assert result.returncode == SUCCESS_EXIT_CODE
    assert result.stdout == ""
    assert result.stderr == "checks.sh: mode 'docs' passed.\n"


def test_failed_mode_reports_bounded_tail_and_retains_full_output(tmp_path: Path) -> None:
    """A failed tool starts concise while preserving opt-in deep diagnostics."""
    repository, _command_log, environment = _repository(tmp_path)
    payload = (
        "discarded diagnostic marker\n"
        f"{'x' * (CHECKS_FAILURE_DIAGNOSTIC_MAX_BYTES + DIAGNOSTIC_OVERFLOW_BYTES)}\n"
        "focused failure"
    )
    environment["OMYM2_CHECK_FAKE_OUTPUT"] = payload
    environment["OMYM2_CHECK_FAIL_COMMAND"] = DOCS_COMMAND
    environment["OMYM2_CHECK_FAIL_EXIT_CODE"] = str(FAKE_FAILURE_EXIT_CODE)

    result = subprocess.run(  # noqa: S603 -- Fixed repository script is exercised with controlled fake tools.
        (str(repository / "scripts/checks.sh"), "docs"),
        cwd=repository,
        capture_output=True,
        text=True,
        check=False,
        env=environment,
    )

    assert result.returncode == FAKE_FAILURE_EXIT_CODE
    assert result.stdout == ""
    assert "gate 'docs bundle' failed with exit code 7" in result.stderr
    assert "[earlier check output omitted]" in result.stderr
    assert "discarded diagnostic marker" not in result.stderr
    assert "focused failure" in result.stderr
    log_prefix = "checks.sh: full output retained at "
    log_line = next(line for line in result.stderr.splitlines() if line.startswith(log_prefix))
    output_path = Path(log_line.removeprefix(log_prefix))
    assert output_path.read_text(encoding="utf-8") == f"{payload}\n"
    output_path.unlink()


def _repository(tmp_path: Path, *, configure_origin: bool = True) -> tuple[Path, Path, dict[str, str]]:
    repository = tmp_path / "repository"
    repository.mkdir()
    _git(repository, "init", "--initial-branch=main")
    _git(repository, "config", "user.email", "checks-script@example.invalid")
    _git(repository, "config", "user.name", "Checks Script Test")
    checks_script = repository / "scripts/checks.sh"
    checks_script.parent.mkdir()
    _ = shutil.copy2(CHECKS_SCRIPT, checks_script)
    _ = shutil.copy2(CHECK_OUTPUT_SCRIPT, checks_script.with_name("check_output.py"))
    _ = shutil.copy2(SCRIPT_CONFIG, checks_script.with_name("config.py"))
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
            "".join(
                (
                    "#!/bin/sh\n",
                    f"command='{command_name}:'\"$*\"\n",
                    'printf \'%s\\n\' "$command" >> "$OMYM2_CHECK_COMMAND_LOG"\n',
                    'if [ -n "${OMYM2_CHECK_FAKE_OUTPUT:-}" ]; then\n',
                    "    printf '%s\\n' \"$OMYM2_CHECK_FAKE_OUTPUT\"\n",
                    "fi\n",
                    'if [ "${OMYM2_CHECK_FAIL_COMMAND:-}" = "$command" ]; then\n',
                    '    exit "$OMYM2_CHECK_FAIL_EXIT_CODE"\n',
                    "fi\n",
                )
            ),
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
