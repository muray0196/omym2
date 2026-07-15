"""
Summary: Audits a frozen Windows desktop archive against its exact audited wheel inputs.
Why: Blocks unsafe paths, missing resources, unwanted runtimes, and wrong PE identity.
"""
# ruff: noqa: T201 -- Standalone audit tooling is directly executable and reports concise results.

from __future__ import annotations

import argparse
import ast
import hashlib
import json
import re
import shutil
import stat
import struct
import subprocess
import sys
import tempfile
import zipfile
from dataclasses import dataclass
from email.parser import BytesParser
from email.policy import default
from pathlib import Path, PurePosixPath
from typing import TYPE_CHECKING, cast

if __package__:
    from scripts import config
else:
    sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
    from scripts import config  # Direct script execution needs the repository script namespace.

if TYPE_CHECKING:
    from collections.abc import Callable, Mapping, Sequence
    from email.message import Message

_PNG_SIGNATURE = b"\x89PNG\r\n\x1a\n"
_PNG_IHDR_CHUNK_TYPE = b"IHDR"
_ICO_HEADER_BYTES = 6
_ICO_DIRECTORY_ENTRY_BYTES = 16
_ICO_BITS_PER_PIXEL = 32
_ICO_MINIMUM_PNG_BYTES = 24
_PNG_IHDR_DATA_BYTES = 13
_DIST_INFO_MEMBER_PARTS = 2
_WINDOWS_VERSION_PARTS = 4
_WINDOWS_VERSION_COMPONENT_MAX = 65_535
_DOS_PE_POINTER_OFFSET = 0x3C
_PE_SIGNATURE = b"PE\x00\x00"
_PE_COFF_HEADER_BYTES = 20
_PE_MACHINE_X86_64 = 0x8664
_PE32_PLUS_MAGIC = 0x20B
_PE_OPTIONAL_SUBSYSTEM_OFFSET = 68
_PE_WINDOWS_GUI_SUBSYSTEM = 2
_VERSION_TUPLE_PATTERN = re.compile(r"(?P<name>filevers|prodvers)\s*=\s*\((?P<values>[^)]*)\)")
_VERSION_STRING_PATTERN = re.compile(
    r"StringStruct\(\s*['\"](?P<name>[^'\"]+)['\"]\s*,\s*['\"](?P<value>[^'\"]*)['\"]\s*\)"
)
_WINDOWS_VERSION_STRING_NAMES = (
    "CompanyName",
    "FileDescription",
    "FileVersion",
    "InternalName",
    "LegalCopyright",
    "OriginalFilename",
    "ProductName",
    "ProductVersion",
)
_SAFE_VERSION_PATTERN = re.compile(r"[A-Za-z0-9](?:[A-Za-z0-9._+-]*[A-Za-z0-9])?")
_WINDOWS_METADATA_SCRIPT = r"""
param([string]$ExecutablePath, [string]$ExpectedIconDirectory)
$ErrorActionPreference = 'Stop'
Add-Type -AssemblyName System.Drawing
$version = (Get-Item -LiteralPath $ExecutablePath).VersionInfo
$executableIcon = [System.Drawing.Icon]::ExtractAssociatedIcon($ExecutablePath)
if ($null -eq $executableIcon) { throw 'The executable has no associated icon.' }
$executableBitmap = $executableIcon.ToBitmap()
$expectedIconPath = Join-Path $ExpectedIconDirectory "$($executableBitmap.Width).png"
if (-not (Test-Path -LiteralPath $expectedIconPath -PathType Leaf)) {
  throw "The committed icon has no $($executableBitmap.Width)-pixel PNG entry."
}
$sourceBitmap = [System.Drawing.Bitmap]::new($expectedIconPath)
$iconMatches = $executableBitmap.Width -eq $sourceBitmap.Width -and $executableBitmap.Height -eq $sourceBitmap.Height
if ($iconMatches) {
  for ($x = 0; $x -lt $executableBitmap.Width -and $iconMatches; $x++) {
    for ($y = 0; $y -lt $executableBitmap.Height; $y++) {
      if ($executableBitmap.GetPixel($x, $y).ToArgb() -ne $sourceBitmap.GetPixel($x, $y).ToArgb()) {
        $iconMatches = $false
        break
      }
    }
  }
}
$payload = [ordered]@{
  CompanyName = $version.CompanyName
  FileDescription = $version.FileDescription
  FileVersion = $version.FileVersion
  InternalName = $version.InternalName
  LegalCopyright = $version.LegalCopyright
  OriginalFilename = $version.OriginalFilename
  ProductName = $version.ProductName
  ProductVersion = $version.ProductVersion
  icon_matches = $iconMatches
  icon_width = $executableBitmap.Width
  icon_height = $executableBitmap.Height
}
$executableBitmap.Dispose()
$sourceBitmap.Dispose()
$executableIcon.Dispose()
$payload | ConvertTo-Json -Compress
"""


class WindowsPackageAuditError(RuntimeError):
    """Raised when a Windows desktop artifact violates its package contract."""


@dataclass(frozen=True, slots=True)
class WindowsExecutableMetadata:
    """Observed Windows version strings and icon identity for one executable."""

    strings: Mapping[str, str]
    icon_matches: bool
    icon_width: int
    icon_height: int


@dataclass(frozen=True, slots=True)
class WheelContract:
    """Auditable package version and immutable wheel resource digests."""

    version: str
    sha256: str
    resource_digests: Mapping[PurePosixPath, str]


@dataclass(frozen=True, slots=True)
class WindowsPackageAudit:
    """Evidence returned after the complete Windows archive audit passes."""

    artifact_sha256: str
    artifact_payload_sha256: str
    artifact_size_bytes: int
    archive_file_count: int
    package_version: str
    pe_machine: str
    pe_subsystem: str
    runtime_distribution_count: int
    runtime_license_file_count: int
    wheel_sha256: str
    verified_resource_count: int
    webview_dll_count: int
    webview_modules: tuple[str, ...]


@dataclass(frozen=True, slots=True)
class ParsedVersionInfo:
    """Expected PE version values parsed without executing the resource file."""

    numeric_versions: Mapping[str, tuple[int, int, int, int]]
    strings: Mapping[str, str]


