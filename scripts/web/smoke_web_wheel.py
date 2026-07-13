"""
Summary: Clean-installs one OMYM2 wheel and runs its Web package smoke checks.
Why: Reuses the same source-free runtime proof on Linux and Windows CI runners.
"""
# ruff: noqa: INP001, T201 -- Standalone smoke script reports concise CLI results.

from __future__ import annotations

import argparse
import os
import subprocess
import sys
import tempfile
from pathlib import Path
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from collections.abc import Sequence

PROJECT_ROOT_NOT_FOUND_MESSAGE = "Unable to locate the project root."
WINDOWS_EXECUTABLE_DIRECTORY_NAME = "Scripts"
POSIX_EXECUTABLE_DIRECTORY_NAME = "bin"
WINDOWS_PYTHON_EXECUTABLE_NAME = "python.exe"
POSIX_PYTHON_EXECUTABLE_NAME = "python"


class WheelSmokeError(RuntimeError):
    """Raised when a wheel cannot be clean-installed or Web-smoked."""


class ParsedArgs(argparse.Namespace):
    """Typed command-line arguments for wheel smoke."""

    def __init__(self) -> None:
        super().__init__()
        self.wheel: Path = Path()


def smoke_wheel(wheel: Path) -> None:
    """Install wheel in a temporary environment and smoke its HTTP surface."""
    wheel = wheel.resolve()
    if not wheel.is_file():
        msg = f"Wheel does not exist: {wheel}"
        raise WheelSmokeError(msg)
    root = _project_root()
    with tempfile.TemporaryDirectory(prefix="omym2-wheel-smoke-") as temporary_directory:
        workspace = Path(temporary_directory)
        virtual_environment = workspace / ".venv"
        _run(("uv", "venv", "--python", sys.executable, str(virtual_environment)), workspace)
        python = _venv_python(virtual_environment)
        _run(("uv", "pip", "install", "--python", str(python), str(wheel)), workspace)
        environment = os.environ.copy()
        _ = environment.pop("PYTHONPATH", None)
        _run(
            (
                str(python),
                str(root / "scripts/web/run_web_test_server.py"),
                "--require-installed",
                "--environment-variable",
                "OMYM2_PACKAGE_BASE_URL",
                "--working-directory",
                str(workspace),
                "--",
                str(python),
                str(root / "scripts/web/smoke_installed_web.py"),
            ),
            workspace,
            environment,
        )


def _venv_python(virtual_environment: Path) -> Path:
    if os.name == "nt":
        return virtual_environment / WINDOWS_EXECUTABLE_DIRECTORY_NAME / WINDOWS_PYTHON_EXECUTABLE_NAME
    return virtual_environment / POSIX_EXECUTABLE_DIRECTORY_NAME / POSIX_PYTHON_EXECUTABLE_NAME


def _run(command: Sequence[str], cwd: Path, environment: dict[str, str] | None = None) -> None:
    result = subprocess.run(  # noqa: S603 -- commands are fixed uv and repository smoke tools.
        tuple(command),
        cwd=cwd,
        env=environment,
        check=False,
    )
    if result.returncode != 0:
        msg = f"Command failed with exit code {result.returncode}: {' '.join(command)}"
        raise WheelSmokeError(msg)


def _project_root() -> Path:
    for parent in Path(__file__).resolve().parents:
        if (parent / "pyproject.toml").is_file():
            return parent
    raise WheelSmokeError(PROJECT_ROOT_NOT_FOUND_MESSAGE)


def _parse_args(argv: Sequence[str] | None) -> ParsedArgs:
    parser = argparse.ArgumentParser(description=__doc__)
    _ = parser.add_argument("--wheel", type=Path, required=True)
    return parser.parse_args(argv, namespace=ParsedArgs())


def main(argv: Sequence[str] | None = None) -> int:
    """Clean-install and smoke one wheel, returning a process exit code."""
    args = _parse_args(argv)
    try:
        smoke_wheel(args.wheel)
    except (OSError, WheelSmokeError) as exc:
        print(f"wheel smoke failed: {exc}", file=sys.stderr)
        return 1
    print(f"wheel smoke passed: {args.wheel}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
