"""
Summary: Audits, prepares, and verifies final and rollback release artifacts.
Why: Preserves same-version rollback packages without invalid distribution renaming.
"""
# ruff: noqa: INP001, T201 -- Standalone release tooling reports concise CLI results.

from __future__ import annotations

import argparse
import base64
import csv
import hashlib
import io
import json
import os
import re
import shutil
import stat
import subprocess
import sys
import tarfile
import tempfile
import zipfile
from dataclasses import dataclass
from email import policy
from email.parser import BytesParser
from pathlib import Path, PurePosixPath
from typing import TYPE_CHECKING, cast

from audit_web_packages import PackageAuditError, audit_packages

if TYPE_CHECKING:
    from collections.abc import Mapping, Sequence
    from email.message import Message

PROJECT_NAME = "omym2"
PROJECT_VERSION = "0.1.0"
WHEEL_FILE_NAME = "omym2-0.1.0-py3-none-any.whl"
SDIST_FILE_NAME = "omym2-0.1.0.tar.gz"
WHEEL_DIST_INFO_DIRECTORY_NAME = "omym2-0.1.0.dist-info"
WHEEL_METADATA_MEMBER_NAME = f"{WHEEL_DIST_INFO_DIRECTORY_NAME}/METADATA"
WHEEL_DESCRIPTOR_MEMBER_NAME = f"{WHEEL_DIST_INFO_DIRECTORY_NAME}/WHEEL"
WHEEL_RECORD_MEMBER_NAME = f"{WHEEL_DIST_INFO_DIRECTORY_NAME}/RECORD"
WHEEL_FORMAT_VERSION = "1.0"
WHEEL_PURELIB_VALUE = "true"
WHEEL_TAG = "py3-none-any"
ROOT_CHECKSUM_FILE_NAME = "omym2-0.1.0-SHA256SUMS"
ROOT_PROVENANCE_FILE_NAME = "omym2-0.1.0-provenance.json"
ROLLBACK_DIRECTORY_NAME = "rollback"
ROLLBACK_README_FILE_NAME = "README.md"
ROLLBACK_CHECKSUM_FILE_NAME = "SHA256SUMS"
ROLLBACK_PROVENANCE_FILE_NAME = "provenance.json"
PROVENANCE_SCHEMA_VERSION = 1
COMMIT_LENGTH = 40
ROLLBACK_COMMIT_DISPLAY_LENGTH = 7
CSV_RECORD_FIELD_COUNT = 3
ZIP_TIMESTAMP = (1980, 1, 1, 0, 0, 0)
ZIP_FILE_MODE = stat.S_IFREG | 0o644
COMMIT_PATTERN = re.compile(r"[0-9a-f]{40}\Z")
SHA256_PATTERN = re.compile(r"[0-9a-f]{64}\Z")
NO_NODE_TOOL_NAMES = ("node", "npm", "npx")
WINDOWS_EXECUTABLE_DIRECTORY_NAME = "Scripts"
POSIX_EXECUTABLE_DIRECTORY_NAME = "bin"
WINDOWS_PYTHON_EXECUTABLE_NAME = "python.exe"
POSIX_PYTHON_EXECUTABLE_NAME = "python"
INSTALLED_PACKAGE_SMOKE = """
from importlib.metadata import version
from importlib.resources import files
import sys

project_name = sys.argv[1]
expected_version = sys.argv[2]
if version(project_name) != expected_version:
    raise SystemExit("installed distribution version differs")
index = files("omym2.adapters.web").joinpath("static_dist").joinpath("index.html")
if not index.is_file():
    raise SystemExit("installed distribution is missing static_dist/index.html")
"""


class ReleaseArtifactError(RuntimeError):
    """Raised when release evidence is incomplete, unsafe, or inconsistent."""


@dataclass(frozen=True, slots=True)
class ArtifactRecord:
    """Integrity metadata for one artifact."""

    name: str
    sha256: str
    size: int


@dataclass(frozen=True, slots=True)
class RollbackContents:
    """Verified members of the rollback package-set archive."""

    wheel: ArtifactRecord
    sdist: ArtifactRecord
    readme: ArtifactRecord


@dataclass(frozen=True, slots=True)
class ReleasePreparation:
    """Inputs required to assemble one final and rollback release set."""

    final_wheel: Path
    final_sdist: Path
    rollback_wheel: Path
    rollback_sdist: Path
    final_commit: str
    rollback_commit: str
    output_directory: Path


@dataclass(frozen=True, slots=True)
class ReleaseProvenance:
    """Records required to render root release provenance."""

    final_commit: str
    rollback_commit: str
    final_wheel: ArtifactRecord
    final_sdist: ArtifactRecord
    rollback_archive: ArtifactRecord
    rollback_contents: RollbackContents