class ParsedArgs(argparse.Namespace):
    """Typed command-line arguments for Windows archive auditing."""

    def __init__(self, *, icon: Path, version_info: Path) -> None:
        super().__init__()
        self.archive: Path = Path()
        self.wheel: Path = Path()
        self.icon: Path = icon
        self.version_info: Path = version_info


type ExecutableMetadataReader = Callable[[Path, Path], WindowsExecutableMetadata]


def audit_windows_package(
    archive_path: Path,
    wheel_path: Path,
    icon_path: Path,
    version_info_path: Path,
    *,
    metadata_reader: ExecutableMetadataReader | None = None,
) -> WindowsPackageAudit:
    """Require one safe, complete, x64-native Windows archive built from the wheel."""
    wheel_contract = read_wheel_contract(wheel_path)
    expected_archive_name = windows_archive_name(wheel_contract.version)
    if archive_path.name != expected_archive_name:
        msg = f"Windows archive must be named {expected_archive_name}, got {archive_path.name}."
        raise WindowsPackageAuditError(msg)
    icon_sizes = read_windows_icon_sizes(icon_path)
    if icon_sizes != config.DESKTOP_WINDOWS_ICON_SIZES:
        msg = f"Windows icon sizes differ: expected={config.DESKTOP_WINDOWS_ICON_SIZES}, actual={icon_sizes}"
        raise WindowsPackageAuditError(msg)
    version_info = read_version_info(version_info_path)
    _require_version_info_matches_package(version_info, wheel_contract.version)

    reader = read_windows_executable_metadata if metadata_reader is None else metadata_reader
    try:
        with zipfile.ZipFile(archive_path) as archive:
            members = _safe_zip_members(archive, label="Windows archive")
            executable_member = _audit_archive_members(members, wheel_contract)
            _audit_wheel_resources(archive, members, wheel_contract)
            executable_metadata = _read_embedded_executable_metadata(
                archive,
                executable_member,
                icon_path,
                reader,
            )
            webview_modules = _audit_freeze_provenance(archive, members, wheel_contract.sha256)
            runtime_distribution_count, runtime_license_file_count = _audit_runtime_inventory(
                archive,
                members,
                wheel_contract.version,
            )
            artifact_payload_sha256 = _canonical_archive_payload_sha256(archive, members)
    except (OSError, zipfile.BadZipFile) as exc:
        msg = f"Unable to read Windows archive {archive_path}: {exc}"
        raise WindowsPackageAuditError(msg) from exc

    _require_executable_metadata(executable_metadata, version_info)
    webview_dll_count = sum(
        1
        for member in members
        if "/webview/lib/" in f"/{member.as_posix().lower()}" and member.suffix.lower() == ".dll"
    )
    return WindowsPackageAudit(
        artifact_sha256=_file_sha256(archive_path),
        artifact_payload_sha256=artifact_payload_sha256,
        artifact_size_bytes=archive_path.stat().st_size,
        archive_file_count=sum(not info.is_dir() for info in members.values()),
        package_version=wheel_contract.version,
        pe_machine="x86_64",
        pe_subsystem="windows_gui",
        runtime_distribution_count=runtime_distribution_count,
        runtime_license_file_count=runtime_license_file_count,
        wheel_sha256=wheel_contract.sha256,
        verified_resource_count=len(wheel_contract.resource_digests),
        webview_dll_count=webview_dll_count,
        webview_modules=webview_modules,
    )


def validate_freeze_provenance(
    payload: object,
    *,
    expected_wheel_sha256: str | None = None,
) -> tuple[str, ...]:
    """Validate and return the exact pywebview modules recorded by PyInstaller."""
    if not isinstance(payload, dict):
        msg = "PyInstaller provenance must be a JSON object."
        raise WindowsPackageAuditError(msg)
    values = cast("dict[str, object]", payload)
    expected = {
        "builtin_imports": sorted(config.DESKTOP_PYINSTALLER_REQUIRED_BUILTIN_MODULES),
        "console": False,
        "contents_directory": config.DESKTOP_PYINSTALLER_CONTENTS_DIRECTORY_NAME,
        "excluded_webview_modules": sorted(
            module for module in config.DESKTOP_PYINSTALLER_EXCLUDED_MODULES if module.startswith("webview.")
        ),
        "format": "onedir",
        "hidden_imports": sorted(config.DESKTOP_PYINSTALLER_HIDDEN_IMPORTS),
        "runtime_hook_policy": config.DESKTOP_PYINSTALLER_RUNTIME_HOOK_POLICY,
        "source_imports": "isolated-wheel-only",
    }
    mismatches = {
        name: values.get(name) for name, expected_value in expected.items() if values.get(name) != expected_value
    }
    if mismatches:
        msg = f"PyInstaller provenance differs from the build contract: {mismatches}"
        raise WindowsPackageAuditError(msg)
    wheel_sha256 = values.get("wheel_sha256")
    if (
        not isinstance(wheel_sha256, str)
        or len(wheel_sha256) != hashlib.sha256().digest_size * 2
        or any(character not in "0123456789abcdef" for character in wheel_sha256)
    ):
        msg = "PyInstaller provenance has no valid audited-wheel SHA-256."
        raise WindowsPackageAuditError(msg)
    if expected_wheel_sha256 is not None and wheel_sha256 != expected_wheel_sha256:
        msg = "Bundled PyInstaller provenance does not match the supplied audited wheel SHA-256."
        raise WindowsPackageAuditError(msg)
    module_count = values.get("omym2_module_count")
    if not isinstance(module_count, int) or isinstance(module_count, bool) or module_count <= 0:
        msg = "PyInstaller provenance has no verified OMYM2 modules."
        raise WindowsPackageAuditError(msg)
    raw_webview_modules = values.get("webview_modules")
    if not isinstance(raw_webview_modules, list):
        msg = "PyInstaller provenance has no auditable pywebview module manifest."
        raise WindowsPackageAuditError(msg)
    raw_modules = cast("list[object]", raw_webview_modules)
    if not all(isinstance(module, str) for module in raw_modules):
        msg = "PyInstaller provenance has no auditable pywebview module manifest."
        raise WindowsPackageAuditError(msg)
    webview_modules = cast("list[str]", raw_modules)
    if webview_modules != sorted(set(webview_modules)):
        msg = "PyInstaller provenance pywebview modules must be sorted and unique."
        raise WindowsPackageAuditError(msg)
    observed_modules = set(webview_modules)
    missing_modules = set(config.DESKTOP_PYINSTALLER_REQUIRED_WEBVIEW_MODULES) - observed_modules
    forbidden_modules = {
        module
        for module in observed_modules
        if any(
            module == excluded_module or module.startswith(f"{excluded_module}.")
            for excluded_module in config.DESKTOP_PYINSTALLER_EXCLUDED_MODULES
            if excluded_module.startswith("webview.")
        )
    }
    if missing_modules or forbidden_modules:
        msg = (
            "PyInstaller provenance violates the Windows pywebview module policy: "
            f"missing={sorted(missing_modules)}, forbidden={sorted(forbidden_modules)}"
        )
        raise WindowsPackageAuditError(msg)
    return tuple(webview_modules)


