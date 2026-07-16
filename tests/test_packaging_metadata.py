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
DESKTOP_EXTRA_NAME = "desktop"
DESKTOP_BUILD_GROUP_NAME = "desktop-build"
DESKTOP_GUI_SCRIPT_NAME = "omym2-desktop"
EXPECTED_DESKTOP_DEPENDENCY = "pywebview==6.2.1; sys_platform == 'win32'"
EXPECTED_DESKTOP_BUILD_DEPENDENCY = "pyinstaller==6.21.0"
EXPECTED_DESKTOP_ENTRY_POINT = "omym2.platform.desktop_entry_point:main"
FASTTEXT_DEPENDENCY_PREFIX = "fasttext"
FASTTEXT_MODEL_SUFFIXES = (".bin", ".ftz")


def test_web_package_data_includes_generated_static_export_tree() -> None:
    """The ignored Web export copy remains included in built Python packages."""
    pyproject = _load_pyproject()
    tool = cast("dict[str, object]", pyproject["tool"])
    setuptools = cast("dict[str, object]", tool["setuptools"])
    package_data = cast("dict[str, object]", setuptools["package-data"])
    web_patterns = cast("list[str]", package_data[WEB_ADAPTER_PACKAGE_NAME])

    for expected_pattern in EXPECTED_WEB_STATIC_PACKAGE_PATTERNS:
        assert expected_pattern in web_patterns


def test_desktop_dependency_and_gui_entry_point_are_separate_from_core_cli() -> None:
    """Core installs stay headless while Windows desktop installs opt into pywebview."""
    pyproject = _load_pyproject()
    project = cast("dict[str, object]", pyproject["project"])
    core_dependencies = cast("list[str]", project["dependencies"])
    optional_dependencies = cast("dict[str, object]", project["optional-dependencies"])
    desktop_dependencies = cast("list[str]", optional_dependencies[DESKTOP_EXTRA_NAME])
    gui_scripts = cast("dict[str, str]", project["gui-scripts"])

    assert EXPECTED_DESKTOP_DEPENDENCY in desktop_dependencies
    assert all(not dependency.startswith("pywebview") for dependency in core_dependencies)
    assert gui_scripts[DESKTOP_GUI_SCRIPT_NAME] == EXPECTED_DESKTOP_ENTRY_POINT


def test_desktop_packaging_tool_is_isolated_in_build_dependency_group() -> None:
    """PyInstaller remains a native artifact build tool, not an application runtime dependency."""
    pyproject = _load_pyproject()
    project = cast("dict[str, object]", pyproject["project"])
    dependency_groups = cast("dict[str, object]", pyproject["dependency-groups"])
    desktop_build_dependencies = cast("list[str]", dependency_groups[DESKTOP_BUILD_GROUP_NAME])
    core_dependencies = cast("list[str]", project["dependencies"])

    assert EXPECTED_DESKTOP_BUILD_DEPENDENCY in desktop_build_dependencies
    assert all(not dependency.startswith("pyinstaller") for dependency in core_dependencies)


def test_fasttext_runtime_and_model_are_not_distributed() -> None:
    """Packaged installs remain local-only until the native runtime and model pass release qualification."""
    pyproject = _load_pyproject()
    project = cast("dict[str, object]", pyproject["project"])
    runtime_dependencies = cast("list[str]", project["dependencies"])
    optional_dependencies = cast("dict[str, list[str]]", project["optional-dependencies"])
    tool = cast("dict[str, object]", pyproject["tool"])
    setuptools = cast("dict[str, object]", tool["setuptools"])
    package_data = cast("dict[str, list[str]]", setuptools["package-data"])

    distributed_dependencies = [
        *runtime_dependencies,
        *(dependency for dependencies in optional_dependencies.values() for dependency in dependencies),
    ]
    distributed_patterns = [pattern for patterns in package_data.values() for pattern in patterns]

    assert all(not dependency.lower().startswith(FASTTEXT_DEPENDENCY_PREFIX) for dependency in distributed_dependencies)
    assert all(not pattern.lower().endswith(FASTTEXT_MODEL_SUFFIXES) for pattern in distributed_patterns)


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
