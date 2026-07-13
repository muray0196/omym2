"""
Summary: Audits bundled Web build content and its synchronized package copy.
Why: Makes ignored generated assets safe and deterministic packaging inputs.
"""
# ruff: noqa: INP001, T201 -- Standalone audit script reports concise CLI results.

from __future__ import annotations

import argparse
import hashlib
import re
import sys
from html.parser import HTMLParser
from pathlib import Path, PurePosixPath
from typing import TYPE_CHECKING, override
from urllib.parse import unquote, urlsplit

from omym2.adapters.web.static_assets import is_hashed_asset_name

if TYPE_CHECKING:
    from collections.abc import Sequence

PROJECT_ROOT_NOT_FOUND_MESSAGE = "Unable to locate the project root."
DEFAULT_WEB_BUILD_RELATIVE_PATH = Path("web/dist")
DEFAULT_PACKAGED_STATIC_RELATIVE_PATH = Path("src/omym2/adapters/web/static_dist")
STATIC_INDEX_FILE_NAME = "index.html"
STATIC_ASSET_DIRECTORY_NAME = "assets"
STATIC_LICENSE_DIRECTORY_NAME = "licenses"
FONT_SUFFIXES = frozenset({".woff", ".woff2"})
REQUIRED_FONT_PREFIXES = ("inter-", "jetbrains-mono-")
REQUIRED_LICENSE_PATHS = frozenset(
    {
        PurePosixPath("licenses/Inter-OFL.txt"),
        PurePosixPath("licenses/JetBrains-Mono-OFL.txt"),
    }
)
ALLOWED_ASSET_SUFFIXES = frozenset({".css", ".js", ".svg", ".woff", ".woff2"})
LICENSE_SUFFIX = ".txt"
LICENSE_PATH_PART_COUNT = 2
TEXT_RUNTIME_SUFFIXES = frozenset({".css", ".html", ".js", ".svg", ".txt"})
DISALLOWED_SUFFIXES = frozenset({".db", ".key", ".log", ".map", ".pem", ".sqlite", ".sqlite3"})
DISALLOWED_FILE_NAMES = frozenset({".env", ".env.local", ".npmrc"})
DISALLOWED_RUNTIME_TEXT = (
    "@vercel/analytics",
    "BEGIN PRIVATE KEY",
    "google-analytics.com",
    "googletagmanager.com",
    "segment.io",
    "sourceMappingURL=",
    "va.vercel-scripts.com",
)
REMOTE_MARKUP_REFERENCE_PATTERN = re.compile(
    r"\b(?:href|src|xlink:href)\s*=\s*[\"']\s*(?:https?:)?//",
    flags=re.IGNORECASE,
)
REMOTE_CSS_REFERENCE_PATTERN = re.compile(
    r"(?:@import\s+|url\(\s*)[\"']?\s*(?:https?:)?//",
    flags=re.IGNORECASE,
)
REMOTE_JAVASCRIPT_REQUEST_PATTERN = re.compile(
    r"\b(?:fetch|WebSocket|EventSource)\s*\(\s*[\"'`]\s*(?:https?:)?//",
    flags=re.IGNORECASE,
)


class StaticAuditError(RuntimeError):
    """Raised when a Web static export violates its distribution contract."""


class ParsedArgs(argparse.Namespace):
    """Typed command-line arguments for static auditing."""

    def __init__(self, source: Path, destination: Path) -> None:
        super().__init__()
        self.source: Path = source
        self.destination: Path = destination


class _IndexReferenceParser(HTMLParser):
    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self.references: list[str] = []
        self.has_inline_script_element: bool = False
        self.has_inline_style_attribute: bool = False
        self.has_inline_style_element: bool = False

    @override
    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        attributes = dict(attrs)
        if "style" in attributes:
            self.has_inline_style_attribute = True
        if tag == "script":
            source = attributes.get("src")
            if source is None:
                self.has_inline_script_element = True
            else:
                self.references.append(source)
        elif tag == "style":
            self.has_inline_style_element = True
        elif tag == "link" and attributes.get("href") is not None:
            self.references.append(attributes["href"] or "")
        elif tag in {"img", "source"} and attributes.get("src") is not None:
            self.references.append(attributes["src"] or "")