class ParsedArgs(argparse.Namespace):
    """Typed command-line arguments for release artifact operations."""

    def __init__(self) -> None:
        super().__init__()
        self.command: str = ""
        self.wheel: Path = Path()
        self.sdist: Path = Path()
        self.expected_static: Path = Path()
        self.final_wheel: Path = Path()
        self.final_sdist: Path = Path()
        self.rollback_wheel: Path = Path()
        self.rollback_sdist: Path = Path()
        self.final_commit: str = ""
        self.rollback_commit: str = ""
        self.output_directory: Path = Path()
        self.input_directory: Path = Path()


def audit_package_set(wheel: Path, sdist: Path, expected_static: Path) -> None:
    """Audit, rebuild, and clean-install one wheel/sdist package set."""
    _validate_package_pair(wheel, sdist)
    audit_packages(wheel, sdist, expected_static)

    with tempfile.TemporaryDirectory(prefix="omym2-release-audit-") as temporary_directory:
        workspace = Path(temporary_directory)
        rebuilt_directory = workspace / "rebuilt-from-sdist"
        rebuilt_directory.mkdir()
        no_node_directory = workspace / "no-node"
        _write_no_node_shims(no_node_directory)
        environment = _node_poisoned_environment(no_node_directory)
        _run(
            ("uv", "build", "--wheel", str(sdist.resolve()), "--out-dir", str(rebuilt_directory)),
            cwd=workspace,
            environment=environment,
        )
        rebuilt_wheel = _one_artifact(rebuilt_directory, "*.whl", "sdist-derived wheel")
        _validate_package_pair(rebuilt_wheel, sdist)
        audit_packages(rebuilt_wheel, sdist, expected_static)
        _smoke_install(wheel, workspace / "direct-smoke", environment)
        _smoke_install(rebuilt_wheel, workspace / "rebuilt-smoke", environment)


def prepare_release_assets(preparation: ReleasePreparation) -> None:
    """Assemble verified final artifacts and an isolated rollback package set."""
    _validate_commit(preparation.final_commit, "final")
    _validate_commit(preparation.rollback_commit, "rollback")
    _validate_package_pair(preparation.final_wheel, preparation.final_sdist)
    _validate_package_pair(preparation.rollback_wheel, preparation.rollback_sdist)
    output_directory = preparation.output_directory.resolve()
    if output_directory.exists():
        msg = f"Release output already exists; refusing to overwrite it: {output_directory}"
        raise ReleaseArtifactError(msg)

    output_directory.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory(prefix="omym2-release-stage-", dir=output_directory.parent) as temporary_directory:
        staging_directory = Path(temporary_directory) / "assets"
        staging_directory.mkdir()
        staged_final_wheel = staging_directory / WHEEL_FILE_NAME
        staged_final_sdist = staging_directory / SDIST_FILE_NAME
        _ = shutil.copyfile(preparation.final_wheel, staged_final_wheel)
        _ = shutil.copyfile(preparation.final_sdist, staged_final_sdist)

        final_wheel_record = _artifact_record(staged_final_wheel)
        final_sdist_record = _artifact_record(staged_final_sdist)
        rollback_archive_name = _rollback_archive_name(preparation.rollback_commit)
        rollback_archive = staging_directory / rollback_archive_name
        rollback_contents = _write_rollback_archive(
            rollback_archive,
            preparation.rollback_wheel,
            preparation.rollback_sdist,
            preparation.rollback_commit,
        )
        rollback_archive_record = _artifact_record(rollback_archive)
        provenance = _root_provenance(
            ReleaseProvenance(
                final_commit=preparation.final_commit,
                rollback_commit=preparation.rollback_commit,
                final_wheel=final_wheel_record,
                final_sdist=final_sdist_record,
                rollback_archive=rollback_archive_record,
                rollback_contents=rollback_contents,
            )
        )
        provenance_path = staging_directory / ROOT_PROVENANCE_FILE_NAME
        _ = provenance_path.write_bytes(_json_bytes(provenance))
        provenance_record = _artifact_record(provenance_path)
        checksum_path = staging_directory / ROOT_CHECKSUM_FILE_NAME
        _ = checksum_path.write_bytes(
            _checksum_bytes(
                (
                    final_wheel_record,
                    final_sdist_record,
                    rollback_archive_record,
                    provenance_record,
                )
            )
        )

        verify_release_assets(
            staging_directory,
            final_commit=preparation.final_commit,
            rollback_commit=preparation.rollback_commit,
        )
        _ = staging_directory.replace(output_directory)


