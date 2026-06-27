"""
Summary: Tests documented dependency boundaries.
Why: Catches imports that would couple policy code to concrete adapters.
"""

from __future__ import annotations

import ast
from pathlib import Path

DOMAIN_ALLOWED_IMPORT_PREFIXES = (
    "omym2.config",
    "omym2.domain",
    "omym2.shared",
)
FEATURE_COMMON_ALLOWED_IMPORT_PREFIXES = DOMAIN_ALLOWED_IMPORT_PREFIXES
SHARED_ALLOWED_IMPORT_PREFIXES = (
    "omym2.config",
    "omym2.shared",
)
PROJECT_ROOT_NOT_FOUND_MESSAGE = "Unable to locate project root from test file."
PYTHON_FILE_PATTERN = "*.py"


def test_domain_does_not_import_adapters_or_platform() -> None:
    """Domain modules must stay pure and adapter-free."""
    for source_file in _python_files_under(_source_root() / "omym2" / "domain"):
        assert not _violating_project_imports(source_file, DOMAIN_ALLOWED_IMPORT_PREFIXES)


def test_usecase_does_not_import_concrete_sqlite_or_filesystem_adapter() -> None:
    """Feature modules must depend on ports, not concrete adapter code."""
    features_root = _source_root() / "omym2" / "features"
    for source_file in _python_files_under(features_root):
        allowed_prefixes = _allowed_feature_import_prefixes(source_file, features_root)

        assert not _violating_project_imports(source_file, allowed_prefixes)


def test_shared_does_not_import_upper_layers() -> None:
    """Shared modules must stay below domain, features, adapters, and platform."""
    for source_file in _python_files_under(_source_root() / "omym2" / "shared"):
        assert not _violating_project_imports(source_file, SHARED_ALLOWED_IMPORT_PREFIXES)


def _allowed_feature_import_prefixes(source_file: Path, features_root: Path) -> tuple[str, ...]:
    relative_parts = source_file.relative_to(features_root).parts
    if source_file.name == "common_ports.py" or len(relative_parts) == 1:
        return FEATURE_COMMON_ALLOWED_IMPORT_PREFIXES

    feature_name = relative_parts[0]
    return (
        "omym2.config",
        "omym2.domain",
        "omym2.shared",
        "omym2.features.common_ports",
        f"omym2.features.{feature_name}",
    )


def _violating_project_imports(source_file: Path, allowed_prefixes: tuple[str, ...]) -> set[str]:
    return {
        imported_module
        for imported_module in _imported_modules(source_file)
        if imported_module.startswith("omym2.") and not _matches_any_prefix(imported_module, allowed_prefixes)
    }


def _matches_any_prefix(imported_module: str, prefixes: tuple[str, ...]) -> bool:
    return any(imported_module == prefix or imported_module.startswith(f"{prefix}.") for prefix in prefixes)


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
