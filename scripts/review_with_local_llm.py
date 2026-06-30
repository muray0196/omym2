# ruff: noqa: C901, EM101, EM102, INP001, PLR0911, PLR0913, S310, S603, TRY003 -- Standalone local tool keeps CLI/context branching in one file and calls configured HTTP, git, and gh.
"""
Summary: Run a test-focused OMYM2 review with a local OpenAI-compatible LLM.
Why: Keep local LLM usage constrained to caller-selected context and test evidence.
"""

from __future__ import annotations

import argparse
import ipaddress
import json
import os
import posixpath
import re
import shutil
import socket
import subprocess
import sys
import textwrap
from dataclasses import dataclass
from pathlib import Path
from typing import TYPE_CHECKING, cast
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen

if TYPE_CHECKING:
    from collections.abc import Iterable
    from http.client import HTTPResponse

DEFAULT_LOCAL_LLM_HOST = "localhost"
DEFAULT_LOCAL_LLM_PORT = 1234
DEFAULT_LOCAL_LLM_API_VERSION = "v1"
DEFAULT_API_KEY = "lm-studio"
DEFAULT_TIMEOUT_SECONDS = 360
DEFAULT_MAX_INPUT_CHARS = 120_000
DEFAULT_MAX_FILE_CHARS = 20_000
DEFAULT_MAX_TOTAL_FILE_CHARS = 80_000
DEFAULT_MAX_OUTPUT_TOKENS = 32768
DEFAULT_TEMPERATURE = 0.1
DEFAULT_REVIEW_MODEL = "gpt-oss:20b"
DEFAULT_CONTEXT_FILES: tuple[str, ...] = ("docs/TESTING.md", "pyproject.toml")
TEST_REVIEW_MODES: tuple[str, ...] = ("review", "cases")
EMPTY_REVIEW_MESSAGE = "local LLM returned an empty review"
TEXT_FILE_SIZE_LIMIT_BYTES = 500_000
MARKDOWN_FENCE_BOUNDARY_LINE_COUNT = 2
MAX_FINDINGS = 6
MAX_MISSING_TEST_CASES = 6
MAX_FLAKY_RISKS = 4
MAX_REVIEW_POINTS = 5
MAX_DO_NOT_CHANGE = 4
MAX_TEST_INVENTORY_LINES = 240
RESOLV_CONF_NAMESERVER_FIELD_COUNT = 2
IP_ROUTE_DEFAULT_GATEWAY_FIELD_COUNT = 3
IP_ROUTE_DEFAULT_GATEWAY_INDEX = 2
LOCAL_LLM_PROBE_TIMEOUT_SECONDS = 0.25
WSL_KERNEL_MARKER = "microsoft"
WSL_RESOLV_CONF_PATH = Path("/etc/resolv.conf")
EXCLUDED_DIFF_PATH_PREFIXES = (".reviews/", ".git/", "__pycache__/")
SENSITIVE_PATH_PARTS = (
    ".env",
    ".aws",
    ".ssh",
    ".gnupg",
    "credential",
    "credentials",
    "secret",
    "secrets",
    "token",
    "tokens",
    "private_key",
    "id_rsa",
    "id_ed25519",
)
SENSITIVE_SUFFIXES = (".pem", ".p12", ".pfx", ".key", ".sqlite", ".sqlite3", ".db")
TEXT_CONTEXT_SUFFIXES = (
    ".py",
    ".pyi",
    ".toml",
    ".ini",
    ".cfg",
    ".yaml",
    ".yml",
    ".json",
    ".md",
    ".txt",
    ".rst",
    ".sql",
    ".html",
    ".css",
    ".js",
    ".ts",
    ".tsx",
)
TEST_PATH_MARKERS = (
    "/tests/",
    "/test/",
    "test_",
    "_test.py",
    ".test.",
    ".spec.",
    "conftest.py",
)
DIFF_HEADER_PATH_RE = re.compile(r"^diff --git a/(.*?) b/(.*?)$")
DIFF_NEW_PATH_RE = re.compile(r"^\+\+\+ b/(.*?)$")
TEST_FUNCTION_RE = re.compile(r"^\s*(?:async\s+def|def)\s+(test_[A-Za-z0-9_]+)\(")


type JsonValue = None | bool | int | float | str | JsonArray | JsonObject
type JsonArray = list[JsonValue]
type JsonObject = dict[str, JsonValue]


class ParsedArgs(argparse.Namespace):
    """Typed argparse result used after parser validation."""

    def __init__(self) -> None:
        super().__init__()
        self.command: str = "review"
        self.worktree: bool = False
        self.staged: bool = False
        self.base: str | None = None
        self.pr: int | None = None
        self.repo: str | None = None
        self.stdin: bool = False
        self.diff_file: Path | None = None
        self.files: list[str] = []
        self.context: list[str] = list(DEFAULT_CONTEXT_FILES)
        self.output: Path | None = None
        self.base_url: str = _default_base_url()
        self.api_key: str = DEFAULT_API_KEY
        self.model: str | None = None
        self.timeout: int = DEFAULT_TIMEOUT_SECONDS
        self.max_input_chars: int = DEFAULT_MAX_INPUT_CHARS
        self.max_file_chars: int = DEFAULT_MAX_FILE_CHARS
        self.max_total_file_chars: int = DEFAULT_MAX_TOTAL_FILE_CHARS
        self.max_output_tokens: int = DEFAULT_MAX_OUTPUT_TOKENS
        self.temperature: float = DEFAULT_TEMPERATURE
        self.dry_prompt: bool = False
        self.no_response_format: bool = False


