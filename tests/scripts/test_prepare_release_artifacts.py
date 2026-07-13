"""
Summary: Tests final and same-version rollback release artifact preparation.
Why: Prevents unsafe, renamed, overwritten, or tampered release packages.
"""

from __future__ import annotations

import base64
import copy
import hashlib
import io
import json
import stat
import subprocess
import sys
import tarfile
import warnings
import zipfile
from pathlib import Path
from typing import cast

import pytest

SCRIPT_RELATIVE_PATH = "scripts/prepare_release_artifacts.py"
WHEEL_FILE_NAME = "omym2-0.1.0-py3-none-any.whl"
SDIST_FILE_NAME = "omym2-0.1.0.tar.gz"
WHEEL_DIST_INFO_DIRECTORY_NAME = "omym2-0.1.0.dist-info"
WHEEL_METADATA_MEMBER_NAME = f"{WHEEL_DIST_INFO_DIRECTORY_NAME}/METADATA"
WHEEL_DESCRIPTOR_MEMBER_NAME = f"{WHEEL_DIST_INFO_DIRECTORY_NAME}/WHEEL"
WHEEL_RECORD_MEMBER_NAME = f"{WHEEL_DIST_INFO_DIRECTORY_NAME}/RECORD"
COMMIT_LENGTH = 40
FINAL_COMMIT = "a" * COMMIT_LENGTH
ROLLBACK_COMMIT = "b" * COMMIT_LENGTH
ROLLBACK_ARCHIVE_FILE_NAME = "omym2-0.1.0-rollback-bbbbbbb.zip"
ROOT_PROVENANCE_FILE_NAME = "omym2-0.1.0-provenance.json"
ROOT_CHECKSUM_FILE_NAME = "omym2-0.1.0-SHA256SUMS"
ROLLBACK_README_MEMBER_NAME = "rollback/README.md"
ROLLBACK_CHECKSUM_MEMBER_NAME = "rollback/SHA256SUMS"
ROLLBACK_PROVENANCE_MEMBER_NAME = "rollback/provenance.json"
ROLLBACK_WHEEL_MEMBER_NAME = f"rollback/{WHEEL_FILE_NAME}"
WHEEL_METADATA = b"Metadata-Version: 2.4\nName: omym2\nVersion: 0.1.0\n\n"
WHEEL_DESCRIPTION = b"Wheel-Version: 1.0\nGenerator: test\nRoot-Is-Purelib: true\nTag: py3-none-any\n"
SDIST_METADATA = b"Metadata-Version: 2.4\nName: omym2\nVersion: 0.1.0\n\n"


def test_prepare_preserves_packages_and_verify_accepts_release_set(tmp_path: Path) -> None:
    """The rollback container isolates duplicate standardized package basenames."""
    final_directory = tmp_path / "final"
    rollback_directory = tmp_path / "rollback-input"
    output_directory = tmp_path / "release"
    final_wheel, final_sdist = _write_package_pair(final_directory, marker=b"final")
    rollback_wheel, rollback_sdist = _write_package_pair(rollback_directory, marker=b"rollback")
    rollback_wheel_bytes = rollback_wheel.read_bytes()
    rollback_sdist_bytes = rollback_sdist.read_bytes()

    prepare_result = _run_prepare(
        final_wheel,
        final_sdist,
        rollback_wheel,
        rollback_sdist,
        output_directory,
    )
    verify_result = _run_verify(output_directory)

    assert prepare_result.returncode == 0, prepare_result.stderr
    assert verify_result.returncode == 0, verify_result.stderr
    assert (output_directory / WHEEL_FILE_NAME).read_bytes() == final_wheel.read_bytes()
    assert (output_directory / SDIST_FILE_NAME).read_bytes() == final_sdist.read_bytes()
    with zipfile.ZipFile(output_directory / ROLLBACK_ARCHIVE_FILE_NAME) as archive:
        assert set(archive.namelist()) == {
            f"rollback/{WHEEL_FILE_NAME}",
            f"rollback/{SDIST_FILE_NAME}",
            ROLLBACK_README_MEMBER_NAME,
            ROLLBACK_CHECKSUM_MEMBER_NAME,
            ROLLBACK_PROVENANCE_MEMBER_NAME,
        }
        assert archive.read(f"rollback/{WHEEL_FILE_NAME}") == rollback_wheel_bytes
        assert archive.read(f"rollback/{SDIST_FILE_NAME}") == rollback_sdist_bytes
        rollback_readme = archive.read(ROLLBACK_README_MEMBER_NAME).decode()
        assert ROLLBACK_COMMIT in rollback_readme
        assert "Restore a pre-cutover backup" in rollback_readme
    provenance = cast(
        "dict[str, object]",
        json.loads((output_directory / ROOT_PROVENANCE_FILE_NAME).read_text(encoding="utf-8")),
    )
    assert cast("dict[str, object]", provenance["final"])["commit"] == FINAL_COMMIT
    assert cast("dict[str, object]", provenance["rollback"])["commit"] == ROLLBACK_COMMIT


