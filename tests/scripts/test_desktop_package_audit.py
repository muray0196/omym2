"""
Summary: Tests Windows desktop archive safety, resources, identity, and license evidence.
Why: Prevents a plausible-looking ZIP from bypassing the frozen package contract.
"""

from __future__ import annotations

import hashlib
import json
import struct
import zipfile
from pathlib import Path
from typing import TYPE_CHECKING

import pytest

from scripts import config
from scripts.desktop.audit_windows_package import (
    _WINDOWS_METADATA_SCRIPT,  # pyright: ignore[reportPrivateUsage] -- protects the native PE inspection contract.
    WindowsExecutableMetadata,
    WindowsPackageAuditError,
    _canonical_archive_payload_sha256,  # pyright: ignore[reportPrivateUsage] -- verifies container-independent identity.
    _safe_zip_members,  # pyright: ignore[reportPrivateUsage] -- supplies validated members to the digest helper.
    audit_windows_package,
    extract_windows_archive,
    read_version_info,
    read_windows_icon_sizes,
    windows_archive_name,
)

if TYPE_CHECKING:
    from collections.abc import Mapping

PACKAGE_VERSION = "0.1.0"
PE_HEADER_OFFSET = 0x80
PE_MACHINE_X86_64 = 0x8664
PE_MACHINE_X86 = 0x014C
PE32_PLUS_MAGIC = 0x20B
PE_GUI_SUBSYSTEM = 2
PE_CONSOLE_SUBSYSTEM = 3
PE_COFF_HEADER_BYTES = 20
PE_OPTIONAL_SUBSYSTEM_OFFSET = 68
PE_FIXTURE_BYTES = 256
EXPECTED_TEST_ICON_PIXELS = 32
ROOT = f"{config.DESKTOP_APPLICATION_NAME}/{config.DESKTOP_PYINSTALLER_CONTENTS_DIRECTORY_NAME}"
STATIC_INDEX = "omym2/adapters/web/static_dist/index.html"
STATIC_SCRIPT = "omym2/adapters/web/static_dist/assets/app-abcdefgh.js"
MIGRATION = "omym2/adapters/db/sqlite/migrations/001_initial.sql"
PROJECT_METADATA = f"omym2-{PACKAGE_VERSION}.dist-info/METADATA"
MUTAGEN_METADATA_DIRECTORY = "mutagen-1.47.0.dist-info"
MUTAGEN_METADATA = f"{MUTAGEN_METADATA_DIRECTORY}/METADATA"
MUTAGEN_LICENSE = f"{MUTAGEN_METADATA_DIRECTORY}/licenses/COPYING"
PYTHON_LICENSE_BODY = b"Python test license\n"
WHEEL_FILES = {
    STATIC_INDEX: b"<!doctype html><script src='/assets/app-abcdefgh.js'></script>",
    STATIC_SCRIPT: b"globalThis.OMYM2 = true;",
    MIGRATION: b"CREATE TABLE test (id INTEGER);",
    PROJECT_METADATA: b"Metadata-Version: 2.4\nName: omym2\nVersion: 0.1.0\n\n",
}


def test_windows_archive_audit_accepts_exact_wheel_resources_and_native_identity(tmp_path: Path) -> None:
    """A safe x64 GUI archive with runtime notices and exact wheel data passes."""
    wheel = _write_wheel(tmp_path)
    archive = _write_archive(tmp_path)

    audit = audit_windows_package(
        archive,
        wheel,
        _icon_path(),
        _version_info_path(),
        metadata_reader=_matching_metadata_reader,
    )

    assert audit.package_version == PACKAGE_VERSION
    assert len(audit.artifact_payload_sha256) == hashlib.sha256().digest_size * 2
    assert audit.pe_machine == "x86_64"
    assert audit.pe_subsystem == "windows_gui"
    assert audit.runtime_distribution_count == 1
    assert audit.runtime_license_file_count == 1
    assert audit.webview_dll_count == len(config.DESKTOP_WINDOWS_REQUIRED_WEBVIEW_DLL_RELATIVE_PATHS)
    assert audit.webview_modules == config.DESKTOP_PYINSTALLER_REQUIRED_WEBVIEW_MODULES