def verify_release_assets(input_directory: Path, *, final_commit: str, rollback_commit: str) -> None:
    """Verify downloaded release assets, nested packages, checksums, and provenance."""
    _validate_commit(final_commit, "final")
    _validate_commit(rollback_commit, "rollback")
    input_directory = input_directory.resolve()
    if not input_directory.is_dir():
        msg = f"Release asset directory does not exist: {input_directory}"
        raise ReleaseArtifactError(msg)

    rollback_archive_name = _rollback_archive_name(rollback_commit)
    expected_names = {
        WHEEL_FILE_NAME,
        SDIST_FILE_NAME,
        rollback_archive_name,
        ROOT_CHECKSUM_FILE_NAME,
        ROOT_PROVENANCE_FILE_NAME,
    }
    actual_entries = tuple(input_directory.iterdir())
    actual_names = {entry.name for entry in actual_entries}
    if actual_names != expected_names or any(not entry.is_file() for entry in actual_entries):
        msg = f"Release asset set differs: expected {sorted(expected_names)}, found {sorted(actual_names)}."
        raise ReleaseArtifactError(msg)

    final_wheel = input_directory / WHEEL_FILE_NAME
    final_sdist = input_directory / SDIST_FILE_NAME
    rollback_archive = input_directory / rollback_archive_name
    provenance_path = input_directory / ROOT_PROVENANCE_FILE_NAME
    checksum_path = input_directory / ROOT_CHECKSUM_FILE_NAME
    _validate_package_pair(final_wheel, final_sdist)
    rollback_contents = _verify_rollback_archive(rollback_archive, rollback_commit)

    final_wheel_record = _artifact_record(final_wheel)
    final_sdist_record = _artifact_record(final_sdist)
    rollback_archive_record = _artifact_record(rollback_archive)
    provenance_record = _artifact_record(provenance_path)
    expected_provenance = _root_provenance(
        ReleaseProvenance(
            final_commit=final_commit,
            rollback_commit=rollback_commit,
            final_wheel=final_wheel_record,
            final_sdist=final_sdist_record,
            rollback_archive=rollback_archive_record,
            rollback_contents=rollback_contents,
        )
    )
    actual_provenance = _load_json_object(provenance_path.read_bytes(), ROOT_PROVENANCE_FILE_NAME)
    if actual_provenance != expected_provenance:
        msg = "Release provenance differs from the verified artifacts and pinned commits."
        raise ReleaseArtifactError(msg)

    expected_checksums = _checksum_mapping(
        (final_wheel_record, final_sdist_record, rollback_archive_record, provenance_record)
    )
    actual_checksums = _load_checksums(checksum_path.read_bytes(), ROOT_CHECKSUM_FILE_NAME)
    if actual_checksums != expected_checksums:
        msg = "Release checksum manifest differs from the verified release assets."
        raise ReleaseArtifactError(msg)


def _write_rollback_archive(
    archive_path: Path,
    wheel: Path,
    sdist: Path,
    rollback_commit: str,
) -> RollbackContents:
    wheel_bytes = wheel.read_bytes()
    sdist_bytes = sdist.read_bytes()
    readme_bytes = _rollback_readme_bytes(rollback_commit)
    wheel_record = _artifact_record_bytes(WHEEL_FILE_NAME, wheel_bytes)
    sdist_record = _artifact_record_bytes(SDIST_FILE_NAME, sdist_bytes)
    readme_record = _artifact_record_bytes(ROLLBACK_README_FILE_NAME, readme_bytes)
    contents = RollbackContents(wheel=wheel_record, sdist=sdist_record, readme=readme_record)
    provenance_bytes = _json_bytes(_rollback_provenance(rollback_commit, contents))
    provenance_record = _artifact_record_bytes(ROLLBACK_PROVENANCE_FILE_NAME, provenance_bytes)
    checksum_bytes = _checksum_bytes((wheel_record, sdist_record, readme_record, provenance_record))
    members = (
        (f"{ROLLBACK_DIRECTORY_NAME}/{WHEEL_FILE_NAME}", wheel_bytes),
        (f"{ROLLBACK_DIRECTORY_NAME}/{SDIST_FILE_NAME}", sdist_bytes),
        (f"{ROLLBACK_DIRECTORY_NAME}/{ROLLBACK_README_FILE_NAME}", readme_bytes),
        (f"{ROLLBACK_DIRECTORY_NAME}/{ROLLBACK_CHECKSUM_FILE_NAME}", checksum_bytes),
        (f"{ROLLBACK_DIRECTORY_NAME}/{ROLLBACK_PROVENANCE_FILE_NAME}", provenance_bytes),
    )
    with zipfile.ZipFile(archive_path, mode="x", compression=zipfile.ZIP_STORED) as archive:
        for member_name, content in members:
            member = zipfile.ZipInfo(member_name, date_time=ZIP_TIMESTAMP)
            member.compress_type = zipfile.ZIP_STORED
            member.create_system = 3
            member.external_attr = ZIP_FILE_MODE << 16
            archive.writestr(member, content)
    return contents


