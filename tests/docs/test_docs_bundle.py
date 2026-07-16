"""
Summary: Enforces documentation bundle conformance for docs/.
Why: Keeps generated documentation frontmatter, indexes, and links from drifting out of sync.
"""

from __future__ import annotations

import re
import shutil
import subprocess
from datetime import datetime, timedelta
from pathlib import Path

import pytest

FrontmatterValue = str | list[str]
FrontmatterFields = dict[str, FrontmatterValue]

PROJECT_ROOT_NOT_FOUND_MESSAGE = "Unable to locate project root from test file."
FRONTMATTER_DELIMITER = "---"
INDEX_FILE_NAME = "index.md"
LOG_FILE_NAME = "log.md"
INDEX_AND_LOG_FILE_NAMES = frozenset({INDEX_FILE_NAME, LOG_FILE_NAME})
REQUIRED_STRING_FIELDS = ("type", "title", "description")
TAGS_FIELD = "tags"
TIMESTAMP_FIELD = "timestamp"
MARKDOWN_FILE_PATTERN = "*.md"
MARKDOWN_LINK_PATTERN = re.compile(r"\]\(([^)]+)\)")
INDEX_ENTRY_PATTERN = re.compile(r"^\*\s+\[(?P<title>[^\]]+)\]\((?P<target>[^)]+)\)\s+-\s+(?P<description>.+)$")
HEADING_PATTERN = re.compile(r"^(#{1,6})\s+(.+?)\s*$")
NON_SLUG_CHAR_PATTERN = re.compile(r"[^\w\s-]")
WHITESPACE_PATTERN = re.compile(r"\s+")
EXTERNAL_LINK_PREFIXES = ("http://", "https://", "mailto:")
RETIRED_DOCS_SEGMENT = "okf"
MIN_QUOTED_LENGTH = 2
QUOTE_CHARACTERS = frozenset({'"', "'"})
TYPE_FIELD = "type"
FRESHNESS_TOLERANCE = timedelta(hours=72)


def test_frontmatter_required_fields() -> None:
    """Every concept doc (non-index, non-log) carries a valid, complete frontmatter block."""
    failures: list[str] = []
    for path in _all_markdown_files():
        if path.name in INDEX_AND_LOG_FILE_NAMES:
            continue
        failures.extend(_frontmatter_failures(path))

    assert not failures, "Frontmatter violations:\n" + "\n".join(failures)


def test_index_files_have_no_frontmatter() -> None:
    """Index files stay frontmatter-free."""
    failures: list[str] = []
    for path in _all_markdown_files():
        if path.name != INDEX_FILE_NAME:
            continue
        failures.extend(_index_frontmatter_failures(path))

    assert not failures, "Index frontmatter violations:\n" + "\n".join(failures)


def test_index_completeness_and_consistency() -> None:
    """Every docs/ directory has an index.md that links and accurately describes each concept file."""
    failures: list[str] = []
    for directory in _all_docs_directories():
        failures.extend(_index_completeness_failures(directory))

    assert not failures, "Index completeness violations:\n" + "\n".join(failures)


def test_links_resolve() -> None:
    """Every relative markdown link resolves to an existing file or directory, with valid anchors."""
    failures: list[str] = []
    for path in _all_markdown_files():
        failures.extend(_link_failures(path))

    assert not failures, "Broken links:\n" + "\n".join(failures)


def test_no_retired_docs_links() -> None:
    """No doc links into the retired docs directory."""
    failures: list[str] = []
    for path in _all_markdown_files():
        failures.extend(_retired_docs_link_failures(path))

    assert not failures, "Links into retired docs directory:\n" + "\n".join(failures)


def test_directories_listed_in_parent_index() -> None:
    """Every docs/ subdirectory is linked and described in its parent directory's index.md."""
    failures: list[str] = []
    for directory in _all_docs_directories():
        if directory == _docs_root():
            continue
        failures.extend(_directory_listing_failures(directory))

    assert not failures, "Directory listing violations:\n" + "\n".join(failures)


def test_directory_type_homogeneity() -> None:
    """Within each docs/ subdirectory, all concept files share one frontmatter 'type' value."""
    failures: list[str] = []
    for directory in _all_docs_directories():
        if directory == _docs_root():
            continue
        failures.extend(_directory_type_homogeneity_failures(directory))

    assert not failures, "Directory type homogeneity violations:\n" + "\n".join(failures)