@dataclass(frozen=True, slots=True)
class ReviewSource:
    """Input gathered for the test-focused review."""

    source_label: str
    diff: str
    changed_files: tuple[str, ...]
    explicit_files: tuple[str, ...]


@dataclass(frozen=True, slots=True)
class ContextFile:
    """A repository file that Python allowed the LLM to read."""

    path: str
    content: str
    source: str
    reason: str


class ReviewError(RuntimeError):
    """Raised when a local review cannot be prepared or executed."""


SYSTEM_PROMPT = """
You are OMYM2's local LLM test assistant.

Hard scope:
- Only analyze testing-related issues.
- Do not perform general code review, architecture review, refactoring advice, documentation review, or feature planning.
- You may discuss production code only when it directly explains a missing test, failing test, assertion mismatch, fixture issue, mock issue, regression risk, or flaky test risk.
- Never suggest file edits as a patch.
- Do not claim certainty when the provided evidence is incomplete.
- Prefer concrete, reviewable findings over generic advice.
- Omit weak, redundant, or purely hypothetical items. Empty arrays are better than noisy arrays.
- Before proposing a missing test, check the existing_tests inventory and context files for likely existing coverage.
- Do not report generic SQLite, filesystem, ordering, or concurrency flake risk unless the diff introduces shared state, nondeterminism, or a reused resource.
- Severity calibration: high means a likely real bug or required test gate failure; medium means a plausible regression hole tied to evidence; low means a minor maintainability point.
- Put ambiguous product/testing questions in review_points instead of findings.

Output rules:
- Return JSON only. No Markdown. No code fences. No commentary outside JSON.
- Keep findings grounded in the provided diff, logs, and file contents.
""".strip()

JSON_OUTPUT_CONTRACT = f"""
Return exactly one JSON object with this shape:
{{
  "mode": "review | cases",
  "scope": "test-only",
  "summary": "string",
  "risk_level": "low | medium | high",
  "findings": [
    {{
      "severity": "low | medium | high",
      "category": "coverage | assertion | mock | fixture | flaky | naming | structure | regression | maintainability | other",
      "location": "file path, test name, or null",
      "evidence": "specific evidence from the provided input",
      "recommendation": "specific action for a human to consider"
    }}
  ],
  "missing_test_cases": [
    {{
      "name": "short test-case name",
      "reason": "why this case matters",
      "priority": "low | medium | high"
    }}
  ],
  "flaky_risks": [
    {{
      "risk": "risk description",
      "evidence": "specific evidence or null if inferred",
      "mitigation": "how to reduce the risk"
    }}
  ],
  "review_points": ["question or decision for the reviewing agent"],
  "do_not_change": ["test/code area that should probably not be changed unnecessarily"],
  "confidence": "low | medium | high"
}}

Limits:
- findings: max {MAX_FINDINGS} items; omit if there is no concrete defect or regression risk
- missing_test_cases: max {MAX_MISSING_TEST_CASES} items; omit cases already represented in existing_tests or context
- flaky_risks: max {MAX_FLAKY_RISKS} items; omit generic risks without a concrete shared resource or nondeterminism
- review_points: max {MAX_REVIEW_POINTS} items
- do_not_change: max {MAX_DO_NOT_CHANGE} items

Evidence rules:
- Each finding evidence must name a file, test, line-like snippet, or observed behavior from the supplied input.
- missing_test_cases must explain why existing tests do not already cover the case.
- If evidence is weak, lower confidence or use review_points instead of findings.
""".strip()

MODE_INSTRUCTIONS: dict[str, str] = {
    "review": textwrap.dedent(
        """
        Mode: review
        Goal: Review provided test code, test support code, or test-related diff.
        Focus on:
        - Whether the tests verify behavior instead of implementation trivia.
        - Assertion strength and clarity.
        - Missing normal/error/boundary/regression cases.
        - Over-mocking, brittle fixtures, hidden shared state, and fixture lifetime mistakes.
        - Flaky risks from time, timezone, async, ordering, randomness, network, filesystem, database state, or concurrency.
        - Test names and structure only when they affect maintainability.
        Report only issues that are actionable from the provided input. Do not fill every output array.
        Do not propose production-code refactors unless directly required to make the tests meaningful.
        """
    ).strip(),
    "cases": textwrap.dedent(
        """
        Mode: cases
        Goal: Generate missing-test ideas from the provided implementation diff and related files.
        Focus on:
        - Normal cases, error cases, boundary values, compatibility/regression cases.
        - OMYM2 domain risks: Plan/PlanAction semantics, FileEvent-before-mutation ordering, root-relative stored paths, library_id identity, and adapter boundary behavior.
        - Cases likely to catch real defects.
        - Cases that should not be added because they would be redundant or too coupled to implementation details.
        First eliminate cases that are likely already covered by existing_tests or context files.
        Prefer a few high-signal cases over a broad backlog.
        Do not generate full test code unless a very small pseudocode sketch is necessary inside a recommendation field.
        """
    ).strip(),
}


