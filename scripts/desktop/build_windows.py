"""
Summary: Builds and evidences the Windows x64 desktop archive from one audited wheel.
Why: Keeps source checkout code outside the isolated native application freeze.
"""
# ruff: noqa: T201 -- Standalone build tooling is directly executable and reports concise results.

from __future__ import annotations

import argparse
import hashlib
import json
import os
import platform
import shutil
import struct
import subprocess
import sys
import tempfile
import zipfile
from dataclasses import dataclass
from pathlib import Path
from typing import TYPE_CHECKING, cast
from urllib.parse import urlsplit
from urllib.request import url2pathname

if __package__:
    from scripts import config
    from scripts.desktop.audit_windows_package import (
        WheelContract,
        WindowsPackageAudit,
        WindowsPackageAuditError,
        audit_windows_package,
        read_version_info,
        read_wheel_contract,
        read_windows_icon_sizes,
        validate_freeze_provenance,
        windows_archive_name,
    )
else:
    sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
    from scripts import config  # Direct script execution needs the repository script namespace.
    from scripts.desktop.audit_windows_package import (  # See the direct-execution path above.
        WheelContract,
        WindowsPackageAudit,
        WindowsPackageAuditError,
        audit_windows_package,
        read_version_info,
        read_wheel_contract,
        read_windows_icon_sizes,
        validate_freeze_provenance,
        windows_archive_name,
    )

if TYPE_CHECKING:
    from collections.abc import Mapping, Sequence

_LAUNCHER_SOURCE = '''"""
Summary: Starts the installed OMYM2 native desktop entry point.
Why: Gives PyInstaller a source-free bootstrap that calls the audited wheel.
"""

from omym2.platform.desktop_entry_point import main

raise SystemExit(main())
'''
_PYWEBVIEW_X64_RUNTIME_HOOK_SOURCE = f'''"""
Summary: Restricts pywebview's frozen native-loader lookup to the packaged x64 resource.
Why: pywebview probes every architecture directory even though OMYM2 ships only the audited x64 loader.
"""

from webview import util as webview_util

_original_interop_dll_path = webview_util.interop_dll_path
_unused_runtime_directories = frozenset({config.DESKTOP_PYWEBVIEW_UNUSED_RUNTIME_DIRECTORY_NAMES!r})


def _x64_interop_dll_path(dll_name: str) -> str:
    if dll_name in _unused_runtime_directories:
        dll_name = {config.DESKTOP_PYWEBVIEW_X64_RUNTIME_DIRECTORY_NAME!r}
    return _original_interop_dll_path(dll_name)


webview_util.interop_dll_path = _x64_interop_dll_path
'''
_INSTALL_PROBE_SOURCE = """
import importlib.metadata, importlib.util, json, pathlib, sysconfig
package = importlib.util.find_spec("omym2")
entry = importlib.util.find_spec("omym2.platform.desktop_entry_point")
if package is None or package.origin is None or entry is None or entry.origin is None:
    raise SystemExit("The installed wheel does not expose the desktop entry point.")
print(json.dumps({
    "entry_origin": str(pathlib.Path(entry.origin).resolve()),
    "package_root": str(pathlib.Path(package.origin).resolve().parent),
    "purelib": str(pathlib.Path(sysconfig.get_path("purelib")).resolve()),
    "version": importlib.metadata.version("omym2"),
}, sort_keys=True))
"""
_RUNTIME_INVENTORY_PROBE_SOURCE = """
import importlib.metadata, json, pathlib, platform, sys
entries = []
for distribution in importlib.metadata.distributions():
    name = distribution.metadata.get("Name", "").strip()
    version = distribution.version
    files = tuple(distribution.files or ())
    metadata_files = [pathlib.PurePosixPath(str(item).replace("\\\\", "/")) for item in files]
    metadata_candidates = [item for item in metadata_files if len(item.parts) >= 2 and item.name == "METADATA" and item.parts[0].endswith(".dist-info")]
    if not name or len(metadata_candidates) != 1:
        continue
    metadata_directory = metadata_candidates[0].parts[0]
    license_files = sorted(
        item.as_posix()
        for item in metadata_files
        if item.parts[0] == metadata_directory
        and any(marker in item.name.casefold() for marker in ("copying", "license", "notice"))
    )
    entries.append({
        "license_files": license_files,
        "metadata_directory": metadata_directory,
        "name": name,
        "version": version,
    })
license_candidates = [pathlib.Path(sys.base_prefix) / name for name in ("LICENSE.txt", "LICENSE")]
python_license = next((path for path in license_candidates if path.is_file()), None)
if python_license is None:
    raise SystemExit("The frozen CPython installation does not expose LICENSE.txt or LICENSE.")
print(json.dumps({
    "distributions": sorted(entries, key=lambda item: item["name"].casefold()),
    "python_license_source": str(python_license.resolve()),
    "python_version": platform.python_version(),
}, sort_keys=True))
"""