def test_windows_archive_audit_rejects_traversal_before_extraction(tmp_path: Path) -> None:
    """A traversal member fails even when every required package resource exists."""
    wheel = _write_wheel(tmp_path)
    archive = _write_archive(tmp_path, extra_files={"../escape.exe": b"unsafe"})

    with pytest.raises(WindowsPackageAuditError, match="unsafe member path"):
        _ = audit_windows_package(
            archive,
            wheel,
            _icon_path(),
            _version_info_path(),
            metadata_reader=_matching_metadata_reader,
        )


@pytest.mark.parametrize(
    "forbidden_member",
    [
        f"{ROOT}/node.exe",
        f"{ROOT}/PySide6/Qt6WebEngineCore.dll",
        f"{ROOT}/cefpython/libcef.dll",
        f"{ROOT}/src/omym2/config.py",
        f"{ROOT}/webview/lib/WebBrowserInterop.x64.dll",
    ],
)
def test_windows_archive_audit_rejects_runtime_and_source_leaks(
    tmp_path: Path,
    forbidden_member: str,
) -> None:
    """Node, bundled Chromium or Qt, and source-checkout content cannot ship."""
    wheel = _write_wheel(tmp_path)
    archive = _write_archive(tmp_path, extra_files={forbidden_member: b"forbidden"})

    with pytest.raises(WindowsPackageAuditError, match=r"forbidden|prohibited|source-tree"):
        _ = audit_windows_package(
            archive,
            wheel,
            _icon_path(),
            _version_info_path(),
            metadata_reader=_matching_metadata_reader,
        )


def test_windows_archive_audit_rejects_wheel_resource_drift(tmp_path: Path) -> None:
    """Frozen static content must remain byte-identical to the audited wheel."""
    wheel = _write_wheel(tmp_path)
    archive = _write_archive(tmp_path, replacements={f"{ROOT}/{STATIC_INDEX}": b"changed"})

    with pytest.raises(WindowsPackageAuditError, match="resource differs"):
        _ = audit_windows_package(
            archive,
            wheel,
            _icon_path(),
            _version_info_path(),
            metadata_reader=_matching_metadata_reader,
        )


def test_windows_archive_audit_rejects_same_version_mismatched_wheel(tmp_path: Path) -> None:
    """Frozen Python provenance binds the archive to the exact supplied wheel, not its version."""
    original_root = tmp_path / "original"
    other_root = tmp_path / "other"
    original_root.mkdir()
    other_root.mkdir()
    _ = _write_wheel(original_root)
    archive = _write_archive(original_root)
    other_wheel = _write_wheel(other_root, extra_files={"omym2/runtime-change.py": b"changed code"})

    with pytest.raises(WindowsPackageAuditError, match="does not match the supplied audited wheel"):
        _ = audit_windows_package(
            archive,
            other_wheel,
            _icon_path(),
            _version_info_path(),
            metadata_reader=_matching_metadata_reader,
        )


@pytest.mark.parametrize(
    ("machine", "subsystem", "message"),
    [
        (PE_MACHINE_X86, PE_GUI_SUBSYSTEM, "not PE x86_64"),
        (PE_MACHINE_X86_64, PE_CONSOLE_SUBSYSTEM, "not a no-console Windows GUI"),
    ],
)
def test_windows_archive_audit_rejects_wrong_pe_target(
    tmp_path: Path,
    machine: int,
    subsystem: int,
    message: str,
) -> None:
    """The actual executable, not only the spec, must be x64 and GUI-subsystem."""
    wheel = _write_wheel(tmp_path)
    archive = _write_archive(tmp_path, executable=_pe_fixture(machine=machine, subsystem=subsystem))

    with pytest.raises(WindowsPackageAuditError, match=message):
        _ = audit_windows_package(
            archive,
            wheel,
            _icon_path(),
            _version_info_path(),
            metadata_reader=_matching_metadata_reader,
        )


