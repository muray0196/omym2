# ruff: noqa: INP001 -- Standalone repo-maintenance script, not part of an importable package.
"""
Summary: Searches OKF docs frontmatter, headings, and section bodies directly from Markdown.
Why: Lets coding agents find and cite authoritative docs sections without a generated index artifact.
"""

from __future__ import annotations

import argparse
import json
import re
import sys
from dataclasses import dataclass
from pathlib import Path

from docs_catalog import DocCard, Heading, build_doc_cards, project_root, tokens

BODY_WEIGHT = 4
PATH_WEIGHT = 8
TYPE_WEIGHT = 10
DESCRIPTION_WEIGHT = 16
TAG_WEIGHT = 24
SECTION_TITLE_WEIGHT = 32
TITLE_WEIGHT = 40
EXACT_PHRASE_MULTIPLIER = 3
DEFAULT_LIMIT = 8
SNIPPET_LIMIT = 220
MARKDOWN_DECORATION_PATTERN: re.Pattern[str] = re.compile(r"^[#*\-\s>|`]+")

JsonObject = dict[str, object]


class SearchError(Exception):
    """Raised when the docs tree cannot be searched."""


class ParsedArgs(argparse.Namespace):
    """Typed argparse result used after parser validation."""

    def __init__(self) -> None:
        super().__init__()
        self.query: list[str] = []
        self.doc_type: str | None = None
        self.limit: int = DEFAULT_LIMIT
        self.json_output: bool = False
        self.docs_root: Path | None = None


@dataclass(frozen=True)
class SearchHit:
    """A ranked docs section result."""

    score: int
    path: str
    line: int
    anchor: str
    title: str
    section: str
    doc_type: str
    reasons: tuple[str, ...]
    snippet: str

    def as_json(self) -> JsonObject:
        """Return a stable JSON result for agents and tests."""
        return {
            "score": self.score,
            "path": self.path,
            "line": self.line,
            "anchor": self.anchor,
            "title": self.title,
            "section": self.section,
            "type": self.doc_type,
            "reasons": list(self.reasons),
            "snippet": self.snippet,
        }


@dataclass(frozen=True)
class DocumentRecord:
    """One searchable docs file parsed from Markdown at query time."""

    path: str
    doc_type: str
    title: str
    description: str
    tags: tuple[str, ...]
    headings: tuple[Heading, ...]
    lines: tuple[str, ...]


@dataclass(frozen=True)
class ScoredSection:
    """A section whose title or body matched the query."""

    score: int
    heading: Heading
    reasons: tuple[str, ...]
    body_text: str


@dataclass(frozen=True)
class QueryTerms:
    """Normalized query text used by scoring and snippets."""

    phrase: str
    tokens: tuple[str, ...]


def main(argv: list[str] | None = None) -> int:
    """Search docs and print ranked section references."""
    args = _parse_args(argv)
    docs_root = args.docs_root if args.docs_root is not None else project_root() / "docs"
    try:
        hits = search_docs(
            query=" ".join(args.query),
            limit=args.limit,
            doc_type=args.doc_type,
            docs_root=docs_root,
        )
    except SearchError as error:
        _ = sys.stderr.write(f"docs search failed: {error}\n")
        return 2

    if args.json_output:
        _ = sys.stdout.write(f"{json.dumps([hit.as_json() for hit in hits], ensure_ascii=False, indent=2)}\n")
        return 0

    _print_text_results(hits)
    return 0


def search_docs(query: str, limit: int, doc_type: str | None, docs_root: Path) -> list[SearchHit]:
    """Return ranked section hits for a docs query, parsing docs/ in memory."""
    if not docs_root.is_dir():
        message = f"{docs_root} does not exist or is not a directory"
        raise SearchError(message)

    terms = QueryTerms(phrase=query.lower(), tokens=tokens(query))
    if not terms.tokens:
        return []

    hits: list[SearchHit] = []
    for document in _documents(docs_root):
        if doc_type and document.doc_type != doc_type:
            continue
        hits.extend(_document_hits(document, terms))
    return sorted(hits, key=lambda hit: (-hit.score, hit.path, hit.line))[:limit]


def _parse_args(argv: list[str] | None) -> ParsedArgs:
    parser = argparse.ArgumentParser(description="Search OMYM2 docs frontmatter, headings, and sections.")
    _ = parser.add_argument("query", nargs="+", help="Search query.")
    _ = parser.add_argument("--type", dest="doc_type", default=None, help="Restrict results to one OKF type value.")
    _ = parser.add_argument("--limit", type=int, default=DEFAULT_LIMIT, help="Maximum number of results.")
    _ = parser.add_argument("--json", dest="json_output", action="store_true", help="Print machine-readable JSON.")
    _ = parser.add_argument(
        "--docs-root",
        type=Path,
        default=None,
        help="Docs directory to search; defaults to the repo docs/ directory.",
    )
    args = parser.parse_args(argv, namespace=ParsedArgs())
    if args.limit < 1:
        parser.error("--limit must be at least 1")
    return args


def _documents(docs_root: Path) -> list[DocumentRecord]:
    return [_document_record(card) for card in build_doc_cards(docs_root)]