def read_wheel_contract(wheel_path: Path) -> WheelContract:
    """Read OMYM2's version and frozen resource hashes from one safe wheel."""
    if not wheel_path.is_file():
        msg = f"Audited wheel does not exist: {wheel_path}"
        raise WindowsPackageAuditError(msg)
    try:
        with zipfile.ZipFile(wheel_path) as wheel:
            members = _safe_zip_members(wheel, label="Wheel")
            metadata_path, metadata = _find_omym2_metadata(wheel, members)
            version = metadata.get("Version", "").strip()
            _require_safe_version(version)
            resources: dict[PurePosixPath, str] = {}
            static_prefix = PurePosixPath("omym2/adapters/web/static_dist")
            migration_prefix = PurePosixPath("omym2/adapters/db/sqlite/migrations")
            for member, info in members.items():
                if info.is_dir():
                    continue
                if (
                    member == metadata_path
                    or member.is_relative_to(static_prefix)
                    or (member.is_relative_to(migration_prefix) and member.suffix.lower() == ".sql")
                ):
                    resources[member] = _zip_member_sha256(wheel, info)
    except (OSError, zipfile.BadZipFile) as exc:
        msg = f"Unable to read audited wheel {wheel_path}: {exc}"
        raise WindowsPackageAuditError(msg) from exc

    if static_prefix / "index.html" not in resources:
        msg = "Audited wheel is missing omym2/adapters/web/static_dist/index.html."
        raise WindowsPackageAuditError(msg)
    if not any(member.is_relative_to(migration_prefix) and member.suffix == ".sql" for member in resources):
        msg = "Audited wheel does not contain SQLite migration SQL."
        raise WindowsPackageAuditError(msg)
    return WheelContract(
        version=version,
        sha256=_file_sha256(wheel_path),
        resource_digests=resources,
    )


def windows_archive_name(version: str) -> str:
    """Return the one accepted deterministic Windows release artifact name."""
    _require_safe_version(version)
    return f"{config.DESKTOP_APPLICATION_NAME}-{version}-{config.DESKTOP_WINDOWS_ARTIFACT_TAG}.zip"


def extract_windows_archive(archive_path: Path, destination: Path) -> Path:
    """Safely extract the audited single-root Windows archive without path traversal."""
    if destination.exists() and any(destination.iterdir()):
        msg = f"Windows extraction destination is not empty: {destination}"
        raise WindowsPackageAuditError(msg)
    destination.mkdir(parents=True, exist_ok=True)
    try:
        with zipfile.ZipFile(archive_path) as archive:
            members = _safe_zip_members(archive, label="Windows archive")
            for member, info in sorted(members.items(), key=lambda item: item[0].as_posix()):
                target = destination.joinpath(*member.parts)
                if info.is_dir():
                    target.mkdir(parents=True, exist_ok=True)
                    continue
                target.parent.mkdir(parents=True, exist_ok=True)
                with archive.open(info) as input_stream, target.open("wb") as output_stream:
                    shutil.copyfileobj(input_stream, output_stream, length=config.DESKTOP_ARCHIVE_IO_CHUNK_BYTES)
    except (OSError, zipfile.BadZipFile) as exc:
        msg = f"Unable to extract Windows archive {archive_path}: {exc}"
        raise WindowsPackageAuditError(msg) from exc
    return destination / config.DESKTOP_APPLICATION_NAME


def read_windows_icon_sizes(icon_path: Path) -> tuple[int, ...]:
    """Validate the committed PNG-backed ICO and return its ordered image sizes."""
    return tuple(size for size, _image in _read_windows_icon_images(icon_path))


def _read_windows_icon_images(icon_path: Path) -> tuple[tuple[int, bytes], ...]:
    """Validate and return every committed ICO size with its exact PNG payload."""
    try:
        payload = icon_path.read_bytes()
    except OSError as exc:
        msg = f"Unable to read Windows icon {icon_path}: {exc}"
        raise WindowsPackageAuditError(msg) from exc
    if len(payload) < _ICO_HEADER_BYTES:
        msg_0 = "Windows icon is truncated before its directory header."
        raise WindowsPackageAuditError(msg_0)
    reserved, image_type, image_count = cast("tuple[int, int, int]", struct.unpack_from("<HHH", payload))
    if reserved != 0 or image_type != 1 or image_count == 0:
        msg_0 = "Windows icon has an invalid ICO directory header."
        raise WindowsPackageAuditError(msg_0)
    directory_end = _ICO_HEADER_BYTES + image_count * _ICO_DIRECTORY_ENTRY_BYTES
    if directory_end > len(payload):
        msg_0 = "Windows icon is truncated inside its image directory."
        raise WindowsPackageAuditError(msg_0)

    images: list[tuple[int, bytes]] = []
    occupied_ranges: list[tuple[int, int]] = []
    for index in range(image_count):
        width, offset, image_end = _read_icon_entry(payload, index, directory_end, occupied_ranges)
        images.append((width, payload[offset:image_end]))
        occupied_ranges.append((offset, image_end))
    return tuple(images)