def main(argv: list[str] | None = None) -> int:
    """Run the local LLM test review command."""
    try:
        args = _parse_args(argv)
        repo_root = _repo_root()
        model = _resolve_model(args.model)
        source = _resolve_review_source(args)
        context = _dedupe_context_files(_load_base_context(args, repo_root, source))
        existing_tests = _test_inventory(repo_root, source)
        user_prompt = _build_user_prompt(args.command, source, context, args, existing_tests)
        if args.dry_prompt:
            _print_dry_prompt(SYSTEM_PROMPT, user_prompt)
            return 0
        review = _request_review(
            base_url=args.base_url,
            api_key=args.api_key,
            model=model,
            system_prompt=SYSTEM_PROMPT,
            user_prompt=user_prompt,
            timeout=args.timeout,
            temperature=args.temperature,
            max_output_tokens=args.max_output_tokens,
            use_response_format=not args.no_response_format,
        )
        result = _compact_review_output(
            _normalize_review_json(_extract_json_object(review), args.command, existing_tests)
        )
        _write_or_print_json(result, args.output)
    except ReviewError as exc:
        _ = sys.stderr.write(f"local LLM test review failed: {exc}\n")
        return 1
    except json.JSONDecodeError as exc:
        _ = sys.stderr.write(f"local LLM test review failed: model did not return valid JSON: {exc}\n")
        return 2
    return 0


def _parse_args(argv: list[str] | None) -> ParsedArgs:
    parser = argparse.ArgumentParser(
        description="Test-only OMYM2 local LLM review. No agent/tool calls and no file edits.",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=textwrap.dedent(
            """
            Examples:
              python scripts/review_with_local_llm.py review --worktree --files tests/scripts/test_review_with_local_llm.py
              python scripts/review_with_local_llm.py review --staged --context tests/scripts/test_review_with_local_llm.py
              python scripts/review_with_local_llm.py cases --base develop --files scripts/review_with_local_llm.py
              git diff | python scripts/review_with_local_llm.py review --stdin --files tests/scripts/test_review_with_local_llm.py
            """
        ),
    )
    subcommands = parser.add_subparsers(dest="command", required=True)
    for command in TEST_REVIEW_MODES:
        subparser = subcommands.add_parser(command, help=f"Run test-focused {command} mode.")
        _add_common_args(subparser)
    return parser.parse_args(argv, namespace=ParsedArgs())


def _add_common_args(parser: argparse.ArgumentParser) -> None:
    source_group = parser.add_mutually_exclusive_group()
    _ = source_group.add_argument(
        "--worktree",
        action="store_true",
        help="Use staged, unstaged, and safe untracked diffs. This is the default source when no source is given.",
    )
    _ = source_group.add_argument("--staged", action="store_true", help="Use git diff --staged.")
    _ = source_group.add_argument("--base", default=None, help="Use git diff BASE...HEAD.")
    _ = source_group.add_argument("--pr", type=int, default=None, help="Use gh pr diff for this pull request number.")
    _ = source_group.add_argument("--diff-file", type=Path, default=None, help="Read review diff/input from this file.")
    _ = parser.add_argument(
        "--stdin",
        action="store_true",
        help="Read review input from stdin.",
    )
    _ = parser.add_argument("--repo", default=None, help="Optional owner/name for gh pr diff.")
    _ = parser.add_argument(
        "--files", action="append", default=[], help="Explicit context file to include. May be repeated."
    )
    _ = parser.add_argument(
        "--context",
        action="append",
        default=list(DEFAULT_CONTEXT_FILES),
        help="Small always-included context file. Defaults to docs/TESTING.md and pyproject.toml.",
    )
    _ = parser.add_argument(
        "--max-file-chars",
        type=int,
        default=DEFAULT_MAX_FILE_CHARS,
        help="Maximum characters read from a single context file.",
    )
    _ = parser.add_argument(
        "--max-total-file-chars",
        type=int,
        default=DEFAULT_MAX_TOTAL_FILE_CHARS,
        help="Maximum total characters read from context files.",
    )
    _ = parser.add_argument(
        "--max-input-chars",
        type=int,
        default=DEFAULT_MAX_INPUT_CHARS,
        help="Maximum diff/log characters included in prompts.",
    )
    _ = parser.add_argument(
        "--base-url",
        default=os.environ.get("OMYM2_LMSTUDIO_BASE_URL")
        or os.environ.get("OMYM2_LOCAL_LLM_BASE_URL")
        or os.environ.get("LLM_BASE_URL")
        or _default_base_url(),
        help="OpenAI-compatible local base URL.",
    )
    _ = parser.add_argument(
        "--api-key",
        default=os.environ.get("OMYM2_LOCAL_LLM_API_KEY") or os.environ.get("LLM_API_KEY") or DEFAULT_API_KEY,
        help="API key for the local endpoint. Local servers usually accept a dummy value.",
    )
    _ = parser.add_argument(
        "--model",
        default=os.environ.get("OMYM2_REVIEW_MODEL")
        or os.environ.get("OMYM2_LOCAL_LLM_MODEL")
        or os.environ.get("LLM_MODEL"),
        help="Model ID. Defaults to OMYM2_REVIEW_MODEL, OMYM2_LOCAL_LLM_MODEL, LLM_MODEL, then gpt-oss:20b.",
    )
    _ = parser.add_argument("--timeout", type=int, default=DEFAULT_TIMEOUT_SECONDS, help="HTTP timeout in seconds.")
    _ = parser.add_argument(
        "--temperature", type=float, default=DEFAULT_TEMPERATURE, help="Review sampling temperature."
    )
    _ = parser.add_argument(
        "--max-output-tokens", type=int, default=DEFAULT_MAX_OUTPUT_TOKENS, help="Max output tokens."
    )
    _ = parser.add_argument(
        "--output", type=Path, default=None, help="Write JSON result to this path. Defaults to stdout."
    )
    _ = parser.add_argument(
        "--dry-prompt", action="store_true", help="Print the prompt that would be sent, without calling the LLM."
    )
    _ = parser.add_argument(
        "--no-response-format",
        action="store_true",
        help="Do not request JSON response_format from the local API.",
    )


