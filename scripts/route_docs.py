# ruff: noqa: INP001 -- Standalone repo-maintenance script, not part of an importable package.
"""
Summary: Routes natural-language tasks to the OMYM2 docs an agent should read.
Why: Gives agents a low-maintenance reading list built from OKF frontmatter and Markdown content.
"""

from __future__ import annotations

import argparse
import json
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import cast

from docs_catalog import DocCard, build_doc_cards, tokens

PROJECT_ROOT_NOT_FOUND_MESSAGE = "Unable to locate project root from script file."
REQUIRED_ARCHITECTURE_DOC = "ARCHITECTURE.md"
DOCS_INDEX_FALLBACK = "docs/index.md"
DEFAULT_ROUTE_LIMIT = 5
DEFAULT_SELECTOR_CANDIDATE_LIMIT = 20
EXACT_PHRASE_MULTIPLIER = 3
EXACT_PATH_MATCH_WEIGHT = 50
FILENAME_TOKEN_WEIGHT = 35
TITLE_TOKEN_WEIGHT = 25
TAG_TOKEN_WEIGHT = 20
DESCRIPTION_TOKEN_WEIGHT = 10
TYPE_TOKEN_WEIGHT = 8
HEADING_TOKEN_WEIGHT = 6
LINK_TOKEN_WEIGHT = 4
EXCERPT_TOKEN_WEIGHT = 2
HIGH_CONFIDENCE_SCORE = 80
MEDIUM_CONFIDENCE_SCORE = 25
MAX_REASON_FIELDS = 5
MIN_SINGULARIZE_TOKEN_LENGTH = 4
BROAD_QUERY_TOKENS = frozenset(
    {
        "a",
        "about",
        "an",
        "and",
        "are",
        "change",
        "docs",
        "documentation",
        "do",
        "does",
        "for",
        "help",
        "how",
        "i",
        "in",
        "is",
        "me",
        "need",
        "of",
        "omym2",
        "on",
        "please",
        "run",
        "should",
        "task",
        "the",
        "to",
        "what",
        "when",
        "where",
        "why",
        "with",
    }
)

JsonObject = dict[str, object]


class RouteError(Exception):
    """Raised when docs cannot be routed."""


class ParsedArgs(argparse.Namespace):
    """Typed argparse result used after parser validation."""

    def __init__(self) -> None:
        super().__init__()
        self.command: str = "route"
        self.query: list[str] = []
        self.docs_root: Path | None = None
        self.limit: int = DEFAULT_ROUTE_LIMIT
        self.dry_prompt: bool = False


@dataclass(frozen=True, slots=True)
class QueryTerms:
    """Normalized query text used by deterministic scoring."""

    phrase: str
    tokens: tuple[str, ...]
    meaningful_tokens: tuple[str, ...]


@dataclass(frozen=True, slots=True)
class ScoredDoc:
    """A docs card with deterministic routing evidence."""

    card: DocCard
    score: int
    reasons: tuple[str, ...]


def main(argv: list[str] | None = None) -> int:
    """Route a task to docs or print the generated catalog."""
    args = _parse_args(argv)
    repo_root = _project_root()
    docs_root = args.docs_root if args.docs_root is not None else repo_root / "docs"

    try:
        if args.command == "catalog":
            cards = load_catalog(docs_root, repo_root)
            _write_json({"docs": [_card_json(card) for card in cards]})
            return 0

        query = " ".join(args.query)
        route = route_query(query=query, docs_root=docs_root, repo_root=repo_root, limit=args.limit)
        if args.dry_prompt:
            _ = sys.stdout.write(f"{_selector_prompt(query, route)}\n")
            return 0
        _write_json(route)
    except RouteError as error:
        _ = sys.stderr.write(f"docs routing failed: {error}\n")
        return 2
    return 0


def load_catalog(docs_root: Path, repo_root: Path) -> list[DocCard]:
    """Load routeable docs cards from the OKF docs tree."""
    if not docs_root.is_dir():
        message = f"{docs_root} does not exist or is not a directory"
        raise RouteError(message)
    return build_doc_cards(docs_root, repo_root)