def test_verify_rejects_tampered_release_asset(tmp_path: Path) -> None:
    """Root checksums reject bytes changed after preparation."""
    output_directory = _prepare_fixture_release(tmp_path)
    final_sdist = output_directory / SDIST_FILE_NAME
    _ = final_sdist.write_bytes(final_sdist.read_bytes() + b"tampered")

    result = _run_verify(output_directory)

    assert result.returncode != 0
    assert "provenance differs" in result.stderr


def test_verify_rejects_unsafe_rollback_archive_member(tmp_path: Path) -> None:
    """Rollback ZIP traversal members fail before checksum comparison."""
    output_directory = _prepare_fixture_release(tmp_path)
    rollback_archive = output_directory / ROLLBACK_ARCHIVE_FILE_NAME
    with zipfile.ZipFile(rollback_archive, mode="a") as archive:
        _ = archive.writestr("../escape", b"unsafe")

    result = _run_verify(output_directory)

    assert result.returncode != 0
    assert "unsafe member path" in result.stderr


def test_prepare_refuses_to_overwrite_existing_release_directory(tmp_path: Path) -> None:
    """A rerun cannot silently replace previously staged release evidence."""
    final_wheel, final_sdist = _write_package_pair(tmp_path / "final", marker=b"final")
    rollback_wheel, rollback_sdist = _write_package_pair(tmp_path / "rollback-input", marker=b"rollback")
    output_directory = tmp_path / "release"
    first_result = _run_prepare(
        final_wheel,
        final_sdist,
        rollback_wheel,
        rollback_sdist,
        output_directory,
    )
    assert first_result.returncode == 0, first_result.stderr

    second_result = _run_prepare(
        final_wheel,
        final_sdist,
        rollback_wheel,
        rollback_sdist,
        output_directory,
    )

    assert second_result.returncode != 0
    assert "refusing to overwrite" in second_result.stderr


def test_prepare_is_byte_reproducible_for_identical_inputs(tmp_path: Path) -> None:
    """Deterministic metadata and ZIP fields produce the same release bytes."""
    final_wheel, final_sdist = _write_package_pair(tmp_path / "final", marker=b"final")
    rollback_wheel, rollback_sdist = _write_package_pair(tmp_path / "rollback-input", marker=b"rollback")
    first_output = tmp_path / "first-release"
    second_output = tmp_path / "second-release"

    first_result = _run_prepare(final_wheel, final_sdist, rollback_wheel, rollback_sdist, first_output)
    second_result = _run_prepare(final_wheel, final_sdist, rollback_wheel, rollback_sdist, second_output)

    assert first_result.returncode == 0, first_result.stderr
    assert second_result.returncode == 0, second_result.stderr
    assert _directory_file_bytes(first_output) == _directory_file_bytes(second_output)


@pytest.mark.parametrize(
    ("artifact_name", "expected_message"),
    [("wheel", "Wheel must retain its standardized filename"), ("sdist", "must retain its standardized filename")],
)
def test_prepare_rejects_renamed_packages(
    tmp_path: Path,
    artifact_name: str,
    expected_message: str,
) -> None:
    """Standard distribution filenames cannot be replaced with release aliases."""
    final_wheel, final_sdist = _write_package_pair(tmp_path / "final", marker=b"final")
    rollback_wheel, rollback_sdist = _write_package_pair(tmp_path / "rollback-input", marker=b"rollback")
    if artifact_name == "wheel":
        final_wheel = final_wheel.rename(final_wheel.with_name("renamed.whl"))
    else:
        final_sdist = final_sdist.rename(final_sdist.with_name("renamed.tar.gz"))

    result = _run_prepare(
        final_wheel,
        final_sdist,
        rollback_wheel,
        rollback_sdist,
        tmp_path / "release",
    )

    assert result.returncode != 0
    assert expected_message in result.stderr