def test_timestamps_fresh() -> None:
    """A concept file's frontmatter timestamp must not lag its last commit date by more than 72h."""
    if _is_shallow_repository():
        pytest.skip("Repository is shallow; last-commit dates are not reliable.")

    failures: list[str] = []
    for path in _all_markdown_files():
        if path.name in INDEX_AND_LOG_FILE_NAMES:
            continue
        failures.extend(_timestamp_freshness_failures(path))

    assert not failures, "Stale timestamp violations:\n" + "\n".join(failures)


# --- Frontmatter parsing -----------------------------------------------------------------------


def _frontmatter_body(text: str) -> str | None:
    opening = f"{FRONTMATTER_DELIMITER}\n"
    if not text.startswith(opening):
        return None

    closing_marker = f"\n{FRONTMATTER_DELIMITER}"
    closing_index = text.find(closing_marker, len(opening))
    if closing_index == -1:
        return None

    return text[len(opening) : closing_index]


def _parse_frontmatter_fields(body: str) -> FrontmatterFields:
    fields: FrontmatterFields = {}
    for line in body.splitlines():
        if not line.strip():
            continue
        if ":" not in line:
            message = f"malformed frontmatter line (missing ':'): {line!r}"
            raise ValueError(message)
        key, _, raw_value = line.partition(":")
        fields[key.strip()] = _parse_frontmatter_value(raw_value)
    return fields


def _parse_frontmatter_value(raw_value: str) -> FrontmatterValue:
    value = raw_value.strip()
    if value.startswith("[") and value.endswith("]"):
        inner = value[1:-1].strip()
        if not inner:
            return []
        return [_unquote(item.strip()) for item in inner.split(",")]
    return _unquote(value)


def _unquote(value: str) -> str:
    if len(value) >= MIN_QUOTED_LENGTH and value[0] == value[-1] and value[0] in QUOTE_CHARACTERS:
        return value[1:-1]
    return value


def _read_frontmatter_fields(path: Path) -> FrontmatterFields | None:
    body = _frontmatter_body(path.read_text(encoding="utf-8"))
    if body is None:
        return None
    try:
        return _parse_frontmatter_fields(body)
    except ValueError:
        return None


# --- test_frontmatter_required_fields ----------------------------------------------------------


def _frontmatter_failures(path: Path) -> list[str]:
    relative = _relative_to_docs(path)
    text = path.read_text(encoding="utf-8")
    body = _frontmatter_body(text)
    if body is None:
        return [f"{relative}: missing frontmatter block"]

    try:
        fields = _parse_frontmatter_fields(body)
    except ValueError as error:
        return [f"{relative}: {error}"]

    failures: list[str] = []
    failures.extend(_required_string_field_failures(relative, fields))
    failures.extend(_tags_field_failures(relative, fields))
    failures.extend(_timestamp_field_failures(relative, fields))
    return failures


def _required_string_field_failures(relative: str, fields: FrontmatterFields) -> list[str]:
    return [
        f"{relative}: field '{field_name}' must be a non-empty string"
        for field_name in REQUIRED_STRING_FIELDS
        if not _is_nonempty_string(fields.get(field_name))
    ]


def _tags_field_failures(relative: str, fields: FrontmatterFields) -> list[str]:
    tags = fields.get(TAGS_FIELD)
    if isinstance(tags, list) and tags and all(_is_nonempty_string(tag) for tag in tags):
        return []
    return [f"{relative}: field 'tags' must be a non-empty list of non-empty strings"]


def _timestamp_field_failures(relative: str, fields: FrontmatterFields) -> list[str]:
    timestamp = fields.get(TIMESTAMP_FIELD)
    if not isinstance(timestamp, str) or not timestamp.strip():
        return [f"{relative}: field 'timestamp' must be a non-empty string"]
    if not _is_iso8601(timestamp):
        return [f"{relative}: field 'timestamp' is not ISO 8601: {timestamp!r}"]
    return []


def _is_nonempty_string(value: object) -> bool:
    return isinstance(value, str) and bool(value.strip())


def _is_iso8601(value: str) -> bool:
    try:
        _ = datetime.fromisoformat(value)
    except ValueError:
        return False
    return True


# --- test_index_files_have_no_frontmatter -------------------------------------------------------


def _index_frontmatter_failures(path: Path) -> list[str]:
    relative = _relative_to_docs(path)
    text = path.read_text(encoding="utf-8")
    body = _frontmatter_body(text)

    if body is not None:
        return [f"{relative}: index files must not carry frontmatter"]
    return []


# --- test_index_completeness_and_consistency ----------------------------------------------------