def _read_icon_entry(
    payload: bytes,
    index: int,
    directory_end: int,
    occupied_ranges: Sequence[tuple[int, int]],
) -> tuple[int, int, int]:
    entry_offset = _ICO_HEADER_BYTES + index * _ICO_DIRECTORY_ENTRY_BYTES
    width_byte, height_byte, color_count, entry_reserved, planes, bit_count, size, offset = cast(
        "tuple[int, int, int, int, int, int, int, int]",
        struct.unpack_from("<BBBBHHII", payload, entry_offset),
    )
    width = 256 if width_byte == 0 else width_byte
    height = 256 if height_byte == 0 else height_byte
    if width != height or color_count != 0 or entry_reserved != 0 or planes != 1 or bit_count != _ICO_BITS_PER_PIXEL:
        msg = f"Windows icon entry {index} has invalid dimensions or color metadata."
        raise WindowsPackageAuditError(msg)
    image_end = offset + size
    if offset < directory_end or size < _ICO_MINIMUM_PNG_BYTES or image_end > len(payload):
        msg = f"Windows icon entry {index} has invalid image bounds."
        raise WindowsPackageAuditError(msg)
    if any(offset < prior_end and prior_start < image_end for prior_start, prior_end in occupied_ranges):
        msg = f"Windows icon entry {index} overlaps another image."
        raise WindowsPackageAuditError(msg)
    if payload[offset : offset + len(_PNG_SIGNATURE)] != _PNG_SIGNATURE:
        msg = f"Windows icon entry {index} is not PNG-backed."
        raise WindowsPackageAuditError(msg)
    chunk_length = cast("tuple[int]", struct.unpack_from(">I", payload, offset + len(_PNG_SIGNATURE)))[0]
    chunk_type = payload[offset + 12 : offset + 16]
    png_width, png_height = cast("tuple[int, int]", struct.unpack_from(">II", payload, offset + 16))
    if (
        chunk_length != _PNG_IHDR_DATA_BYTES
        or chunk_type != _PNG_IHDR_CHUNK_TYPE
        or (png_width, png_height) != (width, height)
    ):
        msg = f"Windows icon entry {index} PNG dimensions do not match its ICO directory."
        raise WindowsPackageAuditError(msg)
    return width, offset, image_end


def read_version_info(version_info_path: Path) -> ParsedVersionInfo:
    """Parse required committed Windows metadata without evaluating Python-like text."""
    try:
        source = version_info_path.read_text(encoding="utf-8")
    except OSError as exc:
        msg = f"Unable to read Windows version metadata {version_info_path}: {exc}"
        raise WindowsPackageAuditError(msg) from exc
    try:
        _ = ast.parse(source, filename=str(version_info_path), mode="eval")
    except SyntaxError as exc:
        msg = "Windows version metadata must be one PyInstaller-compatible expression."
        raise WindowsPackageAuditError(msg) from exc
    numeric_versions: dict[str, tuple[int, int, int, int]] = {}
    for match in _VERSION_TUPLE_PATTERN.finditer(source):
        raw_values = tuple(part.strip() for part in match.group("values").split(",") if part.strip())
        if len(raw_values) != _WINDOWS_VERSION_PARTS or any(not value.isdecimal() for value in raw_values):
            msg = f"Windows version tuple {match.group('name')} must contain four decimal values."
            raise WindowsPackageAuditError(msg)
        numeric_versions[match.group("name")] = cast("tuple[int, int, int, int]", tuple(map(int, raw_values)))
    strings = {match.group("name"): match.group("value") for match in _VERSION_STRING_PATTERN.finditer(source)}
    required_numeric = {"filevers", "prodvers"}
    required_strings = set(_WINDOWS_VERSION_STRING_NAMES)
    if missing := sorted(required_numeric - numeric_versions.keys()):
        msg_0 = f"Windows version metadata is missing numeric fields: {missing}"
        raise WindowsPackageAuditError(msg_0)
    if missing := sorted(required_strings - strings.keys()):
        msg_0 = f"Windows version metadata is missing string fields: {missing}"
        raise WindowsPackageAuditError(msg_0)
    return ParsedVersionInfo(numeric_versions=numeric_versions, strings=strings)


def read_windows_executable_metadata(executable: Path, icon: Path) -> WindowsExecutableMetadata:
    """Read actual PE version strings and compare the associated icon through Windows APIs."""
    with tempfile.TemporaryDirectory(prefix="omym2-icon-audit-") as temporary_directory:
        expected_icon_directory = Path(temporary_directory)
        for size, image in _read_windows_icon_images(icon):
            expected_image = expected_icon_directory / f"{size}.png"
            if expected_image.exists():
                msg = f"Windows icon contains duplicate {size}-pixel entries."
                raise WindowsPackageAuditError(msg)
            _ = expected_image.write_bytes(image)
        result = subprocess.run(  # noqa: S603 -- fixed PowerShell program audits local build artifacts only.
            (
                config.DESKTOP_WINDOWS_POWERSHELL_EXECUTABLE_NAME,
                "-NoLogo",
                "-NoProfile",
                "-NonInteractive",
                "-Command",
                f"& {{\n{_WINDOWS_METADATA_SCRIPT}\n}}",
                str(executable),
                str(expected_icon_directory),
            ),
            capture_output=True,
            text=True,
            encoding="utf-8",
            check=False,
            timeout=config.DESKTOP_WINDOWS_METADATA_TIMEOUT_SECONDS,
        )
    if result.returncode != 0:
        detail = result.stderr.strip() or result.stdout.strip() or "no diagnostic output"
        msg = f"Unable to inspect Windows executable metadata: {detail}"
        raise WindowsPackageAuditError(msg)
    try:
        payload = cast("object", json.loads(result.stdout))
    except json.JSONDecodeError as exc:
        msg = "Windows executable metadata inspection returned invalid JSON."
        raise WindowsPackageAuditError(msg) from exc
    if not isinstance(payload, dict):
        msg_0 = "Windows executable metadata inspection did not return an object."
        raise WindowsPackageAuditError(msg_0)
    values = cast("dict[str, object]", payload)
    strings = {name: str(values.get(name, "")).strip() for name in _WINDOWS_VERSION_STRING_NAMES}
    return WindowsExecutableMetadata(
        strings=strings,
        icon_matches=values.get("icon_matches") is True,
        icon_width=_required_positive_int(values.get("icon_width"), "icon_width"),
        icon_height=_required_positive_int(values.get("icon_height"), "icon_height"),
    )