@pytest.mark.parametrize(
    ("final_commit", "rollback_commit", "expected_message"),
    [
        ("a" * (COMMIT_LENGTH - 1), ROLLBACK_COMMIT, "Final commit must be"),
        (FINAL_COMMIT, "B" * COMMIT_LENGTH, "Rollback commit must be"),
    ],
)
def test_prepare_rejects_invalid_commit_identifiers(
    tmp_path: Path,
    final_commit: str,
    rollback_commit: str,
    expected_message: str,
) -> None:
    """Provenance accepts only full lowercase commit object identifiers."""
    final_wheel, final_sdist = _write_package_pair(tmp_path / "final", marker=b"final")
    rollback_wheel, rollback_sdist = _write_package_pair(tmp_path / "rollback-input", marker=b"rollback")

    result = _run_prepare_with_commits(
        (final_wheel, final_sdist),
        (rollback_wheel, rollback_sdist),
        tmp_path / "release",
        (final_commit, rollback_commit),
    )

    assert result.returncode != 0
    assert expected_message in result.stderr


@pytest.mark.parametrize(
    ("commits", "expected_message"),
    [
        (("c" * COMMIT_LENGTH, ROLLBACK_COMMIT), "provenance differs"),
        ((FINAL_COMMIT, "c" * COMMIT_LENGTH), "Release asset set differs"),
    ],
)
def test_verify_rejects_wrong_expected_commits(
    tmp_path: Path,
    commits: tuple[str, str],
    expected_message: str,
) -> None:
    """Valid but incorrect expected commits cannot authenticate provenance."""
    output_directory = _prepare_fixture_release(tmp_path)

    result = _run_verify_with_commits(output_directory, commits)

    assert result.returncode != 0
    assert expected_message in result.stderr


def test_prepare_rejects_mismatched_wheel_dist_info_directory(tmp_path: Path) -> None:
    """The standardized wheel filename binds its internal dist-info directory."""
    final_wheel, final_sdist = _write_package_pair(tmp_path / "final", marker=b"final")
    _write_wheel(final_wheel, b"final", dist_info_directory="different-0.0.dist-info")
    rollback_wheel, rollback_sdist = _write_package_pair(tmp_path / "rollback-input", marker=b"rollback")

    result = _run_prepare(
        final_wheel,
        final_sdist,
        rollback_wheel,
        rollback_sdist,
        tmp_path / "release",
    )

    assert result.returncode != 0
    assert "exact omym2-0.1.0.dist-info directory" in result.stderr


@pytest.mark.parametrize("member_name", ["../escape/", "C:/escape/", "..\\escape/"])
def test_prepare_rejects_unsafe_wheel_directory_member(tmp_path: Path, member_name: str) -> None:
    """Wheel directory entries receive the same traversal checks as files."""
    final_wheel, final_sdist = _write_package_pair(tmp_path / "final", marker=b"final")
    unsafe_member = zipfile.ZipInfo(member_name)
    unsafe_member.create_system = 3
    unsafe_member.external_attr = (stat.S_IFDIR | 0o755) << 16
    with zipfile.ZipFile(final_wheel, mode="a") as archive:
        archive.writestr(unsafe_member, b"")
    rollback_wheel, rollback_sdist = _write_package_pair(tmp_path / "rollback-input", marker=b"rollback")

    result = _run_prepare(
        final_wheel,
        final_sdist,
        rollback_wheel,
        rollback_sdist,
        tmp_path / "release",
    )

    assert result.returncode != 0
    assert "unsafe member path" in result.stderr


@pytest.mark.parametrize(
    ("corruption", "expected_message"),
    [
        ("metadata", "wheel METADATA identifies"),
        ("descriptor", "tag differs from its filename"),
        ("record", "RECORD integrity differs"),
        ("missing_descriptor", "is missing omym2-0.1.0.dist-info/WHEEL"),
    ],
)
def test_prepare_rejects_malformed_wheel_contracts(
    tmp_path: Path,
    corruption: str,
    expected_message: str,
) -> None:
    """Core metadata, WHEEL tags, and RECORD integrity are all binding."""
    final_wheel, final_sdist = _write_package_pair(tmp_path / "final", marker=b"final")
    _corrupt_wheel(final_wheel, corruption)
    rollback_wheel, rollback_sdist = _write_package_pair(tmp_path / "rollback-input", marker=b"rollback")

    result = _run_prepare(
        final_wheel,
        final_sdist,
        rollback_wheel,
        rollback_sdist,
        tmp_path / "release",
    )

    assert result.returncode != 0
    assert expected_message in result.stderr


