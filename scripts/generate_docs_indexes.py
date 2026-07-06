# ruff: noqa: INP001 -- Standalone repo-maintenance script, not part of an importable package.
"""
Summary: Generates docs/ index.md files from concept files' frontmatter (title, description).
Why: Makes frontmatter the single source of truth for docs/ indexes instead of hand-maintaining links.
"""

from __future__ import annotations

import argparse
import sys
from dataclasses import dataclass
from pathlib import Path

PROJECT_ROOT_NOT_FOUND_MESSAGE = "Unable to locate project root from script file."
FRONTMATTER_DELIMITER = "---"
INDEX_FILE_NAME = "index.md"
LOG_FILE_NAME = "log.md"
INDEX_AND_LOG_FILE_NAMES = frozenset({INDEX_FILE_NAME, LOG_FILE_NAME})
MARKDOWN_SUFFIX = ".md"
TITLE_FIELD = "title"
DESCRIPTION_FIELD = "description"
MIN_QUOTED_LENGTH = 2
QUOTE_CHARACTERS = frozenset({'"', "'"})
DEFAULT_DIRECTORIES_HEADING = "Directories"


class GenerationError(Exception):
    """Raised when docs/ content or metadata cannot produce a valid index."""


class ParsedArgs(argparse.Namespace):
    """Typed argparse result used after parser validation."""

    def __init__(self) -> None:
        super().__init__()
        self.check: bool = False
        self.write: bool = False


@dataclass(frozen=True)
class DirectoryMetadata:
    """Presentation metadata used to render one docs/ directory's index.md.

    `heading` and `intro` control this directory's own index.md body. `display_name`
    and `parent_description` control how this directory is listed as an entry in its
    *parent's* index.md (only relevant for non-root directories). `file_order` pins an
    explicit order for concept-file entries; any concept files not named fall back to
    alphabetical order appended after it.
    """

    heading: str
    intro: str | None = None
    display_name: str = ""
    parent_description: str = ""
    file_order: tuple[str, ...] = ()
    directories_heading: str = DEFAULT_DIRECTORIES_HEADING


# Keyed by docs-relative POSIX directory path; "" is the docs/ bundle root.
DIRECTORY_METADATA: dict[str, DirectoryMetadata] = {
    "": DirectoryMetadata(
        heading="Core Documentation",
        file_order=(
            "PRODUCT.md",
            "DOMAIN.md",
            "STORAGE.md",
            "DEVELOPMENT.md",
            "TESTING.md",
            "COMMANDS.md",
        ),
    ),
    "codebase": DirectoryMetadata(
        heading="Codebase",
        intro="This folder contains detailed source layout, dependency, port, and naming rules.",
        display_name="Codebase",
        parent_description="Source layout, dependency, port, and naming rules.",
        file_order=(
            "source-layout.md",
            "dependency-boundaries.md",
            "ports-uow.md",
            "naming.md",
            "web-frontend.md",
        ),
    ),
    "contracts": DirectoryMetadata(
        heading="Contracts",
        intro=("This folder contains concrete contracts for persisted state and externally\nobservable values."),
        display_name="Contracts",
        parent_description="Config, DB schema, path identity, storage representation, and status values.",
        file_order=(
            "config.md",
            "db-schema.md",
            "path-identity-storage.md",
            "status-reason-catalog.md",
        ),
    ),
    "execution": DirectoryMetadata(
        heading="Execution",
        intro="Use this file as the execution router. Read the focused file for the task.",
        display_name="Execution",
        parent_description="Plan, apply, undo, refresh, organize, check, and failure semantics.",
        file_order=(
            "model.md",
            "failure-policy.md",
            "add.md",
            "organize.md",
            "refresh.md",
            "apply.md",
            "undo.md",
            "check.md",
        ),
    ),
}


