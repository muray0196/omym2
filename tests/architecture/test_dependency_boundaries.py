"""
Summary: Tests documented dependency boundaries.
Why: Catches imports that would couple policy code to concrete adapters.
"""

from __future__ import annotations

import ast
from pathlib import Path

DOMAIN_FORBIDDEN_IMPORT_PREFIXES = (
    "omym2.adapters",
    "omym2.platform",
)
FEATURE_FORBIDDEN_IMPORT_PREFIXES = ("omym2.adapters",)
PROJECT_ROOT_NOT_FOUND_MESSAGE = "Unable to locate project root from test file."
PYTHON_FILE_PATTERN = "*.py"


def test_domain_does_not_import_adapters_or_platform() -> None:
    """Domain modules must stay pure and adapter-free."""
    for source_file in _python_files_under(_source_root() / "omym2" / "domain"):
        assert not _imports_any_prefix(source_file, DOMAIN_FORBIDDEN_IMPORT_PREFIXES)


def test_usecase_does_not_import_concrete_sqlite_or_filesystem_adapter() -> None:
    """Feature modules must depend on ports, not concrete adapter code."""
    for source_file in _python_files_under(_source_root() / "omym2" / "features"):
        assert not _imports_any_prefix(source_file, FEATURE_FORBIDDEN_IMPORT_PREFIXES)


def _imports_any_prefix(source_file: Path, prefixes: tuple[str, ...]) -> bool:
    imported_modules = _imported_modules(source_file)
    return any(
        imported_module == prefix or imported_module.startswith(f"{prefix}.")
        for imported_module in imported_modules
        for prefix in prefixes
    )


def _imported_modules(source_file: Path) -> set[str]:
    module_tree = ast.parse(source_file.read_text(encoding="utf-8"))
    imported_modules: set[str] = set()

    for node in ast.walk(module_tree):
        if isinstance(node, ast.Import):
            imported_modules.update(alias.name for alias in node.names)
        elif isinstance(node, ast.ImportFrom) and node.module is not None:
            imported_modules.add(node.module)

    return imported_modules


def _python_files_under(directory: Path):
    if not directory.exists():
        return ()
    return directory.rglob(PYTHON_FILE_PATTERN)


def _source_root() -> Path:
    return _project_root() / "src"


def _project_root() -> Path:
    current_file = Path(__file__).resolve()
    for parent in current_file.parents:
        if (parent / "pyproject.toml").is_file():
            return parent
    raise RuntimeError(PROJECT_ROOT_NOT_FOUND_MESSAGE)