class WindowsPackageBuildError(RuntimeError):
    """Raised when the isolated Windows package build cannot be completed."""


@dataclass(frozen=True, slots=True)
class InstalledWheelProbe:
    """Resolved installed-wheel locations from the isolated build interpreter."""

    entry_origin: Path
    package_root: Path
    purelib: Path
    version: str


@dataclass(frozen=True, slots=True)
class WindowsBuildOutputs:
    """Paths written by one successful Windows desktop package build."""

    archive: Path
    checksum: Path
    evidence: Path


@dataclass(frozen=True, slots=True)
class DesktopBuildInputs:
    """Validated repository and wheel inputs for one isolated native build."""

    artifact_name: str
    icon: Path
    output_directory: Path
    root: Path
    spec: Path
    version_info: Path
    wheel: Path
    wheel_contract: WheelContract


@dataclass(frozen=True, slots=True)
class IsolatedBuildEnvironment:
    """Locked runtime and build-tool state installed outside the source checkout."""

    build_requirements: Path
    environment: dict[str, str]
    installed_inventory: list[str]
    probe: InstalledWheelProbe
    python: Path
    python_runtime_license: Path
    runtime_distribution_names: list[str]
    runtime_inventory: dict[str, object]
    runtime_inventory_path: Path
    runtime_requirements: Path


class ParsedArgs(argparse.Namespace):
    """Typed command-line arguments for the Windows desktop build."""

    def __init__(self, output_directory: Path) -> None:
        super().__init__()
        self.wheel: Path = Path()
        self.output_directory: Path = output_directory


def build_windows_package(wheel_path: Path, output_directory: Path) -> WindowsBuildOutputs:
    """Freeze one audited wheel in an external venv, then archive and audit it."""
    inputs = _validated_build_inputs(wheel_path, output_directory)
    inputs.output_directory.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory(prefix="omym2-windows-build-") as temporary_directory:
        workspace = Path(temporary_directory).resolve()
        _require_external_workspace(workspace, inputs.root)
        isolated = _prepare_isolated_environment(inputs, workspace)
        return _freeze_and_publish(inputs, workspace, isolated)


def _validated_build_inputs(wheel_path: Path, output_directory: Path) -> DesktopBuildInputs:
    root = _project_root()
    wheel_path = wheel_path.resolve()
    output_directory = output_directory.resolve()
    require_windows_x64(sys.platform, platform.machine(), struct.calcsize("P"))
    wheel_contract = read_wheel_contract(wheel_path)
    icon = (root / config.DESKTOP_WINDOWS_ICON_RELATIVE_PATH).resolve()
    version_info_path = (root / config.DESKTOP_WINDOWS_VERSION_RELATIVE_PATH).resolve()
    spec = (root / config.DESKTOP_WINDOWS_SPEC_RELATIVE_PATH).resolve()
    if not spec.is_file():
        msg = f"PyInstaller specification does not exist: {spec}"
        raise WindowsPackageBuildError(msg)
    if read_windows_icon_sizes(icon) != config.DESKTOP_WINDOWS_ICON_SIZES:
        msg = "The committed Windows icon does not have the configured image sizes."
        raise WindowsPackageBuildError(msg)
    committed_version = read_version_info(version_info_path).strings["ProductVersion"]
    if committed_version != wheel_contract.version:
        msg = f"Committed Windows version {committed_version!r} does not match wheel {wheel_contract.version!r}."
        raise WindowsPackageBuildError(msg)

    return DesktopBuildInputs(
        artifact_name=windows_archive_name(wheel_contract.version),
        icon=icon,
        output_directory=output_directory,
        root=root,
        spec=spec,
        version_info=version_info_path,
        wheel=wheel_path,
        wheel_contract=wheel_contract,
    )