def _resolve_model(model_arg: str | None) -> str:
    return model_arg or DEFAULT_REVIEW_MODEL


def _resolve_review_source(args: ParsedArgs) -> ReviewSource:
    stdin_text = sys.stdin.read() if args.stdin else ""
    if args.pr is not None:
        diff = _load_pr_diff(args.pr, args.repo)
        return ReviewSource(f"pr-{args.pr}", diff, tuple(_parse_changed_files_from_diff(diff)), tuple(args.files))
    if args.stdin:
        return ReviewSource(
            args.command + ":stdin",
            stdin_text,
            tuple(_parse_changed_files_from_diff(stdin_text)),
            tuple(args.files),
        )
    if args.diff_file is not None:
        diff = _read_text_file(args.diff_file, max_chars=args.max_input_chars)
        return ReviewSource(
            f"diff-file:{args.diff_file}", diff, tuple(_parse_changed_files_from_diff(diff)), tuple(args.files)
        )
    if args.staged:
        diff = _run_git_diff(["diff", "--cached", "--", ".", ":(exclude).reviews"])
        changed_files = _git_changed_files(["diff", "--cached", "--name-only", "--", ".", ":(exclude).reviews"])
        return ReviewSource("staged", diff, tuple(changed_files), tuple(args.files))
    if args.base is not None:
        diff = _run_git_diff(["diff", f"{args.base}...HEAD", "--", ".", ":(exclude).reviews"])
        changed_files = _git_changed_files(
            ["diff", "--name-only", f"{args.base}...HEAD", "--", ".", ":(exclude).reviews"]
        )
        return ReviewSource(f"base:{args.base}", diff, tuple(changed_files), tuple(args.files))
    diff = _load_worktree_diff()
    return ReviewSource("worktree", diff, tuple(_worktree_changed_files()), tuple(args.files))


def _load_pr_diff(pr_number: int, repo: str | None) -> str:
    command = ["gh", "pr", "diff", str(pr_number), "--color=never"]
    if repo is not None:
        command.extend(("--repo", repo))
    return _run_command(command)


def _load_worktree_diff() -> str:
    sections = [
        ("staged changes", _run_git_diff(["diff", "--cached", "--", ".", ":(exclude).reviews"])),
        ("unstaged changes", _run_git_diff(["diff", "--", ".", ":(exclude).reviews"])),
        ("untracked files", _load_untracked_file_diffs()),
    ]
    rendered_sections = [f"# {title}\n\n{content}" for title, content in sections if content.strip()]
    if rendered_sections:
        return "\n\n".join(rendered_sections)
    raise ReviewError("no staged, unstaged, or safe untracked changes were found")


def _load_untracked_file_diffs() -> str:
    output = _run_command(["git", "ls-files", "--others", "--exclude-standard"])
    diffs: list[str] = []
    for raw_path in output.splitlines():
        path = Path(raw_path)
        if _should_skip_untracked_path(raw_path, path):
            continue
        try:
            diffs.append(_new_file_diff(path))
        except (OSError, UnicodeDecodeError) as exc:
            diffs.append(f"diff --git a/{raw_path} b/{raw_path}\n# skipped unreadable or non-text file: {exc}\n")
    return "\n".join(diffs)


def _should_skip_untracked_path(raw_path: str, path: Path) -> bool:
    if raw_path.startswith(EXCLUDED_DIFF_PATH_PREFIXES):
        return True
    if _is_sensitive_relative_path(raw_path):
        return True
    if path.suffix.lower() not in TEXT_CONTEXT_SUFFIXES:
        return True
    if not path.is_file():
        return True
    try:
        return path.stat().st_size > TEXT_FILE_SIZE_LIMIT_BYTES
    except OSError:
        return True


def _new_file_diff(path: Path) -> str:
    raw_path = path.as_posix()
    text = path.read_text(encoding="utf-8")
    lines = text.splitlines()
    header = [
        f"diff --git a/{raw_path} b/{raw_path}",
        "new file mode 100644",
        "--- /dev/null",
        f"+++ b/{raw_path}",
        f"@@ -0,0 +1,{len(lines)} @@",
    ]
    body = [f"+{line}" for line in lines]
    if text.endswith("\n"):
        return "\n".join([*header, *body, ""])
    return "\n".join([*header, *body, "\\ No newline at end of file", ""])


def _worktree_changed_files() -> list[str]:
    files = [
        *_git_changed_files(["diff", "--cached", "--name-only", "--", ".", ":(exclude).reviews"]),
        *_git_changed_files(["diff", "--name-only", "--", ".", ":(exclude).reviews"]),
        *_safe_untracked_files(),
    ]
    return _unique_strings(files)


def _git_changed_files(args: list[str]) -> list[str]:
    return [line.strip() for line in _run_git_diff(args).splitlines() if line.strip()]