def route_query(query: str, docs_root: Path, repo_root: Path, limit: int = DEFAULT_ROUTE_LIMIT) -> JsonObject:
    """Return deterministic docs routing JSON for one natural-language task."""
    cards = load_catalog(docs_root, repo_root)
    terms = _query_terms(query)
    scored_docs = _scored_docs(cards, terms)
    selected_docs = scored_docs[:limit]
    confidence = _route_confidence(selected_docs)
    return {
        "query": query,
        "required_docs": [
            {
                "path": REQUIRED_ARCHITECTURE_DOC,
                "reason": "Required by AGENTS.md.",
            }
        ],
        "docs_to_read": [_reading_json(scored_doc, priority) for priority, scored_doc in enumerate(selected_docs, 1)],
        "fallback_docs": _fallback_docs(terms, confidence),
        "confidence": confidence,
    }


def _parse_args(argv: list[str] | None) -> ParsedArgs:
    parser = argparse.ArgumentParser(description="Route an OMYM2 task to the docs an agent should read.")
    subcommands = parser.add_subparsers(dest="command", required=True)

    route = subcommands.add_parser("route", help="Return docs to read for a natural-language task.")
    _ = route.add_argument("query", nargs="+", help="Natural-language task or docs question.")
    _ = route.add_argument("--limit", type=int, default=DEFAULT_ROUTE_LIMIT, help="Maximum docs_to_read entries.")
    _ = route.add_argument(
        "--dry-prompt",
        action="store_true",
        help="Print the future final-selector prompt using deterministic candidates; call no model.",
    )
    _add_docs_root_arg(route)

    catalog = subcommands.add_parser("catalog", help="Print the generated routing catalog as JSON.")
    _add_docs_root_arg(catalog)

    args = parser.parse_args(argv, namespace=ParsedArgs())
    if args.command == "route" and args.limit < 1:
        parser.error("--limit must be at least 1")
    return args


def _add_docs_root_arg(parser: argparse.ArgumentParser) -> None:
    _ = parser.add_argument(
        "--docs-root",
        type=Path,
        default=None,
        help="Docs directory to route; defaults to the repo docs/ directory.",
    )


def _query_terms(query: str) -> QueryTerms:
    query_tokens = tokens(query)
    return QueryTerms(
        phrase=query.lower(),
        tokens=query_tokens,
        meaningful_tokens=tuple(token for token in query_tokens if token not in BROAD_QUERY_TOKENS),
    )


def _scored_docs(cards: list[DocCard], terms: QueryTerms) -> list[ScoredDoc]:
    scored = [_score_doc(card, terms) for card in cards]
    return sorted((item for item in scored if item.score > 0), key=lambda item: (-item.score, item.card.path))


def _score_doc(card: DocCard, terms: QueryTerms) -> ScoredDoc:
    reasons: list[str] = []
    score = 0
    score += _score_exact_path(card, terms, reasons)
    score += _score_field(Path(card.docs_path).stem, terms, FILENAME_TOKEN_WEIGHT, reasons, "filename")
    score += _score_field(card.title, terms, TITLE_TOKEN_WEIGHT, reasons, "title")
    score += _score_field(" ".join(card.tags), terms, TAG_TOKEN_WEIGHT, reasons, "tags")
    score += _score_field(card.description, terms, DESCRIPTION_TOKEN_WEIGHT, reasons, "description")
    score += _score_field(card.doc_type, terms, TYPE_TOKEN_WEIGHT, reasons, "type")
    score += _score_field(
        " ".join(heading.title for heading in card.headings), terms, HEADING_TOKEN_WEIGHT, reasons, "headings"
    )
    score += _score_field(" ".join(card.links), terms, LINK_TOKEN_WEIGHT, reasons, "links")
    score += _score_field(card.excerpt, terms, EXCERPT_TOKEN_WEIGHT, reasons, "excerpt")
    return ScoredDoc(card=card, score=score, reasons=tuple(dict.fromkeys(reasons)))


def _score_exact_path(card: DocCard, terms: QueryTerms, reasons: list[str]) -> int:
    if not terms.phrase:
        return 0
    if terms.phrase in card.path.lower() or terms.phrase in card.docs_path.lower():
        reasons.append("path")
        return EXACT_PATH_MATCH_WEIGHT
    return 0