def _safe_zip_members(archive: zipfile.ZipFile, *, label: str) -> dict[PurePosixPath, zipfile.ZipInfo]:
    members: dict[PurePosixPath, zipfile.ZipInfo] = {}
    casefolded: dict[str, PurePosixPath] = {}
    for info in archive.infolist():
        member = _safe_member_path(info.filename, label=label)
        if member in members:
            msg = f"{label} contains a duplicate member: {member.as_posix()}"
            raise WindowsPackageAuditError(msg)
        folded = member.as_posix().casefold()
        if prior := casefolded.get(folded):
            msg = f"{label} contains Windows-colliding members: {prior.as_posix()} and {member.as_posix()}"
            raise WindowsPackageAuditError(msg)
        if stat.S_ISLNK(info.external_attr >> 16):
            msg = f"{label} contains a symbolic link: {member.as_posix()}"
            raise WindowsPackageAuditError(msg)
        if info.flag_bits & 0x1:
            msg = f"{label} contains an encrypted member: {member.as_posix()}"
            raise WindowsPackageAuditError(msg)
        members[member] = info
        casefolded[folded] = member
    return members


def _safe_member_path(raw_path: str, *, label: str) -> PurePosixPath:
    path = PurePosixPath(raw_path)
    if (
        path.is_absolute()
        or not path.parts
        or ".." in path.parts
        or "." in path.parts
        or "\\" in raw_path
        or "\x00" in raw_path
        or path.parts[0].endswith(":")
    ):
        msg = f"{label} contains an unsafe member path: {raw_path}"
        raise WindowsPackageAuditError(msg)
    return path


def _find_omym2_metadata(
    wheel: zipfile.ZipFile,
    members: Mapping[PurePosixPath, zipfile.ZipInfo],
) -> tuple[PurePosixPath, Message]:
    matches: list[tuple[PurePosixPath, Message]] = []
    for member, info in members.items():
        if info.is_dir() or len(member.parts) != _DIST_INFO_MEMBER_PARTS or not member.parts[0].endswith(".dist-info"):
            continue
        if member.name != "METADATA":
            continue
        metadata = BytesParser(policy=default).parsebytes(wheel.read(info))
        if metadata.get("Name", "").strip().casefold() == "omym2":
            matches.append((member, metadata))
    if len(matches) != 1:
        msg = f"Wheel must contain exactly one OMYM2 METADATA file, found {len(matches)}."
        raise WindowsPackageAuditError(msg)
    return matches[0]


def _audit_archive_members(
    members: Mapping[PurePosixPath, zipfile.ZipInfo],
    wheel_contract: WheelContract,
) -> PurePosixPath:
    root = PurePosixPath(config.DESKTOP_APPLICATION_NAME)
    executable = root / config.DESKTOP_WINDOWS_EXECUTABLE_NAME
    if executable not in members or members[executable].is_dir():
        msg = f"Windows archive is missing {executable.as_posix()}."
        raise WindowsPackageAuditError(msg)
    support_root = root / config.DESKTOP_PYINSTALLER_CONTENTS_DIRECTORY_NAME
    if not members:
        msg = "Windows archive is empty."
        raise WindowsPackageAuditError(msg)
    for member, info in members.items():
        _audit_archive_member(member, info, root, support_root)
    _require_collected_archive_components(members, wheel_contract, support_root)
    return executable


def _audit_archive_member(
    member: PurePosixPath,
    info: zipfile.ZipInfo,
    root: PurePosixPath,
    support_root: PurePosixPath,
) -> None:
    if member.parts[0] != root.name:
        msg = f"Windows archive member escapes the {root.name}/ root: {member.as_posix()}"
        raise WindowsPackageAuditError(msg)
    if info.is_dir():
        return
    lowered = member.as_posix().casefold()
    basename = member.name.casefold()
    if basename in config.DESKTOP_WINDOWS_FORBIDDEN_ARCHIVE_BASENAMES:
        msg = f"Windows archive bundles a forbidden runtime: {member.as_posix()}"
        raise WindowsPackageAuditError(msg)
    if any(fragment in lowered for fragment in config.DESKTOP_WINDOWS_FORBIDDEN_ARCHIVE_FRAGMENTS):
        msg = f"Windows archive bundles a forbidden framework: {member.as_posix()}"
        raise WindowsPackageAuditError(msg)
    if any(part.casefold() in config.DESKTOP_WINDOWS_SOURCE_TREE_MEMBER_NAMES for part in member.parts):
        msg = f"Windows archive contains source-tree content: {member.as_posix()}"
        raise WindowsPackageAuditError(msg)
    if member.is_relative_to(support_root / "omym2") and member.suffix.casefold() in {".py", ".pyc"}:
        msg = f"Windows archive contains unpacked OMYM2 source code: {member.as_posix()}"
        raise WindowsPackageAuditError(msg)
    if any(fragment in f"/{lowered}" for fragment in config.DESKTOP_WINDOWS_FORBIDDEN_WEBVIEW_RESOURCES):
        msg = f"Windows archive contains a prohibited WebView resource: {member.as_posix()}"
        raise WindowsPackageAuditError(msg)


def _require_collected_archive_components(
    members: Mapping[PurePosixPath, zipfile.ZipInfo],
    wheel_contract: WheelContract,
    support_root: PurePosixPath,
) -> None:
    expected_metadata = [
        support_root / member
        for member in wheel_contract.resource_digests
        if member.name == "METADATA" and member.parent.name.endswith(".dist-info")
    ]
    if len(expected_metadata) != 1 or expected_metadata[0] not in members:
        msg = "Windows archive is missing the OMYM2 distribution metadata."
        raise WindowsPackageAuditError(msg)
    static_index_suffix = PurePosixPath("omym2/adapters/web/static_dist/index.html")
    static_indexes = [member for member in members if member.is_relative_to(support_root)]
    static_indexes = [member for member in static_indexes if PurePosixPath(*member.parts[-5:]) == static_index_suffix]
    if len(static_indexes) != 1:
        msg = f"Windows archive must contain one static_dist/index.html, found {len(static_indexes)}."
        raise WindowsPackageAuditError(msg)
    expected_webview_dlls = {
        support_root / PurePosixPath(relative_path)
        for relative_path in config.DESKTOP_WINDOWS_REQUIRED_WEBVIEW_DLL_RELATIVE_PATHS
    }
    observed_webview_dlls = {
        member
        for member in members
        if member.is_relative_to(support_root / "webview" / "lib") and member.suffix.casefold() == ".dll"
    }
    if observed_webview_dlls != expected_webview_dlls:
        missing = sorted(member.as_posix() for member in expected_webview_dlls - observed_webview_dlls)
        unexpected = sorted(member.as_posix() for member in observed_webview_dlls - expected_webview_dlls)
        msg = f"Windows archive WebView2 DLL payload differs: missing={missing}, unexpected={unexpected}"
        raise WindowsPackageAuditError(msg)