def test_windows_archive_audit_rejects_missing_python_license(tmp_path: Path) -> None:
    """The frozen CPython runtime cannot ship without its declared LICENSE.txt."""
    wheel = _write_wheel(tmp_path)
    archive = _write_archive(tmp_path, omitted={f"{ROOT}/{config.DESKTOP_PYTHON_RUNTIME_LICENSE_FILE_NAME}"})

    with pytest.raises(WindowsPackageAuditError, match="CPython LICENSE"):
        _ = audit_windows_package(
            archive,
            wheel,
            _icon_path(),
            _version_info_path(),
            metadata_reader=_matching_metadata_reader,
        )


def test_windows_archive_audit_rejects_incomplete_webview2_dll_payload(tmp_path: Path) -> None:
    """Both managed EdgeChromium assemblies are required alongside the x64 loader."""
    wheel = _write_wheel(tmp_path)
    missing_dll = f"{ROOT}/webview/lib/Microsoft.Web.WebView2.Core.dll"
    archive = _write_archive(tmp_path, omitted={missing_dll})

    with pytest.raises(WindowsPackageAuditError, match="WebView2 DLL payload differs"):
        _ = audit_windows_package(
            archive,
            wheel,
            _icon_path(),
            _version_info_path(),
            metadata_reader=_matching_metadata_reader,
        )


def test_windows_archive_audit_rejects_excluded_pywebview_renderer(tmp_path: Path) -> None:
    """The embedded freeze manifest cannot claim an alternate Windows renderer."""
    wheel = _write_wheel(tmp_path)
    provenance_path = f"{ROOT}/{config.DESKTOP_PYINSTALLER_PROVENANCE_FILE_NAME}"
    provenance = _freeze_provenance(hashlib.sha256(wheel.read_bytes()).hexdigest())
    provenance["webview_modules"] = sorted(
        (*config.DESKTOP_PYINSTALLER_REQUIRED_WEBVIEW_MODULES, "webview.platforms.mshtml")
    )
    archive = _write_archive(
        tmp_path,
        replacements={provenance_path: json.dumps(provenance, sort_keys=True).encode()},
    )

    with pytest.raises(WindowsPackageAuditError, match=r"forbidden=.*mshtml"):
        _ = audit_windows_package(
            archive,
            wheel,
            _icon_path(),
            _version_info_path(),
            metadata_reader=_matching_metadata_reader,
        )


def test_safe_extraction_rejects_traversal_archive(tmp_path: Path) -> None:
    """The smoke extractor independently refuses traversal instead of using extractall."""
    archive = tmp_path / "unsafe.zip"
    with zipfile.ZipFile(archive, mode="w") as package:
        package.writestr("../escape", b"unsafe")

    with pytest.raises(WindowsPackageAuditError, match="unsafe member path"):
        _ = extract_windows_archive(archive, tmp_path / "output")

    assert not (tmp_path / "escape").exists()


def test_canonical_archive_payload_digest_ignores_zip_container_metadata(tmp_path: Path) -> None:
    """Reordering and recompressing identical members cannot masquerade as a different build payload."""
    files = {"root/a.txt": b"alpha", "root/b.txt": b"beta"}
    first = tmp_path / "first.zip"
    second = tmp_path / "second.zip"
    with zipfile.ZipFile(first, mode="w", compression=zipfile.ZIP_STORED) as package:
        for name, content in files.items():
            package.writestr(name, content)
    with zipfile.ZipFile(second, mode="w", compression=zipfile.ZIP_DEFLATED) as package:
        for name, content in reversed(tuple(files.items())):
            package.writestr(name, content)

    assert first.read_bytes() != second.read_bytes()
    assert _archive_payload_sha256(first) == _archive_payload_sha256(second)


def test_committed_windows_icon_and_version_metadata_match_package_contract() -> None:
    """The committed ICO and PyInstaller expression are valid and version-aligned."""
    version_info = read_version_info(_version_info_path())

    assert read_windows_icon_sizes(_icon_path()) == config.DESKTOP_WINDOWS_ICON_SIZES
    assert version_info.strings["ProductVersion"] == PACKAGE_VERSION
    assert version_info.strings["OriginalFilename"] == config.DESKTOP_WINDOWS_EXECUTABLE_NAME
    assert version_info.numeric_versions["filevers"] == (0, 1, 0, 0)