def _verify_rollback_archive(archive_path: Path, rollback_commit: str) -> RollbackContents:
    expected_names = {
        f"{ROLLBACK_DIRECTORY_NAME}/{WHEEL_FILE_NAME}",
        f"{ROLLBACK_DIRECTORY_NAME}/{SDIST_FILE_NAME}",
        f"{ROLLBACK_DIRECTORY_NAME}/{ROLLBACK_README_FILE_NAME}",
        f"{ROLLBACK_DIRECTORY_NAME}/{ROLLBACK_CHECKSUM_FILE_NAME}",
        f"{ROLLBACK_DIRECTORY_NAME}/{ROLLBACK_PROVENANCE_FILE_NAME}",
    }
    try:
        with zipfile.ZipFile(archive_path) as archive:
            infos = tuple(archive.infolist())
            names = tuple(info.filename for info in infos)
            if len(names) != len(set(names)):
                msg = "Rollback archive contains duplicate member names."
                raise ReleaseArtifactError(msg)
            for info in infos:
                _validate_archive_member_path(info.filename, "rollback archive")
                mode = (info.external_attr >> 16) & 0xFFFF
                if info.is_dir() or (mode != 0 and not stat.S_ISREG(mode)):
                    msg = f"Rollback archive contains a non-regular member: {info.filename}"
                    raise ReleaseArtifactError(msg)
            if set(names) != expected_names:
                msg = f"Rollback archive members differ: expected {sorted(expected_names)}, found {sorted(names)}."
                raise ReleaseArtifactError(msg)
            invalid_member = archive.testzip()
            if invalid_member is not None:
                msg = f"Rollback archive CRC check failed: {invalid_member}"
                raise ReleaseArtifactError(msg)
            wheel_bytes = archive.read(f"{ROLLBACK_DIRECTORY_NAME}/{WHEEL_FILE_NAME}")
            sdist_bytes = archive.read(f"{ROLLBACK_DIRECTORY_NAME}/{SDIST_FILE_NAME}")
            readme_bytes = archive.read(f"{ROLLBACK_DIRECTORY_NAME}/{ROLLBACK_README_FILE_NAME}")
            checksum_bytes = archive.read(f"{ROLLBACK_DIRECTORY_NAME}/{ROLLBACK_CHECKSUM_FILE_NAME}")
            provenance_bytes = archive.read(f"{ROLLBACK_DIRECTORY_NAME}/{ROLLBACK_PROVENANCE_FILE_NAME}")
    except (OSError, zipfile.BadZipFile) as exc:
        msg = f"Unable to read rollback archive {archive_path}: {exc}"
        raise ReleaseArtifactError(msg) from exc

    _validate_wheel_bytes(WHEEL_FILE_NAME, wheel_bytes)
    _validate_sdist_bytes(SDIST_FILE_NAME, sdist_bytes)
    if readme_bytes != _rollback_readme_bytes(rollback_commit):
        msg = "Rollback README differs from the pinned commit and safety guidance."
        raise ReleaseArtifactError(msg)
    wheel_record = _artifact_record_bytes(WHEEL_FILE_NAME, wheel_bytes)
    sdist_record = _artifact_record_bytes(SDIST_FILE_NAME, sdist_bytes)
    readme_record = _artifact_record_bytes(ROLLBACK_README_FILE_NAME, readme_bytes)
    contents = RollbackContents(wheel=wheel_record, sdist=sdist_record, readme=readme_record)
    expected_provenance = _rollback_provenance(rollback_commit, contents)
    actual_provenance = _load_json_object(provenance_bytes, ROLLBACK_PROVENANCE_FILE_NAME)
    if actual_provenance != expected_provenance:
        msg = "Rollback provenance differs from the verified package set."
        raise ReleaseArtifactError(msg)
    provenance_record = _artifact_record_bytes(ROLLBACK_PROVENANCE_FILE_NAME, provenance_bytes)
    expected_checksums = _checksum_mapping((wheel_record, sdist_record, readme_record, provenance_record))
    actual_checksums = _load_checksums(checksum_bytes, ROLLBACK_CHECKSUM_FILE_NAME)
    if actual_checksums != expected_checksums:
        msg = "Rollback checksum manifest differs from the verified package set."
        raise ReleaseArtifactError(msg)
    return contents


def _validate_package_pair(wheel: Path, sdist: Path) -> None:
    if wheel.name != WHEEL_FILE_NAME:
        msg = f"Wheel must retain its standardized filename {WHEEL_FILE_NAME}: {wheel}"
        raise ReleaseArtifactError(msg)
    if sdist.name != SDIST_FILE_NAME:
        msg = f"Source distribution must retain its standardized filename {SDIST_FILE_NAME}: {sdist}"
        raise ReleaseArtifactError(msg)
    if not wheel.is_file() or not sdist.is_file():
        msg = f"Package pair is incomplete: {wheel} and {sdist}"
        raise ReleaseArtifactError(msg)
    _validate_wheel_bytes(wheel.name, wheel.read_bytes())
    _validate_sdist_bytes(sdist.name, sdist.read_bytes())