def main(argv: list[str] | None = None) -> int:
    """Run the docs/ index generator in --check or --write mode."""
    args = _parse_args(argv)
    docs_root = _docs_root()

    try:
        generated_by_path = _generate_all(docs_root)
    except GenerationError as error:
        _ = sys.stderr.write(f"docs index generation failed: {error}\n")
        return 2

    if args.write:
        _write_all(generated_by_path)
        _ = sys.stdout.write(f"wrote {len(generated_by_path)} index.md file(s)\n")
        return 0

    return _check_all(generated_by_path)


# --- CLI ------------------------------------------------------------------------------------


def _parse_args(argv: list[str] | None) -> ParsedArgs:
    parser = argparse.ArgumentParser(description="Generate docs/ index.md files from frontmatter.")
    mode = parser.add_mutually_exclusive_group(required=True)
    _ = mode.add_argument(
        "--check",
        action="store_true",
        help="Compare generated indexes against disk; write nothing; exit 1 on any mismatch.",
    )
    _ = mode.add_argument(
        "--write",
        action="store_true",
        help="Write generated indexes to disk.",
    )
    return parser.parse_args(argv, namespace=ParsedArgs())


# --- Generation -------------------------------------------------------------------------------


def _generate_all(docs_root: Path) -> dict[Path, str]:
    return {
        directory / INDEX_FILE_NAME: _render_index(directory, docs_root) for directory in _docs_directories(docs_root)
    }


def _render_index(directory: Path, docs_root: Path) -> str:
    relative_key = _relative_key(directory, docs_root)
    metadata = _metadata_for(relative_key, directory)

    lines: list[str] = []
    lines.append(f"# {metadata.heading}")
    lines.append("")
    if metadata.intro:
        lines.extend(metadata.intro.split("\n"))
        lines.append("")

    for concept_file in _ordered_concept_files(directory, metadata, relative_key):
        fields = _frontmatter_title_and_description(concept_file)
        lines.append(f"* [{fields[TITLE_FIELD]}]({concept_file.name}) - {fields[DESCRIPTION_FIELD]}")

    subdirectories = _subdirectories(directory)
    if subdirectories:
        _append_section_break(lines)
        lines.append(f"# {metadata.directories_heading}")
        lines.append("")
        for subdirectory in subdirectories:
            sub_key = _relative_key(subdirectory, docs_root)
            sub_metadata = _metadata_for(sub_key, subdirectory)
            if not sub_metadata.parent_description:
                message = (
                    f"docs/{sub_key}: no non-empty parent_description in DIRECTORY_METADATA; "
                    "add an entry to scripts/generate_docs_indexes.py's DIRECTORY_METADATA "
                    "with a non-empty parent_description so it can be listed in its parent index."
                )
                raise GenerationError(message)
            lines.append(f"* [{sub_metadata.display_name}]({subdirectory.name}/) - {sub_metadata.parent_description}")

    return "\n".join(lines).rstrip("\n") + "\n"


def _append_section_break(lines: list[str]) -> None:
    if lines and lines[-1] != "":
        lines.append("")


def _metadata_for(relative_key: str, directory: Path) -> DirectoryMetadata:
    metadata = DIRECTORY_METADATA.get(relative_key)
    if metadata is not None:
        return metadata
    return DirectoryMetadata(heading=directory.name.replace("-", " ").capitalize(), display_name=directory.name)


def _ordered_concept_files(directory: Path, metadata: DirectoryMetadata, relative_key: str) -> list[Path]:
    files_by_name = {path.name: path for path in _concept_files(directory)}
    if not metadata.file_order:
        return [files_by_name[name] for name in sorted(files_by_name)]

    missing = [name for name in metadata.file_order if name not in files_by_name]
    if missing:
        location = f"docs/{relative_key}" if relative_key else "docs"
        message = f"{location}: DIRECTORY_METADATA file_order references missing file(s) {missing}"
        raise GenerationError(message)

    remaining = sorted(name for name in files_by_name if name not in metadata.file_order)
    return [files_by_name[name] for name in (*metadata.file_order, *remaining)]