@pytest.mark.parametrize(
    ("mutation", "expected_message"),
    [
        ("missing", "Release asset set differs"),
        ("extra", "Release asset set differs"),
        ("checksum", "Release checksum manifest differs"),
        ("provenance", "Release provenance differs"),
    ],
)
def test_verify_rejects_root_asset_set_and_manifest_mutations(
    tmp_path: Path,
    mutation: str,
    expected_message: str,
) -> None:
    """The root asset set, checksums, and commit provenance remain exact."""
    output_directory = _prepare_fixture_release(tmp_path)
    _mutate_root_release(output_directory, mutation)

    result = _run_verify(output_directory)

    assert result.returncode != 0
    assert expected_message in result.stderr


@pytest.mark.parametrize(
    ("mutation", "expected_message"),
    [
        ("missing", "Rollback archive members differ"),
        ("duplicate", "duplicate member names"),
        ("package", "Rollback provenance differs"),
        ("readme", "Rollback README differs"),
        ("checksum", "Rollback checksum manifest differs"),
        ("provenance", "Rollback provenance differs"),
    ],
)
def test_verify_rejects_nested_rollback_mutations(
    tmp_path: Path,
    mutation: str,
    expected_message: str,
) -> None:
    """Every nested package, guidance, checksum, and provenance member is binding."""
    output_directory = _prepare_fixture_release(tmp_path)
    _mutate_rollback_archive(output_directory / ROLLBACK_ARCHIVE_FILE_NAME, mutation)

    result = _run_verify(output_directory)

    assert result.returncode != 0
    assert expected_message in result.stderr


def test_audit_package_set_rejects_static_content_mismatch(tmp_path: Path) -> None:
    """The audit command rejects packages that differ from the expected static tree."""
    wheel, sdist = _write_package_pair(tmp_path / "packages", marker=b"package")
    expected_static = tmp_path / "expected-static"
    expected_static.mkdir()
    _ = (expected_static / "index.html").write_bytes(b"different")

    result = _run_script(
        "audit-package-set",
        "--wheel",
        str(wheel),
        "--sdist",
        str(sdist),
        "--expected-static",
        str(expected_static),
    )

    assert result.returncode != 0
    assert "static file content differs" in result.stderr


def _prepare_fixture_release(tmp_path: Path) -> Path:
    final_wheel, final_sdist = _write_package_pair(tmp_path / "final", marker=b"final")
    rollback_wheel, rollback_sdist = _write_package_pair(tmp_path / "rollback-input", marker=b"rollback")
    output_directory = tmp_path / "release"
    result = _run_prepare(
        final_wheel,
        final_sdist,
        rollback_wheel,
        rollback_sdist,
        output_directory,
    )
    assert result.returncode == 0, result.stderr
    return output_directory


def _directory_file_bytes(directory: Path) -> dict[str, bytes]:
    return {path.name: path.read_bytes() for path in directory.iterdir() if path.is_file()}


def _corrupt_wheel(wheel: Path, corruption: str) -> None:
    contents = _zip_member_bytes(wheel)
    replacements: dict[str, bytes] = {}
    removed_names: set[str] = set()
    if corruption == "metadata":
        replacements[WHEEL_METADATA_MEMBER_NAME] = contents[WHEEL_METADATA_MEMBER_NAME].replace(
            b"Version: 0.1.0",
            b"Version: 9.9.9",
        )
    elif corruption == "descriptor":
        replacements[WHEEL_DESCRIPTOR_MEMBER_NAME] = contents[WHEEL_DESCRIPTOR_MEMBER_NAME].replace(
            b"Tag: py3-none-any",
            b"Tag: cp314-cp314-manylinux_2_39_x86_64",
        )
    elif corruption == "record":
        replacements[WHEEL_RECORD_MEMBER_NAME] = contents[WHEEL_RECORD_MEMBER_NAME].replace(
            b"sha256=",
            b"sha256=changed",
            1,
        )
    elif corruption == "missing_descriptor":
        removed_names.add(WHEEL_DESCRIPTOR_MEMBER_NAME)
    else:
        msg = f"Unknown wheel corruption: {corruption}"
        raise ValueError(msg)
    _rewrite_zip_archive(wheel, replacements=replacements, removed_names=removed_names)


