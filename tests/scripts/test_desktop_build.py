"""
Summary: Tests deterministic desktop build helpers and committed PyInstaller policy.
Why: Keeps Windows artifacts isolated, locked, onedir, and reproducibly archived.
"""

from __future__ import annotations

import zipfile
from pathlib import Path

import pytest

from scripts import config
from scripts.desktop.build_windows import (
    _PYWEBVIEW_X64_RUNTIME_HOOK_SOURCE,  # pyright: ignore[reportPrivateUsage] -- verifies frozen hook policy.
    InstalledWheelProbe,
    WindowsPackageBuildError,
    _isolated_environment,  # pyright: ignore[reportPrivateUsage] -- directly verifies build isolation.
    _validate_installed_probe,  # pyright: ignore[reportPrivateUsage] -- directly verifies wheel provenance.
    _validate_locked_requirements,  # pyright: ignore[reportPrivateUsage] -- directly verifies locked inputs.
    create_deterministic_zip,
    require_windows_x64,
)

WINDOWS_PLATFORM = "win32"
WINDOWS_MACHINE = "AMD64"
WINDOWS_POINTER_BYTES = 8
WINDOWS_X86_POINTER_BYTES = 4
SOURCE_DATE_SENTINEL = "source-date-sentinel"


def test_deterministic_zip_normalizes_order_timestamp_and_permissions(tmp_path: Path) -> None:
    """Identical onedir bytes produce identical ZIP bytes despite source mtimes."""
    bundle = tmp_path / "bundle"
    internal = bundle / config.DESKTOP_PYINSTALLER_CONTENTS_DIRECTORY_NAME
    internal.mkdir(parents=True)
    _ = (bundle / config.DESKTOP_WINDOWS_EXECUTABLE_NAME).write_bytes(b"MZ executable")
    _ = (internal / "z-last.dat").write_bytes(b"last")
    _ = (internal / "a-first.dat").write_bytes(b"first")
    first_archive = tmp_path / "first.zip"
    second_archive = tmp_path / "second.zip"

    create_deterministic_zip(bundle, first_archive)
    for source in bundle.rglob("*"):
        source.touch()
    create_deterministic_zip(bundle, second_archive)

    assert first_archive.read_bytes() == second_archive.read_bytes()
    with zipfile.ZipFile(first_archive) as archive:
        members = archive.infolist()
        assert [member.filename for member in members] == sorted(member.filename for member in members)
        assert {member.date_time for member in members} == {config.DESKTOP_ARCHIVE_TIMESTAMP}
        assert all(not member.filename.startswith("/") for member in members)


@pytest.mark.parametrize(
    ("platform_name", "machine_name", "pointer_bytes"),
    [
        ("linux", WINDOWS_MACHINE, WINDOWS_POINTER_BYTES),
        (WINDOWS_PLATFORM, "ARM64", WINDOWS_POINTER_BYTES),
        (WINDOWS_PLATFORM, WINDOWS_MACHINE, WINDOWS_X86_POINTER_BYTES),
    ],
)
def test_windows_build_preflight_rejects_non_x64_native_hosts(
    platform_name: str,
    machine_name: str,
    pointer_bytes: int,
) -> None:
    """Cross-platform or 32-bit freezes fail before creating output."""
    with pytest.raises(WindowsPackageBuildError):
        require_windows_x64(platform_name, machine_name, pointer_bytes)


def test_windows_build_preflight_accepts_x64_windows() -> None:
    """The supported native Windows x64 build host passes preflight."""
    require_windows_x64(WINDOWS_PLATFORM, WINDOWS_MACHINE, WINDOWS_POINTER_BYTES)


