# ruff: noqa: EM102, INP001, TRY003 -- Standalone script raises descriptive CLI errors.
"""
Summary: Evaluates deterministic docs router results against JSONL routing cases.
Why: Tracks docs routing recall and forbidden hits without requiring local model servers.
"""

from __future__ import annotations

import argparse
import json
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import cast

from docs_catalog import DocCard, project_root
from route_docs import DEFAULT_ROUTE_LIMIT, RouteError, load_catalog, route_query

DEFAULT_CASES_RELATIVE_PATH = Path("tests/fixtures/docs_routing_cases.jsonl")
DEFAULT_DOCS_RELATIVE_PATH = Path("docs")
REQUIRED_QUERY_FIELD = "query"
EXPECTED_FIELD = "expected"
FORBIDDEN_FIELD = "forbidden"

JsonObject = dict[str, object]


class EvalError(Exception):
    """Raised when docs router evaluation cannot run."""


class ParsedArgs(argparse.Namespace):
    """Typed argparse result used after parser validation."""

    def __init__(self) -> None:
        super().__init__()
        self.cases: Path | None = None
        self.docs_root: Path | None = None
        self.limit: int = DEFAULT_ROUTE_LIMIT
        self.json_output: bool = False


@dataclass(frozen=True, slots=True)
class RoutingCase:
    """One expected docs routing example."""

    query: str
    expected: tuple[str, ...]
    forbidden: tuple[str, ...]
    line_number: int


def main(argv: list[str] | None = None) -> int:
    """Evaluate route_docs.py against checked-in routing cases."""
    args = _parse_args(argv)
    repo_root = project_root()
    cases_path = args.cases if args.cases is not None else repo_root / DEFAULT_CASES_RELATIVE_PATH
    docs_root = args.docs_root if args.docs_root is not None else repo_root / DEFAULT_DOCS_RELATIVE_PATH
    try:
        result = evaluate_cases(cases_path=cases_path, docs_root=docs_root, repo_root=repo_root, limit=args.limit)
    except (EvalError, RouteError) as error:
        _ = sys.stderr.write(f"docs router eval failed: {error}\n")
        return 2
    if args.json_output:
        _write_json(result)
        return 0
    _print_text_result(result)
    return 0


def evaluate_cases(cases_path: Path, docs_root: Path, repo_root: Path, limit: int) -> JsonObject:
    """Return aggregate routing metrics for JSONL cases."""
    cases = _read_cases(cases_path)
    if not cases:
        raise EvalError(f"{cases_path} did not contain any routing cases")

    catalog = load_catalog(docs_root, repo_root)
    _validate_case_paths(cases, catalog, cases_path)

    case_results = [_evaluate_case(case, docs_root, repo_root, limit) for case in cases]
    total_cases = len(case_results)
    return {
        "case_count": total_cases,
        f"recall@{limit}": sum(_float_metric(case, "recall") for case in case_results) / total_cases,
        f"precision@{limit}": sum(_float_metric(case, "precision") for case in case_results) / total_cases,
        "required_miss_count": sum(_int_metric(case, "required_miss_count") for case in case_results),
        "forbidden_hit_count": sum(_int_metric(case, "forbidden_hit_count") for case in case_results),
        "cases": case_results,
    }


def _parse_args(argv: list[str] | None) -> ParsedArgs:
    parser = argparse.ArgumentParser(description="Evaluate deterministic OMYM2 docs routing cases.")
    _ = parser.add_argument(
        "--cases",
        type=Path,
        default=None,
        help=f"JSONL routing cases; defaults to {DEFAULT_CASES_RELATIVE_PATH}.",
    )
    _ = parser.add_argument(
        "--docs-root",
        type=Path,
        default=None,
        help=f"Docs directory; defaults to {DEFAULT_DOCS_RELATIVE_PATH}.",
    )
    _ = parser.add_argument("--limit", type=int, default=DEFAULT_ROUTE_LIMIT, help="Docs to evaluate per route.")
    _ = parser.add_argument("--json", dest="json_output", action="store_true", help="Print JSON metrics.")
    args = parser.parse_args(argv, namespace=ParsedArgs())
    if args.limit < 1:
        parser.error("--limit must be at least 1")
    return args