def _validate_wheel_bytes(file_name: str, content: bytes) -> None:
    if file_name != WHEEL_FILE_NAME:
        msg = f"Unexpected wheel filename: {file_name}"
        raise ReleaseArtifactError(msg)
    try:
        with zipfile.ZipFile(io.BytesIO(content)) as archive:
            names = _validated_wheel_member_names(archive)
            invalid_member = archive.testzip()
            if invalid_member is not None:
                msg = f"Wheel CRC check failed: {invalid_member}"
                raise ReleaseArtifactError(msg)
            metadata_names = tuple(name for name in names if name.endswith(".dist-info/METADATA"))
            descriptor_names = tuple(name for name in names if name.endswith(".dist-info/WHEEL"))
            record_names = tuple(name for name in names if name.endswith(".dist-info/RECORD"))
            if metadata_names != (WHEEL_METADATA_MEMBER_NAME,) or record_names != (WHEEL_RECORD_MEMBER_NAME,):
                msg = "Wheel must contain METADATA and RECORD in the exact omym2-0.1.0.dist-info directory."
                raise ReleaseArtifactError(msg)
            if WHEEL_DESCRIPTOR_MEMBER_NAME not in names:
                msg = "Wheel is missing omym2-0.1.0.dist-info/WHEEL."
                raise ReleaseArtifactError(msg)
            if descriptor_names != (WHEEL_DESCRIPTOR_MEMBER_NAME,):
                msg = "Wheel must contain exactly one WHEEL file in the omym2-0.1.0.dist-info directory."
                raise ReleaseArtifactError(msg)
            _validate_core_metadata(archive.read(WHEEL_METADATA_MEMBER_NAME), "wheel METADATA")
            _validate_wheel_descriptor(archive.read(WHEEL_DESCRIPTOR_MEMBER_NAME))
            _validate_wheel_record(archive, names, WHEEL_RECORD_MEMBER_NAME)
    except (OSError, zipfile.BadZipFile, UnicodeDecodeError, csv.Error) as exc:
        msg = f"Unable to validate wheel {file_name}: {exc}"
        raise ReleaseArtifactError(msg) from exc


def _validated_wheel_member_names(archive: zipfile.ZipFile) -> tuple[str, ...]:
    all_infos = tuple(archive.infolist())
    all_names = tuple(info.filename for info in all_infos)
    normalized_names = tuple(info.filename.removesuffix("/") if info.is_dir() else info.filename for info in all_infos)
    if len(all_names) != len(set(all_names)) or len(normalized_names) != len(set(normalized_names)):
        msg = "Wheel contains duplicate member names."
        raise ReleaseArtifactError(msg)
    for info in all_infos:
        _validate_zip_member_path(info, "wheel")
        mode = (info.external_attr >> 16) & 0xFFFF
        if info.is_dir():
            if mode != 0 and not stat.S_ISDIR(mode):
                msg = f"Wheel contains a non-directory member marked as a directory: {info.filename}"
                raise ReleaseArtifactError(msg)
            continue
        if mode != 0 and not stat.S_ISREG(mode):
            msg = f"Wheel contains a non-regular member: {info.filename}"
            raise ReleaseArtifactError(msg)
    return tuple(info.filename for info in all_infos if not info.is_dir())


def _validate_wheel_descriptor(content: bytes) -> None:
    descriptor = cast("Message[object, object]", BytesParser(policy=policy.default).parsebytes(content))
    wheel_versions = tuple(str(value) for value in descriptor.get_all("Wheel-Version", ()))
    purelib_values = tuple(str(value) for value in descriptor.get_all("Root-Is-Purelib", ()))
    tags = tuple(str(value) for value in descriptor.get_all("Tag", ()))
    if wheel_versions != (WHEEL_FORMAT_VERSION,):
        msg = f"Wheel descriptor must declare Wheel-Version: {WHEEL_FORMAT_VERSION}."
        raise ReleaseArtifactError(msg)
    if purelib_values != (WHEEL_PURELIB_VALUE,):
        msg = f"Wheel descriptor must declare Root-Is-Purelib: {WHEEL_PURELIB_VALUE}."
        raise ReleaseArtifactError(msg)
    if tags != (WHEEL_TAG,):
        msg = f"Wheel descriptor tag differs from its filename: expected {WHEEL_TAG}."
        raise ReleaseArtifactError(msg)