def _mutate_root_release(output_directory: Path, mutation: str) -> None:
    if mutation == "missing":
        (output_directory / SDIST_FILE_NAME).unlink()
    elif mutation == "extra":
        _ = (output_directory / "unexpected.txt").write_bytes(b"unexpected")
    elif mutation == "checksum":
        checksum_path = output_directory / ROOT_CHECKSUM_FILE_NAME
        _ = checksum_path.write_bytes(_changed_checksum_bytes(checksum_path.read_bytes()))
    elif mutation == "provenance":
        provenance_path = output_directory / ROOT_PROVENANCE_FILE_NAME
        payload = cast("dict[str, object]", json.loads(provenance_path.read_bytes()))
        final = cast("dict[str, object]", payload["final"])
        final["commit"] = "c" * COMMIT_LENGTH
        _ = provenance_path.write_bytes(_json_bytes(payload))
    else:
        msg = f"Unknown root release mutation: {mutation}"
        raise ValueError(msg)


def _mutate_rollback_archive(archive_path: Path, mutation: str) -> None:
    contents = _zip_member_bytes(archive_path)
    replacements: dict[str, bytes] = {}
    removed_names: set[str] = set()
    duplicate_name: str | None = None
    if mutation == "missing":
        removed_names.add(ROLLBACK_WHEEL_MEMBER_NAME)
    elif mutation == "duplicate":
        duplicate_name = ROLLBACK_PROVENANCE_MEMBER_NAME
    elif mutation == "package":
        replacements[ROLLBACK_WHEEL_MEMBER_NAME] = contents[ROLLBACK_WHEEL_MEMBER_NAME] + b"tampered"
    elif mutation == "readme":
        replacements[ROLLBACK_README_MEMBER_NAME] = contents[ROLLBACK_README_MEMBER_NAME] + b"tampered"
    elif mutation == "checksum":
        replacements[ROLLBACK_CHECKSUM_MEMBER_NAME] = _changed_checksum_bytes(contents[ROLLBACK_CHECKSUM_MEMBER_NAME])
    elif mutation == "provenance":
        payload = cast("dict[str, object]", json.loads(contents[ROLLBACK_PROVENANCE_MEMBER_NAME]))
        payload["commit"] = "c" * COMMIT_LENGTH
        replacements[ROLLBACK_PROVENANCE_MEMBER_NAME] = _json_bytes(payload)
    else:
        msg = f"Unknown rollback archive mutation: {mutation}"
        raise ValueError(msg)
    _rewrite_zip_archive(
        archive_path,
        replacements=replacements,
        removed_names=removed_names,
        duplicate_name=duplicate_name,
    )


def _zip_member_bytes(archive_path: Path) -> dict[str, bytes]:
    with zipfile.ZipFile(archive_path) as archive:
        return {info.filename: archive.read(info) for info in archive.infolist()}


def _rewrite_zip_archive(
    archive_path: Path,
    *,
    replacements: dict[str, bytes],
    removed_names: set[str],
    duplicate_name: str | None = None,
) -> None:
    with zipfile.ZipFile(archive_path) as source:
        members = tuple((copy.copy(info), source.read(info)) for info in source.infolist())
    temporary_path = archive_path.with_name(f"{archive_path.name}.rewrite")
    with warnings.catch_warnings():
        warnings.simplefilter("ignore", UserWarning)
        with zipfile.ZipFile(temporary_path, mode="x") as target:
            for info, content in members:
                if info.filename in removed_names:
                    continue
                updated_content = replacements.get(info.filename, content)
                target.writestr(copy.copy(info), updated_content)
                if info.filename == duplicate_name:
                    target.writestr(copy.copy(info), updated_content)
    _ = temporary_path.replace(archive_path)


def _changed_checksum_bytes(content: bytes) -> bytes:
    first_line, newline, remaining = content.partition(b"\n")
    digest, separator, name = first_line.partition(b"  ")
    changed_prefix = b"0" if digest[:1] != b"0" else b"1"
    return changed_prefix + digest[1:] + separator + name + newline + remaining


def _json_bytes(payload: dict[str, object]) -> bytes:
    return f"{json.dumps(payload, indent=2, sort_keys=True)}\n".encode()


def _write_package_pair(directory: Path, *, marker: bytes) -> tuple[Path, Path]:
    directory.mkdir()
    wheel = directory / WHEEL_FILE_NAME
    sdist = directory / SDIST_FILE_NAME
    _write_wheel(wheel, marker)
    _write_sdist(sdist, marker)
    return wheel, sdist