def test_windows_metadata_probe_reads_every_committed_string() -> None:
    """The native PowerShell probe must expose every string compared by the audit."""
    version_info = read_version_info(_version_info_path())

    for name in version_info.strings:
        assert f"{name} = $version.{name}" in _WINDOWS_METADATA_SCRIPT

    assert "[System.Drawing.Bitmap]::new($expectedIconPath)" in _WINDOWS_METADATA_SCRIPT
    assert "[System.Drawing.Icon]::new($IconPath" not in _WINDOWS_METADATA_SCRIPT


def test_version_metadata_rejects_a_file_header_before_the_expression(tmp_path: Path) -> None:
    """PyInstaller eval mode cannot accept a docstring before VSVersionInfo."""
    version_info = tmp_path / "windows-version-info.txt"
    _ = version_info.write_text(
        '"""not an expression header"""\nVSVersionInfo()\n',
        encoding="utf-8",
    )

    with pytest.raises(WindowsPackageAuditError, match="one PyInstaller-compatible expression"):
        _ = read_version_info(version_info)


def _write_wheel(tmp_path: Path, *, extra_files: Mapping[str, bytes] | None = None) -> Path:
    wheel = tmp_path / "omym2-0.1.0-py3-none-any.whl"
    with zipfile.ZipFile(wheel, mode="w") as package:
        for name, content in {**WHEEL_FILES, **(extra_files or {})}.items():
            package.writestr(name, content)
    return wheel


def _write_archive(
    tmp_path: Path,
    *,
    executable: bytes | None = None,
    extra_files: Mapping[str, bytes] | None = None,
    replacements: Mapping[str, bytes] | None = None,
    omitted: set[str] | None = None,
) -> Path:
    archive = tmp_path / windows_archive_name(PACKAGE_VERSION)
    wheel = tmp_path / "omym2-0.1.0-py3-none-any.whl"
    if not wheel.is_file():
        msg = "Archive fixture requires its exact wheel fixture first."
        raise AssertionError(msg)
    wheel_sha256 = hashlib.sha256(wheel.read_bytes()).hexdigest()
    files = _valid_archive_files(executable or _pe_fixture(), wheel_sha256)
    files.update(extra_files or {})
    files.update(replacements or {})
    omitted_files = omitted or set()
    with zipfile.ZipFile(archive, mode="w") as package:
        for name, content in files.items():
            if name not in omitted_files:
                package.writestr(name, content)
    return archive


def _valid_archive_files(executable: bytes, wheel_sha256: str) -> dict[str, bytes]:
    python_license_digest = hashlib.sha256(PYTHON_LICENSE_BODY).hexdigest()
    inventory: dict[str, object] = {
        "project": {
            "license_files": [],
            "metadata_directory": f"omym2-{PACKAGE_VERSION}.dist-info",
            "name": "omym2",
            "version": PACKAGE_VERSION,
        },
        "project_license": "unresolved",
        "python_runtime": {
            "license_file": config.DESKTOP_PYTHON_RUNTIME_LICENSE_FILE_NAME,
            "license_sha256": python_license_digest,
            "version": "3.14.0",
        },
        "third_party": [
            {
                "license_files": [MUTAGEN_LICENSE],
                "metadata_directory": MUTAGEN_METADATA_DIRECTORY,
                "name": "mutagen",
                "version": "1.47.0",
            }
        ],
    }
    files = {f"{ROOT}/{name}": content for name, content in WHEEL_FILES.items()}
    files.update(
        {
            f"{config.DESKTOP_APPLICATION_NAME}/{config.DESKTOP_WINDOWS_EXECUTABLE_NAME}": executable,
            f"{ROOT}/{config.DESKTOP_PYINSTALLER_PROVENANCE_FILE_NAME}": json.dumps(
                _freeze_provenance(wheel_sha256), sort_keys=True
            ).encode(),
            f"{ROOT}/{config.DESKTOP_PYTHON_RUNTIME_LICENSE_FILE_NAME}": PYTHON_LICENSE_BODY,
            f"{ROOT}/{config.DESKTOP_RUNTIME_INVENTORY_FILE_NAME}": json.dumps(inventory).encode(),
            f"{ROOT}/{MUTAGEN_METADATA}": b"Metadata-Version: 2.4\nName: mutagen\nVersion: 1.47.0\n\n",
            f"{ROOT}/{MUTAGEN_LICENSE}": b"Mutagen test license\n",
            f"{ROOT}/webview/lib/Microsoft.Web.WebView2.Core.dll": b"managed WebView2 core",
            f"{ROOT}/webview/lib/Microsoft.Web.WebView2.WinForms.dll": b"managed WebView2 WinForms",
            f"{ROOT}/webview/lib/runtimes/win-x64/native/WebView2Loader.dll": b"native WebView2 loader",
        }
    )
    return files