def _safe_untracked_files() -> list[str]:
    output = _run_command(["git", "ls-files", "--others", "--exclude-standard"])
    return [path for path in output.splitlines() if path.strip() and not _should_skip_untracked_path(path, Path(path))]


def _run_git_diff(args: list[str]) -> str:
    return _run_command(["git", *args], allow_exit_codes={0, 1})


def _run_command(command: list[str], allow_exit_codes: set[int] | None = None) -> str:
    allowed = {0} if allow_exit_codes is None else allow_exit_codes
    try:
        result = subprocess.run(
            command, check=False, capture_output=True, text=True, encoding="utf-8", errors="replace"
        )
    except FileNotFoundError as exc:
        raise ReviewError(f"required command was not found: {command[0]}") from exc
    if result.returncode not in allowed:
        stderr = result.stderr.strip()
        raise ReviewError(f"command failed ({' '.join(command)}): {stderr or result.returncode}")
    return result.stdout


def _parse_changed_files_from_diff(diff: str) -> list[str]:
    paths: list[str] = []
    for line in diff.splitlines():
        header_match = DIFF_HEADER_PATH_RE.match(line)
        if header_match is not None:
            paths.append(header_match.group(2))
            continue
        new_path_match = DIFF_NEW_PATH_RE.match(line)
        if new_path_match is not None and new_path_match.group(1) != "/dev/null":
            paths.append(new_path_match.group(1))
    return _unique_strings(paths)


def _load_base_context(args: ParsedArgs, repo_root: Path, source: ReviewSource) -> list[ContextFile]:
    context_paths = [*args.context, *source.explicit_files, *_inferred_context_paths(source, args.command)]
    context: list[ContextFile] = []
    total_chars = 0
    for raw_path in _unique_strings(context_paths):
        allow_untracked = raw_path in source.explicit_files
        safe_path = _safe_repo_relative_path(repo_root, raw_path, _tracked_file_set(), allow_untracked=allow_untracked)
        if safe_path is None:
            continue
        full_path = repo_root / safe_path
        content = _read_text_file(full_path, max_chars=args.max_file_chars)
        if not content.strip():
            continue
        remaining = max(0, args.max_total_file_chars - total_chars)
        if remaining <= 0:
            break
        clipped = _clip_middle(content, remaining)
        total_chars += len(clipped)
        context.append(
            ContextFile(safe_path, clipped, "manual-or-inferred", "explicit, default, or changed-file context")
        )
    return context


def _inferred_context_paths(source: ReviewSource, mode: str) -> list[str]:
    changed_files = list(source.changed_files)
    if mode == "review":
        return [path for path in changed_files if _is_test_path(path)]
    if mode == "cases":
        return [path for path in changed_files if _looks_like_text_context_file(path) and not _is_test_path(path)]
    return []


def _tracked_file_set() -> set[str]:
    try:
        output = _run_command(["git", "ls-files"])
    except ReviewError:
        return set()
    return {_normalize_relative_path_text(line) for line in output.splitlines() if line.strip()}


def _repo_root() -> Path:
    try:
        root = _run_command(["git", "rev-parse", "--show-toplevel"]).strip()
    except ReviewError:
        root = ""
    if root:
        return Path(root).resolve()
    current = Path.cwd().resolve()
    for parent in (current, *current.parents):
        if (parent / "pyproject.toml").is_file():
            return parent
    return current


def _safe_repo_relative_path(
    repo_root: Path,
    raw_path: str,
    tracked_files: set[str],
    *,
    allow_untracked: bool,
) -> str | None:
    normalized = _normalize_relative_path_text(raw_path)
    if _validate_context_path(repo_root, raw_path, tracked_files, allow_untracked=allow_untracked) is not None:
        return None
    return normalized


def _validate_context_path(
    repo_root: Path,
    raw_path: str,
    tracked_files: set[str],
    *,
    allow_untracked: bool = False,
) -> str | None:
    """Return a concrete rejection reason for tests and future callers."""
    if not raw_path or "\x00" in raw_path:
        return "empty or invalid path"
    raw_normalized = raw_path.replace("\\", "/")
    if Path(raw_path).is_absolute():
        return "absolute paths are not allowed"
    if any(part == ".." for part in raw_normalized.split("/")):
        return "path escapes repository root"
    normalized = _normalize_relative_path_text(raw_path)
    if normalized in {".", ""} or normalized.startswith("../") or "/../" in f"/{normalized}/":
        return "path escapes repository root"
    if _is_sensitive_relative_path(normalized):
        return "sensitive-looking paths are not allowed"
    if not allow_untracked and tracked_files and normalized not in tracked_files:
        return "path is not tracked by git"
    full_path = (repo_root / normalized).resolve()
    try:
        _ = full_path.relative_to(repo_root.resolve())
    except ValueError:
        return "path escapes repository root"
    if not full_path.is_file():
        return "path is not a readable file"
    if full_path.is_symlink():
        return "symlinks are not allowed"
    if not _looks_like_text_context_file(normalized):
        return "unsupported file type"
    try:
        if full_path.stat().st_size > TEXT_FILE_SIZE_LIMIT_BYTES:
            return "file is too large"
    except OSError:
        return "path is not a readable file"
    return None


def _normalize_relative_path_text(path: str) -> str:
    normalized = path.replace("\\", "/")
    while normalized.startswith("./"):
        normalized = normalized[2:]
    normalized = posixpath.normpath(normalized)
    return "" if normalized == "." else normalized