def _score_field(text: str, terms: QueryTerms, weight: int, reasons: list[str], reason: str) -> int:
    haystack = text.lower()
    score = 0
    if terms.phrase and terms.phrase in haystack:
        score += weight * EXACT_PHRASE_MULTIPLIER
        reasons.append(reason)
    field_tokens = _field_token_set(text)
    token_hits = sum(1 for token in _expanded_query_tokens(terms) if token in field_tokens)
    if token_hits:
        score += token_hits * weight
        reasons.append(reason)
    return score


def _expanded_query_tokens(terms: QueryTerms) -> tuple[str, ...]:
    expanded: list[str] = []
    for token in terms.meaningful_tokens:
        expanded.extend(_token_variants(token))
    return tuple(dict.fromkeys(expanded))


def _field_token_set(text: str) -> set[str]:
    expanded: set[str] = set()
    for token in tokens(text):
        expanded.update(_token_variants(token))
    return expanded


def _token_variants(token: str) -> tuple[str, ...]:
    variants = [token]
    compact = token.replace("-", "").replace(".", "").replace("/", "")
    if compact != token:
        variants.append(compact)
    variants.extend(
        candidate[:-1]
        for candidate in (token, compact)
        if len(candidate) >= MIN_SINGULARIZE_TOKEN_LENGTH and candidate.endswith("s")
    )
    return tuple(dict.fromkeys(variants))


def _route_confidence(selected_docs: list[ScoredDoc]) -> str:
    if not selected_docs:
        return "low"
    return _confidence_for_score(selected_docs[0].score)


def _confidence_for_score(score: int) -> str:
    if score >= HIGH_CONFIDENCE_SCORE:
        return "high"
    if score >= MEDIUM_CONFIDENCE_SCORE:
        return "medium"
    return "low"


def _fallback_docs(terms: QueryTerms, confidence: str) -> list[str]:
    if confidence == "low" or not terms.meaningful_tokens:
        return [DOCS_INDEX_FALLBACK]
    return []


def _reading_json(scored_doc: ScoredDoc, priority: int) -> JsonObject:
    return {
        "path": scored_doc.card.path,
        "priority": priority,
        "reason": _reason_text(scored_doc),
        "confidence": _confidence_for_score(scored_doc.score),
    }


def _reason_text(scored_doc: ScoredDoc) -> str:
    if not scored_doc.reasons:
        return "Selected by deterministic routing score."
    fields = ", ".join(scored_doc.reasons[:MAX_REASON_FIELDS])
    return f"Matches {fields}."


def _card_json(card: DocCard) -> JsonObject:
    return {
        "path": card.path,
        "docs_path": card.docs_path,
        "content_hash": card.content_hash,
        "type": card.doc_type,
        "title": card.title,
        "description": card.description,
        "tags": list(card.tags),
        "headings": [
            {
                "level": heading.level,
                "title": heading.title,
                "anchor": heading.slug,
                "line": heading.line,
            }
            for heading in card.headings
        ],
        "links": list(card.links),
        "excerpt": card.excerpt,
        "routing_text": card.routing_text,
    }


def _selector_prompt(query: str, route: JsonObject) -> str:
    raw_candidates = route.get("docs_to_read")
    candidates = cast("list[object]", raw_candidates) if isinstance(raw_candidates, list) else []
    clipped_candidates = candidates[:DEFAULT_SELECTOR_CANDIDATE_LIMIT]
    return "\n\n".join(
        (
            "You are OMYM2's docs router.",
            "Return JSON only. Select only paths present in <candidates>. Do not invent files.",
            "Prefer recall over precision. One extra doc is acceptable; missing an authoritative doc is worse.",
            f"<request>\n{query}\n</request>",
            f"<candidates>\n{json.dumps(clipped_candidates, ensure_ascii=False, indent=2)}\n</candidates>",
        )
    )


def _write_json(payload: JsonObject) -> None:
    _ = sys.stdout.write(f"{json.dumps(payload, ensure_ascii=False, indent=2)}\n")


def _project_root() -> Path:
    current_file = Path(__file__).resolve()
    for parent in current_file.parents:
        if (parent / "pyproject.toml").is_file():
            return parent
    raise RuntimeError(PROJECT_ROOT_NOT_FOUND_MESSAGE)


if __name__ == "__main__":
    raise SystemExit(main())