def test_isolated_environment_removes_source_shadowing_inputs(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """PyInstaller children cannot inherit checkout-oriented Python paths."""
    monkeypatch.setenv("PYTHONPATH", SOURCE_DATE_SENTINEL)
    monkeypatch.setenv("PYTHONHOME", SOURCE_DATE_SENTINEL)
    monkeypatch.setenv("VIRTUAL_ENV", SOURCE_DATE_SENTINEL)

    environment = _isolated_environment(tmp_path)

    assert "PYTHONPATH" not in environment
    assert "PYTHONHOME" not in environment
    assert "VIRTUAL_ENV" not in environment
    assert environment["PYTHONSAFEPATH"] == "1"
    assert environment["SOURCE_DATE_EPOCH"] == config.DESKTOP_PYINSTALLER_SOURCE_DATE_EPOCH


def test_installed_probe_rejects_source_checkout_resolution(tmp_path: Path) -> None:
    """An import resolving under the repository cannot satisfy wheel isolation."""
    project_root = tmp_path / "repo"
    virtual_environment = tmp_path / "build-venv"
    purelib = virtual_environment / "Lib" / "site-packages"
    probe = InstalledWheelProbe(
        entry_origin=project_root / "src/omym2/platform/desktop_entry_point.py",
        package_root=project_root / "src/omym2",
        purelib=purelib,
        version="0.1.0",
    )

    with pytest.raises(WindowsPackageBuildError, match=r"site-packages|source checkout"):
        _validate_installed_probe(probe, virtual_environment, project_root, "0.1.0")


def test_locked_requirements_separate_runtime_and_build_tools(tmp_path: Path) -> None:
    """Runtime export admits pywebview while rejecting an accidentally mixed PyInstaller."""
    requirements = tmp_path / "runtime.txt"
    _ = requirements.write_text("pywebview==6.2.1\n", encoding="utf-8")
    _validate_locked_requirements(
        requirements,
        tmp_path / "repo",
        required=("pywebview==",),
        forbidden=("pyinstaller==",),
    )
    _ = requirements.write_text("pywebview==6.2.1\npyinstaller==6.21.0\n", encoding="utf-8")

    with pytest.raises(WindowsPackageBuildError, match="forbidden build inputs"):
        _validate_locked_requirements(
            requirements,
            tmp_path / "repo",
            required=("pywebview==",),
            forbidden=("pyinstaller==",),
        )


def test_pyinstaller_spec_forces_desktop_resources_and_gui_mode() -> None:
    """The committed spec exposes the core frozen-package decisions to review."""
    source = (_project_root() / config.DESKTOP_WINDOWS_SPEC_RELATIVE_PATH).read_text(encoding="utf-8")

    assert 'collect_data_files(\n    "omym2.adapters.web"' in source
    assert 'collect_data_files(\n    "omym2.adapters.db.sqlite.migrations"' in source
    assert 'copy_metadata("omym2")' in source
    assert 'collect_submodules("webview")' not in source
    assert 'collect_dynamic_libs("webview")' in source
    assert 'os.environ["OMYM2_DESKTOP_HIDDEN_IMPORTS"]' in source
    assert "analysis.graph.is_a_builtin(module_name)" in source
    assert 'os.environ["OMYM2_DESKTOP_REQUIRED_WEBVIEW_MODULES"]' in source
    assert "runtime_hooks=[str(runtime_hook)]" in source
    assert '"runtime_hook_policy": runtime_hook_policy' in source
    assert 'os.environ["OMYM2_DESKTOP_WHEEL_SHA256"]' in source
    assert 'module_name.startswith("webview.")' in source
    assert '"wheel_sha256": wheel_sha256' in source
    assert 'analysis.datas.append((provenance_path.name, str(provenance_path), "DATA"))' in source
    assert "webview.platforms.mshtml" in config.DESKTOP_PYINSTALLER_EXCLUDED_MODULES
    assert "webview.platforms.edgechromium" in config.DESKTOP_PYINSTALLER_HIDDEN_IMPORTS
    assert "webview.platforms.winforms" in config.DESKTOP_PYINSTALLER_HIDDEN_IMPORTS
    assert "winreg" in config.DESKTOP_PYINSTALLER_HIDDEN_IMPORTS
    assert config.DESKTOP_PYINSTALLER_REQUIRED_BUILTIN_MODULES == ("msvcrt", "winreg")
    assert "exclude_binaries=True" in source
    assert "console=False" in source
    assert "icon=str(icon)" in source
    assert "version=str(version_info)" in source


def test_pywebview_runtime_hook_aliases_only_unused_architecture_probes_to_x64() -> None:
    """The frozen hook satisfies pywebview's broad directory probe without bundling non-x64 DLLs."""
    source = _PYWEBVIEW_X64_RUNTIME_HOOK_SOURCE

    _ = compile(source, "omym2_pywebview_x64_runtime_hook.py", "exec")
    assert repr(config.DESKTOP_PYWEBVIEW_UNUSED_RUNTIME_DIRECTORY_NAMES) in source
    assert repr(config.DESKTOP_PYWEBVIEW_X64_RUNTIME_DIRECTORY_NAME) in source
    assert "webview_util.interop_dll_path = _x64_interop_dll_path" in source
    assert "from webview import util as webview_util" in source


def test_all_desktop_python_and_spec_files_have_exact_file_header() -> None:
    """New standalone code retains the required four-line business-reason header."""
    desktop_scripts = _project_root() / "scripts/desktop"
    for path in sorted((*desktop_scripts.glob("*.py"), *desktop_scripts.glob("*.spec"))):
        lines = path.read_text(encoding="utf-8").splitlines()
        assert lines[0] == '"""'
        assert lines[1].startswith("Summary: ")
        assert lines[2].startswith("Why: ")
        assert lines[3] == '"""'


def _project_root() -> Path:
    for parent in Path(__file__).resolve().parents:
        if (parent / "pyproject.toml").is_file():
            return parent
    msg = "Unable to locate project root from desktop build test."
    raise AssertionError(msg)