def _audit_wheel_resources(
    archive: zipfile.ZipFile,
    members: Mapping[PurePosixPath, zipfile.ZipInfo],
    wheel_contract: WheelContract,
) -> None:
    resource_root = PurePosixPath(
        config.DESKTOP_APPLICATION_NAME,
        config.DESKTOP_PYINSTALLER_CONTENTS_DIRECTORY_NAME,
    )
    for wheel_member, expected_digest in wheel_contract.resource_digests.items():
        archive_member = resource_root / wheel_member
        info = members.get(archive_member)
        if info is None or info.is_dir():
            msg = f"Windows archive is missing wheel resource: {wheel_member.as_posix()}"
            raise WindowsPackageAuditError(msg)
        actual_digest = _zip_member_sha256(archive, info)
        if actual_digest != expected_digest:
            msg = f"Windows archive resource differs from the wheel: {wheel_member.as_posix()}"
            raise WindowsPackageAuditError(msg)


def _audit_freeze_provenance(
    archive: zipfile.ZipFile,
    members: Mapping[PurePosixPath, zipfile.ZipInfo],
    expected_wheel_sha256: str,
) -> tuple[str, ...]:
    support_root = PurePosixPath(
        config.DESKTOP_APPLICATION_NAME,
        config.DESKTOP_PYINSTALLER_CONTENTS_DIRECTORY_NAME,
    )
    provenance_member = support_root / config.DESKTOP_PYINSTALLER_PROVENANCE_FILE_NAME
    provenance_info = members.get(provenance_member)
    if provenance_info is None or provenance_info.is_dir():
        msg = "Windows archive is missing its PyInstaller provenance manifest."
        raise WindowsPackageAuditError(msg)
    try:
        payload = cast("object", json.loads(archive.read(provenance_info)))
    except json.JSONDecodeError as exc:
        msg = "Bundled PyInstaller provenance manifest is not valid JSON."
        raise WindowsPackageAuditError(msg) from exc
    return validate_freeze_provenance(payload, expected_wheel_sha256=expected_wheel_sha256)


def _audit_runtime_inventory(
    archive: zipfile.ZipFile,
    members: Mapping[PurePosixPath, zipfile.ZipInfo],
    package_version: str,
) -> tuple[int, int]:
    support_root = PurePosixPath(
        config.DESKTOP_APPLICATION_NAME,
        config.DESKTOP_PYINSTALLER_CONTENTS_DIRECTORY_NAME,
    )
    inventory = _read_runtime_inventory(archive, members, support_root)
    if inventory.get("project_license") != "unresolved":
        msg = "Runtime inventory must not claim an unresolved OMYM2 project license."
        raise WindowsPackageAuditError(msg)
    _audit_python_runtime_license(archive, members, support_root, inventory)
    _audit_inventory_project(inventory, package_version)
    raw_third_party = inventory.get("third_party")
    if not isinstance(raw_third_party, list) or not raw_third_party:
        msg = "Runtime inventory does not contain third-party distributions."
        raise WindowsPackageAuditError(msg)
    third_party = cast("list[object]", raw_third_party)

    seen_names: set[str] = set()
    license_count = 0
    mutagen_copying_found = False
    for raw_entry in third_party:
        entry_license_count, entry_is_mutagen = _audit_inventory_distribution(
            archive,
            members,
            support_root,
            raw_entry,
            seen_names,
        )
        entry = cast("dict[str, object]", raw_entry)
        folded_name = str(entry["name"]).casefold()
        seen_names.add(folded_name)
        license_count += entry_license_count
        mutagen_copying_found = mutagen_copying_found or entry_is_mutagen
    if not mutagen_copying_found:
        msg = "Windows archive must include Mutagen's dist-info COPYING license file."
        raise WindowsPackageAuditError(msg)
    return len(third_party), license_count


def _read_runtime_inventory(
    archive: zipfile.ZipFile,
    members: Mapping[PurePosixPath, zipfile.ZipInfo],
    support_root: PurePosixPath,
) -> dict[str, object]:
    inventory_member = support_root / config.DESKTOP_RUNTIME_INVENTORY_FILE_NAME
    inventory_info = members.get(inventory_member)
    if inventory_info is None or inventory_info.is_dir():
        msg = "Windows archive is missing its third-party runtime inventory."
        raise WindowsPackageAuditError(msg)
    try:
        payload = cast("object", json.loads(archive.read(inventory_info)))
    except json.JSONDecodeError as exc:
        msg = "Bundled third-party runtime inventory is not valid JSON."
        raise WindowsPackageAuditError(msg) from exc
    if not isinstance(payload, dict):
        msg = "Bundled third-party runtime inventory must be a JSON object."
        raise WindowsPackageAuditError(msg)
    return cast("dict[str, object]", payload)


def _audit_python_runtime_license(
    archive: zipfile.ZipFile,
    members: Mapping[PurePosixPath, zipfile.ZipInfo],
    support_root: PurePosixPath,
    inventory: Mapping[str, object],
) -> None:
    python_runtime = inventory.get("python_runtime")
    if not isinstance(python_runtime, dict):
        msg = "Runtime inventory is missing the frozen CPython license record."
        raise WindowsPackageAuditError(msg)
    python_runtime = cast("dict[str, object]", python_runtime)
    python_license_digest = python_runtime.get("license_sha256")
    valid_runtime = (
        python_runtime.get("license_file") == config.DESKTOP_PYTHON_RUNTIME_LICENSE_FILE_NAME
        and isinstance(python_license_digest, str)
        and len(python_license_digest) == hashlib.sha256().digest_size * 2
        and isinstance(python_runtime.get("version"), str)
        and bool(python_runtime.get("version"))
    )
    if not valid_runtime:
        msg = "Runtime inventory has invalid frozen CPython license fields."
        raise WindowsPackageAuditError(msg)
    python_license_member = support_root / config.DESKTOP_PYTHON_RUNTIME_LICENSE_FILE_NAME
    python_license_info = members.get(python_license_member)
    if python_license_info is None or python_license_info.is_dir():
        msg = "Windows archive is missing the frozen CPython LICENSE.txt."
        raise WindowsPackageAuditError(msg)
    if _zip_member_sha256(archive, python_license_info) != python_license_digest:
        msg = "Bundled CPython LICENSE.txt differs from the runtime inventory."
        raise WindowsPackageAuditError(msg)