def audit_static_export(source: Path, destination: Path) -> None:
    """Validate one Vite export and require an identical packaged copy."""
    source_files = _collect_files(source)
    destination_files = _collect_files(destination)
    if source_files.keys() != destination_files.keys():
        missing = sorted(source_files.keys() - destination_files.keys())
        extra = sorted(destination_files.keys() - source_files.keys())
        msg = f"Static trees differ; missing={missing}, extra={extra}"
        raise StaticAuditError(msg)

    for relative_path, source_path in source_files.items():
        if _digest(source_path) != _digest(destination_files[relative_path]):
            msg = f"Static file content differs: {relative_path.as_posix()}"
            raise StaticAuditError(msg)

    _audit_export_content(source, source_files)


def _collect_files(root: Path) -> dict[PurePosixPath, Path]:
    root = root.resolve()
    if not root.is_dir():
        msg = f"Static directory does not exist: {root}"
        raise StaticAuditError(msg)
    result: dict[PurePosixPath, Path] = {}
    for path in sorted(root.rglob("*")):
        if path.is_symlink():
            msg = f"Static trees must not contain symlinks: {path}"
            raise StaticAuditError(msg)
        if path.is_file():
            result[PurePosixPath(path.relative_to(root).as_posix())] = path
    return result


def _audit_export_content(root: Path, files: dict[PurePosixPath, Path]) -> None:
    index_relative_path = PurePosixPath(STATIC_INDEX_FILE_NAME)
    if index_relative_path not in files:
        msg = f"Static export is missing {STATIC_INDEX_FILE_NAME}."
        raise StaticAuditError(msg)

    missing_licenses = sorted(REQUIRED_LICENSE_PATHS - files.keys())
    if missing_licenses:
        msg = f"Static export is missing required font licenses: {missing_licenses}"
        raise StaticAuditError(msg)
    font_names = tuple(path.name.lower() for path in files if path.suffix.lower() in FONT_SUFFIXES)
    missing_font_prefixes = tuple(
        prefix for prefix in REQUIRED_FONT_PREFIXES if not any(name.startswith(prefix) for name in font_names)
    )
    if missing_font_prefixes:
        msg = f"Static export is missing required self-hosted font families: {missing_font_prefixes}"
        raise StaticAuditError(msg)

    for relative_path, path in files.items():
        _audit_path_shape(relative_path)
        _audit_file(relative_path, path)
    _audit_index(root, files[index_relative_path])


def _audit_path_shape(relative_path: PurePosixPath) -> None:
    if relative_path == PurePosixPath(STATIC_INDEX_FILE_NAME):
        return
    if relative_path.parts[0] == STATIC_ASSET_DIRECTORY_NAME:
        if relative_path.suffix.lower() not in ALLOWED_ASSET_SUFFIXES:
            msg = f"Static export contains an unsupported asset type: {relative_path.as_posix()}"
            raise StaticAuditError(msg)
        if not is_hashed_asset_name(relative_path.name):
            msg = f"Static export contains an unhashed asset: {relative_path.as_posix()}"
            raise StaticAuditError(msg)
        return
    if (
        len(relative_path.parts) == LICENSE_PATH_PART_COUNT
        and relative_path.parts[0] == STATIC_LICENSE_DIRECTORY_NAME
        and relative_path.suffix.lower() == LICENSE_SUFFIX
    ):
        return
    msg = f"Static export contains an unexpected file location or type: {relative_path.as_posix()}"
    raise StaticAuditError(msg)


def _audit_file(relative_path: PurePosixPath, path: Path) -> None:
    if any(part.startswith(".") for part in relative_path.parts) or path.name in DISALLOWED_FILE_NAMES:
        msg = f"Static export contains a dotfile or local configuration file: {relative_path.as_posix()}"
        raise StaticAuditError(msg)
    if path.suffix.lower() in DISALLOWED_SUFFIXES:
        msg = f"Static export contains a prohibited artifact: {relative_path.as_posix()}"
        raise StaticAuditError(msg)
    if path.suffix.lower() not in TEXT_RUNTIME_SUFFIXES:
        return
    try:
        content = path.read_text(encoding="utf-8")
    except UnicodeDecodeError as exc:
        msg = f"Runtime text asset is not UTF-8: {relative_path.as_posix()}"
        raise StaticAuditError(msg) from exc
    if relative_path.parts[0] != STATIC_LICENSE_DIRECTORY_NAME and _contains_remote_runtime_reference(path, content):
        msg = f"Runtime asset contains a remote URL: {relative_path.as_posix()}"
        raise StaticAuditError(msg)
    for prohibited in DISALLOWED_RUNTIME_TEXT:
        if prohibited in content:
            msg = f"Runtime asset contains prohibited text {prohibited!r}: {relative_path.as_posix()}"
            raise StaticAuditError(msg)
    if path.suffix.lower() in {".html", ".svg"}:
        _audit_markup(relative_path, content)