def _index_completeness_failures(directory: Path) -> list[str]:
    relative_dir = _relative_to_docs(directory)
    index_path = directory / INDEX_FILE_NAME
    if not index_path.is_file():
        return [f"{relative_dir}: missing index.md"]

    entries_by_target = _index_entries_by_target(index_path)
    return [
        failure
        for concept_file in _concept_files_in(directory)
        for failure in _concept_index_failures(relative_dir, concept_file, entries_by_target)
    ]


def _concept_index_failures(
    relative_dir: str,
    concept_file: Path,
    entries_by_target: dict[str, tuple[str, str]],
) -> list[str]:
    if concept_file.name not in entries_by_target:
        return [f"{relative_dir}/index.md: missing link entry for {concept_file.name}"]

    linked_title, linked_description = entries_by_target[concept_file.name]
    fields = _read_frontmatter_fields(concept_file) or {}
    failures: list[str] = []

    expected_title = fields.get("title")
    if isinstance(expected_title, str) and linked_title != expected_title:
        title_mismatch = (
            f"{relative_dir}/index.md: link title {linked_title!r} for {concept_file.name} "
            f"does not match frontmatter title {expected_title!r}"
        )
        failures.append(title_mismatch)

    expected_description = fields.get("description")
    if isinstance(expected_description, str) and linked_description != expected_description:
        failures.append(
            f"{relative_dir}/index.md: link description for {concept_file.name} does not match frontmatter description"
        )

    return failures


def _concept_files_in(directory: Path) -> list[Path]:
    return sorted(path for path in directory.glob(MARKDOWN_FILE_PATTERN) if path.name not in INDEX_AND_LOG_FILE_NAMES)


def _index_entries_by_target(index_path: Path) -> dict[str, tuple[str, str]]:
    entries: dict[str, tuple[str, str]] = {}
    for line in index_path.read_text(encoding="utf-8").splitlines():
        match = INDEX_ENTRY_PATTERN.match(line)
        if match is None:
            continue
        entries[match.group("target")] = (match.group("title"), match.group("description"))
    return entries


# --- test_links_resolve ---------------------------------------------------------------------


def _link_failures(path: Path) -> list[str]:
    relative = _relative_to_docs(path)
    text = path.read_text(encoding="utf-8")
    failures: list[str] = []
    for raw_target in _markdown_link_targets(text):
        if raw_target.startswith(EXTERNAL_LINK_PREFIXES):
            continue
        failures.extend(_link_target_failures(path, relative, raw_target))
    return failures


def _link_target_failures(path: Path, relative: str, raw_target: str) -> list[str]:
    target_path_part, _, anchor = raw_target.partition("#")
    resolved = (path.parent / target_path_part).resolve() if target_path_part else path.resolve()

    if not resolved.exists():
        return [f"{relative}: broken link target {raw_target!r}"]

    if anchor and resolved.is_file() and resolved.suffix == ".md" and anchor not in _heading_slugs(resolved):
        display_target = target_path_part or path.name
        return [f"{relative}: anchor '#{anchor}' not found in {display_target}"]

    return []


def _heading_slugs(path: Path) -> set[str]:
    slugs: set[str] = set()
    seen_counts: dict[str, int] = {}
    for line in path.read_text(encoding="utf-8").splitlines():
        match = HEADING_PATTERN.match(line)
        if match is None:
            continue
        slug = _slugify(match.group(2))
        occurrence = seen_counts.get(slug, 0)
        seen_counts[slug] = occurrence + 1
        slugs.add(slug if occurrence == 0 else f"{slug}-{occurrence}")
    return slugs


def _slugify(heading_text: str) -> str:
    lowered = heading_text.strip().lower()
    without_punctuation = NON_SLUG_CHAR_PATTERN.sub("", lowered)
    return WHITESPACE_PATTERN.sub("-", without_punctuation.strip())


# --- test_no_retired_docs_links -----------------------------------------------------------------


def _retired_docs_link_failures(path: Path) -> list[str]:
    relative = _relative_to_docs(path)
    text = path.read_text(encoding="utf-8")
    failures: list[str] = []
    for raw_target in _markdown_link_targets(text):
        if raw_target.startswith(EXTERNAL_LINK_PREFIXES):
            continue
        target_path_part = raw_target.partition("#")[0]
        if target_path_part and RETIRED_DOCS_SEGMENT in Path(target_path_part).parts:
            failures.append(f"{relative}: links into retired docs directory: {raw_target!r}")
    return failures


def _markdown_link_targets(text: str) -> list[str]:
    targets: list[str] = MARKDOWN_LINK_PATTERN.findall(text)
    return targets


# --- test_directories_listed_in_parent_index ----------------------------------------------------


