# ruff: noqa: EM101, EM102, INP001, PLR0913, S310, S608, TRY003 -- Standalone script raises descriptive CLI errors and uses configured HTTP plus fixed SQL table names.
"""
Summary: Routes natural-language tasks to the OMYM2 docs an agent should read.
Why: Gives agents a low-maintenance reading list built from OKF frontmatter and Markdown content.
"""

from __future__ import annotations

import argparse
import contextlib
import ipaddress
import json
import math
import os
import socket
import sqlite3
import sys
from dataclasses import dataclass, field
from pathlib import Path
from typing import TYPE_CHECKING, cast
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen

from docs_catalog import DocCard, build_doc_cards, project_root, tokens

if TYPE_CHECKING:
    from http.client import HTTPResponse

REQUIRED_ARCHITECTURE_DOC = "ARCHITECTURE.md"
DOCS_INDEX_FALLBACK = "docs/index.md"
DOC_ROUTER_CACHE_DIR = ".doc-router"
EMBEDDINGS_CACHE_FILE_NAME = "embeddings.sqlite"
EMBEDDINGS_TABLE_NAME = "doc_embeddings"
DEFAULT_ROUTE_LIMIT = 5
DEFAULT_LOCAL_MODEL_HOST = "localhost"
DEFAULT_LOCAL_MODEL_PORT = 1234
DEFAULT_LOCAL_MODEL_API_VERSION = "v1"
DEFAULT_LOCAL_MODEL_BASE_URL = (
    f"http://{DEFAULT_LOCAL_MODEL_HOST}:{DEFAULT_LOCAL_MODEL_PORT}/{DEFAULT_LOCAL_MODEL_API_VERSION}"
)
DEFAULT_API_KEY = "lm-studio"
DEFAULT_TIMEOUT_SECONDS = 360
DEFAULT_LOCAL_MODEL_TTL_SECONDS = 600
DEFAULT_TEMPERATURE = 0.1
DEFAULT_LEXICAL_CANDIDATE_LIMIT = 40
DEFAULT_EMBEDDING_CANDIDATE_LIMIT = 80
DEFAULT_SELECTOR_OUTPUT_TOKENS = 1200
EMBEDDING_SCORE_MULTIPLIER = 0.25
ROUTER_SCHEMA_VERSION = "1"
DEFAULT_EMBEDDING_MODEL = "text-embedding-qwen3-embedding-0.6b"
DEFAULT_SELECTOR_MODEL = "qwen/qwen3-4b-2507"
EMPTY_SELECTOR_RESPONSE_MESSAGE = "local docs selector returned an empty response"
MARKDOWN_FENCE_BOUNDARY_LINE_COUNT = 2
DOC_EMBEDDING_INSTRUCTION = "Represent this OMYM2 docs routing text for finding docs an agent should read."
QUERY_EMBEDDING_INSTRUCTION = "Represent this OMYM2 user request for finding docs an agent should read."
SELECTOR_SYSTEM_PROMPT = "You are OMYM2's docs router. Return JSON only."
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
BROAD_TOKEN_DAMPING = 0.25
HIGH_CONFIDENCE_SCORE = 80
MEDIUM_CONFIDENCE_SCORE = 25
MAX_REASON_FIELDS = 5
MAX_MODEL_REASON_CHARS = 200
MIN_SINGULARIZE_TOKEN_LENGTH = 4
LOCAL_MODEL_PROBE_TIMEOUT_SECONDS = 0.2
WSL_KERNEL_MARKER = "microsoft"
WSL_KERNEL_RELEASE_PATH = Path("/proc/sys/kernel/osrelease")
WSL_RESOLV_CONF_PATH = Path("/etc/resolv.conf")
WSL_PROC_NET_ROUTE_PATH = Path("/proc/net/route")
RESOLV_CONF_NAMESERVER_FIELD_COUNT = 2
PROC_NET_ROUTE_MIN_FIELD_COUNT = 3
PROC_NET_ROUTE_DESTINATION_INDEX = 1
PROC_NET_ROUTE_GATEWAY_INDEX = 2
PROC_NET_ROUTE_DEFAULT_DESTINATION = "00000000"
PROC_NET_ROUTE_HEX_IPV4_LENGTH = 8
BROAD_QUERY_TOKENS = frozenset(
    {
        "a",
        "about",
        "an",
        "and",
        "are",
        "change",
        "command",
        "commands",
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
        self.lexical_only: bool = False
        self.embedding_base_url: str = _default_model_base_url("OMYM2_DOC_EMBED_BASE_URL")
        self.embedding_model: str = _default_model_name("OMYM2_DOC_EMBED_MODEL", DEFAULT_EMBEDDING_MODEL)
        self.embedding_api_key: str = _default_model_api_key("OMYM2_DOC_EMBED_API_KEY")
        self.selector_base_url: str = _default_model_base_url("OMYM2_LOCAL_LLM_BASE_URL")
        self.selector_model: str = _default_model_name("OMYM2_LOCAL_LLM_MODEL", DEFAULT_SELECTOR_MODEL)
        self.selector_api_key: str = _default_model_api_key("OMYM2_LOCAL_LLM_API_KEY")
        self.timeout: int = DEFAULT_TIMEOUT_SECONDS


@dataclass(frozen=True, slots=True)
class QueryTerms:
    """Normalized query text used by deterministic scoring."""

    phrase: str
    tokens: tuple[str, ...]
    meaningful_tokens: tuple[str, ...]
    expanded_tokens: tuple[str, ...]
    damped_tokens: tuple[str, ...]


@dataclass(frozen=True, slots=True)
class ScoredDoc:
    """A docs card with deterministic routing evidence."""

    card: DocCard
    score: float
    reasons: tuple[str, ...]


@dataclass(frozen=True, slots=True)
class RouteOptions:
    """Optional model-backed routing settings."""

    use_embeddings: bool = False
    use_selector: bool = False
    require_full_model_pipeline: bool = False
    embedding_base_url: str = field(default_factory=lambda: _default_model_base_url("OMYM2_DOC_EMBED_BASE_URL"))
    embedding_model: str = DEFAULT_EMBEDDING_MODEL
    embedding_api_key: str = field(default_factory=lambda: _default_model_api_key("OMYM2_DOC_EMBED_API_KEY"))
    selector_base_url: str = field(default_factory=lambda: _default_model_base_url("OMYM2_LOCAL_LLM_BASE_URL"))
    selector_model: str = DEFAULT_SELECTOR_MODEL
    selector_api_key: str = field(default_factory=lambda: _default_model_api_key("OMYM2_LOCAL_LLM_API_KEY"))
    timeout: int = DEFAULT_TIMEOUT_SECONDS


@dataclass(frozen=True, slots=True)
class RouteComputation:
    """Ranked docs plus metadata about optional routing layers."""

    selected_docs: list[ScoredDoc]
    confidence: str
    layers: tuple[str, ...]
    warnings: tuple[str, ...]


def main(argv: list[str] | None = None) -> int:
    """Route a task to docs or print the generated catalog."""
    args = _parse_args(argv)
    repo_root = project_root()
    docs_root = args.docs_root if args.docs_root is not None else repo_root / "docs"
    options = _route_options(args)

    try:
        if args.command == "catalog":
            cards = load_catalog(docs_root, repo_root)
            _write_json({"docs": [_card_json(card) for card in cards]})
            return 0
        if args.command == "refresh":
            cards = load_catalog(docs_root, repo_root)
            _write_json(refresh_embedding_cache(cards, repo_root, options))
            return 0

        query = " ".join(args.query)
        if args.dry_prompt:
            cards = load_catalog(docs_root, repo_root)
            terms = _query_terms(query)
            candidates = _scored_docs(cards, terms)[:DEFAULT_LEXICAL_CANDIDATE_LIMIT]
            _ = sys.stdout.write(f"{_selector_prompt(query, candidates)}\n")
            return 0
        route = route_query(query=query, docs_root=docs_root, repo_root=repo_root, limit=args.limit, options=options)
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


def route_query(
    query: str,
    docs_root: Path,
    repo_root: Path,
    limit: int = DEFAULT_ROUTE_LIMIT,
    options: RouteOptions | None = None,
) -> JsonObject:
    """Return deterministic docs routing JSON for one natural-language task."""
    cards = load_catalog(docs_root, repo_root)
    terms = _query_terms(query)
    route_options = options if options is not None else RouteOptions()
    computation = _compute_route(query, cards, terms, repo_root, limit, route_options)
    return {
        "query": query,
        "required_docs": [
            {
                "path": REQUIRED_ARCHITECTURE_DOC,
                "reason": "Required by AGENTS.md.",
            }
        ],
        "docs_to_read": [
            _reading_json(scored_doc, priority) for priority, scored_doc in enumerate(computation.selected_docs, 1)
        ],
        "fallback_docs": _fallback_docs(terms, computation.confidence),
        "confidence": computation.confidence,
        "routing": {
            "layers": list(computation.layers),
            "warnings": list(computation.warnings),
        },
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
    _ = route.add_argument(
        "--lexical-only",
        action="store_true",
        help="Disable the default local-model pipeline and use deterministic lexical routing only.",
    )
    _add_model_args(route)
    _add_docs_root_arg(route)

    catalog = subcommands.add_parser("catalog", help="Print the generated routing catalog as JSON.")
    _add_docs_root_arg(catalog)

    refresh = subcommands.add_parser("refresh", help="Refresh the local embedding cache for docs routing.")
    _add_embedding_args(refresh)
    _ = refresh.add_argument("--timeout", type=int, default=DEFAULT_TIMEOUT_SECONDS, help="HTTP timeout in seconds.")
    _add_docs_root_arg(refresh)

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


def _add_model_args(parser: argparse.ArgumentParser) -> None:
    _ = parser.add_argument("--timeout", type=int, default=DEFAULT_TIMEOUT_SECONDS, help="HTTP timeout in seconds.")
    _add_embedding_args(parser)
    _add_selector_args(parser)


def _add_embedding_args(parser: argparse.ArgumentParser) -> None:
    _ = parser.add_argument(
        "--embedding-base-url",
        default=_default_model_base_url("OMYM2_DOC_EMBED_BASE_URL"),
        help="OpenAI-compatible embedding endpoint base URL.",
    )
    _ = parser.add_argument(
        "--embedding-model",
        default=_default_model_name("OMYM2_DOC_EMBED_MODEL", DEFAULT_EMBEDDING_MODEL),
        help="Embedding model identifier.",
    )
    _ = parser.add_argument(
        "--embedding-api-key",
        default=_default_model_api_key("OMYM2_DOC_EMBED_API_KEY"),
        help="API key for the embedding endpoint.",
    )


def _add_selector_args(parser: argparse.ArgumentParser) -> None:
    _ = parser.add_argument(
        "--selector-base-url",
        default=_default_model_base_url("OMYM2_LOCAL_LLM_BASE_URL"),
        help="OpenAI-compatible chat selector endpoint base URL.",
    )
    _ = parser.add_argument(
        "--selector-model",
        default=_default_model_name("OMYM2_LOCAL_LLM_MODEL", DEFAULT_SELECTOR_MODEL),
        help="Chat selector model identifier.",
    )
    _ = parser.add_argument(
        "--selector-api-key",
        default=_default_model_api_key("OMYM2_LOCAL_LLM_API_KEY"),
        help="API key for the selector endpoint.",
    )


def _route_options(args: ParsedArgs) -> RouteOptions:
    use_default_model_pipeline = args.command == "route" and not args.lexical_only
    return RouteOptions(
        use_embeddings=use_default_model_pipeline,
        use_selector=use_default_model_pipeline,
        require_full_model_pipeline=use_default_model_pipeline,
        embedding_base_url=args.embedding_base_url,
        embedding_model=args.embedding_model,
        embedding_api_key=args.embedding_api_key,
        selector_base_url=args.selector_base_url,
        selector_model=args.selector_model,
        selector_api_key=args.selector_api_key,
        timeout=args.timeout,
    )


def _default_model_base_url(env_name: str) -> str:
    return (
        os.environ.get(env_name)
        or os.environ.get("OMYM2_LMSTUDIO_BASE_URL")
        or os.environ.get("OMYM2_LOCAL_LLM_BASE_URL")
        or os.environ.get("LLM_BASE_URL")
        or _default_local_model_base_url()
    )


def _default_local_model_base_url() -> str:
    host = _default_local_model_host()
    return f"http://{host}:{DEFAULT_LOCAL_MODEL_PORT}/{DEFAULT_LOCAL_MODEL_API_VERSION}"


def _default_local_model_host() -> str:
    if not _is_wsl():
        return DEFAULT_LOCAL_MODEL_HOST
    for host in _wsl_host_candidates():
        if _can_connect(host, DEFAULT_LOCAL_MODEL_PORT):
            return host
    return DEFAULT_LOCAL_MODEL_HOST


def _wsl_host_candidates() -> list[str]:
    return _unique_strings(
        [
            DEFAULT_LOCAL_MODEL_HOST,
            _wsl_resolv_nameserver(),
            _wsl_default_gateway(),
        ]
    )


def _wsl_resolv_nameserver() -> str | None:
    try:
        resolv_conf = WSL_RESOLV_CONF_PATH.read_text(encoding="utf-8")
    except OSError:
        return None
    for line in resolv_conf.splitlines():
        fields = line.split()
        if len(fields) == RESOLV_CONF_NAMESERVER_FIELD_COUNT and fields[0] == "nameserver":
            candidate = fields[1]
            if _is_ipv4_address(candidate):
                return candidate
    return None


def _wsl_default_gateway() -> str | None:
    try:
        route_table = WSL_PROC_NET_ROUTE_PATH.read_text(encoding="utf-8")
    except OSError:
        return None
    for line in route_table.splitlines()[1:]:
        fields = line.split()
        if (
            len(fields) >= PROC_NET_ROUTE_MIN_FIELD_COUNT
            and fields[PROC_NET_ROUTE_DESTINATION_INDEX] == PROC_NET_ROUTE_DEFAULT_DESTINATION
        ):
            return _ipv4_from_proc_net_route_hex(fields[PROC_NET_ROUTE_GATEWAY_INDEX])
    return None


def _ipv4_from_proc_net_route_hex(value: str) -> str | None:
    if len(value) != PROC_NET_ROUTE_HEX_IPV4_LENGTH:
        return None
    try:
        packed = bytes.fromhex(value)
    except ValueError:
        return None
    return ".".join(str(octet) for octet in reversed(packed))


def _can_connect(host: str, port: int) -> bool:
    try:
        with socket.create_connection((host, port), timeout=LOCAL_MODEL_PROBE_TIMEOUT_SECONDS):
            return True
    except OSError:
        return False


def _is_wsl() -> bool:
    if os.environ.get("WSL_INTEROP") is not None:
        return True
    try:
        kernel_release = WSL_KERNEL_RELEASE_PATH.read_text(encoding="utf-8")
    except OSError:
        return False
    return WSL_KERNEL_MARKER in kernel_release.lower()


def _is_ipv4_address(value: str) -> bool:
    try:
        address = ipaddress.ip_address(value)
    except ValueError:
        return False
    return isinstance(address, ipaddress.IPv4Address)


def _unique_strings(values: list[str | None]) -> list[str]:
    unique: list[str] = []
    for value in values:
        if value is not None and value not in unique:
            unique.append(value)
    return unique


def _default_model_name(env_name: str, fallback: str) -> str:
    return os.environ.get(env_name) or fallback


def _default_model_api_key(env_name: str) -> str:
    return (
        os.environ.get(env_name)
        or os.environ.get("OMYM2_LOCAL_LLM_API_KEY")
        or os.environ.get("LLM_API_KEY")
        or DEFAULT_API_KEY
    )


def _request_chat_completion(
    *,
    base_url: str,
    api_key: str,
    model: str,
    system_prompt: str,
    user_prompt: str,
    timeout: int,
    temperature: float,
    max_output_tokens: int,
    use_response_format: bool,
    empty_message: str,
) -> str:
    request_body: JsonObject = {
        "model": model,
        "messages": [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": user_prompt},
        ],
        "temperature": temperature,
        "stream": False,
        "max_tokens": max_output_tokens,
        "ttl": DEFAULT_LOCAL_MODEL_TTL_SECONDS,
    }
    if use_response_format:
        request_body["response_format"] = {"type": "json_object"}
    try:
        payload = _http_json("POST", _openai_url(base_url, "chat/completions"), api_key, request_body, timeout)
    except RouteError as exc:
        error_text = str(exc)
        if use_response_format and (
            "response_format" in error_text or "HTTP 400" in error_text or "HTTP 422" in error_text
        ):
            return _request_chat_completion(
                base_url=base_url,
                api_key=api_key,
                model=model,
                system_prompt=system_prompt,
                user_prompt=user_prompt,
                timeout=timeout,
                temperature=temperature,
                max_output_tokens=max_output_tokens,
                use_response_format=False,
                empty_message=empty_message,
            )
        raise
    choices = payload.get("choices")
    if not isinstance(choices, list) or not choices:
        raise RouteError("chat completion response did not contain choices[0].message.content")
    raw_first_choice = cast("list[object]", choices)[0]
    if not isinstance(raw_first_choice, dict):
        raise RouteError("chat completion response did not contain choices[0].message.content")
    first_choice = cast("dict[str, object]", raw_first_choice)
    raw_message = first_choice.get("message")
    if not isinstance(raw_message, dict):
        raise RouteError("chat completion response did not contain choices[0].message.content")
    message = cast("dict[str, object]", raw_message)
    content = message.get("content")
    if not isinstance(content, str):
        raise RouteError("chat completion content was not text")
    answer = _strip_outer_markdown_fence(content.strip())
    if not answer and use_response_format:
        return _request_chat_completion(
            base_url=base_url,
            api_key=api_key,
            model=model,
            system_prompt=system_prompt,
            user_prompt=user_prompt,
            timeout=timeout,
            temperature=temperature,
            max_output_tokens=max_output_tokens,
            use_response_format=False,
            empty_message=empty_message,
        )
    return _require_non_empty_answer(answer, _empty_answer_message(empty_message, first_choice))


def _empty_answer_message(empty_message: str, choice: dict[str, object]) -> str:
    finish_reason = choice.get("finish_reason")
    if isinstance(finish_reason, str) and finish_reason:
        return f"{empty_message} (finish_reason={finish_reason})"
    return empty_message


def _http_json(method: str, url: str, api_key: str, body: JsonObject | None, timeout: int) -> JsonObject:
    data = None if body is None else json.dumps(body).encode("utf-8")
    request = Request(
        url,
        data=data,
        method=method,
        headers={
            "Authorization": f"Bearer {api_key}",
            "Content-Type": "application/json",
        },
    )
    try:
        with cast("HTTPResponse", urlopen(request, timeout=timeout)) as response:
            raw_payload = response.read().decode("utf-8")
    except HTTPError as exc:
        body_text = exc.read().decode("utf-8", errors="replace")[:1000]
        raise RouteError(f"HTTP {exc.code} from model endpoint: {body_text}") from exc
    except TimeoutError as exc:
        raise RouteError(f"timed out after {timeout} seconds waiting for model endpoint at {url}") from exc
    except URLError as exc:
        raise RouteError(f"could not reach model endpoint at {url}: {exc.reason}") from exc
    try:
        payload = cast("object", json.loads(raw_payload))
    except json.JSONDecodeError as exc:
        raise RouteError("model endpoint returned invalid JSON") from exc
    if not isinstance(payload, dict):
        raise RouteError("model endpoint returned a non-object JSON payload")
    return cast("JsonObject", payload)


def _openai_url(base_url: str, endpoint: str) -> str:
    normalized = base_url.rstrip("/")
    if normalized.endswith("/v1"):
        return f"{normalized}/{endpoint}"
    return f"{normalized}/v1/{endpoint}"


def _extract_json_object(text: str) -> JsonObject:
    stripped = _strip_outer_markdown_fence(text.strip())
    if not stripped:
        raise RouteError(EMPTY_SELECTOR_RESPONSE_MESSAGE)
    try:
        payload = cast("object", json.loads(stripped))
    except json.JSONDecodeError:
        start = stripped.find("{")
        end = stripped.rfind("}")
        if start < 0 or end <= start:
            raise
        payload = cast("object", json.loads(stripped[start : end + 1]))
    if not isinstance(payload, dict):
        raise json.JSONDecodeError("expected JSON object", stripped, 0)
    return cast("JsonObject", payload)


def _require_non_empty_answer(answer: str, empty_message: str) -> str:
    answer_body = answer.strip()
    if not answer_body:
        raise RouteError(empty_message)
    return answer_body


def _strip_outer_markdown_fence(content: str) -> str:
    lines = content.splitlines()
    if len(lines) < MARKDOWN_FENCE_BOUNDARY_LINE_COUNT:
        return content
    first = lines[0].strip().lower()
    last = lines[-1].strip()
    if first in {"```", "```json", "```md", "```markdown"} and last == "```":
        return "\n".join(lines[1:-1]).strip()
    return content


def _query_terms(query: str) -> QueryTerms:
    query_tokens = tokens(query)
    meaningful_tokens = tuple(token for token in query_tokens if token not in BROAD_QUERY_TOKENS)
    broad_tokens = tuple(token for token in query_tokens if token in BROAD_QUERY_TOKENS)
    expanded_tokens = _expanded_query_tokens(meaningful_tokens)
    damped_tokens = tuple(token for token in _expanded_query_tokens(broad_tokens) if token not in expanded_tokens)
    return QueryTerms(
        phrase=query.lower(),
        tokens=query_tokens,
        meaningful_tokens=meaningful_tokens,
        expanded_tokens=expanded_tokens,
        damped_tokens=damped_tokens,
    )


def _scored_docs(cards: list[DocCard], terms: QueryTerms) -> list[ScoredDoc]:
    scored = [_score_doc(card, terms) for card in cards]
    return sorted((item for item in scored if item.score > 0), key=lambda item: (-item.score, item.card.path))


def _compute_route(
    query: str,
    cards: list[DocCard],
    terms: QueryTerms,
    repo_root: Path,
    limit: int,
    options: RouteOptions,
) -> RouteComputation:
    lexical_docs = _scored_docs(cards, terms)
    candidates = lexical_docs[:DEFAULT_LEXICAL_CANDIDATE_LIMIT]
    layers = ["lexical"]
    warnings: list[str] = []

    if options.use_embeddings:
        try:
            embedding_docs = _embedding_scored_docs(query, cards, repo_root, options)
            candidates = _merge_candidates(candidates, embedding_docs[:DEFAULT_EMBEDDING_CANDIDATE_LIMIT])
            layers.append("embeddings")
        except RouteError as error:
            warning = f"embedding unavailable: {error}"
            if options.require_full_model_pipeline:
                return _lexical_fallback_route(lexical_docs, limit, warning)
            warnings.append(warning)

    selected_docs = candidates[:limit]
    if options.use_selector and candidates:
        try:
            selected_docs = _select_docs(query, candidates, options, limit)
            layers.append("selector")
        except RouteError as error:
            warning = f"selector unavailable: {error}"
            if options.require_full_model_pipeline:
                return _lexical_fallback_route(lexical_docs, limit, warning)
            warnings.append(warning)

    return RouteComputation(
        selected_docs=selected_docs,
        confidence=_route_confidence(selected_docs),
        layers=tuple(layers),
        warnings=tuple(warnings),
    )


def _lexical_fallback_route(lexical_docs: list[ScoredDoc], limit: int, warning: str) -> RouteComputation:
    """Return the deterministic route after the default local-model pipeline fails."""
    selected_docs = lexical_docs[:limit]
    return RouteComputation(
        selected_docs=selected_docs,
        confidence=_route_confidence(selected_docs),
        layers=("lexical",),
        warnings=(f"model routing unavailable: {warning}",),
    )


def _score_doc(card: DocCard, terms: QueryTerms) -> ScoredDoc:
    reasons: list[str] = []
    score = 0.0
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


def _score_field(text: str, terms: QueryTerms, weight: int, reasons: list[str], reason: str) -> float:
    haystack = text.lower()
    score = 0.0
    if terms.phrase and terms.phrase in haystack:
        score += weight * EXACT_PHRASE_MULTIPLIER
        reasons.append(reason)
    field_tokens = _field_token_set(text)
    token_hits = sum(1 for token in terms.expanded_tokens if token in field_tokens)
    damped_hits = sum(1 for token in terms.damped_tokens if token in field_tokens)
    if token_hits or damped_hits:
        score += token_hits * weight + damped_hits * weight * BROAD_TOKEN_DAMPING
        reasons.append(reason)
    return score


def _expanded_query_tokens(meaningful_tokens: tuple[str, ...]) -> tuple[str, ...]:
    expanded: list[str] = []
    for token in meaningful_tokens:
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


def refresh_embedding_cache(cards: list[DocCard], repo_root: Path, options: RouteOptions) -> JsonObject:
    """Refresh local doc embeddings and return cache stats."""
    with contextlib.closing(_embedding_cache(repo_root)) as connection:
        pruned = _prune_stale_embeddings(connection, cards, options)
        cached = _cached_doc_embeddings(connection, cards, options)
        missing_cards = [card for card in cards if card.path not in cached]
        if missing_cards:
            embeddings = _request_embeddings([_doc_embedding_text(card) for card in missing_cards], options)
            for card, embedding in zip(missing_cards, embeddings, strict=True):
                _store_doc_embedding(connection, card, embedding, options)
            connection.commit()
        return {
            "cache_path": _embedding_cache_path(repo_root).as_posix(),
            "model": options.embedding_model,
            "router_schema_version": ROUTER_SCHEMA_VERSION,
            "embedded": len(missing_cards),
            "reused": len(cached),
            "pruned": pruned,
        }


def _embedding_scored_docs(
    query: str,
    cards: list[DocCard],
    repo_root: Path,
    options: RouteOptions,
) -> list[ScoredDoc]:
    query_embedding = _request_embeddings([_query_embedding_text(query)], options)[0]
    with contextlib.closing(_embedding_cache(repo_root)) as connection:
        cached = _cached_doc_embeddings(connection, cards, options)
        missing_cards = [card for card in cards if card.path not in cached]
        if missing_cards:
            embeddings = _request_embeddings([_doc_embedding_text(card) for card in missing_cards], options)
            for card, embedding in zip(missing_cards, embeddings, strict=True):
                _store_doc_embedding(connection, card, embedding, options)
                cached[card.path] = embedding
            connection.commit()
    scored = [
        ScoredDoc(card=card, score=_cosine_similarity(query_embedding, cached[card.path]) * 100, reasons=("embedding",))
        for card in cards
        if card.path in cached
    ]
    return sorted((item for item in scored if item.score > 0), key=lambda item: (-item.score, item.card.path))


def _embedding_cache(repo_root: Path) -> sqlite3.Connection:
    cache_path = _embedding_cache_path(repo_root)
    cache_path.parent.mkdir(parents=True, exist_ok=True)
    connection = sqlite3.connect(cache_path)
    _ensure_embedding_table(connection)
    return connection


def _embedding_cache_path(repo_root: Path) -> Path:
    return repo_root / DOC_ROUTER_CACHE_DIR / EMBEDDINGS_CACHE_FILE_NAME


def _ensure_embedding_table(connection: sqlite3.Connection) -> None:
    _ = connection.execute(
        f"""
        CREATE TABLE IF NOT EXISTS {EMBEDDINGS_TABLE_NAME} (
            path TEXT NOT NULL,
            content_hash TEXT NOT NULL,
            model TEXT NOT NULL,
            dimension INTEGER NOT NULL,
            instruction TEXT NOT NULL,
            router_schema_version TEXT NOT NULL,
            embedding_json TEXT NOT NULL,
            PRIMARY KEY (path, content_hash, model, dimension, instruction, router_schema_version)
        )
        """
    )
    connection.commit()


def _cached_doc_embeddings(
    connection: sqlite3.Connection,
    cards: list[DocCard],
    options: RouteOptions,
) -> dict[str, list[float]]:
    current_by_path = {card.path: card for card in cards}
    cached: dict[str, list[float]] = {}
    rows = connection.execute(
        f"""
        SELECT path, content_hash, dimension, embedding_json
        FROM {EMBEDDINGS_TABLE_NAME}
        WHERE model = ? AND instruction = ? AND router_schema_version = ?
        """,
        (options.embedding_model, DOC_EMBEDDING_INSTRUCTION, ROUTER_SCHEMA_VERSION),
    )
    for path, content_hash, dimension, embedding_json in cast(
        "list[tuple[object, object, object, object]]",
        list(rows),
    ):
        if not isinstance(path, str) or not isinstance(content_hash, str) or not isinstance(dimension, int):
            continue
        card = current_by_path.get(path)
        if card is None or card.content_hash != content_hash:
            continue
        embedding = _decode_embedding(embedding_json)
        if len(embedding) == dimension:
            cached[path] = embedding
    return cached


def _store_doc_embedding(
    connection: sqlite3.Connection,
    card: DocCard,
    embedding: list[float],
    options: RouteOptions,
) -> None:
    _ = connection.execute(
        f"""
        INSERT OR REPLACE INTO {EMBEDDINGS_TABLE_NAME}
            (path, content_hash, model, dimension, instruction, router_schema_version, embedding_json)
        VALUES (?, ?, ?, ?, ?, ?, ?)
        """,
        (
            card.path,
            card.content_hash,
            options.embedding_model,
            len(embedding),
            DOC_EMBEDDING_INSTRUCTION,
            ROUTER_SCHEMA_VERSION,
            json.dumps(embedding),
        ),
    )


def _prune_stale_embeddings(connection: sqlite3.Connection, cards: list[DocCard], options: RouteOptions) -> int:
    current_hashes = {card.path: card.content_hash for card in cards}
    rows = list(
        connection.execute(
            f"""
            SELECT path, content_hash, dimension
            FROM {EMBEDDINGS_TABLE_NAME}
            WHERE model = ? AND instruction = ? AND router_schema_version = ?
            """,
            (options.embedding_model, DOC_EMBEDDING_INSTRUCTION, ROUTER_SCHEMA_VERSION),
        )
    )
    pruned = 0
    for path, content_hash, dimension in cast("list[tuple[object, object, object]]", rows):
        if not isinstance(path, str) or not isinstance(content_hash, str) or not isinstance(dimension, int):
            continue
        if current_hashes.get(path) == content_hash:
            continue
        _ = connection.execute(
            f"""
            DELETE FROM {EMBEDDINGS_TABLE_NAME}
            WHERE path = ? AND content_hash = ? AND model = ? AND dimension = ?
                AND instruction = ? AND router_schema_version = ?
            """,
            (path, content_hash, options.embedding_model, dimension, DOC_EMBEDDING_INSTRUCTION, ROUTER_SCHEMA_VERSION),
        )
        pruned += 1
    connection.commit()
    return pruned


def _doc_embedding_text(card: DocCard) -> str:
    return f"Instruction: {DOC_EMBEDDING_INSTRUCTION}\n\n{card.routing_text}"


def _query_embedding_text(query: str) -> str:
    return f"Instruction: {QUERY_EMBEDDING_INSTRUCTION}\n\nRequest: {query}"


def _request_embeddings(texts: list[str], options: RouteOptions) -> list[list[float]]:
    if not texts:
        return []
    request_body: JsonObject = {
        "model": options.embedding_model,
        "input": texts,
        "ttl": DEFAULT_LOCAL_MODEL_TTL_SECONDS,
    }
    try:
        payload = _http_json(
            "POST",
            _openai_url(options.embedding_base_url, "embeddings"),
            options.embedding_api_key,
            request_body,
            options.timeout,
        )
    except RouteError as exc:
        raise RouteError(str(exc)) from exc
    data = payload.get("data")
    if not isinstance(data, list):
        raise RouteError("embedding response did not contain data")
    by_index: dict[int, list[float]] = {}
    for position, item in enumerate(cast("list[object]", data)):
        if not isinstance(item, dict):
            continue
        entry = cast("dict[str, object]", item)
        raw_index = entry.get("index")
        index = raw_index if isinstance(raw_index, int) else position
        by_index[index] = _decode_embedding(entry.get("embedding"))
    embeddings = [by_index[index] for index in range(len(texts)) if index in by_index]
    if len(embeddings) != len(texts):
        raise RouteError("embedding response count did not match request count")
    return embeddings


def _decode_embedding(value: object) -> list[float]:
    raw_embedding = value
    if isinstance(value, str):
        try:
            raw_embedding = cast("object", json.loads(value))
        except json.JSONDecodeError as exc:
            raise RouteError("cached embedding was not valid JSON") from exc
    if not isinstance(raw_embedding, list) or not raw_embedding:
        raise RouteError("embedding value was not a non-empty list")
    embedding: list[float] = []
    for raw_value in cast("list[object]", raw_embedding):
        if not isinstance(raw_value, int | float):
            raise RouteError("embedding value contained a non-numeric item")
        embedding.append(float(raw_value))
    return embedding


def _cosine_similarity(left: list[float], right: list[float]) -> float:
    if len(left) != len(right) or not left:
        return 0.0
    dot_product = sum(left_value * right_value for left_value, right_value in zip(left, right, strict=True))
    left_norm = math.sqrt(sum(value * value for value in left))
    right_norm = math.sqrt(sum(value * value for value in right))
    if left_norm == 0 or right_norm == 0:
        return 0.0
    return dot_product / (left_norm * right_norm)


def _merge_candidates(primary: list[ScoredDoc], secondary: list[ScoredDoc]) -> list[ScoredDoc]:
    by_path: dict[str, tuple[DocCard, float, float, tuple[str, ...]]] = {}
    for candidate in primary:
        by_path[candidate.card.path] = (candidate.card, candidate.score, 0.0, candidate.reasons)
    for candidate in secondary:
        existing = by_path.get(candidate.card.path)
        if existing is None:
            by_path[candidate.card.path] = (candidate.card, 0.0, candidate.score, candidate.reasons)
            continue
        card, lexical_score, _embedding_score, reasons = existing
        by_path[candidate.card.path] = (
            card,
            lexical_score,
            candidate.score,
            tuple(dict.fromkeys((*reasons, *candidate.reasons))),
        )
    merged = [
        ScoredDoc(
            card=card,
            score=lexical_score + embedding_score * EMBEDDING_SCORE_MULTIPLIER,
            reasons=reasons,
        )
        for card, lexical_score, embedding_score, reasons in by_path.values()
    ]
    return sorted(merged, key=lambda item: (-item.score, item.card.path))


def _select_docs(query: str, candidates: list[ScoredDoc], options: RouteOptions, limit: int) -> list[ScoredDoc]:
    prompt = _selector_prompt(query, candidates)
    try:
        answer = _request_chat_completion(
            base_url=options.selector_base_url,
            api_key=options.selector_api_key,
            model=options.selector_model,
            system_prompt=SELECTOR_SYSTEM_PROMPT,
            user_prompt=prompt,
            timeout=options.timeout,
            temperature=DEFAULT_TEMPERATURE,
            max_output_tokens=DEFAULT_SELECTOR_OUTPUT_TOKENS,
            use_response_format=True,
            empty_message=EMPTY_SELECTOR_RESPONSE_MESSAGE,
        )
        payload = _extract_json_object(answer)
    except (RouteError, json.JSONDecodeError) as exc:
        raise RouteError(str(exc)) from exc
    selected = _selected_docs_from_payload(payload, candidates, limit)
    if not selected:
        raise RouteError("selector response did not contain any valid candidate paths")
    return selected


def _selected_docs_from_payload(payload: JsonObject, candidates: list[ScoredDoc], limit: int) -> list[ScoredDoc]:
    by_path = {candidate.card.path: candidate for candidate in candidates}
    raw_docs = payload.get("docs_to_read", payload.get("selected_docs"))
    if not isinstance(raw_docs, list):
        return []
    selected: list[ScoredDoc] = []
    seen: set[str] = set()
    for raw_item in cast("list[object]", raw_docs):
        if isinstance(raw_item, str):
            item: dict[str, object] = {"path": raw_item}
        elif isinstance(raw_item, dict):
            item = cast("dict[str, object]", raw_item)
        else:
            continue
        path = item.get("path")
        if not isinstance(path, str) or path in seen or path not in by_path:
            continue
        seen.add(path)
        selected.append(_selector_scored_doc(by_path[path], item))
        if len(selected) >= limit:
            break
    return selected


def _selector_scored_doc(candidate: ScoredDoc, item: dict[str, object]) -> ScoredDoc:
    raw_reason = item.get("reason")
    reason = raw_reason[:MAX_MODEL_REASON_CHARS] if isinstance(raw_reason, str) else "final selector"
    raw_confidence = item.get("confidence")
    confidence = raw_confidence if isinstance(raw_confidence, str) else "medium"
    return ScoredDoc(
        card=candidate.card,
        score=_score_for_confidence(confidence),
        reasons=tuple(dict.fromkeys((f"selector: {reason}", *candidate.reasons))),
    )


def _route_confidence(selected_docs: list[ScoredDoc]) -> str:
    if not selected_docs:
        return "low"
    return _confidence_for_score(selected_docs[0].score)


def _confidence_for_score(score: float) -> str:
    if score >= HIGH_CONFIDENCE_SCORE:
        return "high"
    if score >= MEDIUM_CONFIDENCE_SCORE:
        return "medium"
    return "low"


def _score_for_confidence(confidence: str) -> float:
    if confidence == "high":
        return float(HIGH_CONFIDENCE_SCORE)
    if confidence == "low":
        return 1.0
    return float(MEDIUM_CONFIDENCE_SCORE)


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


def _selector_prompt(query: str, candidates: list[ScoredDoc]) -> str:
    candidate_payload = [_selector_candidate_json(candidate) for candidate in candidates]
    return "\n\n".join(
        (
            "You are OMYM2's docs router.",
            "Return JSON only with docs_to_read and confidence.",
            "Select only paths present in <candidates>. Do not invent files.",
            "Select every doc needed for the request; there is no fixed target count.",
            "Include authoritative docs and useful supporting docs. Omit only clearly irrelevant candidates.",
            "Prefer recall over precision. One extra doc is acceptable; missing an authoritative doc is worse.",
            f"<request>\n{query}\n</request>",
            f"<candidates>\n{json.dumps(candidate_payload, ensure_ascii=False, indent=2)}\n</candidates>",
        )
    )


def _selector_candidate_json(candidate: ScoredDoc) -> JsonObject:
    return {
        "path": candidate.card.path,
        "title": candidate.card.title,
        "description": candidate.card.description,
        "tags": list(candidate.card.tags),
        "reason": _reason_text(candidate),
        "confidence": _confidence_for_score(candidate.score),
    }


def _write_json(payload: JsonObject) -> None:
    _ = sys.stdout.write(f"{json.dumps(payload, ensure_ascii=False, indent=2)}\n")


if __name__ == "__main__":
    raise SystemExit(main())
