"""
Summary: Builds, audits, rebuilds, installs, and smokes Web package evidence.
Why: Proves release artifacts are complete and require no Node.js at runtime.
"""
# ruff: noqa: INP001, T201 -- Standalone evidence script reports concise CLI results.

from __future__ import annotations

import argparse
import json
import os
import shutil
import stat
import subprocess
import sys
import tempfile
from pathlib import Path
from typing import TYPE_CHECKING, cast

from audit_web_packages import PackageAuditError, audit_packages
from audit_web_static import StaticAuditError, audit_static_export
from run_web_test_server import CHILD_PATH_OVERRIDE_ENVIRONMENT_VARIABLE
from sync_web_static import StaticSyncError, sync_static_export

if TYPE_CHECKING:
    from collections.abc import Sequence

PROJECT_ROOT_NOT_FOUND_MESSAGE = "Unable to locate the project root."
WEB_SOURCE_RELATIVE_PATH = Path("web")
WEB_BUILD_RELATIVE_PATH = WEB_SOURCE_RELATIVE_PATH / "dist"
PACKAGED_STATIC_RELATIVE_PATH = Path("src/omym2/adapters/web/static_dist")
DEFAULT_EVIDENCE_RELATIVE_PATH = Path("build/web-package-evidence")
PYTHON_BUILD_STAGING_RELATIVE_PATH = Path("build")
REBUILT_WHEEL_DIRECTORY_NAME = "rebuilt-from-sdist"
PERFORMANCE_BASE_URL_ENVIRONMENT_VARIABLE = "OMYM2_PERFORMANCE_BASE_URL"
NO_NODE_DIRECTORY_NAME = "no-node"
NO_NODE_TOOL_NAMES = ("node", "npm", "npx")
WINDOWS_EXECUTABLE_DIRECTORY_NAME = "Scripts"
POSIX_EXECUTABLE_DIRECTORY_NAME = "bin"
WINDOWS_PYTHON_EXECUTABLE_NAME = "python.exe"
POSIX_PYTHON_EXECUTABLE_NAME = "python"


class EvidenceBuildError(RuntimeError):
    """Raised when Web package evidence cannot be produced or verified."""


class ParsedArgs(argparse.Namespace):
    """Typed command-line arguments for evidence building."""

    def __init__(self, output_directory: Path) -> None:
        super().__init__()
        self.output_directory: Path = output_directory
        self.run_performance: bool = False


def build_web_evidence(output_directory: Path, *, run_performance: bool) -> None:
    """Build and verify direct and sdist-derived Web package artifacts."""
    root = _project_root()
    web_source = root / WEB_SOURCE_RELATIVE_PATH
    web_build = root / WEB_BUILD_RELATIVE_PATH
    packaged_static = root / PACKAGED_STATIC_RELATIVE_PATH
    output_directory = output_directory.resolve()
    _run(("npm", "run", "build"), cwd=web_source)
    sync_static_export(web_build, packaged_static)
    audit_static_export(web_build, packaged_static)

    shutil.rmtree(root / PYTHON_BUILD_STAGING_RELATIVE_PATH, ignore_errors=True)
    if output_directory.exists():
        shutil.rmtree(output_directory)
    output_directory.mkdir(parents=True)
    _run(
        ("uv", "build", "--clear", "--wheel", "--sdist", "--out-dir", str(output_directory)),
        cwd=root,
    )
    wheel = _one_artifact(output_directory, "*.whl", "wheel")
    sdist = _one_artifact(output_directory, "*.tar.gz", "source distribution")
    audit_packages(wheel, sdist, packaged_static)

    rebuilt_directory = output_directory / REBUILT_WHEEL_DIRECTORY_NAME
    rebuilt_directory.mkdir()
    with tempfile.TemporaryDirectory(prefix="omym2-no-node-") as temporary_directory:
        no_node_directory = Path(temporary_directory) / NO_NODE_DIRECTORY_NAME
        _write_no_node_shims(no_node_directory)
        environment = _node_poisoned_environment(no_node_directory)
        _run(
            ("uv", "build", "--wheel", str(sdist), "--out-dir", str(rebuilt_directory)),
            cwd=root,
            environment=environment,
        )
        rebuilt_wheel = _one_artifact(rebuilt_directory, "*.whl", "sdist-derived wheel")
        audit_packages(rebuilt_wheel, sdist, packaged_static)

        _smoke_wheel(wheel, root, environment=environment)
        _smoke_wheel(rebuilt_wheel, root, environment=environment)
        if run_performance:
            performance_environment = environment.copy()
            performance_environment[CHILD_PATH_OVERRIDE_ENVIRONMENT_VARIABLE] = os.environ.get("PATH", "")
            _run_performance(wheel, root, environment=performance_environment)


def _smoke_wheel(wheel: Path, root: Path, *, environment: dict[str, str]) -> None:
    with tempfile.TemporaryDirectory(prefix="omym2-wheel-smoke-") as temporary_directory:
        workspace = Path(temporary_directory)
        python = _install_wheel(wheel, workspace)
        _run(
            (
                str(python),
                str(root / "scripts/run_web_test_server.py"),
                "--require-installed",
                "--environment-variable",
                "OMYM2_PACKAGE_BASE_URL",
                "--working-directory",
                str(workspace),
                "--",
                str(python),
                str(root / "scripts/smoke_installed_web.py"),
            ),
            cwd=workspace,
            environment=environment,
        )