def _directory_listing_failures(directory: Path) -> list[str]:
    relative_parent = _relative_to_docs(directory.parent)
    dir_name = directory.name
    parent_index = directory.parent / INDEX_FILE_NAME
    if not parent_index.is_file():
        return [f"{relative_parent}/index.md: missing, cannot list subdirectory {dir_name}/"]

    entries_by_target = _index_entries_by_target(parent_index)
    expected_targets = (f"{dir_name}/", f"{dir_name}/{INDEX_FILE_NAME}")
    matched_targets = [target for target in expected_targets if target in entries_by_target]

    if not matched_targets:
        return [f"{relative_parent}/index.md: missing link entry for subdirectory {dir_name}/"]

    _, description = entries_by_target[matched_targets[0]]
    if not description.strip():
        return [f"{relative_parent}/index.md: link entry for subdirectory {dir_name}/ has an empty description"]

    return []


# --- test_directory_type_homogeneity ------------------------------------------------------------


def _directory_type_homogeneity_failures(directory: Path) -> list[str]:
    relative_dir = _relative_to_docs(directory)
    types_by_file: dict[str, str] = {}
    for concept_file in _concept_files_in(directory):
        fields = _read_frontmatter_fields(concept_file) or {}
        type_value = fields.get(TYPE_FIELD)
        if isinstance(type_value, str) and type_value.strip():
            types_by_file[concept_file.name] = type_value

    distinct_types = set(types_by_file.values())
    if len(distinct_types) <= 1:
        return []

    details = ", ".join(f"{name}={type_value!r}" for name, type_value in sorted(types_by_file.items()))
    return [f"{relative_dir}: mixed frontmatter 'type' values across concept files: {details}"]


# --- test_timestamps_fresh -----------------------------------------------------------------------

GIT_EXECUTABLE: str = shutil.which("git") or "git"


def _run_git(*args: str) -> str:
    # Trusted, hardcoded git subcommands over a resolved executable path; no untrusted input.
    result = subprocess.run(  # noqa: S603
        [GIT_EXECUTABLE, *args],
        cwd=_project_root(),
        capture_output=True,
        text=True,
        check=True,
    )
    return result.stdout.strip()


def _is_shallow_repository() -> bool:
    return _run_git("rev-parse", "--is-shallow-repository") == "true"


def _has_uncommitted_changes(path: Path) -> bool:
    return bool(_run_git("status", "--porcelain", "--", str(path)))


def _last_commit_date(path: Path) -> str:
    return _run_git("log", "-1", "--format=%cI", "--", str(path))


def _frontmatter_timestamp(path: Path) -> str | None:
    fields = _read_frontmatter_fields(path)
    if fields is None:
        return None
    timestamp = fields.get(TIMESTAMP_FIELD)
    if isinstance(timestamp, str) and timestamp.strip():
        return timestamp
    return None


def _parse_freshness_dates(timestamp: str, commit_date_raw: str) -> tuple[datetime, datetime] | None:
    try:
        return datetime.fromisoformat(timestamp), datetime.fromisoformat(commit_date_raw)
    except ValueError:
        return None


def _timestamp_freshness_failures(path: Path) -> list[str]:
    relative = _relative_to_docs(path)
    if _has_uncommitted_changes(path):
        return []

    commit_date_raw = _last_commit_date(path)
    if not commit_date_raw:
        return []

    timestamp = _frontmatter_timestamp(path)
    if timestamp is None:
        return []

    parsed = _parse_freshness_dates(timestamp, commit_date_raw)
    if parsed is None:
        return []

    timestamp_value, commit_date = parsed
    if timestamp_value >= commit_date - FRESHNESS_TOLERANCE:
        return []
    return [f"{relative}: frontmatter timestamp {timestamp!r} is stale relative to last commit {commit_date_raw!r}"]


# --- shared path helpers -----------------------------------------------------------------------


def _all_markdown_files() -> list[Path]:
    return sorted(_docs_root().rglob(MARKDOWN_FILE_PATTERN))


def _all_docs_directories() -> list[Path]:
    docs_root = _docs_root()
    directories = {docs_root}
    directories.update(path for path in docs_root.rglob("*") if path.is_dir())
    return sorted(directories)


def _relative_to_docs(path: Path) -> str:
    return str(path.resolve().relative_to(_docs_root()))


def _docs_root() -> Path:
    return _project_root() / "docs"


def _project_root() -> Path:
    current_file = Path(__file__).resolve()
    for parent in current_file.parents:
        if (parent / "pyproject.toml").is_file():
            return parent
    raise RuntimeError(PROJECT_ROOT_NOT_FOUND_MESSAGE)