def _audit_inventory_project(inventory: Mapping[str, object], package_version: str) -> None:
    project = inventory.get("project")
    if not isinstance(project, dict):
        msg = "Runtime inventory is missing its OMYM2 project record."
        raise WindowsPackageAuditError(msg)
    project = cast("dict[str, object]", project)
    if str(project.get("name", "")).casefold() != "omym2" or project.get("version") != package_version:
        msg = "Runtime inventory project record differs from wheel metadata."
        raise WindowsPackageAuditError(msg)


def _audit_inventory_distribution(
    archive: zipfile.ZipFile,
    members: Mapping[PurePosixPath, zipfile.ZipInfo],
    support_root: PurePosixPath,
    raw_entry: object,
    seen_names: set[str],
) -> tuple[int, bool]:
    if not isinstance(raw_entry, dict):
        msg = "Runtime inventory contains a non-object distribution record."
        raise WindowsPackageAuditError(msg)
    entry = cast("dict[str, object]", raw_entry)
    name = str(entry.get("name", "")).strip()
    version = str(entry.get("version", "")).strip()
    folded_name = name.casefold()
    if not name or not version or folded_name in seen_names:
        msg = f"Runtime inventory contains an invalid or duplicate distribution: {name!r}"
        raise WindowsPackageAuditError(msg)
    metadata_path = _inventory_member_path(str(entry.get("metadata_directory", "")), expected_metadata_directory=True)
    metadata_member = support_root / metadata_path / "METADATA"
    metadata_info = members.get(metadata_member)
    if metadata_info is None or metadata_info.is_dir():
        msg = f"Runtime metadata is missing for {name}=={version}."
        raise WindowsPackageAuditError(msg)
    metadata = BytesParser(policy=default).parsebytes(archive.read(metadata_info))
    if metadata.get("Name", "").strip().casefold() != folded_name or metadata.get("Version", "").strip() != version:
        msg = f"Bundled runtime metadata differs for {name}=={version}."
        raise WindowsPackageAuditError(msg)
    license_files = entry.get("license_files")
    if not isinstance(license_files, list):
        msg = f"Runtime license inventory is invalid for {name}=={version}."
        raise WindowsPackageAuditError(msg)
    return _audit_inventory_license_files(
        members,
        support_root,
        metadata_path,
        cast("list[object]", license_files),
        name,
    )


def _audit_inventory_license_files(
    members: Mapping[PurePosixPath, zipfile.ZipInfo],
    support_root: PurePosixPath,
    metadata_path: PurePosixPath,
    license_files: Sequence[object],
    distribution_name: str,
) -> tuple[int, bool]:
    mutagen_copying_found = False
    for raw_license in license_files:
        license_path = _inventory_member_path(str(raw_license), expected_metadata_directory=False)
        if not license_path.is_relative_to(metadata_path):
            msg = f"Runtime license path escapes metadata for {distribution_name}: {license_path}"
            raise WindowsPackageAuditError(msg)
        license_member = support_root / license_path
        license_info = members.get(license_member)
        if license_info is None or license_info.is_dir():
            msg = f"Runtime license file is missing for {distribution_name}: {license_path}"
            raise WindowsPackageAuditError(msg)
        if distribution_name.casefold() == "mutagen" and license_path.name.casefold() == "copying":
            mutagen_copying_found = True
    return len(license_files), mutagen_copying_found


def _inventory_member_path(raw_path: str, *, expected_metadata_directory: bool) -> PurePosixPath:
    path = _safe_member_path(raw_path, label="Runtime inventory")
    if expected_metadata_directory:
        if len(path.parts) != 1 or not path.name.casefold().endswith(".dist-info"):
            msg = f"Runtime inventory has an invalid metadata directory: {raw_path}"
            raise WindowsPackageAuditError(msg)
    elif len(path.parts) < _DIST_INFO_MEMBER_PARTS or not path.parts[0].casefold().endswith(".dist-info"):
        msg = f"Runtime inventory has an invalid license path: {raw_path}"
        raise WindowsPackageAuditError(msg)
    return path


def _read_embedded_executable_metadata(
    archive: zipfile.ZipFile,
    executable_member: PurePosixPath,
    icon_path: Path,
    reader: ExecutableMetadataReader,
) -> WindowsExecutableMetadata:
    executable_bytes = archive.read(executable_member.as_posix())
    _require_x64_gui_pe(executable_bytes)
    with tempfile.TemporaryDirectory(prefix="omym2-pe-audit-") as temporary_directory:
        executable = Path(temporary_directory) / config.DESKTOP_WINDOWS_EXECUTABLE_NAME
        _ = executable.write_bytes(executable_bytes)
        return reader(executable, icon_path)


def _require_x64_gui_pe(executable: bytes) -> None:
    minimum_dos_bytes = _DOS_PE_POINTER_OFFSET + struct.calcsize("<I")
    if len(executable) < minimum_dos_bytes or not executable.startswith(b"MZ"):
        msg = "Packaged executable does not have a complete PE DOS header."
        raise WindowsPackageAuditError(msg)
    pe_offset = cast("tuple[int]", struct.unpack_from("<I", executable, _DOS_PE_POINTER_OFFSET))[0]
    optional_header_offset = pe_offset + len(_PE_SIGNATURE) + _PE_COFF_HEADER_BYTES
    subsystem_offset = optional_header_offset + _PE_OPTIONAL_SUBSYSTEM_OFFSET
    if subsystem_offset + struct.calcsize("<H") > len(executable):
        msg = "Packaged executable has a truncated PE header."
        raise WindowsPackageAuditError(msg)
    if executable[pe_offset : pe_offset + len(_PE_SIGNATURE)] != _PE_SIGNATURE:
        msg = "Packaged executable does not have a valid PE signature."
        raise WindowsPackageAuditError(msg)
    machine = cast("tuple[int]", struct.unpack_from("<H", executable, pe_offset + len(_PE_SIGNATURE)))[0]
    if machine != _PE_MACHINE_X86_64:
        msg = f"Packaged executable is not PE x86_64: machine=0x{machine:04x}"
        raise WindowsPackageAuditError(msg)
    optional_magic = cast("tuple[int]", struct.unpack_from("<H", executable, optional_header_offset))[0]
    if optional_magic != _PE32_PLUS_MAGIC:
        msg = f"Packaged executable is not PE32+: magic=0x{optional_magic:04x}"
        raise WindowsPackageAuditError(msg)
    subsystem = cast("tuple[int]", struct.unpack_from("<H", executable, subsystem_offset))[0]
    if subsystem != _PE_WINDOWS_GUI_SUBSYSTEM:
        msg = f"Packaged executable is not a no-console Windows GUI: subsystem={subsystem}"
        raise WindowsPackageAuditError(msg)