def _concept_files(directory: Path) -> list[Path]:
    return [
        path
        for path in directory.iterdir()
        if path.is_file() and path.suffix == MARKDOWN_SUFFIX and path.name not in INDEX_AND_LOG_FILE_NAMES
    ]


def _subdirectories(directory: Path) -> list[Path]:
    return sorted((path for path in directory.iterdir() if path.is_dir()), key=lambda path: path.name)


def _docs_directories(docs_root: Path) -> list[Path]:
    directories = [docs_root]
    directories.extend(
        sorted((path for path in docs_root.rglob("*") if path.is_dir()), key=lambda path: path.as_posix())
    )
    return directories


def _relative_key(directory: Path, docs_root: Path) -> str:
    if directory == docs_root:
        return ""
    return directory.relative_to(docs_root).as_posix()


# --- Frontmatter parsing -----------------------------------------------------------------------


def _frontmatter_title_and_description(path: Path) -> dict[str, str]:
    text = path.read_text(encoding="utf-8")
    body = _frontmatter_body(text)
    if body is None:
        message = f"{path}: missing frontmatter block"
        raise GenerationError(message)

    fields = _parse_frontmatter_fields(body)
    result: dict[str, str] = {}
    for field_name in (TITLE_FIELD, DESCRIPTION_FIELD):
        value = fields.get(field_name)
        if not value:
            message = f"{path}: frontmatter field '{field_name}' must be a non-empty string"
            raise GenerationError(message)
        result[field_name] = value
    return result


def _frontmatter_body(text: str) -> str | None:
    opening = f"{FRONTMATTER_DELIMITER}\n"
    if not text.startswith(opening):
        return None

    closing_marker = f"\n{FRONTMATTER_DELIMITER}"
    closing_index = text.find(closing_marker, len(opening))
    if closing_index == -1:
        return None

    return text[len(opening) : closing_index]


def _parse_frontmatter_fields(body: str) -> dict[str, str]:
    fields: dict[str, str] = {}
    for line in body.splitlines():
        if not line.strip():
            continue
        if ":" not in line:
            continue
        key, _, raw_value = line.partition(":")
        fields[key.strip()] = _unquote(raw_value.strip())
    return fields


def _unquote(value: str) -> str:
    if len(value) >= MIN_QUOTED_LENGTH and value[0] == value[-1] and value[0] in QUOTE_CHARACTERS:
        return value[1:-1]
    return value


# --- --check / --write ------------------------------------------------------------------------


def _check_all(generated_by_path: dict[Path, str]) -> int:
    differs: list[Path] = []
    missing: list[Path] = []
    for path, generated in sorted(generated_by_path.items()):
        if not path.is_file():
            missing.append(path)
            continue
        if path.read_text(encoding="utf-8") != generated:
            differs.append(path)

    if not differs and not missing:
        _ = sys.stdout.write("docs indexes are up to date\n")
        return 0

    for path in missing:
        _ = sys.stdout.write(f"missing: {path}\n")
    for path in differs:
        _ = sys.stdout.write(f"differs: {path}\n")
    _ = sys.stdout.write("docs indexes are out of date; run `python scripts/generate_docs_indexes.py --write`\n")
    return 1


def _write_all(generated_by_path: dict[Path, str]) -> None:
    for path, generated in generated_by_path.items():
        _ = path.write_text(generated, encoding="utf-8")


# --- shared path helpers -----------------------------------------------------------------------


def _docs_root() -> Path:
    return _project_root() / "docs"


def _project_root() -> Path:
    current_file = Path(__file__).resolve()
    for parent in current_file.parents:
        if (parent / "pyproject.toml").is_file():
            return parent
    raise RuntimeError(PROJECT_ROOT_NOT_FOUND_MESSAGE)


if __name__ == "__main__":
    raise SystemExit(main())