def _read_cases(cases_path: Path) -> list[RoutingCase]:
    if not cases_path.is_file():
        raise EvalError(f"{cases_path} does not exist or is not a file")
    cases: list[RoutingCase] = []
    for line_number, line in enumerate(cases_path.read_text(encoding="utf-8").splitlines(), start=1):
        stripped = line.strip()
        if not stripped:
            continue
        try:
            payload = cast("JsonObject", json.loads(stripped))
        except json.JSONDecodeError as exc:
            raise EvalError(f"{cases_path}:{line_number} is not valid JSON") from exc
        cases.append(_routing_case(payload, cases_path, line_number))
    return cases


def _routing_case(payload: JsonObject, cases_path: Path, line_number: int) -> RoutingCase:
    query = payload.get(REQUIRED_QUERY_FIELD)
    expected = payload.get(EXPECTED_FIELD)
    forbidden = payload.get(FORBIDDEN_FIELD, [])
    if not isinstance(query, str) or not query.strip():
        raise EvalError(f"{cases_path}:{line_number} field {REQUIRED_QUERY_FIELD!r} must be a non-empty string")
    if not _is_string_list(expected):
        raise EvalError(f"{cases_path}:{line_number} field {EXPECTED_FIELD!r} must be a list of strings")
    if not _is_string_list(forbidden):
        raise EvalError(f"{cases_path}:{line_number} field {FORBIDDEN_FIELD!r} must be a list of strings")
    expected_items = cast("list[str]", expected)
    forbidden_items = cast("list[str]", forbidden)
    return RoutingCase(
        query=query,
        expected=tuple(expected_items),
        forbidden=tuple(forbidden_items),
        line_number=line_number,
    )


def _is_string_list(value: object) -> bool:
    if not isinstance(value, list):
        return False
    items = cast("list[object]", value)
    return all(isinstance(item, str) for item in items)


def _validate_case_paths(cases: list[RoutingCase], catalog: list[DocCard], cases_path: Path) -> None:
    """Raise EvalError for any expected/forbidden path missing from the current docs catalog."""
    known_paths = {card.path for card in catalog}
    for case in cases:
        for path in (*case.expected, *case.forbidden):
            if path not in known_paths:
                raise EvalError(f"{cases_path}:{case.line_number} references unknown docs path {path!r}")


def _evaluate_case(case: RoutingCase, docs_root: Path, repo_root: Path, limit: int) -> JsonObject:
    route = route_query(query=case.query, docs_root=docs_root, repo_root=repo_root, limit=limit)
    returned = _returned_paths(route)
    expected_hits = [path for path in case.expected if path in returned]
    required_misses = [path for path in case.expected if path not in returned]
    forbidden_hits = [path for path in case.forbidden if path in returned]
    return {
        "query": case.query,
        "returned": returned,
        "expected": list(case.expected),
        "forbidden": list(case.forbidden),
        # An empty expected list is a legitimate forbidden-only case; recall is vacuously 1.0.
        "recall": len(expected_hits) / len(case.expected) if case.expected else 1.0,
        "precision": len(expected_hits) / len(returned) if returned else 0.0,
        "required_miss_count": len(required_misses),
        "forbidden_hit_count": len(forbidden_hits),
        "required_misses": required_misses,
        "forbidden_hits": forbidden_hits,
    }


def _returned_paths(route: JsonObject) -> list[str]:
    docs_to_read = route.get("docs_to_read")
    if not isinstance(docs_to_read, list):
        return []
    paths: list[str] = []
    for item in cast("list[object]", docs_to_read):
        if not isinstance(item, dict):
            continue
        route_item = cast("dict[str, object]", item)
        path = route_item.get("path")
        if isinstance(path, str):
            paths.append(path)
    return paths


def _float_metric(payload: JsonObject, key: str) -> float:
    value = payload.get(key)
    return value if isinstance(value, float) else 0.0


def _int_metric(payload: JsonObject, key: str) -> int:
    value = payload.get(key)
    return value if isinstance(value, int) else 0


def _print_text_result(result: JsonObject) -> None:
    for key, value in result.items():
        if key == "cases":
            continue
        _ = sys.stdout.write(f"{key}: {value}\n")


def _write_json(payload: JsonObject) -> None:
    _ = sys.stdout.write(f"{json.dumps(payload, ensure_ascii=False, indent=2)}\n")


if __name__ == "__main__":
    raise SystemExit(main())