def _prepare_isolated_environment(inputs: DesktopBuildInputs, workspace: Path) -> IsolatedBuildEnvironment:
    environment = _isolated_environment(workspace)
    virtual_environment = workspace / "build-venv"
    _run(("uv", "venv", "--python", sys.executable, str(virtual_environment)), cwd=workspace, environment=environment)
    python = _venv_python(virtual_environment)
    runtime_requirements = workspace / "windows-runtime-requirements.txt"
    _export_locked_requirements(inputs.root, runtime_requirements, environment, runtime=True)
    _validate_locked_requirements(
        runtime_requirements,
        inputs.root,
        required=("pywebview==",),
        forbidden=("pyinstaller==",),
    )
    _install_locked_requirements(python, runtime_requirements, workspace, environment)
    _run(
        ("uv", "pip", "install", "--no-config", "--python", str(python), "--no-deps", str(inputs.wheel)),
        cwd=workspace,
        environment=environment,
    )
    _check_isolated_environment(python, workspace, environment)
    runtime_inventory, runtime_inventory_path, python_runtime_license = _prepare_runtime_inventory(
        python,
        workspace,
        environment,
    )
    raw_third_party = runtime_inventory["third_party"]
    if not isinstance(raw_third_party, list):
        msg = "Validated runtime inventory lost its third-party distribution list."
        raise WindowsPackageBuildError(msg)
    runtime_distribution_names: list[str] = []
    for raw_entry in cast("list[object]", raw_third_party):
        if isinstance(raw_entry, dict):
            entry = cast("dict[str, object]", raw_entry)
            if isinstance(name := entry.get("name"), str):
                runtime_distribution_names.append(name)
    build_requirements = workspace / "windows-build-requirements.txt"
    _export_locked_requirements(inputs.root, build_requirements, environment, runtime=False)
    _validate_locked_requirements(
        build_requirements,
        inputs.root,
        required=(config.DESKTOP_PYINSTALLER_REQUIREMENT.casefold(),),
        forbidden=(),
    )
    _install_locked_requirements(python, build_requirements, workspace, environment)
    _check_isolated_environment(python, workspace, environment)
    installed_inventory = _installed_inventory(python, workspace, environment, inputs.wheel)
    probe = _probe_installed_wheel(python, workspace, environment)
    _validate_installed_probe(probe, virtual_environment, inputs.root, inputs.wheel_contract.version)
    return IsolatedBuildEnvironment(
        build_requirements=build_requirements,
        environment=environment,
        installed_inventory=installed_inventory,
        probe=probe,
        python=python,
        python_runtime_license=python_runtime_license,
        runtime_distribution_names=runtime_distribution_names,
        runtime_inventory=runtime_inventory,
        runtime_inventory_path=runtime_inventory_path,
        runtime_requirements=runtime_requirements,
    )


def _freeze_and_publish(
    inputs: DesktopBuildInputs,
    workspace: Path,
    isolated: IsolatedBuildEnvironment,
) -> WindowsBuildOutputs:
    launcher = workspace / "omym2_desktop_launcher.py"
    _ = launcher.write_text(_LAUNCHER_SOURCE, encoding="utf-8", newline="\n")
    runtime_hook = workspace / "omym2_pywebview_x64_runtime_hook.py"
    _ = runtime_hook.write_text(_PYWEBVIEW_X64_RUNTIME_HOOK_SOURCE, encoding="utf-8", newline="\n")
    provenance = workspace / config.DESKTOP_PYINSTALLER_PROVENANCE_FILE_NAME
    isolated.environment.update(
        {
            "OMYM2_DESKTOP_ALLOWED_PACKAGE_ROOT": str(isolated.probe.package_root),
            "OMYM2_DESKTOP_APPLICATION_NAME": config.DESKTOP_APPLICATION_NAME,
            "OMYM2_DESKTOP_CONTENTS_DIRECTORY": config.DESKTOP_PYINSTALLER_CONTENTS_DIRECTORY_NAME,
            "OMYM2_DESKTOP_EXCLUDED_MODULES": json.dumps(config.DESKTOP_PYINSTALLER_EXCLUDED_MODULES),
            "OMYM2_DESKTOP_FORBIDDEN_WEBVIEW_RESOURCES": json.dumps(config.DESKTOP_WINDOWS_FORBIDDEN_WEBVIEW_RESOURCES),
            "OMYM2_DESKTOP_HIDDEN_IMPORTS": json.dumps(config.DESKTOP_PYINSTALLER_HIDDEN_IMPORTS),
            "OMYM2_DESKTOP_ICON": str(inputs.icon),
            "OMYM2_DESKTOP_LAUNCHER": str(launcher),
            "OMYM2_DESKTOP_PROVENANCE": str(provenance),
            "OMYM2_DESKTOP_PYTHON_RUNTIME_LICENSE": str(isolated.python_runtime_license),
            "OMYM2_DESKTOP_RUNTIME_DISTRIBUTIONS": json.dumps(isolated.runtime_distribution_names),
            "OMYM2_DESKTOP_RUNTIME_INVENTORY": str(isolated.runtime_inventory_path),
            "OMYM2_DESKTOP_REQUIRED_WEBVIEW_MODULES": json.dumps(config.DESKTOP_PYINSTALLER_REQUIRED_WEBVIEW_MODULES),
            "OMYM2_DESKTOP_REQUIRED_BUILTIN_MODULES": json.dumps(config.DESKTOP_PYINSTALLER_REQUIRED_BUILTIN_MODULES),
            "OMYM2_DESKTOP_RUNTIME_HOOK": str(runtime_hook),
            "OMYM2_DESKTOP_RUNTIME_HOOK_POLICY": config.DESKTOP_PYINSTALLER_RUNTIME_HOOK_POLICY,
            "OMYM2_DESKTOP_VERSION_INFO": str(inputs.version_info),
            "OMYM2_DESKTOP_WHEEL_SHA256": _file_sha256(inputs.wheel),
        }
    )
    distribution_directory = workspace / "dist"
    _run(
        (
            str(isolated.python),
            "-I",
            "-m",
            "PyInstaller",
            "--clean",
            "--noconfirm",
            "--distpath",
            str(distribution_directory),
            "--workpath",
            str(workspace / "pyinstaller-work"),
            str(inputs.spec),
        ),
        cwd=workspace,
        environment=isolated.environment,
    )
    provenance_payload = _read_provenance(provenance)
    bundle = distribution_directory / config.DESKTOP_APPLICATION_NAME
    if not bundle.is_dir():
        msg = f"PyInstaller did not create the expected onedir bundle: {bundle}"
        raise WindowsPackageBuildError(msg)
    workspace_archive = workspace / inputs.artifact_name
    create_deterministic_zip(bundle, workspace_archive)
    audit = audit_windows_package(workspace_archive, inputs.wheel, inputs.icon, inputs.version_info)
    return _publish_outputs(inputs, isolated, provenance_payload, workspace_archive, audit)