def _is_sensitive_relative_path(path: str) -> bool:
    normalized = _normalize_relative_path_text(path).lower()
    parts = normalized.split("/")
    if any(part in SENSITIVE_PATH_PARTS for part in parts):
        return True
    if any(part.startswith(".env") and part not in {".env.example", ".env.sample"} for part in parts):
        return True
    if any(marker in normalized for marker in SENSITIVE_PATH_PARTS):
        return True
    return normalized.endswith(SENSITIVE_SUFFIXES)


def _looks_like_text_context_file(path: str) -> bool:
    return Path(path).suffix.lower() in TEXT_CONTEXT_SUFFIXES


def _is_test_path(path: str) -> bool:
    normalized = f"/{_normalize_relative_path_text(path).lower()}"
    return any(marker in normalized for marker in TEST_PATH_MARKERS)


def _dedupe_context_files(files: list[ContextFile]) -> list[ContextFile]:
    seen: set[str] = set()
    result: list[ContextFile] = []
    for file in files:
        if file.path in seen:
            continue
        seen.add(file.path)
        result.append(file)
    return result


def _test_inventory(repo_root: Path, source: ReviewSource) -> str:
    """Return a compact index that helps the model avoid duplicate test ideas."""
    test_paths = sorted(path for path in _tracked_file_set() if _is_test_path(path) and path.endswith(".py"))
    lines: list[str] = []
    for path in _prioritize_test_inventory_paths(test_paths, source.changed_files):
        full_path = repo_root / path
        try:
            content = full_path.read_text(encoding="utf-8", errors="replace")
        except OSError:
            continue
        test_names = _parse_test_names(content)
        if not test_names:
            continue
        lines.extend(f"{path}::{test_name}" for test_name in test_names)
        if len(lines) >= MAX_TEST_INVENTORY_LINES:
            clipped = lines[:MAX_TEST_INVENTORY_LINES]
            clipped.append("[test inventory clipped]")
            return "\n".join(clipped)
    return "\n".join(lines) if lines else "[none]"


def _prioritize_test_inventory_paths(test_paths: list[str], changed_files: tuple[str, ...]) -> list[str]:
    changed_tests = [path for path in changed_files if path in test_paths]
    return _unique_strings([*changed_tests, *test_paths])


def _parse_test_names(content: str) -> list[str]:
    return [match.group(1) for line in content.splitlines() if (match := TEST_FUNCTION_RE.match(line)) is not None]


def _build_user_prompt(
    mode: str,
    source: ReviewSource,
    context_files: list[ContextFile],
    args: ParsedArgs,
    existing_tests: str,
) -> str:
    context_blocks = (
        "\n\n".join(
            _xml_block(
                "file",
                file.content,
                {"path": file.path, "source": file.source, "reason": file.reason},
            )
            for file in context_files
        )
        or "[No context files were loaded.]"
    )
    diff = _clip_middle(source.diff, args.max_input_chars)
    sections = [
        MODE_INSTRUCTIONS[mode],
        JSON_OUTPUT_CONTRACT,
        _xml_block("source_label", source.source_label),
        _xml_block("changed_files", "\n".join(source.changed_files) or "[none]"),
        _xml_block("existing_tests", existing_tests),
        _xml_block("diff", diff or "[no diff supplied]"),
        _xml_block("context_files", context_blocks),
    ]
    sections.append(
        "Use only the diff, logs, and context file contents above. If context is insufficient, say so in confidence or review_points."
    )
    return "\n\n".join(sections)


def _xml_block(name: str, content: str, attrs: dict[str, str] | None = None) -> str:
    attr_text = ""
    if attrs:
        rendered_attrs = " ".join(f"{key}={json.dumps(value, ensure_ascii=False)}" for key, value in attrs.items())
        attr_text = f" {rendered_attrs}"
    return f"<{name}{attr_text}>\n{content}\n</{name}>"


def _print_dry_prompt(system_prompt: str, user_prompt: str) -> None:
    _ = sys.stdout.write(_xml_block("system_prompt", system_prompt))
    _ = sys.stdout.write("\n\n")
    _ = sys.stdout.write(_xml_block("user_prompt", user_prompt))
    _ = sys.stdout.write("\n")


def _read_text_file(path: Path, *, max_chars: int | None = None) -> str:
    try:
        text = path.read_text(encoding="utf-8", errors="replace")
    except OSError as exc:
        raise ReviewError(f"failed to read {path}: {exc}") from exc
    if max_chars is None:
        return text
    return _clip_middle(text, max_chars)


def _clip_middle(text: str, max_chars: int) -> str:
    if max_chars <= 0 or len(text) <= max_chars:
        return text
    head_len = max_chars * 7 // 10
    tail_len = max_chars - head_len
    omitted = len(text) - max_chars
    return f"{text[:head_len]}\n\n[... omitted {omitted} characters ...]\n\n{text[-tail_len:]}"


