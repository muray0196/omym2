# ruff: noqa: INP001 -- Standalone script-local module shared by developer docs tools.
"""
Summary: Builds the script-local OKF docs catalog from Markdown frontmatter and content.
Why: Keeps docs search, docs routing, and local LLM docs selection on one parser.
"""

from __future__ import annotations

import hashlib
import re
from dataclasses import dataclass
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from pathlib import Path

FRONTMATTER_DELIMITER = "---"
INDEX_FILE_NAME = "index.md"
LOG_FILE_NAME = "log.md"
INDEX_AND_LOG_FILE_NAMES = frozenset({INDEX_FILE_NAME, LOG_FILE_NAME})
MARKDOWN_SUFFIX = ".md"
TAGS_FIELD = "tags"
TYPE_FIELD = "type"
TITLE_FIELD = "title"
DESCRIPTION_FIELD = "description"
MIN_QUOTED_LENGTH = 2
QUOTE_CHARACTERS = frozenset({'"', "'"})
DEFAULT_EXCERPT_CHAR_LIMIT = 1_500
CONTENT_HASH_ALGORITHM = "sha256"
TOKEN_PATTERN: re.Pattern[str] = re.compile(r"[a-z0-9_./-]+")
HEADING_PATTERN: re.Pattern[str] = re.compile(r"^(#{1,6})\s+(.+?)\s*$")
NON_SLUG_CHAR_PATTERN: re.Pattern[str] = re.compile(r"[^\w\s-]")
WHITESPACE_PATTERN: re.Pattern[str] = re.compile(r"\s+")
MARKDOWN_LINK_PATTERN: re.Pattern[str] = re.compile(r"\]\(([^)]+)\)")
ROUTING_FIELD_SEPARATOR = "; "

FrontmatterValue = str | list[str]


@dataclass(frozen=True, slots=True)
class Heading:
    """Markdown heading location and stable GitHub-style anchor."""

    level: int
    title: str
    slug: str
    line: int
    end_line: int


@dataclass(frozen=True, slots=True)
class DocCard:
    """One OKF concept doc represented for search and routing."""

    path: str
    docs_path: str
    content_hash: str
    doc_type: str
    title: str
    description: str
    tags: tuple[str, ...]
    headings: tuple[Heading, ...]
    links: tuple[str, ...]
    excerpt: str
    routing_text: str
    lines: tuple[str, ...]


def build_doc_cards(docs_root: Path, repo_root: Path | None = None) -> list[DocCard]:
    """Return all concept docs under docs_root as routing cards."""
    resolved_docs_root = docs_root.resolve()
    root = repo_root.resolve() if repo_root is not None else resolved_docs_root.parent
    return [_doc_card(path, resolved_docs_root, root) for path in concept_files(resolved_docs_root)]


def concept_files(docs_root: Path) -> list[Path]:
    """Return Markdown concept files, excluding generated routers and logs."""
    return sorted(path for path in docs_root.rglob(f"*{MARKDOWN_SUFFIX}") if path.name not in INDEX_AND_LOG_FILE_NAMES)


def tokens(text: str) -> tuple[str, ...]:
    """Return stable lower-case search tokens."""
    return tuple(dict.fromkeys(TOKEN_PATTERN.findall(text.lower())))


def _doc_card(path: Path, docs_root: Path, repo_root: Path) -> DocCard:
    text = _read_doc_text(path)
    fields = _frontmatter_fields(text)
    headings = tuple(_headings(text))
    repo_relative_path = path.relative_to(repo_root).as_posix()
    docs_relative_path = path.relative_to(docs_root).as_posix()
    excerpt = _excerpt_text(text)
    links = tuple(_links(text))
    card = DocCard(
        path=repo_relative_path,
        docs_path=docs_relative_path,
        content_hash=_content_hash(text),
        doc_type=_string_field(fields, TYPE_FIELD),
        title=_string_field(fields, TITLE_FIELD),
        description=_string_field(fields, DESCRIPTION_FIELD),
        tags=_tags_field(fields),
        headings=headings,
        links=links,
        excerpt=excerpt,
        routing_text="",
        lines=tuple(text.splitlines()),
    )
    return DocCard(
        path=card.path,
        docs_path=card.docs_path,
        content_hash=card.content_hash,
        doc_type=card.doc_type,
        title=card.title,
        description=card.description,
        tags=card.tags,
        headings=card.headings,
        links=card.links,
        excerpt=card.excerpt,
        routing_text=_routing_text(card),
        lines=card.lines,
    )