def _validate_wheel_record(archive: zipfile.ZipFile, member_names: Sequence[str], record_name: str) -> None:
    rows: dict[str, tuple[str, str]] = {}
    record_text = archive.read(record_name).decode("utf-8")
    for row in csv.reader(io.StringIO(record_text, newline="")):
        if len(row) != CSV_RECORD_FIELD_COUNT:
            msg = "Wheel RECORD contains a malformed row."
            raise ReleaseArtifactError(msg)
        name, digest, size = row
        if name in rows:
            msg = f"Wheel RECORD contains a duplicate path: {name}"
            raise ReleaseArtifactError(msg)
        rows[name] = (digest, size)
    if set(rows) != set(member_names):
        msg = "Wheel RECORD paths differ from archive members."
        raise ReleaseArtifactError(msg)
    for member_name in member_names:
        digest, size = rows[member_name]
        if member_name == record_name:
            if digest != "" or size != "":
                msg = "Wheel RECORD must leave its own hash and size empty."
                raise ReleaseArtifactError(msg)
            continue
        member_content = archive.read(member_name)
        encoded_digest = base64.urlsafe_b64encode(hashlib.sha256(member_content).digest()).rstrip(b"=").decode("ascii")
        if digest != f"sha256={encoded_digest}" or size != str(len(member_content)):
            msg = f"Wheel RECORD integrity differs for {member_name}."
            raise ReleaseArtifactError(msg)


def _validate_sdist_bytes(file_name: str, content: bytes) -> None:
    if file_name != SDIST_FILE_NAME:
        msg = f"Unexpected source-distribution filename: {file_name}"
        raise ReleaseArtifactError(msg)
    root_name = SDIST_FILE_NAME.removesuffix(".tar.gz")
    metadata_name = f"{root_name}/PKG-INFO"
    try:
        with tarfile.open(fileobj=io.BytesIO(content), mode="r:gz") as archive:
            members = tuple(archive.getmembers())
            names = tuple(member.name for member in members)
            if len(names) != len(set(names)):
                msg = "Source distribution contains duplicate member names."
                raise ReleaseArtifactError(msg)
            for member in members:
                _validate_archive_member_path(member.name, "source distribution")
                if member.name != root_name and not member.name.startswith(f"{root_name}/"):
                    msg = f"Source-distribution member escapes its root directory: {member.name}"
                    raise ReleaseArtifactError(msg)
                if not member.isdir() and not member.isreg():
                    msg = f"Source distribution contains a non-regular member: {member.name}"
                    raise ReleaseArtifactError(msg)
            metadata_member = archive.getmember(metadata_name)
            metadata_file = archive.extractfile(metadata_member)
            if metadata_file is None:
                msg = "Source distribution PKG-INFO is not a regular file."
                raise ReleaseArtifactError(msg)
            _validate_core_metadata(metadata_file.read(), "source distribution PKG-INFO")
    except (KeyError, OSError, tarfile.TarError, UnicodeDecodeError) as exc:
        msg = f"Unable to validate source distribution {file_name}: {exc}"
        raise ReleaseArtifactError(msg) from exc


def _validate_core_metadata(content: bytes, label: str) -> None:
    metadata = cast("Message[object, object]", BytesParser(policy=policy.default).parsebytes(content))
    names = tuple(str(value) for value in metadata.get_all("Name", ()))
    versions = tuple(str(value) for value in metadata.get_all("Version", ()))
    if names != (PROJECT_NAME,) or versions != (PROJECT_VERSION,):
        msg = (
            f"{label} identifies names={names!r} versions={versions!r}, "
            f"expected {(PROJECT_NAME,)!r} and {(PROJECT_VERSION,)!r}."
        )
        raise ReleaseArtifactError(msg)


def _validate_archive_member_path(member_name: str, label: str) -> None:
    if "\\" in member_name or "\x00" in member_name:
        msg = f"{label} contains an unsafe member path: {member_name!r}"
        raise ReleaseArtifactError(msg)
    path = PurePosixPath(member_name)
    parts = member_name.split("/")
    if path.is_absolute() or any(part in {"", ".", ".."} for part in parts) or parts[0].endswith(":"):
        msg = f"{label} contains an unsafe member path: {member_name!r}"
        raise ReleaseArtifactError(msg)


def _validate_zip_member_path(info: zipfile.ZipInfo, label: str) -> None:
    member_name = info.filename.removesuffix("/") if info.is_dir() else info.filename
    _validate_archive_member_path(member_name, label)


def _root_provenance(provenance: ReleaseProvenance) -> dict[str, object]:
    return {
        "schema_version": PROVENANCE_SCHEMA_VERSION,
        "project": PROJECT_NAME,
        "version": PROJECT_VERSION,
        "final": {
            "commit": provenance.final_commit,
            "wheel": _record_payload(provenance.final_wheel),
            "sdist": _record_payload(provenance.final_sdist),
        },
        "rollback": {
            "commit": provenance.rollback_commit,
            "archive": _record_payload(provenance.rollback_archive),
            "wheel": _record_payload(provenance.rollback_contents.wheel),
            "sdist": _record_payload(provenance.rollback_contents.sdist),
            "readme": _record_payload(provenance.rollback_contents.readme),
        },
    }