def _request_review(
    *,
    base_url: str,
    api_key: str,
    model: str,
    system_prompt: str,
    user_prompt: str,
    timeout: int,
    temperature: float,
    max_output_tokens: int = DEFAULT_MAX_OUTPUT_TOKENS,
    use_response_format: bool = False,
    empty_message: str = EMPTY_REVIEW_MESSAGE,
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
    }
    if use_response_format:
        request_body["response_format"] = {"type": "json_object"}
    try:
        payload = _http_json("POST", _openai_url(base_url, "chat/completions"), api_key, request_body, timeout)
    except ReviewError as exc:
        error_text = str(exc)
        if use_response_format and (
            "response_format" in error_text or "HTTP 400" in error_text or "HTTP 422" in error_text
        ):
            return _request_review(
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
        raise ReviewError("chat completion response did not contain choices[0].message.content")
    first_choice = choices[0]
    if not isinstance(first_choice, dict):
        raise ReviewError("chat completion response did not contain choices[0].message.content")
    message = first_choice.get("message")
    if not isinstance(message, dict):
        raise ReviewError("chat completion response did not contain choices[0].message.content")
    content = message.get("content")
    if not isinstance(content, str):
        raise ReviewError("chat completion content was not text")
    review = _strip_outer_markdown_fence(content.strip())
    if not review and use_response_format:
        return _request_review(
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
    return _require_non_empty_review(review, _empty_review_message(empty_message, first_choice))


def _empty_review_message(empty_message: str, choice: JsonObject) -> str:
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
        raise ReviewError(f"HTTP {exc.code} from local LLM endpoint: {body_text}") from exc
    except TimeoutError as exc:
        raise ReviewError(f"timed out after {timeout} seconds waiting for local LLM endpoint at {url}") from exc
    except URLError as exc:
        raise ReviewError(f"could not reach local LLM endpoint at {url}: {exc.reason}") from exc
    try:
        payload = cast("JsonValue", json.loads(raw_payload))
    except json.JSONDecodeError as exc:
        raise ReviewError("local LLM endpoint returned invalid JSON") from exc
    if not isinstance(payload, dict):
        raise ReviewError("local LLM endpoint returned a non-object JSON payload")
    return payload


def _openai_url(base_url: str, endpoint: str) -> str:
    normalized = base_url.rstrip("/")
    if normalized.endswith("/v1"):
        return f"{normalized}/{endpoint}"
    return f"{normalized}/v1/{endpoint}"


def _extract_json_object(text: str) -> JsonObject:
    stripped = _strip_outer_markdown_fence(text.strip())
    if not stripped:
        raise ReviewError(EMPTY_REVIEW_MESSAGE)
    payload: JsonValue
    try:
        payload = cast("JsonValue", json.loads(stripped))
    except json.JSONDecodeError:
        start = stripped.find("{")
        end = stripped.rfind("}")
        if start < 0 or end <= start:
            raise
        payload = cast("JsonValue", json.loads(stripped[start : end + 1]))
    if not isinstance(payload, dict):
        raise json.JSONDecodeError("expected JSON object", stripped, 0)
    return payload


def _normalize_review_json(obj: JsonObject, mode: str, existing_tests: str = "") -> JsonObject:
    _ = obj.setdefault("mode", mode)
    _ = obj.setdefault("scope", "test-only")
    _ = obj.setdefault("summary", "")
    _ = obj.setdefault("risk_level", "low")
    _ = obj.setdefault("findings", [])
    _ = obj.setdefault("missing_test_cases", [])
    _ = obj.setdefault("flaky_risks", [])
    _ = obj.setdefault("review_points", [])
    _ = obj.setdefault("do_not_change", [])
    _ = obj.setdefault("confidence", "low")
    if obj.get("mode") not in set(TEST_REVIEW_MODES):
        obj["mode"] = mode
    obj["scope"] = "test-only"
    if obj.get("risk_level") not in {"low", "medium", "high"}:
        obj["risk_level"] = "low"
    if obj.get("confidence") not in {"low", "medium", "high"}:
        obj["confidence"] = "low"
    _filter_items_without_evidence(obj, "findings")
    _filter_items_without_evidence(obj, "flaky_risks")
    _filter_existing_missing_test_cases(obj, existing_tests)
    _dedupe_and_limit_list_field(obj, "findings", MAX_FINDINGS)
    _dedupe_and_limit_list_field(obj, "missing_test_cases", MAX_MISSING_TEST_CASES)
    _dedupe_and_limit_list_field(obj, "flaky_risks", MAX_FLAKY_RISKS)
    _dedupe_and_limit_list_field(obj, "review_points", MAX_REVIEW_POINTS)
    _dedupe_and_limit_list_field(obj, "do_not_change", MAX_DO_NOT_CHANGE)
    return obj


def _dedupe_and_limit_list_field(obj: JsonObject, key: str, limit: int) -> None:
    value = obj.get(key)
    if not isinstance(value, list):
        obj[key] = []
        return
    seen: set[str] = set()
    items: JsonArray = []
    for item in value:
        fingerprint = json.dumps(item, sort_keys=True, ensure_ascii=False)
        if fingerprint in seen:
            continue
        seen.add(fingerprint)
        items.append(item)
        if len(items) >= limit:
            break
    obj[key] = items


def _filter_items_without_evidence(obj: JsonObject, key: str) -> None:
    value = obj.get(key)
    if not isinstance(value, list):
        return
    obj[key] = [item for item in value if _has_specific_evidence(item)]


def _has_specific_evidence(item: JsonValue) -> bool:
    if not isinstance(item, dict):
        return False
    evidence = item.get("evidence")
    return isinstance(evidence, str) and bool(evidence.strip())


def _filter_existing_missing_test_cases(obj: JsonObject, existing_tests: str) -> None:
    value = obj.get("missing_test_cases")
    if not isinstance(value, list):
        return
    existing_names = _existing_test_name_set(existing_tests)
    if not existing_names:
        return
    obj["missing_test_cases"] = [item for item in value if _missing_test_case_name(item) not in existing_names]


def _existing_test_name_set(existing_tests: str) -> set[str]:
    names: set[str] = set()
    for line in existing_tests.splitlines():
        if "::" not in line:
            continue
        _, raw_name = line.rsplit("::", maxsplit=1)
        normalized = _normalized_test_name(raw_name)
        if normalized:
            names.add(normalized)
    return names


def _missing_test_case_name(item: JsonValue) -> str:
    if not isinstance(item, dict):
        return ""
    name = item.get("name")
    return _normalized_test_name(name) if isinstance(name, str) else ""


def _normalized_test_name(name: str) -> str:
    return re.sub(r"[^a-z0-9]+", "", name.lower())


def _compact_review_output(obj: JsonObject) -> JsonObject:
    """Keep only fields useful when another agent reads the script output."""
    output: JsonObject = {}
    for key in ("mode", "summary", "risk_level", "confidence"):
        value = obj.get(key)
        if isinstance(value, str) and value:
            output[key] = value
    for key in ("findings", "missing_test_cases", "flaky_risks", "review_points", "do_not_change"):
        value = obj.get(key)
        if isinstance(value, list) and value:
            output[key] = value
    return output


def _write_or_print_json(result: JsonObject, output_path: Path | None) -> None:
    output = json.dumps(result, ensure_ascii=False, indent=2)
    if output_path is None:
        _ = sys.stdout.write(f"{output}\n")
        return
    output_path.parent.mkdir(parents=True, exist_ok=True)
    _ = output_path.write_text(f"{output}\n", encoding="utf-8")
    _ = sys.stdout.write(f"wrote {output_path}\n")


def _require_non_empty_review(review: str, empty_message: str = EMPTY_REVIEW_MESSAGE) -> str:
    review_body = review.strip()
    if not review_body:
        raise ReviewError(empty_message)
    return review_body


def _strip_outer_markdown_fence(content: str) -> str:
    lines = content.splitlines()
    if len(lines) < MARKDOWN_FENCE_BOUNDARY_LINE_COUNT:
        return content
    first = lines[0].strip().lower()
    last = lines[-1].strip()
    if first in {"```", "```json", "```md", "```markdown"} and last == "```":
        return "\n".join(lines[1:-1]).strip()
    return content


def _default_base_url() -> str:
    host = _default_local_llm_host()
    return f"http://{host}:{DEFAULT_LOCAL_LLM_PORT}/{DEFAULT_LOCAL_LLM_API_VERSION}"


def _default_local_llm_host() -> str:
    if not _is_wsl():
        return DEFAULT_LOCAL_LLM_HOST
    for host in _wsl_host_candidates():
        if _can_connect(host, DEFAULT_LOCAL_LLM_PORT):
            return host
    return DEFAULT_LOCAL_LLM_HOST


def _wsl_host_candidates() -> list[str]:
    candidates = [
        candidate for candidate in (_wsl_default_gateway(), _wsl_resolv_nameserver()) if candidate is not None
    ]
    return _unique_strings([*candidates, DEFAULT_LOCAL_LLM_HOST])


def _wsl_default_gateway() -> str | None:
    ip_command = shutil.which("ip")
    if ip_command is None:
        return None
    try:
        result = subprocess.run([ip_command, "route", "show", "default"], check=False, capture_output=True, text=True)
    except FileNotFoundError:
        return None
    if result.returncode != 0:
        return None
    for line in result.stdout.splitlines():
        fields = line.split()
        if (
            len(fields) >= IP_ROUTE_DEFAULT_GATEWAY_FIELD_COUNT
            and fields[0] == "default"
            and fields[1] == "via"
            and _is_ipv4_address(fields[IP_ROUTE_DEFAULT_GATEWAY_INDEX])
        ):
            return fields[IP_ROUTE_DEFAULT_GATEWAY_INDEX]
    return None


def _wsl_resolv_nameserver() -> str | None:
    try:
        resolv_conf = WSL_RESOLV_CONF_PATH.read_text(encoding="utf-8")
    except OSError:
        return None
    for line in resolv_conf.splitlines():
        fields = line.split()
        if (
            len(fields) == RESOLV_CONF_NAMESERVER_FIELD_COUNT
            and fields[0] == "nameserver"
            and _is_ipv4_address(fields[1])
        ):
            return fields[1]
    return None


def _can_connect(host: str, port: int) -> bool:
    try:
        with socket.create_connection((host, port), timeout=LOCAL_LLM_PROBE_TIMEOUT_SECONDS):
            return True
    except OSError:
        return False


def _is_wsl() -> bool:
    if os.environ.get("WSL_INTEROP") is not None:
        return True
    try:
        kernel_release = Path("/proc/sys/kernel/osrelease").read_text(encoding="utf-8")
    except OSError:
        return False
    return WSL_KERNEL_MARKER in kernel_release.lower()


def _is_ipv4_address(value: str) -> bool:
    try:
        return isinstance(ipaddress.ip_address(value), ipaddress.IPv4Address)
    except ValueError:
        return False


def _unique_strings(values: Iterable[str]) -> list[str]:
    unique_values: list[str] = []
    seen: set[str] = set()
    for value in values:
        if value not in seen:
            seen.add(value)
            unique_values.append(value)
    return unique_values


if __name__ == "__main__":
    raise SystemExit(main())