def _validate_performance_record(root: Path) -> None:
    configured_output = os.environ.get("OMYM2_PERFORMANCE_OUTPUT")
    if configured_output is None:
        return
    output = Path(configured_output)
    if not output.is_absolute():
        output = root / WEB_SOURCE_RELATIVE_PATH / output
    if not output.is_file():
        msg = f"Performance command did not write its configured record: {output.resolve()}"
        raise EvidenceBuildError(msg)
    try:
        payload = cast("object", json.loads(output.read_text(encoding="utf-8")))
    except json.JSONDecodeError as exc:
        msg = f"Performance record is not valid JSON: {output.resolve()}"
        raise EvidenceBuildError(msg) from exc
    if not isinstance(payload, dict):
        msg = f"Performance record must be a JSON object: {output.resolve()}"
        raise EvidenceBuildError(msg)


def _run_performance(wheel: Path, root: Path, *, environment: dict[str, str]) -> None:
    with tempfile.TemporaryDirectory(prefix="omym2-performance-") as temporary_directory:
        workspace = Path(temporary_directory)
        python = _install_wheel(wheel, workspace)
        _run(
            (
                str(python),
                str(root / "scripts/run_web_test_server.py"),
                "--require-installed",
                "--environment-variable",
                PERFORMANCE_BASE_URL_ENVIRONMENT_VARIABLE,
                "--working-directory",
                str(root / WEB_SOURCE_RELATIVE_PATH),
                "--",
                "npm",
                "run",
                "test:performance",
            ),
            cwd=workspace,
            environment=environment,
        )
        _validate_performance_record(root)


def _install_wheel(wheel: Path, workspace: Path) -> Path:
    virtual_environment = workspace / ".venv"
    _run(("uv", "venv", "--python", sys.executable, str(virtual_environment)), cwd=workspace)
    python = _venv_python(virtual_environment)
    _run(("uv", "pip", "install", "--python", str(python), str(wheel)), cwd=workspace)
    return python


def _installed_environment() -> dict[str, str]:
    environment = os.environ.copy()
    _ = environment.pop("PYTHONPATH", None)
    return environment


def _node_poisoned_environment(no_node_directory: Path) -> dict[str, str]:
    environment = _installed_environment()
    environment["PATH"] = os.pathsep.join((str(no_node_directory), environment.get("PATH", "")))
    return environment


def _write_no_node_shims(directory: Path) -> None:
    directory.mkdir(parents=True)
    if os.name == "nt":
        for tool_name in NO_NODE_TOOL_NAMES:
            _ = (directory / f"{tool_name}.cmd").write_text("@exit /b 97\r\n", encoding="utf-8")
        return
    for tool_name in NO_NODE_TOOL_NAMES:
        shim = directory / tool_name
        _ = shim.write_text("#!/bin/sh\nexit 97\n", encoding="utf-8")
        _ = shim.chmod(shim.stat().st_mode | stat.S_IXUSR)


def _venv_python(virtual_environment: Path) -> Path:
    if os.name == "nt":
        return virtual_environment / WINDOWS_EXECUTABLE_DIRECTORY_NAME / WINDOWS_PYTHON_EXECUTABLE_NAME
    return virtual_environment / POSIX_EXECUTABLE_DIRECTORY_NAME / POSIX_PYTHON_EXECUTABLE_NAME


def _one_artifact(directory: Path, pattern: str, label: str) -> Path:
    artifacts = tuple(directory.glob(pattern))
    if len(artifacts) != 1:
        msg = f"Expected exactly one {label} in {directory}, found {len(artifacts)}."
        raise EvidenceBuildError(msg)
    return artifacts[0]


def _run(
    command: Sequence[str],
    *,
    cwd: Path,
    environment: dict[str, str] | None = None,
) -> None:
    result = subprocess.run(  # noqa: S603 -- commands are fixed repository build and verification tools.
        tuple(command),
        cwd=cwd,
        env=environment,
        check=False,
    )
    if result.returncode != 0:
        msg = f"Command failed with exit code {result.returncode}: {' '.join(command)}"
        raise EvidenceBuildError(msg)


def _project_root() -> Path:
    for parent in Path(__file__).resolve().parents:
        if (parent / "pyproject.toml").is_file():
            return parent
    raise EvidenceBuildError(PROJECT_ROOT_NOT_FOUND_MESSAGE)


def _parse_args(argv: Sequence[str] | None) -> ParsedArgs:
    root = _project_root()
    parser = argparse.ArgumentParser(description=__doc__)
    _ = parser.add_argument("--output-directory", type=Path, default=root / DEFAULT_EVIDENCE_RELATIVE_PATH)
    _ = parser.add_argument("--run-performance", action="store_true")
    return parser.parse_args(argv, namespace=ParsedArgs(root / DEFAULT_EVIDENCE_RELATIVE_PATH))


def main(argv: Sequence[str] | None = None) -> int:
    """Build package evidence and report a concise result."""
    args = _parse_args(argv)
    try:
        build_web_evidence(args.output_directory, run_performance=args.run_performance)
    except (EvidenceBuildError, PackageAuditError, StaticAuditError, StaticSyncError) as exc:
        print(f"Web evidence build failed: {exc}", file=sys.stderr)
        return 1
    print(f"Web evidence build passed: {args.output_directory}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