def _write_wheel(
    wheel: Path,
    marker: bytes,
    *,
    dist_info_directory: str = WHEEL_DIST_INFO_DIRECTORY_NAME,
) -> None:
    metadata_path = f"{dist_info_directory}/METADATA"
    wheel_path = f"{dist_info_directory}/WHEEL"
    record_path = f"{dist_info_directory}/RECORD"
    files = {
        metadata_path: WHEEL_METADATA,
        wheel_path: WHEEL_DESCRIPTION,
        "omym2/adapters/web/static_dist/index.html": b"<!doctype html>" + marker,
    }
    record_lines: list[str] = []
    for name, content in sorted(files.items()):
        digest = base64.urlsafe_b64encode(hashlib.sha256(content).digest()).rstrip(b"=").decode("ascii")
        record_lines.append(f"{name},sha256={digest},{len(content)}\n")
    record_lines.append(f"{record_path},,\n")
    with zipfile.ZipFile(wheel, mode="w") as archive:
        for name, content in files.items():
            _write_regular_zip_member(archive, name, content)
        _write_regular_zip_member(archive, record_path, "".join(record_lines).encode())


def _write_regular_zip_member(archive: zipfile.ZipFile, name: str, content: bytes) -> None:
    member = zipfile.ZipInfo(name)
    member.create_system = 3
    member.external_attr = (stat.S_IFREG | 0o644) << 16
    archive.writestr(member, content)


def _write_sdist(sdist: Path, marker: bytes) -> None:
    files = {
        "omym2-0.1.0/PKG-INFO": SDIST_METADATA,
        "omym2-0.1.0/pyproject.toml": b'[project]\nname = "omym2"\nversion = "0.1.0"\n',
        "omym2-0.1.0/src/omym2/adapters/web/static_dist/index.html": b"<!doctype html>" + marker,
    }
    with tarfile.open(sdist, mode="w:gz") as archive:
        for name, content in files.items():
            member = tarfile.TarInfo(name)
            member.size = len(content)
            archive.addfile(member, io.BytesIO(content))


def _run_prepare(
    final_wheel: Path,
    final_sdist: Path,
    rollback_wheel: Path,
    rollback_sdist: Path,
    output_directory: Path,
) -> subprocess.CompletedProcess[str]:
    return _run_prepare_with_commits(
        (final_wheel, final_sdist),
        (rollback_wheel, rollback_sdist),
        output_directory,
        (FINAL_COMMIT, ROLLBACK_COMMIT),
    )


def _run_prepare_with_commits(
    final_packages: tuple[Path, Path],
    rollback_packages: tuple[Path, Path],
    output_directory: Path,
    commits: tuple[str, str],
) -> subprocess.CompletedProcess[str]:
    final_wheel, final_sdist = final_packages
    rollback_wheel, rollback_sdist = rollback_packages
    final_commit, rollback_commit = commits
    return _run_script(
        "prepare",
        "--final-wheel",
        str(final_wheel),
        "--final-sdist",
        str(final_sdist),
        "--rollback-wheel",
        str(rollback_wheel),
        "--rollback-sdist",
        str(rollback_sdist),
        "--final-commit",
        final_commit,
        "--rollback-commit",
        rollback_commit,
        "--output-directory",
        str(output_directory),
    )


def _run_verify(output_directory: Path) -> subprocess.CompletedProcess[str]:
    return _run_verify_with_commits(output_directory, (FINAL_COMMIT, ROLLBACK_COMMIT))


def _run_verify_with_commits(
    output_directory: Path,
    commits: tuple[str, str],
) -> subprocess.CompletedProcess[str]:
    final_commit, rollback_commit = commits
    return _run_script(
        "verify",
        "--input-directory",
        str(output_directory),
        "--final-commit",
        final_commit,
        "--rollback-commit",
        rollback_commit,
    )


def _run_script(*args: str) -> subprocess.CompletedProcess[str]:
    return subprocess.run(  # noqa: S603 -- Fixed argv invokes this repository's own script.
        (sys.executable, SCRIPT_RELATIVE_PATH, *args),
        cwd=_project_root(),
        capture_output=True,
        text=True,
        check=False,
    )


def _project_root() -> Path:
    for parent in Path(__file__).resolve().parents:
        if (parent / "pyproject.toml").is_file():
            return parent
    msg = "Unable to locate project root from test file."
    raise RuntimeError(msg)