def _publish_outputs(
    inputs: DesktopBuildInputs,
    isolated: IsolatedBuildEnvironment,
    provenance: Mapping[str, object],
    workspace_archive: Path,
    audit: WindowsPackageAudit,
) -> WindowsBuildOutputs:
    final_archive = inputs.output_directory / inputs.artifact_name
    final_checksum = inputs.output_directory / f"{inputs.artifact_name}.sha256"
    final_evidence = inputs.output_directory / f"{inputs.artifact_name}.json"
    _copy_atomically(workspace_archive, final_archive)
    _write_text_atomically(final_checksum, f"{audit.artifact_sha256}  {inputs.artifact_name}\n")
    evidence = {
        "artifact": {
            "file_count": audit.archive_file_count,
            "filename": inputs.artifact_name,
            "format": "zip",
            "mode": "onedir",
            "platform": config.DESKTOP_WINDOWS_ARTIFACT_TAG,
            "pe_machine": audit.pe_machine,
            "pe_subsystem": audit.pe_subsystem,
            "sha256": audit.artifact_sha256,
            "payload_sha256": audit.artifact_payload_sha256,
            "size_bytes": audit.artifact_size_bytes,
        },
        "audit": {
            "icon": "committed-and-embedded",
            "node_chromium_qt": "absent",
            "resource_count": audit.verified_resource_count,
            "runtime_distribution_count": audit.runtime_distribution_count,
            "runtime_license_file_count": audit.runtime_license_file_count,
            "source_imports": provenance["source_imports"],
            "version_metadata": "committed-and-embedded",
            "webview_modules": list(audit.webview_modules),
            "webview_dll_count": audit.webview_dll_count,
        },
        "build": {
            "application": config.DESKTOP_APPLICATION_NAME,
            "console": False,
            "pyinstaller": config.DESKTOP_PYINSTALLER_REQUIREMENT,
            "specification_sha256": _file_sha256(inputs.spec),
        },
        "inputs": {
            "icon_sha256": _file_sha256(inputs.icon),
            "installed_inventory": isolated.installed_inventory,
            "locked_build_requirements_sha256": _file_sha256(isolated.build_requirements),
            "locked_runtime_requirements_sha256": _file_sha256(isolated.runtime_requirements),
            "runtime_inventory": isolated.runtime_inventory,
            "uv_lock_sha256": _file_sha256(inputs.root / "uv.lock"),
            "version_info_sha256": _file_sha256(inputs.version_info),
            "wheel_filename": inputs.wheel.name,
            "wheel_sha256": audit.wheel_sha256,
        },
        "package_version": audit.package_version,
        "release_authorization": {
            "project_license": "unresolved",
            "public_distribution": "not_authorized_by_build_evidence",
        },
    }
    _write_text_atomically(final_evidence, json.dumps(evidence, indent=2, sort_keys=True) + "\n")
    return WindowsBuildOutputs(archive=final_archive, checksum=final_checksum, evidence=final_evidence)