def _document_record(card: DocCard) -> DocumentRecord:
    return DocumentRecord(
        path=card.path,
        doc_type=card.doc_type,
        title=card.title,
        description=card.description,
        tags=card.tags,
        headings=card.headings,
        lines=card.lines,
    )


def _document_hits(document: DocumentRecord, terms: QueryTerms) -> list[SearchHit]:
    doc_score, doc_reasons = _doc_level_score(document, terms)
    scored_sections = _scored_sections(document, terms)

    if not scored_sections:
        if doc_score <= 0:
            return []
        return [_doc_level_hit(document, doc_score, doc_reasons, terms)]

    best = min(scored_sections, key=lambda section: (-section.score, section.heading.line))
    hits: list[SearchHit] = []
    for section in scored_sections:
        score = section.score
        reasons = section.reasons
        if section is best:
            score += doc_score
            reasons = tuple(dict.fromkeys((*doc_reasons, *section.reasons)))
        hits.append(
            SearchHit(
                score=score,
                path=document.path,
                line=section.heading.line,
                anchor=section.heading.slug,
                title=document.title,
                section=section.heading.title,
                doc_type=document.doc_type,
                reasons=reasons,
                snippet=_snippet(section.body_text, document.description, terms.tokens),
            )
        )
    return hits


def _scored_sections(document: DocumentRecord, terms: QueryTerms) -> list[ScoredSection]:
    scored: list[ScoredSection] = []
    for heading in document.headings:
        body_text = "\n".join(document.lines[heading.line : heading.end_line])
        reasons: list[str] = []
        score = 0
        score += _score_field(heading.title, terms, SECTION_TITLE_WEIGHT, reasons, "section")
        score += _score_field(body_text, terms, BODY_WEIGHT, reasons, "body")
        if score > 0:
            scored.append(
                ScoredSection(score=score, heading=heading, reasons=tuple(dict.fromkeys(reasons)), body_text=body_text)
            )
    return scored


def _doc_level_score(document: DocumentRecord, terms: QueryTerms) -> tuple[int, tuple[str, ...]]:
    reasons: list[str] = []
    score = 0
    score += _score_field(document.title, terms, TITLE_WEIGHT, reasons, "title")
    score += _score_field(" ".join(document.tags), terms, TAG_WEIGHT, reasons, "tags")
    score += _score_field(document.description, terms, DESCRIPTION_WEIGHT, reasons, "description")
    score += _score_field(document.doc_type, terms, TYPE_WEIGHT, reasons, "type")
    score += _score_field(document.path, terms, PATH_WEIGHT, reasons, "path")
    return score, tuple(dict.fromkeys(reasons))


def _doc_level_hit(
    document: DocumentRecord,
    doc_score: int,
    doc_reasons: tuple[str, ...],
    terms: QueryTerms,
) -> SearchHit:
    first_heading = document.headings[0] if document.headings else None
    return SearchHit(
        score=doc_score,
        path=document.path,
        line=first_heading.line if first_heading else 1,
        anchor=first_heading.slug if first_heading else "",
        title=document.title,
        section=first_heading.title if first_heading else document.title,
        doc_type=document.doc_type,
        reasons=doc_reasons,
        snippet=_snippet("", document.description, terms.tokens),
    )


def _score_field(
    text: str,
    terms: QueryTerms,
    weight: int,
    reasons: list[str],
    reason: str,
) -> int:
    haystack = text.lower()
    score = 0
    if terms.phrase in haystack:
        score += weight * EXACT_PHRASE_MULTIPLIER
        reasons.append(reason)
    token_hits = sum(1 for token in terms.tokens if token in haystack)
    if token_hits:
        score += token_hits * weight
        reasons.append(reason)
    return score


def _snippet(section_text: str, fallback: str, tokens: tuple[str, ...]) -> str:
    best_line = ""
    best_score = 0
    for line in section_text.splitlines():
        cleaned = _clean_snippet_line(line)
        if not cleaned:
            continue
        token_hits = sum(1 for token in tokens if token in cleaned.lower())
        if token_hits > best_score:
            best_line = cleaned
            best_score = token_hits
    if best_line:
        return _clip(best_line)
    return _clip(fallback)


def _clean_snippet_line(line: str) -> str:
    return MARKDOWN_DECORATION_PATTERN.sub("", line).strip()


def _clip(text: str) -> str:
    if len(text) <= SNIPPET_LIMIT:
        return text
    return f"{text[: SNIPPET_LIMIT - 3].rstrip()}..."


def _print_text_results(hits: list[SearchHit]) -> None:
    if not hits:
        _ = sys.stdout.write("no docs matches\n")
        return

    for hit in hits:
        _ = sys.stdout.write(f"{hit.path}:{hit.line} {hit.section} #{hit.anchor}\n")
        _ = sys.stdout.write(f"  score={hit.score} match={','.join(hit.reasons)} type={hit.doc_type}\n")
        if hit.snippet:
            _ = sys.stdout.write(f"  {hit.snippet}\n")


if __name__ == "__main__":
    raise SystemExit(main())
