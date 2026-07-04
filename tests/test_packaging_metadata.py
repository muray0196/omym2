"""
Summary: Tests packaging metadata for generated assets.
Why: Keeps generated Web UI files packageable without tracking them in Git.
"""

from __future__ import annotations

import tomllib
from pathlib import Path
from typing import cast

from omym2.config import WEB_STATIC_EXPORT_DIRECTORY_NAME

PROJECT_ROOT_NOT_FOUND_MESSAGE = "Unable to locate project root from test file."
PYPROJECT_FILE_NAME = "pyproject.toml"
WEB_ADAPTER_PACKAGE_NAME = "omym2.adapters.web"
EXPECTED_WEB_STATIC_PACKAGE_PATTERNS = (
    f"{WEB_STATIC_EXPORT_DIRECTORY_NAME}/*",
    f"{WEB_STATIC_EXPORT_DIRECTORY_NAME}/**/*",
)


def test_web_package_data_includes_generated_static_export_tree() -> None:
    """The ignored Web export copy remains included in built Python packages."""
    pyproject = _load_pyproject()
    tool = cast("dict[str, object]", pyproject["tool"])
    setuptools = cast("dict[str, object]", tool["setuptools"])
    package_data = cast("dict[str, object]", setuptools["package-data"])
    web_patterns = cast("list[str]", package_data[WEB_ADAPTER_PACKAGE_NAME])

    for expected_pattern in EXPECTED_WEB_STATIC_PACKAGE_PATTERNS:
        assert expected_pattern in web_patterns


def _load_pyproject() -> dict[str, object]:
    return cast(
        "dict[str, object]",
        tomllib.loads((_project_root() / PYPROJECT_FILE_NAME).read_text(encoding="utf-8")),
    )


def _project_root() -> Path:
    for parent in Path(__file__).resolve().parents:
        if (parent / PYPROJECT_FILE_NAME).is_file():
            return parent
    raise AssertionError(PROJECT_ROOT_NOT_FOUND_MESSAGE)
