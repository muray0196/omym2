"""
Summary: Tests deterministic OpenAPI export from the schema-only Web app.
Why: Makes generated-client drift observable without touching runtime state.
"""

from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path
from typing import cast

PROJECT_ROOT_NOT_FOUND_MESSAGE = "Unable to locate project root from test file."
EXPORT_SCRIPT_RELATIVE_PATH = "scripts/export_web_openapi.py"


def test_openapi_export_is_deterministic_and_checkable(tmp_path: Path) -> None:
    """Generated JSON is stable, newline-terminated, and accepted by check mode."""
    output = tmp_path / "openapi.json"

    export_result = _run_script("--output", str(output))
    first_content = output.read_text(encoding="utf-8")
    second_result = _run_script("--output", str(output))
    check_result = _run_script("--output", str(output), "--check")
    schema = cast("dict[str, object]", json.loads(first_content))

    assert export_result.returncode == 0, export_result.stderr
    assert second_result.returncode == 0, second_result.stderr
    assert check_result.returncode == 0, check_result.stderr
    assert output.read_text(encoding="utf-8") == first_content
    assert first_content.endswith("\n")
    assert "/api/bootstrap" in cast("dict[str, object]", schema["paths"])


def test_openapi_check_reports_drift_without_rewriting_committed_file(tmp_path: Path) -> None:
    """Check mode fails on drift and leaves intentional working-tree content untouched."""
    output = tmp_path / "openapi.json"
    drifted_content = '{"drifted": true}\n'
    _ = output.write_text(drifted_content, encoding="utf-8")

    result = _run_script("--output", str(output), "--check")

    assert result.returncode != 0
    assert "has drifted" in result.stderr
    assert output.read_text(encoding="utf-8") == drifted_content


def test_openapi_check_rejects_missing_committed_document(tmp_path: Path) -> None:
    """A missing generated document cannot silently pass client drift validation."""
    output = tmp_path / "missing.json"

    result = _run_script("--output", str(output), "--check")

    assert result.returncode != 0
    assert "does not exist" in result.stderr


def _run_script(*args: str) -> subprocess.CompletedProcess[str]:
    return subprocess.run(  # noqa: S603 -- fixed argv invokes this repository's own generator.
        (sys.executable, EXPORT_SCRIPT_RELATIVE_PATH, *args),
        cwd=_project_root(),
        capture_output=True,
        text=True,
        check=False,
    )


def _project_root() -> Path:
    for parent in Path(__file__).resolve().parents:
        if (parent / "pyproject.toml").is_file():
            return parent
    raise RuntimeError(PROJECT_ROOT_NOT_FOUND_MESSAGE)