def _routing_text(card: DocCard) -> str:
    headings = ROUTING_FIELD_SEPARATOR.join(heading.title for heading in card.headings)
    links = ROUTING_FIELD_SEPARATOR.join(card.links)
    return "\n".join(
        (
            f"Path: {card.path}",
            f"Type: {card.doc_type}",
            f"Title: {card.title}",
            f"Description: {card.description}",
            f"Tags: {', '.join(card.tags)}",
            f"Headings: {headings}",
            f"Links: {links}",
            f"Excerpt: {card.excerpt}",
        )
    )


def _content_hash(text: str) -> str:
    return hashlib.new(CONTENT_HASH_ALGORITHM, text.encode("utf-8")).hexdigest()


def _excerpt_text(text: str) -> str:
    body = _body_without_frontmatter(text)
    normalized = WHITESPACE_PATTERN.sub(" ", body).strip()
    if len(normalized) <= DEFAULT_EXCERPT_CHAR_LIMIT:
        return normalized
    return f"{normalized[: DEFAULT_EXCERPT_CHAR_LIMIT - 3].rstrip()}..."


def _body_without_frontmatter(text: str) -> str:
    body = _frontmatter_body(text)
    if body is None:
        return text
    closing_marker = f"\n{FRONTMATTER_DELIMITER}"
    closing_index = text.find(closing_marker, len(FRONTMATTER_DELIMITER) + 1)
    if closing_index == -1:
        return text
    return text[closing_index + len(closing_marker) :].lstrip()


def _links(text: str) -> list[str]:
    return sorted(dict.fromkeys(match.group(1).strip() for match in MARKDOWN_LINK_PATTERN.finditer(text)))


def _read_doc_text(path: Path) -> str:
    try:
        return path.read_text(encoding="utf-8")
    except OSError:
        return ""


def _frontmatter_fields(text: str) -> dict[str, FrontmatterValue]:
    body = _frontmatter_body(text)
    if body is None:
        return {}
    return _parse_frontmatter_fields(body)


def _frontmatter_body(text: str) -> str | None:
    opening = f"{FRONTMATTER_DELIMITER}\n"
    if not text.startswith(opening):
        return None

    closing_marker = f"\n{FRONTMATTER_DELIMITER}"
    closing_index = text.find(closing_marker, len(opening))
    if closing_index == -1:
        return None

    return text[len(opening) : closing_index]


def _parse_frontmatter_fields(body: str) -> dict[str, FrontmatterValue]:
    fields: dict[str, FrontmatterValue] = {}
    for line in body.splitlines():
        if not line.strip() or ":" not in line:
            continue
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


def _string_field(fields: dict[str, FrontmatterValue], key: str) -> str:
    value = fields.get(key)
    return value if isinstance(value, str) else ""


def _tags_field(fields: dict[str, FrontmatterValue]) -> tuple[str, ...]:
    value = fields.get(TAGS_FIELD)
    if not isinstance(value, list):
        return ()
    return tuple(value)


def _headings(text: str) -> list[Heading]:
    raw_headings = _raw_headings(text)
    headings: list[Heading] = []
    line_count = len(text.splitlines())
    for index, raw_heading in enumerate(raw_headings):
        next_line = raw_headings[index + 1].line if index + 1 < len(raw_headings) else line_count + 1
        headings.append(
            Heading(
                level=raw_heading.level,
                title=raw_heading.title,
                slug=raw_heading.slug,
                line=raw_heading.line,
                end_line=next_line - 1,
            )
        )
    return headings


def _raw_headings(text: str) -> list[Heading]:
    headings: list[Heading] = []
    seen_counts: dict[str, int] = {}
    in_fenced_code = False
    for line_number, line in enumerate(text.splitlines(), start=1):
        if line.strip().startswith("```"):
            in_fenced_code = not in_fenced_code
            continue
        if in_fenced_code:
            continue
        match = HEADING_PATTERN.match(line)
        if match is None:
            continue
        base_slug = _slugify(match.group(2))
        occurrence = seen_counts.get(base_slug, 0)
        seen_counts[base_slug] = occurrence + 1
        slug = base_slug if occurrence == 0 else f"{base_slug}-{occurrence}"
        headings.append(
            Heading(
                level=len(match.group(1)),
                title=match.group(2),
                slug=slug,
                line=line_number,
                end_line=line_number,
            )
        )
    return headings


def _slugify(heading_text: str) -> str:
    lowered = heading_text.strip().lower()
    without_punctuation = NON_SLUG_CHAR_PATTERN.sub("", lowered)
    return WHITESPACE_PATTERN.sub("-", without_punctuation.strip())