def _rollback_provenance(rollback_commit: str, contents: RollbackContents) -> dict[str, object]:
    return {
        "schema_version": PROVENANCE_SCHEMA_VERSION,
        "project": PROJECT_NAME,
        "version": PROJECT_VERSION,
        "commit": rollback_commit,
        "wheel": _record_payload(contents.wheel),
        "sdist": _record_payload(contents.sdist),
        "readme": _record_payload(contents.readme),
    }


def _rollback_readme_bytes(rollback_commit: str) -> bytes:
    return f"""# OMYM2 {PROJECT_VERSION} rollback package set

The wheel and source distribution in this directory are the untouched packages
built from commit `{rollback_commit}`.

This rollback changes application code only. Restore a pre-cutover backup of
persisted application state before using it; backward configuration and database
state compatibility is not guaranteed.

Both the final and rollback packages identify themselves as version
`{PROJECT_VERSION}`. Extract this ZIP first, then install into a fresh environment
or force a reinstall. Verify the package bytes against `SHA256SUMS`.
""".encode()


def _record_payload(record: ArtifactRecord) -> dict[str, object]:
    return {"name": record.name, "sha256": record.sha256, "size": record.size}


def _artifact_record(path: Path) -> ArtifactRecord:
    return ArtifactRecord(name=path.name, sha256=_sha256_bytes(path.read_bytes()), size=path.stat().st_size)


def _artifact_record_bytes(name: str, content: bytes) -> ArtifactRecord:
    return ArtifactRecord(name=name, sha256=_sha256_bytes(content), size=len(content))


def _sha256_bytes(content: bytes) -> str:
    return hashlib.sha256(content).hexdigest()


def _checksum_bytes(records: Sequence[ArtifactRecord]) -> bytes:
    lines = tuple(f"{record.sha256}  {record.name}\n" for record in sorted(records, key=lambda item: item.name))
    return "".join(lines).encode("utf-8")


def _checksum_mapping(records: Sequence[ArtifactRecord]) -> dict[str, str]:
    return {record.name: record.sha256 for record in records}


def _load_checksums(content: bytes, label: str) -> dict[str, str]:
    try:
        lines = content.decode("utf-8").splitlines()
    except UnicodeDecodeError as exc:
        msg = f"{label} is not UTF-8 text."
        raise ReleaseArtifactError(msg) from exc
    checksums: dict[str, str] = {}
    for line in lines:
        digest, separator, name = line.partition("  ")
        if separator == "" or SHA256_PATTERN.fullmatch(digest) is None or not name:
            msg = f"{label} contains a malformed checksum line."
            raise ReleaseArtifactError(msg)
        _validate_archive_member_path(name, label)
        if "/" in name or name in checksums:
            msg = f"{label} contains an unsafe or duplicate filename: {name!r}"
            raise ReleaseArtifactError(msg)
        checksums[name] = digest
    return checksums


def _json_bytes(payload: Mapping[str, object]) -> bytes:
    return f"{json.dumps(payload, indent=2, sort_keys=True)}\n".encode()


def _load_json_object(content: bytes, label: str) -> dict[str, object]:
    try:
        payload = cast("object", json.loads(content))
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        msg = f"{label} is not valid UTF-8 JSON."
        raise ReleaseArtifactError(msg) from exc
    if not isinstance(payload, dict):
        msg = f"{label} must contain one JSON object with string keys."
        raise ReleaseArtifactError(msg)
    object_mapping = cast("dict[object, object]", payload)
    if any(not isinstance(key, str) for key in object_mapping):
        msg = f"{label} must contain one JSON object with string keys."
        raise ReleaseArtifactError(msg)
    return cast("dict[str, object]", object_mapping)


def _rollback_archive_name(rollback_commit: str) -> str:
    return f"omym2-0.1.0-rollback-{rollback_commit[:ROLLBACK_COMMIT_DISPLAY_LENGTH]}.zip"


def _validate_commit(commit: str, label: str) -> None:
    if len(commit) != COMMIT_LENGTH or COMMIT_PATTERN.fullmatch(commit) is None:
        msg = f"{label.capitalize()} commit must be a full lowercase 40-character SHA-1."
        raise ReleaseArtifactError(msg)


def _one_artifact(directory: Path, pattern: str, label: str) -> Path:
    artifacts = tuple(directory.glob(pattern))
    if len(artifacts) != 1:
        msg = f"Expected exactly one {label} in {directory}, found {len(artifacts)}."
        raise ReleaseArtifactError(msg)
    return artifacts[0]


def _smoke_install(wheel: Path, workspace: Path, environment: dict[str, str]) -> None:
    workspace.mkdir()
    virtual_environment = workspace / ".venv"
    _run(("uv", "venv", "--python", sys.executable, str(virtual_environment)), cwd=workspace, environment=environment)
    python = _venv_python(virtual_environment)
    _run(
        ("uv", "pip", "install", "--python", str(python), str(wheel.resolve())),
        cwd=workspace,
        environment=environment,
    )
    _run(
        (str(python), "-I", "-c", INSTALLED_PACKAGE_SMOKE, PROJECT_NAME, PROJECT_VERSION),
        cwd=workspace,
        environment=environment,
    )