def _freeze_provenance(wheel_sha256: str) -> dict[str, object]:
    return {
        "builtin_imports": sorted(config.DESKTOP_PYINSTALLER_REQUIRED_BUILTIN_MODULES),
        "console": False,
        "contents_directory": config.DESKTOP_PYINSTALLER_CONTENTS_DIRECTORY_NAME,
        "excluded_webview_modules": sorted(
            module for module in config.DESKTOP_PYINSTALLER_EXCLUDED_MODULES if module.startswith("webview.")
        ),
        "format": "onedir",
        "hidden_imports": sorted(config.DESKTOP_PYINSTALLER_HIDDEN_IMPORTS),
        "omym2_module_count": 1,
        "runtime_hook_policy": config.DESKTOP_PYINSTALLER_RUNTIME_HOOK_POLICY,
        "source_imports": "isolated-wheel-only",
        "webview_modules": list(config.DESKTOP_PYINSTALLER_REQUIRED_WEBVIEW_MODULES),
        "wheel_sha256": wheel_sha256,
    }


def _archive_payload_sha256(path: Path) -> str:
    with zipfile.ZipFile(path) as archive:
        members = _safe_zip_members(archive, label="test archive")
        return _canonical_archive_payload_sha256(archive, members)


def _pe_fixture(
    *,
    machine: int = PE_MACHINE_X86_64,
    subsystem: int = PE_GUI_SUBSYSTEM,
) -> bytes:
    payload = bytearray(PE_FIXTURE_BYTES)
    payload[:2] = b"MZ"
    struct.pack_into("<I", payload, 0x3C, PE_HEADER_OFFSET)
    payload[PE_HEADER_OFFSET : PE_HEADER_OFFSET + 4] = b"PE\x00\x00"
    struct.pack_into("<H", payload, PE_HEADER_OFFSET + 4, machine)
    optional_header = PE_HEADER_OFFSET + 4 + PE_COFF_HEADER_BYTES
    struct.pack_into("<H", payload, optional_header, PE32_PLUS_MAGIC)
    struct.pack_into("<H", payload, optional_header + PE_OPTIONAL_SUBSYSTEM_OFFSET, subsystem)
    return bytes(payload)


def _matching_metadata_reader(_executable: Path, _icon: Path) -> WindowsExecutableMetadata:
    return WindowsExecutableMetadata(
        strings=read_version_info(_version_info_path()).strings,
        icon_matches=True,
        icon_width=EXPECTED_TEST_ICON_PIXELS,
        icon_height=EXPECTED_TEST_ICON_PIXELS,
    )


def _icon_path() -> Path:
    return _project_root() / config.DESKTOP_WINDOWS_ICON_RELATIVE_PATH


def _version_info_path() -> Path:
    return _project_root() / config.DESKTOP_WINDOWS_VERSION_RELATIVE_PATH


def _project_root() -> Path:
    for parent in Path(__file__).resolve().parents:
        if (parent / "pyproject.toml").is_file():
            return parent
    msg = "Unable to locate project root from desktop package test."
    raise AssertionError(msg)
