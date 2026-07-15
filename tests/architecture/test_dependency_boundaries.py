"""
Summary: Tests documented dependency boundaries.
Why: Catches imports that would couple policy code to concrete adapters.
"""

from __future__ import annotations

import ast
import itertools
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

INBOUND_ADAPTER_FORBIDDEN_OUTBOUND_PREFIXES = (
    "omym2.adapters.db",
    "omym2.adapters.fs",
    "omym2.adapters.metadata",
    "omym2.adapters.config",
    "omym2.adapters.artist_ids",
)

# Exact (file, imported-module) pairs exempted from the inbound-adapter boundary
# check. Membership rule: pure, I/O-free functions coupled to the TOML config
# representation only.
INBOUND_ADAPTER_ALLOWED_OUTBOUND_IMPORTS = (
    ("adapters/cli/commands/config.py", "omym2.adapters.config.toml_config_store"),
)
FORBIDDEN_FILESYSTEM_METHODS = ("expanduser", "resolve")


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


def test_adapters_does_not_import_platform() -> None:
    """Adapters must not depend on the platform composition root that wires them."""
    for source_file in _python_files_under(_source_root() / "omym2" / "adapters"):
        assert not _project_imports_matching_prefixes(source_file, ("omym2.platform",))


def test_inbound_adapters_does_not_import_concrete_outbound_adapters() -> None:
    """CLI, Web, and desktop adapters must not construct or import outbound adapters."""
    adapters_root = _source_root() / "omym2" / "adapters"
    cli_root = adapters_root / "cli"
    web_root = adapters_root / "web"
    desktop_root = adapters_root / "desktop"
    inbound_roots = (cli_root, web_root, desktop_root)

    for source_file in itertools.chain.from_iterable(_python_files_under(root) for root in inbound_roots):
        forbidden_prefixes = INBOUND_ADAPTER_FORBIDDEN_OUTBOUND_PREFIXES
        if source_file.is_relative_to(cli_root) or source_file.is_relative_to(desktop_root):
            forbidden_prefixes += ("omym2.adapters.web",)

        allowed_prefixes = _allowed_outbound_import_prefixes(source_file)
        violations = {
            imported_module
            for imported_module in _project_imports_matching_prefixes(source_file, forbidden_prefixes)
            if not _matches_any_prefix(imported_module, allowed_prefixes)
        }

        assert not violations


def test_cli_command_modules_do_not_resolve_paths_directly() -> None:
    """CLI command adapters must not call filesystem path resolution helpers directly."""
    command_modules = _python_files_under(_source_root() / "omym2" / "adapters" / "cli" / "commands")

    for source_file in command_modules:
        forbidden_calls = _forbidden_filesystem_calls(source_file)
        assert not forbidden_calls


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


def _project_imports_matching_prefixes(source_file: Path, forbidden_prefixes: tuple[str, ...]) -> set[str]:
    return {
        imported_module
        for imported_module in _imported_modules(source_file)
        if _matches_any_prefix(imported_module, forbidden_prefixes)
    }


def _allowed_outbound_import_prefixes(source_file: Path) -> tuple[str, ...]:
    relative_path = source_file.relative_to(_source_root() / "omym2").as_posix()
    return tuple(
        module_prefix
        for path_suffix, module_prefix in INBOUND_ADAPTER_ALLOWED_OUTBOUND_IMPORTS
        if relative_path.endswith(path_suffix)
    )


def _forbidden_filesystem_calls(source_file: Path) -> set[str]:
    module_tree = ast.parse(source_file.read_text(encoding="utf-8"))
    return {
        f"{source_file.name}:{node.lineno}:{node.func.attr}"
        for node in ast.walk(module_tree)
        if isinstance(node, ast.Call)
        and isinstance(node.func, ast.Attribute)
        and node.func.attr in FORBIDDEN_FILESYSTEM_METHODS
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
