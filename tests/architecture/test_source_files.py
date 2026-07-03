"""
Summary: Tests source naming conventions.
Why: Keeps module names aligned with the documented architecture.
"""

from __future__ import annotations

import re
from pathlib import Path

ALLOWED_DUNDER_MODULES = {"__init__.py", "__main__.py"}
AMBIGUOUS_MODULE_STEMS = {"common", "helpers", "manager", "service", "utils"}
PROJECT_ROOT_NOT_FOUND_MESSAGE = "Unable to locate project root from test file."
PYTHON_FILE_PATTERN = "*.py"
SNAKE_CASE_MODULE_PATTERN = re.compile(r"^[a-z][a-z0-9_]*\.py$")


def test_source_files_follow_naming_convention() -> None:
    """Python modules under src use snake_case names and avoid vague modules."""
    for source_file in _source_root().rglob(PYTHON_FILE_PATTERN):
        if source_file.name in ALLOWED_DUNDER_MODULES:
            continue

        assert SNAKE_CASE_MODULE_PATTERN.fullmatch(source_file.name) is not None
        assert source_file.stem not in AMBIGUOUS_MODULE_STEMS


def _source_root() -> Path:
    return _project_root() / "src"


def _project_root() -> Path:
    current_file = Path(__file__).resolve()
    for parent in current_file.parents:
        if (parent / "pyproject.toml").is_file():
            return parent
    raise RuntimeError(PROJECT_ROOT_NOT_FOUND_MESSAGE)