def _contains_remote_runtime_reference(path: Path, content: str) -> bool:
    suffix = path.suffix.lower()
    if suffix in {".html", ".svg", ".xml"}:
        return REMOTE_MARKUP_REFERENCE_PATTERN.search(content) is not None
    if suffix == ".css":
        return REMOTE_CSS_REFERENCE_PATTERN.search(content) is not None
    if suffix == ".js":
        return REMOTE_JAVASCRIPT_REQUEST_PATTERN.search(content) is not None
    return False


def _audit_markup(relative_path: PurePosixPath, content: str) -> None:
    parser = _IndexReferenceParser()
    parser.feed(content)
    if parser.has_inline_script_element:
        msg = f"Markup contains an inline script: {relative_path.as_posix()}"
        raise StaticAuditError(msg)
    if parser.has_inline_style_element:
        msg = f"Markup contains an inline style block: {relative_path.as_posix()}"
        raise StaticAuditError(msg)
    if parser.has_inline_style_attribute:
        msg = f"Markup contains an inline style attribute: {relative_path.as_posix()}"
        raise StaticAuditError(msg)


def _audit_index(root: Path, index_path: Path) -> None:
    parser = _IndexReferenceParser()
    parser.feed(index_path.read_text(encoding="utf-8"))
    if parser.has_inline_script_element:
        msg = "index.html contains an inline script."
        raise StaticAuditError(msg)
    resolved_references = tuple(_resolve_reference(reference) for reference in parser.references if reference)
    asset_references = tuple(path for path in resolved_references if path.parts[0] == STATIC_ASSET_DIRECTORY_NAME)
    if not asset_references:
        msg = f"index.html does not reference any {STATIC_ASSET_DIRECTORY_NAME}/ asset."
        raise StaticAuditError(msg)
    for relative_path in resolved_references:
        candidate = root / relative_path
        if not candidate.is_file():
            msg = f"index.html references a missing asset: {relative_path.as_posix()}"
            raise StaticAuditError(msg)
        if relative_path.parts[0] == STATIC_ASSET_DIRECTORY_NAME and not is_hashed_asset_name(relative_path.name):
            msg = f"Referenced asset name is not content-hashed: {relative_path.as_posix()}"
            raise StaticAuditError(msg)


def _resolve_reference(reference: str) -> PurePosixPath:
    parsed = urlsplit(reference)
    if parsed.scheme or parsed.netloc or reference.startswith("//"):
        msg = f"index.html contains a remote asset reference: {reference}"
        raise StaticAuditError(msg)
    decoded = unquote(parsed.path)
    relative = PurePosixPath(decoded.removeprefix("/"))
    if not relative.parts or relative.is_absolute() or ".." in relative.parts:
        msg = f"index.html contains an unsafe asset reference: {reference}"
        raise StaticAuditError(msg)
    return relative


def _digest(path: Path) -> str:
    with path.open("rb") as stream:
        return hashlib.file_digest(stream, "sha256").hexdigest()


def _project_root() -> Path:
    for parent in Path(__file__).resolve().parents:
        if (parent / "pyproject.toml").is_file():
            return parent
    raise StaticAuditError(PROJECT_ROOT_NOT_FOUND_MESSAGE)


def _parse_args(argv: Sequence[str] | None) -> ParsedArgs:
    root = _project_root()
    parser = argparse.ArgumentParser(description=__doc__)
    _ = parser.add_argument("--source", type=Path, default=root / DEFAULT_WEB_BUILD_RELATIVE_PATH)
    _ = parser.add_argument("--destination", type=Path, default=root / DEFAULT_PACKAGED_STATIC_RELATIVE_PATH)
    return parser.parse_args(
        argv,
        namespace=ParsedArgs(root / DEFAULT_WEB_BUILD_RELATIVE_PATH, root / DEFAULT_PACKAGED_STATIC_RELATIVE_PATH),
    )


def main(argv: Sequence[str] | None = None) -> int:
    """Audit the source and packaged copies and report a concise result."""
    args = _parse_args(argv)
    try:
        audit_static_export(args.source, args.destination)
    except StaticAuditError as exc:
        print(f"static audit failed: {exc}", file=sys.stderr)
        return 1
    print(f"static audit passed: {args.source} == {args.destination}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