def _write_no_node_shims(directory: Path) -> None:
    directory.mkdir()
    if os.name == "nt":
        for tool_name in NO_NODE_TOOL_NAMES:
            _ = (directory / f"{tool_name}.cmd").write_text("@exit /b 97\r\n", encoding="utf-8")
        return
    for tool_name in NO_NODE_TOOL_NAMES:
        shim = directory / tool_name
        _ = shim.write_text("#!/bin/sh\nexit 97\n", encoding="utf-8")
        _ = shim.chmod(shim.stat().st_mode | stat.S_IXUSR)


def _node_poisoned_environment(no_node_directory: Path) -> dict[str, str]:
    environment = os.environ.copy()
    _ = environment.pop("PYTHONPATH", None)
    environment["PATH"] = os.pathsep.join((str(no_node_directory), environment.get("PATH", "")))
    return environment


def _venv_python(virtual_environment: Path) -> Path:
    if os.name == "nt":
        return virtual_environment / WINDOWS_EXECUTABLE_DIRECTORY_NAME / WINDOWS_PYTHON_EXECUTABLE_NAME
    return virtual_environment / POSIX_EXECUTABLE_DIRECTORY_NAME / POSIX_PYTHON_EXECUTABLE_NAME


def _run(command: Sequence[str], *, cwd: Path, environment: dict[str, str]) -> None:
    result = subprocess.run(  # noqa: S603 -- Commands are fixed release build and verification tools.
        tuple(command),
        cwd=cwd,
        env=environment,
        check=False,
    )
    if result.returncode != 0:
        msg = f"Command failed with exit code {result.returncode}: {' '.join(command)}"
        raise ReleaseArtifactError(msg)


def _parse_args(argv: Sequence[str] | None) -> ParsedArgs:
    parser = argparse.ArgumentParser(description=__doc__)
    subparsers = parser.add_subparsers(dest="command", required=True)

    audit_parser = subparsers.add_parser("audit-package-set", help="audit, rebuild, and smoke one package set")
    _ = audit_parser.add_argument("--wheel", type=Path, required=True)
    _ = audit_parser.add_argument("--sdist", type=Path, required=True)
    _ = audit_parser.add_argument("--expected-static", type=Path, required=True)

    prepare_parser = subparsers.add_parser("prepare", help="prepare final and rollback release assets")
    _ = prepare_parser.add_argument("--final-wheel", type=Path, required=True)
    _ = prepare_parser.add_argument("--final-sdist", type=Path, required=True)
    _ = prepare_parser.add_argument("--rollback-wheel", type=Path, required=True)
    _ = prepare_parser.add_argument("--rollback-sdist", type=Path, required=True)
    _ = prepare_parser.add_argument("--final-commit", required=True)
    _ = prepare_parser.add_argument("--rollback-commit", required=True)
    _ = prepare_parser.add_argument("--output-directory", type=Path, required=True)

    verify_parser = subparsers.add_parser("verify", help="verify prepared or downloaded release assets")
    _ = verify_parser.add_argument("--input-directory", type=Path, required=True)
    _ = verify_parser.add_argument("--final-commit", required=True)
    _ = verify_parser.add_argument("--rollback-commit", required=True)
    return parser.parse_args(argv, namespace=ParsedArgs())


def main(argv: Sequence[str] | None = None) -> int:
    """Run one release artifact operation and report a concise result."""
    args = _parse_args(argv)
    try:
        if args.command == "audit-package-set":
            audit_package_set(args.wheel, args.sdist, args.expected_static)
            print(f"release package audit passed: {args.wheel} and {args.sdist}")
        elif args.command == "prepare":
            prepare_release_assets(
                ReleasePreparation(
                    final_wheel=args.final_wheel,
                    final_sdist=args.final_sdist,
                    rollback_wheel=args.rollback_wheel,
                    rollback_sdist=args.rollback_sdist,
                    final_commit=args.final_commit,
                    rollback_commit=args.rollback_commit,
                    output_directory=args.output_directory,
                )
            )
            print(f"release asset preparation passed: {args.output_directory}")
        elif args.command == "verify":
            verify_release_assets(
                args.input_directory,
                final_commit=args.final_commit,
                rollback_commit=args.rollback_commit,
            )
            print(f"release asset verification passed: {args.input_directory}")
        else:
            print(f"release artifact operation failed: unknown command {args.command}", file=sys.stderr)
            return 2
    except (OSError, PackageAuditError, ReleaseArtifactError) as exc:
        print(f"release artifact operation failed: {exc}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