def _export_locked_requirements(
    root: Path,
    destination: Path,
    environment: Mapping[str, str],
    *,
    runtime: bool,
) -> None:
    selection = ("--extra", "desktop") if runtime else ("--only-group", "desktop-build")
    _run(
        (
            "uv",
            "export",
            "--locked",
            "--no-default-groups",
            *selection,
            "--no-emit-project",
            "--no-emit-local",
            "--format",
            "requirements.txt",
            "--output-file",
            str(destination),
        ),
        cwd=root,
        environment=environment,
    )


def _install_locked_requirements(
    python: Path,
    requirements: Path,
    workspace: Path,
    environment: Mapping[str, str],
) -> None:
    _run(
        (
            "uv",
            "pip",
            "install",
            "--no-config",
            "--python",
            str(python),
            "--requirements",
            str(requirements),
            "--require-hashes",
            "--strict",
        ),
        cwd=workspace,
        environment=environment,
    )


def _check_isolated_environment(python: Path, workspace: Path, environment: Mapping[str, str]) -> None:
    _run(
        ("uv", "pip", "check", "--no-config", "--python", str(python)),
        cwd=workspace,
        environment=environment,
    )


def _prepare_runtime_inventory(
    python: Path,
    workspace: Path,
    environment: Mapping[str, str],
) -> tuple[dict[str, object], Path, Path]:
    inventory = _runtime_inventory(python, workspace, environment)
    inventory_path = workspace / config.DESKTOP_RUNTIME_INVENTORY_FILE_NAME
    python_license = workspace / config.DESKTOP_PYTHON_RUNTIME_LICENSE_FILE_NAME
    python_license_source = Path(str(inventory.pop("python_license_source"))).resolve()
    _ = shutil.copyfile(python_license_source, python_license)
    inventory["python_runtime"] = {
        "license_file": config.DESKTOP_PYTHON_RUNTIME_LICENSE_FILE_NAME,
        "license_sha256": _file_sha256(python_license),
        "version": inventory.pop("python_version"),
    }
    _ = inventory_path.write_text(
        json.dumps(inventory, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
        newline="\n",
    )
    return inventory, inventory_path, python_license


def create_deterministic_zip(bundle: Path, destination: Path) -> None:
    """Write one sorted, timestamp-normalized ZIP without following links."""
    if not bundle.is_dir():
        msg = f"Bundle directory does not exist: {bundle}"
        raise WindowsPackageBuildError(msg)
    files: list[Path] = []
    for path in sorted(bundle.rglob("*"), key=lambda candidate: candidate.relative_to(bundle).as_posix()):
        if path.is_symlink():
            msg = f"Bundle contains a symbolic link: {path}"
            raise WindowsPackageBuildError(msg)
        if path.is_file():
            files.append(path)
    if not files:
        msg = "Bundle directory does not contain any files."
        raise WindowsPackageBuildError(msg)
    destination.parent.mkdir(parents=True, exist_ok=True)
    try:
        with zipfile.ZipFile(
            destination,
            mode="w",
            compression=zipfile.ZIP_DEFLATED,
            compresslevel=config.DESKTOP_ARCHIVE_COMPRESSION_LEVEL,
            strict_timestamps=True,
        ) as archive:
            for source in files:
                member = Path(config.DESKTOP_APPLICATION_NAME) / source.relative_to(bundle)
                info = zipfile.ZipInfo(member.as_posix(), date_time=config.DESKTOP_ARCHIVE_TIMESTAMP)
                info.compress_type = zipfile.ZIP_DEFLATED
                info.create_system = 3
                permissions = 0o100755 if source.name == config.DESKTOP_WINDOWS_EXECUTABLE_NAME else 0o100644
                info.external_attr = permissions << 16
                info.flag_bits = 0
                with source.open("rb") as input_stream, archive.open(info, mode="w", force_zip64=True) as output_stream:
                    shutil.copyfileobj(input_stream, output_stream, length=config.DESKTOP_ARCHIVE_IO_CHUNK_BYTES)
    except OSError as exc:
        msg = f"Unable to create deterministic Windows archive {destination}: {exc}"
        raise WindowsPackageBuildError(msg) from exc


def require_windows_x64(platform_name: str, machine_name: str, pointer_bytes: int) -> None:
    if platform_name != config.DESKTOP_WINDOWS_PLATFORM_NAME:
        msg = f"Windows desktop packages must be built on Windows, got {platform_name!r}."
        raise WindowsPackageBuildError(msg)
    if machine_name.casefold() not in config.DESKTOP_WINDOWS_MACHINE_NAMES:
        msg = f"Windows desktop packages require x86_64, got {machine_name!r}."
        raise WindowsPackageBuildError(msg)
    if pointer_bytes != config.DESKTOP_WINDOWS_POINTER_BYTES:
        msg = f"Windows desktop packages require a 64-bit interpreter, got {pointer_bytes} bytes."
        raise WindowsPackageBuildError(msg)


def _require_external_workspace(workspace: Path, project_root: Path) -> None:
    if workspace == project_root or workspace.is_relative_to(project_root):
        msg = f"The isolated build workspace must be outside the source checkout: {workspace}"
        raise WindowsPackageBuildError(msg)


def _probe_installed_wheel(
    python: Path,
    workspace: Path,
    environment: Mapping[str, str],
) -> InstalledWheelProbe:
    result = subprocess.run(  # noqa: S603 -- fixed isolated interpreter probes only its installed wheel.
        (str(python), "-I", "-c", _INSTALL_PROBE_SOURCE),
        cwd=workspace,
        env=dict(environment),
        capture_output=True,
        text=True,
        encoding="utf-8",
        check=False,
    )
    if result.returncode != 0:
        detail = result.stderr.strip() or result.stdout.strip() or "no diagnostic output"
        msg = f"Unable to probe the isolated wheel install: {detail}"
        raise WindowsPackageBuildError(msg)
    try:
        payload = cast("object", json.loads(result.stdout))
    except json.JSONDecodeError as exc:
        msg = "The isolated wheel probe returned invalid JSON."
        raise WindowsPackageBuildError(msg) from exc
    if not isinstance(payload, dict):
        msg = "The isolated wheel probe did not return an object."
        raise WindowsPackageBuildError(msg)
    values = cast("dict[str, object]", payload)
    return InstalledWheelProbe(
        entry_origin=Path(str(values.get("entry_origin", ""))).resolve(),
        package_root=Path(str(values.get("package_root", ""))).resolve(),
        purelib=Path(str(values.get("purelib", ""))).resolve(),
        version=str(values.get("version", "")),
    )


def _validate_installed_probe(
    probe: InstalledWheelProbe,
    virtual_environment: Path,
    project_root: Path,
    expected_version: str,
) -> None:
    virtual_environment = virtual_environment.resolve()
    if not probe.purelib.is_relative_to(virtual_environment):
        msg = f"Isolated purelib escaped the build venv: {probe.purelib}"
        raise WindowsPackageBuildError(msg)
    if not probe.package_root.is_relative_to(probe.purelib):
        msg = f"OMYM2 package did not resolve from isolated site-packages: {probe.package_root}"
        raise WindowsPackageBuildError(msg)
    if not probe.entry_origin.is_relative_to(probe.package_root):
        msg = f"Desktop entry point escaped the installed OMYM2 package: {probe.entry_origin}"
        raise WindowsPackageBuildError(msg)
    if probe.package_root.is_relative_to(project_root) or probe.entry_origin.is_relative_to(project_root):
        msg = "The isolated wheel probe resolved OMYM2 from the source checkout."
        raise WindowsPackageBuildError(msg)
    if probe.version != expected_version:
        msg = f"Installed wheel version {probe.version!r} does not match audited metadata {expected_version!r}."
        raise WindowsPackageBuildError(msg)


def _isolated_environment(workspace: Path) -> dict[str, str]:
    environment = os.environ.copy()
    for name in ("PYTHONHOME", "PYTHONPATH", "VIRTUAL_ENV"):
        _ = environment.pop(name, None)
    environment.update(
        {
            "PYINSTALLER_CONFIG_DIR": str(workspace / "pyinstaller-cache"),
            "PYTHONHASHSEED": "0",
            "PYTHONNOUSERSITE": "1",
            "PYTHONSAFEPATH": "1",
            "SOURCE_DATE_EPOCH": config.DESKTOP_PYINSTALLER_SOURCE_DATE_EPOCH,
        }
    )
    return environment


def _validate_locked_requirements(
    requirements: Path,
    project_root: Path,
    *,
    required: Sequence[str],
    forbidden: Sequence[str],
) -> None:
    try:
        content = requirements.read_text(encoding="utf-8")
    except OSError as exc:
        msg = f"Unable to read locked Windows requirements: {exc}"
        raise WindowsPackageBuildError(msg) from exc
    lowered = content.casefold()
    missing = [requirement for requirement in required if requirement not in lowered]
    if missing:
        msg = f"Locked Windows requirements are missing build inputs: {missing}"
        raise WindowsPackageBuildError(msg)
    source_inputs = (str(project_root).casefold(), "-e ", "omym2 @ file:")
    if present := [value for value in source_inputs if value in lowered]:
        msg = f"Locked Windows requirements contain source-checkout inputs: {present}"
        raise WindowsPackageBuildError(msg)
    if present := [value for value in forbidden if value in lowered]:
        msg = f"Locked Windows requirements contain forbidden build inputs: {present}"
        raise WindowsPackageBuildError(msg)


def _runtime_inventory(python: Path, workspace: Path, environment: Mapping[str, str]) -> dict[str, object]:
    result = subprocess.run(  # noqa: S603 -- fixed isolated interpreter reads installed distribution metadata.
        (str(python), "-I", "-c", _RUNTIME_INVENTORY_PROBE_SOURCE),
        cwd=workspace,
        env=dict(environment),
        capture_output=True,
        text=True,
        encoding="utf-8",
        check=False,
    )
    if result.returncode != 0:
        detail = result.stderr.strip() or result.stdout.strip() or "no diagnostic output"
        msg = f"Unable to record the runtime distribution inventory: {detail}"
        raise WindowsPackageBuildError(msg)
    try:
        payload = cast("object", json.loads(result.stdout))
    except json.JSONDecodeError as exc:
        msg = "Runtime distribution inventory returned invalid JSON."
        raise WindowsPackageBuildError(msg) from exc
    if not isinstance(payload, dict):
        msg = "Runtime distribution inventory must be a JSON object."
        raise WindowsPackageBuildError(msg)
    raw_inventory = cast("dict[str, object]", payload)
    entries = raw_inventory.get("distributions")
    python_license_source = raw_inventory.get("python_license_source")
    python_version = raw_inventory.get("python_version")
    if (
        not isinstance(entries, list)
        or not isinstance(python_license_source, str)
        or not isinstance(python_version, str)
    ):
        msg = "Runtime distribution inventory has invalid Python runtime fields."
        raise WindowsPackageBuildError(msg)
    distribution_entries: list[dict[str, object]] = []
    for raw_entry in cast("list[object]", entries):
        if not isinstance(raw_entry, dict):
            msg = "Runtime distribution inventory contains a non-object entry."
            raise WindowsPackageBuildError(msg)
        distribution_entries.append(cast("dict[str, object]", raw_entry))
    project_entries = [entry for entry in distribution_entries if entry.get("name") == "omym2"]
    third_party = [entry for entry in distribution_entries if entry.get("name") != "omym2"]
    if len(project_entries) != 1:
        msg = "Runtime distribution inventory must contain OMYM2 exactly once."
        raise WindowsPackageBuildError(msg)
    mutagen = [entry for entry in third_party if str(entry.get("name", "")).casefold() == "mutagen"]
    mutagen_license_files = mutagen[0].get("license_files") if len(mutagen) == 1 else None
    if not isinstance(mutagen_license_files, list) or not any(
        str(path).casefold().endswith("/copying") for path in cast("list[object]", mutagen_license_files)
    ):
        msg = "Runtime distribution inventory does not expose Mutagen's COPYING file."
        raise WindowsPackageBuildError(msg)
    return {
        "project": project_entries[0],
        "project_license": "unresolved",
        "python_license_source": python_license_source,
        "python_version": python_version,
        "third_party": third_party,
    }


def _installed_inventory(
    python: Path,
    workspace: Path,
    environment: Mapping[str, str],
    wheel_path: Path,
) -> list[str]:
    result = subprocess.run(  # noqa: S603 -- fixed uv command reads the isolated venv inventory.
        (_uv_executable(), "pip", "freeze", "--no-config", "--python", str(python)),
        cwd=workspace,
        env=dict(environment),
        capture_output=True,
        text=True,
        encoding="utf-8",
        check=False,
    )
    if result.returncode != 0:
        detail = result.stderr.strip() or result.stdout.strip() or "no diagnostic output"
        msg = f"Unable to record the isolated package inventory: {detail}"
        raise WindowsPackageBuildError(msg)
    inventory = sorted(line.strip() for line in result.stdout.splitlines() if line.strip())
    omym2_lines = [line for line in inventory if line.casefold().startswith("omym2 @ ")]
    if len(omym2_lines) != 1:
        msg = "The isolated package inventory must contain one direct OMYM2 wheel URL."
        raise WindowsPackageBuildError(msg)
    wheel_url = omym2_lines[0].partition(" @ ")[2]
    parsed_url = urlsplit(wheel_url)
    if parsed_url.scheme != "file":
        msg = "The isolated OMYM2 inventory entry is not a local audited wheel URL."
        raise WindowsPackageBuildError(msg)
    installed_wheel = Path(url2pathname(parsed_url.path)).resolve()
    if installed_wheel != wheel_path.resolve():
        msg = f"The isolated OMYM2 inventory points to {installed_wheel}, not audited wheel {wheel_path.resolve()}."
        raise WindowsPackageBuildError(msg)
    return inventory


def _read_provenance(path: Path) -> dict[str, object]:
    try:
        payload = cast("object", json.loads(path.read_text(encoding="utf-8")))
    except (OSError, json.JSONDecodeError) as exc:
        msg = f"Unable to read PyInstaller provenance {path}: {exc}"
        raise WindowsPackageBuildError(msg) from exc
    values = cast("dict[str, object]", payload)
    _ = validate_freeze_provenance(values)
    return values


def _venv_python(virtual_environment: Path) -> Path:
    return virtual_environment / "Scripts" / "python.exe"


def _uv_executable() -> str:
    executable = shutil.which("uv")
    if executable is None:
        msg = "The uv executable is required for Windows desktop packaging."
        raise WindowsPackageBuildError(msg)
    return executable


def _run(command: Sequence[str], *, cwd: Path, environment: Mapping[str, str]) -> None:
    result = subprocess.run(  # noqa: S603 -- argv is fixed build tooling plus validated local paths.
        tuple(command),
        cwd=cwd,
        env=dict(environment),
        check=False,
    )
    if result.returncode != 0:
        msg = f"Command failed with exit code {result.returncode}: {' '.join(command)}"
        raise WindowsPackageBuildError(msg)


def _copy_atomically(source: Path, destination: Path) -> None:
    temporary = destination.with_name(f".{destination.name}.tmp")
    try:
        _ = shutil.copyfile(source, temporary)
        _ = temporary.replace(destination)
    except OSError as exc:
        temporary.unlink(missing_ok=True)
        msg = f"Unable to write artifact {destination}: {exc}"
        raise WindowsPackageBuildError(msg) from exc


def _write_text_atomically(destination: Path, content: str) -> None:
    temporary = destination.with_name(f".{destination.name}.tmp")
    try:
        _ = temporary.write_text(content, encoding="utf-8", newline="\n")
        _ = temporary.replace(destination)
    except OSError as exc:
        temporary.unlink(missing_ok=True)
        msg = f"Unable to write artifact evidence {destination}: {exc}"
        raise WindowsPackageBuildError(msg) from exc


def _file_sha256(path: Path) -> str:
    with path.open("rb") as stream:
        return hashlib.file_digest(stream, "sha256").hexdigest()


def _project_root() -> Path:
    for parent in Path(__file__).resolve().parents:
        if (parent / "pyproject.toml").is_file():
            return parent
    msg = "Unable to locate the project root."
    raise WindowsPackageBuildError(msg)


def _parse_args(argv: Sequence[str] | None) -> ParsedArgs:
    default_output = _project_root() / config.DESKTOP_WINDOWS_DEFAULT_OUTPUT_RELATIVE_PATH
    parser = argparse.ArgumentParser(description=__doc__)
    _ = parser.add_argument("--wheel", type=Path, required=True)
    _ = parser.add_argument("--output-directory", type=Path, default=default_output)
    return parser.parse_args(argv, namespace=ParsedArgs(default_output))


def main(argv: Sequence[str] | None = None) -> int:
    """Build one Windows x64 package and report its three release artifacts."""
    args = _parse_args(argv)
    try:
        outputs = build_windows_package(args.wheel, args.output_directory)
    except (WindowsPackageBuildError, WindowsPackageAuditError) as exc:
        print(f"Windows package build failed: {exc}", file=sys.stderr)
        return 1
    print(
        json.dumps(
            {
                "archive": str(outputs.archive),
                "checksum": str(outputs.checksum),
                "evidence": str(outputs.evidence),
            },
            sort_keys=True,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