def _require_version_info_matches_package(version_info: ParsedVersionInfo, version: str) -> None:
    product_version = version_info.strings["ProductVersion"]
    if product_version != version:
        msg = f"Committed ProductVersion {product_version!r} does not match wheel version {version!r}."
        raise WindowsPackageAuditError(msg)
    numeric_version = _numeric_version(version)
    if version_info.numeric_versions["prodvers"] != numeric_version:
        msg = "Committed prodvers does not match the wheel version."
        raise WindowsPackageAuditError(msg)
    if version_info.numeric_versions["filevers"] != numeric_version:
        msg = "Committed filevers does not match the wheel version."
        raise WindowsPackageAuditError(msg)


def _require_executable_metadata(actual: WindowsExecutableMetadata, expected: ParsedVersionInfo) -> None:
    mismatches = {
        name: {"expected": expected.strings[name], "actual": actual.strings.get(name, "")}
        for name in expected.strings
        if actual.strings.get(name, "") != expected.strings[name]
    }
    if mismatches:
        msg = f"Windows executable version metadata differs: {mismatches}"
        raise WindowsPackageAuditError(msg)
    if not actual.icon_matches:
        msg = "Windows executable icon does not match the committed icon."
        raise WindowsPackageAuditError(msg)
    if actual.icon_width <= 0 or actual.icon_height <= 0:
        msg = "Windows executable icon has invalid dimensions."
        raise WindowsPackageAuditError(msg)


def _numeric_version(version: str) -> tuple[int, int, int, int]:
    parts = version.split(".")
    if len(parts) > _WINDOWS_VERSION_PARTS or any(not part.isdecimal() for part in parts):
        msg = f"Windows PE metadata requires a one-to-four-part numeric package version, got {version!r}."
        raise WindowsPackageAuditError(msg)
    values = tuple(map(int, parts)) + (0,) * (_WINDOWS_VERSION_PARTS - len(parts))
    if any(value > _WINDOWS_VERSION_COMPONENT_MAX for value in values):
        msg_0 = "Windows PE numeric version components must be <= 65535."
        raise WindowsPackageAuditError(msg_0)
    return cast("tuple[int, int, int, int]", values)


def _require_safe_version(version: str) -> None:
    if not _SAFE_VERSION_PATTERN.fullmatch(version) or ".." in version:
        msg = f"Package version is unsafe for a Windows artifact name: {version!r}"
        raise WindowsPackageAuditError(msg)


def _zip_member_sha256(archive: zipfile.ZipFile, info: zipfile.ZipInfo) -> str:
    digest = hashlib.sha256()
    with archive.open(info) as stream:
        while chunk := stream.read(config.DESKTOP_ARCHIVE_IO_CHUNK_BYTES):
            digest.update(chunk)
    return digest.hexdigest()


def _canonical_archive_payload_sha256(
    archive: zipfile.ZipFile,
    members: Mapping[PurePosixPath, zipfile.ZipInfo],
) -> str:
    """Hash member paths and uncompressed bytes independently of ZIP container metadata."""
    manifest = [
        (member.as_posix(), info.file_size, _zip_member_sha256(archive, info))
        for member, info in sorted(members.items(), key=lambda item: item[0].as_posix())
        if not info.is_dir()
    ]
    payload = json.dumps(manifest, ensure_ascii=True, separators=(",", ":")).encode()
    return hashlib.sha256(payload).hexdigest()


def _file_sha256(path: Path) -> str:
    try:
        with path.open("rb") as stream:
            return hashlib.file_digest(stream, "sha256").hexdigest()
    except OSError as exc:
        msg = f"Unable to hash file {path}: {exc}"
        raise WindowsPackageAuditError(msg) from exc


def _required_positive_int(value: object, field_name: str) -> int:
    if not isinstance(value, int) or isinstance(value, bool) or value <= 0:
        msg = f"Windows executable metadata field {field_name} is not a positive integer."
        raise WindowsPackageAuditError(msg)
    return value


def _project_root() -> Path:
    for parent in Path(__file__).resolve().parents:
        if (parent / "pyproject.toml").is_file():
            return parent
    msg = "Unable to locate the project root."
    raise WindowsPackageAuditError(msg)


def _parse_args(argv: Sequence[str] | None) -> ParsedArgs:
    root = _project_root()
    default_icon = root / config.DESKTOP_WINDOWS_ICON_RELATIVE_PATH
    default_version = root / config.DESKTOP_WINDOWS_VERSION_RELATIVE_PATH
    parser = argparse.ArgumentParser(description=__doc__)
    _ = parser.add_argument("--archive", type=Path, required=True)
    _ = parser.add_argument("--wheel", type=Path, required=True)
    _ = parser.add_argument("--icon", type=Path, default=default_icon)
    _ = parser.add_argument("--version-info", type=Path, default=default_version)
    return parser.parse_args(argv, namespace=ParsedArgs(icon=default_icon, version_info=default_version))


def main(argv: Sequence[str] | None = None) -> int:
    """Audit one Windows package and report a concise result."""
    args = _parse_args(argv)
    try:
        audit = audit_windows_package(args.archive, args.wheel, args.icon, args.version_info)
    except WindowsPackageAuditError as exc:
        print(f"Windows package audit failed: {exc}", file=sys.stderr)
        return 1
    print(
        f"Windows package audit passed: {args.archive} sha256={audit.artifact_sha256} resources={audit.verified_resource_count}"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
