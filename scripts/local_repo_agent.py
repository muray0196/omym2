# ruff: noqa: EM101, EM102, PLR0911, PLR0913, S310, S603, TRY003, TRY300 -- Local developer script calls configured HTTP and git.
"""
Summary: Provide a read-only tool agent for local repository review.
Why: Let local LLM review inspect bounded OMYM2 context safely.
"""

from __future__ import annotations

import argparse
import json
import os
import re
import subprocess
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import TYPE_CHECKING, cast
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen

if TYPE_CHECKING:
    from http.client import HTTPResponse

DEFAULT_BASE_URL = "http://localhost:1234/v1"
DEFAULT_MODEL = "omym2-review"
DEFAULT_API_KEY = "lm-studio"
DEFAULT_TIMEOUT_SECONDS = 300
DEFAULT_TEMPERATURE = 0.1
DEFAULT_TOOL_ITERATIONS = 8
DEFAULT_LIST_FILE_LIMIT = 200
DEFAULT_GREP_MATCH_LIMIT = 80
DEFAULT_READ_LINE_LIMIT = 160
DEFAULT_GIT_DIFF_BASE = "HEAD~1"
DEFAULT_GIT_DIFF_CHAR_LIMIT = 120_000
MAX_LIST_FILE_LIMIT = 500
MAX_GREP_MATCH_LIMIT = 200
MAX_READ_LINE_LIMIT = 240
MAX_GIT_DIFF_CHAR_LIMIT = 200_000
TEXT_FILE_SIZE_LIMIT_BYTES = 1_000_000
MATCH_LINE_TEXT_LIMIT = 240
TOOL_RESULT_CHAR_LIMIT = 60_000
JSON_PREVIEW_LIMIT = 1000
IGNORED_DIRECTORY_NAMES = frozenset(
    {
        ".git",
        ".venv",
        "__pycache__",
        ".pytest_cache",
        ".mypy_cache",
        ".ruff_cache",
        ".data",
        ".reviews",
        "dist",
        "build",
    }
)
GIT_DIFF_DEFAULT_PATHS = (
    "src",
    "tests",
    "docs",
    "scripts",
    "AGENTS.md",
    "ARCHITECTURE.md",
    "pyproject.toml",
)

SYSTEM_PROMPT = """You are a read-only review agent for the OMYM2 repository.

You cannot see repository files unless you call tools.

Use tools to inspect only the minimum relevant context.

Prefer grep or list_files before read_file unless an exact path is already known.

When reading files, request bounded line ranges.

Do not request write access.

Do not request shell access.

Report findings with file paths and line numbers when possible. Mark uncertainty explicitly."""

type JsonValue = None | bool | int | float | str | JsonArray | JsonObject
type JsonArray = list[JsonValue]
type JsonObject = dict[str, JsonValue]


@dataclass(frozen=True, slots=True)
class AgentResult:
    """Final local review response and execution metadata."""

    content: str
    tool_iterations: int
    exhausted_tool_budget: bool


class LocalRepoAgentError(RuntimeError):
    """Raised when the local repo agent cannot complete a review."""


class ParsedArgs(argparse.Namespace):
    """Typed argparse result for the local repo agent CLI."""

    def __init__(self) -> None:
        super().__init__()
        self.request: list[str] = []
        self.base_url: str = os.environ.get("OMYM2_LMSTUDIO_BASE_URL", DEFAULT_BASE_URL)
        self.api_key: str = os.environ.get("OMYM2_LOCAL_LLM_API_KEY", DEFAULT_API_KEY)
        self.model: str = os.environ.get("OMYM2_REVIEW_MODEL", DEFAULT_MODEL)
        self.timeout: int = DEFAULT_TIMEOUT_SECONDS
        self.max_tool_iterations: int = DEFAULT_TOOL_ITERATIONS


class RepoReadOnlyTools:
    """Validated read-only repository tools exposed to the local review model."""

    def __init__(self, repo_root: Path) -> None:
        self._repo_root: Path = repo_root.resolve()

    def list_files(self, substring: str | None = None, max_results: int = DEFAULT_LIST_FILE_LIMIT) -> JsonObject:
        """List readable text files under the repository root."""
        limit = _clamp_int(max_results, minimum=1, maximum=MAX_LIST_FILE_LIMIT)
        paths: list[str] = []
        for path in sorted(self._repo_root.rglob("*")):
            if len(paths) >= limit:
                break
            if not path.is_file() or self._is_ignored_path(path):
                continue
            relative_path = self._relative_path(path)
            if substring and substring not in relative_path:
                continue
            if self._read_text(path) is None:
                continue
            paths.append(relative_path)
        return cast(
            "JsonObject",
            {
                "files": paths,
                "count": len(paths),
                "limit": limit,
                "truncated": len(paths) >= limit,
            },
        )

    def grep(self, pattern: str, max_matches: int = DEFAULT_GREP_MATCH_LIMIT) -> JsonObject:
        """Search UTF-8 text files with an explicit regular expression."""
        limit = _clamp_int(max_matches, minimum=1, maximum=MAX_GREP_MATCH_LIMIT)
        try:
            regex = re.compile(pattern)
        except re.error as exc:
            return {"error": f"invalid regex: {exc}"}

        matches: list[JsonObject] = []
        for path in sorted(self._repo_root.rglob("*")):
            if len(matches) >= limit:
                break
            if not path.is_file() or self._is_ignored_path(path):
                continue
            text = self._read_text(path)
            if text is None:
                continue
            relative_path = self._relative_path(path)
            for line_number, line in enumerate(text.splitlines(), start=1):
                if regex.search(line) is None:
                    continue
                matches.append(
                    {
                        "path": relative_path,
                        "line": line_number,
                        "text": line.strip()[:MATCH_LINE_TEXT_LIMIT],
                    }
                )
                if len(matches) >= limit:
                    break
        return cast(
            "JsonObject",
            {
                "matches": matches,
                "count": len(matches),
                "limit": limit,
                "truncated": len(matches) >= limit,
                "search_mode": "python-regex",
            },
        )

    def read_file(self, path: str, start_line: int = 1, max_lines: int = DEFAULT_READ_LINE_LIMIT) -> JsonObject:
        """Read a bounded line range from a repository-relative text file."""
        resolved_path = self._resolve_repo_file(path)
        limit = _clamp_int(max_lines, minimum=1, maximum=MAX_READ_LINE_LIMIT)
        start = _clamp_int(start_line, minimum=1, maximum=10_000_000)
        text = self._read_text(resolved_path)
        if text is None:
            return {"error": f"unsupported, binary, huge, or unreadable file: {path}"}

        lines = text.splitlines()
        selected = lines[start - 1 : start - 1 + limit]
        end_line = start + len(selected) - 1 if selected else start - 1
        numbered_content = "\n".join(f"{line_number}: {line}" for line_number, line in enumerate(selected, start=start))
        return cast(
            "JsonObject",
            {
                "path": self._relative_path(resolved_path),
                "start_line": start,
                "end_line": end_line,
                "content": numbered_content,
                "truncated": start - 1 + limit < len(lines),
            },
        )

    def git_diff(self, base: str = DEFAULT_GIT_DIFF_BASE, max_chars: int = DEFAULT_GIT_DIFF_CHAR_LIMIT) -> JsonObject:
        """Read a bounded no-ext-diff git diff for review-relevant repository areas."""
        limit = _clamp_int(max_chars, minimum=1, maximum=MAX_GIT_DIFF_CHAR_LIMIT)
        command = [
            "git",
            "-C",
            str(self._repo_root),
            "diff",
            "--no-ext-diff",
            base,
            "--",
            *GIT_DIFF_DEFAULT_PATHS,
        ]
        result = subprocess.run(command, check=False, capture_output=True, text=True)
        if result.returncode not in {0, 1}:
            return {"error": result.stderr.strip() or f"git diff failed with exit code {result.returncode}"}
        diff = result.stdout
        truncated = len(diff) > limit
        if truncated:
            diff = diff[:limit]
        return cast(
            "JsonObject",
            {
                "base": base,
                "paths": list(GIT_DIFF_DEFAULT_PATHS),
                "diff": diff,
                "truncated": truncated,
                "max_chars": limit,
            },
        )

    def execute(self, name: str, arguments: JsonObject) -> JsonObject:
        """Run a named read-only tool after model arguments have been parsed."""
        try:
            if name == "list_files":
                return self.list_files(
                    substring=_optional_str(arguments.get("substring")),
                    max_results=_optional_int(arguments.get("max_results"), DEFAULT_LIST_FILE_LIMIT),
                )
            if name == "grep":
                pattern = arguments.get("pattern")
                if not isinstance(pattern, str) or not pattern:
                    return {"error": "grep requires a non-empty string pattern"}
                return self.grep(
                    pattern=pattern,
                    max_matches=_optional_int(arguments.get("max_matches"), DEFAULT_GREP_MATCH_LIMIT),
                )
            if name == "read_file":
                path = arguments.get("path")
                if not isinstance(path, str) or not path:
                    return {"error": "read_file requires a non-empty repo-relative path"}
                return self.read_file(
                    path=path,
                    start_line=_optional_int(arguments.get("start_line"), 1),
                    max_lines=_optional_int(arguments.get("max_lines"), DEFAULT_READ_LINE_LIMIT),
                )
            if name == "git_diff":
                return self.git_diff(
                    base=_optional_str(arguments.get("base")) or DEFAULT_GIT_DIFF_BASE,
                    max_chars=_optional_int(arguments.get("max_chars"), DEFAULT_GIT_DIFF_CHAR_LIMIT),
                )
            return {"error": f"unknown or unavailable read-only tool: {name}"}
        except LocalRepoAgentError as exc:
            return {"error": str(exc)}

    def _resolve_repo_file(self, raw_path: str) -> Path:
        candidate = Path(raw_path)
        if candidate.is_absolute():
            raise LocalRepoAgentError("absolute paths are not allowed")
        resolved_path = (self._repo_root / candidate).resolve()
        if not resolved_path.is_relative_to(self._repo_root):
            raise LocalRepoAgentError("path escapes repository root")
        if self._is_ignored_path(resolved_path):
            raise LocalRepoAgentError("path is inside an ignored directory")
        if not resolved_path.is_file():
            raise LocalRepoAgentError("path is not a readable file")
        return resolved_path

    def _is_ignored_path(self, path: Path) -> bool:
        try:
            relative_path = path.resolve().relative_to(self._repo_root)
        except ValueError:
            return True
        return any(part in IGNORED_DIRECTORY_NAMES for part in relative_path.parts)

    def _relative_path(self, path: Path) -> str:
        return path.resolve().relative_to(self._repo_root).as_posix()

    def _read_text(self, path: Path) -> str | None:
        try:
            if path.stat().st_size > TEXT_FILE_SIZE_LIMIT_BYTES:
                return None
            data = path.read_bytes()
        except OSError:
            return None
        if b"\x00" in data:
            return None
        try:
            return data.decode("utf-8")
        except UnicodeDecodeError:
            return None


def run_local_repo_agent(
    *,
    user_request: str,
    repo_root: Path | None = None,
    base_url: str | None = None,
    api_key: str = DEFAULT_API_KEY,
    model: str | None = None,
    timeout: int = DEFAULT_TIMEOUT_SECONDS,
    temperature: float = DEFAULT_TEMPERATURE,
    max_tool_iterations: int = DEFAULT_TOOL_ITERATIONS,
) -> AgentResult:
    """Run the local read-only repository review agent."""
    root = Path.cwd() if repo_root is None else repo_root
    tools = RepoReadOnlyTools(root)
    endpoint_base_url = base_url or os.environ.get("OMYM2_LMSTUDIO_BASE_URL", DEFAULT_BASE_URL)
    selected_model = model or os.environ.get("OMYM2_REVIEW_MODEL", DEFAULT_MODEL)
    iterations = _clamp_int(max_tool_iterations, minimum=0, maximum=DEFAULT_TOOL_ITERATIONS)
    messages: list[JsonObject] = [
        {"role": "system", "content": SYSTEM_PROMPT},
        {"role": "user", "content": user_request},
    ]

    for iteration in range(iterations + 1):
        payload = _request_chat_completion(
            base_url=endpoint_base_url,
            api_key=api_key,
            model=selected_model,
            messages=messages,
            timeout=timeout,
            temperature=temperature,
            include_tools=iteration < iterations,
        )
        message = _first_message(payload)
        tool_calls = _tool_calls(message)
        if not tool_calls:
            return AgentResult(
                content=_message_content(message),
                tool_iterations=iteration,
                exhausted_tool_budget=False,
            )
        if iteration >= iterations:
            partial = _message_content(message).strip()
            suffix = "\n\nTool iteration budget exhausted before the model produced a final answer."
            return AgentResult(
                content=f"{partial}{suffix}" if partial else suffix.strip(),
                tool_iterations=iteration,
                exhausted_tool_budget=True,
            )

        messages.append(message)
        for tool_call in tool_calls:
            tool_name = _tool_call_name(tool_call)
            tool_arguments = _tool_call_arguments(tool_call)
            result = tools.execute(tool_name, tool_arguments)
            messages.append(
                {
                    "role": "tool",
                    "tool_call_id": _tool_call_id(tool_call),
                    "content": _json_tool_result(result),
                }
            )

    return AgentResult(
        content="Tool iteration budget exhausted before the model produced a final answer.",
        tool_iterations=iterations,
        exhausted_tool_budget=True,
    )


def _request_chat_completion(
    *,
    base_url: str,
    api_key: str,
    model: str,
    messages: list[JsonObject],
    timeout: int,
    temperature: float,
    include_tools: bool,
) -> JsonObject:
    body: JsonObject = cast(
        "JsonObject",
        {
            "model": model,
            "messages": messages,
            "temperature": temperature,
            "stream": False,
        },
    )
    if include_tools:
        body["tools"] = _tool_schemas()
        body["tool_choice"] = "auto"
    return _http_json("POST", _openai_url(base_url, "chat/completions"), api_key, body, timeout)


def _tool_schemas() -> JsonArray:
    return [
        _tool_schema(
            "list_files",
            "List readable UTF-8 text files under the repo root. Supports optional substring filtering.",
            {
                "substring": {"type": "string"},
                "max_results": {"type": "integer", "minimum": 1, "maximum": MAX_LIST_FILE_LIMIT},
            },
            [],
        ),
        _tool_schema(
            "grep",
            "Search readable UTF-8 text files with a Python regular expression.",
            {
                "pattern": {"type": "string"},
                "max_matches": {"type": "integer", "minimum": 1, "maximum": MAX_GREP_MATCH_LIMIT},
            },
            ["pattern"],
        ),
        _tool_schema(
            "read_file",
            "Read a bounded line range from one repo-relative UTF-8 text file.",
            {
                "path": {"type": "string"},
                "start_line": {"type": "integer", "minimum": 1},
                "max_lines": {"type": "integer", "minimum": 1, "maximum": MAX_READ_LINE_LIMIT},
            },
            ["path"],
        ),
        _tool_schema(
            "git_diff",
            "Read a bounded git diff using git diff --no-ext-diff for review-relevant paths.",
            {
                "base": {"type": "string"},
                "max_chars": {"type": "integer", "minimum": 1, "maximum": MAX_GIT_DIFF_CHAR_LIMIT},
            },
            [],
        ),
    ]


def _tool_schema(name: str, description: str, properties: JsonObject, required: list[str]) -> JsonObject:
    return cast(
        "JsonObject",
        {
            "type": "function",
            "function": {
                "name": name,
                "description": description,
                "parameters": {
                    "type": "object",
                    "properties": properties,
                    "required": required,
                    "additionalProperties": False,
                },
            },
        },
    )


def _first_message(payload: JsonObject) -> JsonObject:
    choices = payload.get("choices")
    if not isinstance(choices, list) or not choices:
        raise LocalRepoAgentError("chat completion response did not contain choices[0].message")
    first_choice = choices[0]
    if not isinstance(first_choice, dict):
        raise LocalRepoAgentError("chat completion response did not contain choices[0].message")
    message = first_choice.get("message")
    if not isinstance(message, dict):
        raise LocalRepoAgentError("chat completion response did not contain choices[0].message")
    return message


def _message_content(message: JsonObject) -> str:
    content = message.get("content")
    if content is None:
        return ""
    if not isinstance(content, str):
        raise LocalRepoAgentError("chat completion message content was not text")
    return content.strip()


def _tool_calls(message: JsonObject) -> list[JsonObject]:
    tool_calls = message.get("tool_calls")
    if tool_calls is None:
        return []
    if not isinstance(tool_calls, list):
        raise LocalRepoAgentError("chat completion tool_calls was not a list")
    return [tool_call for tool_call in tool_calls if isinstance(tool_call, dict)]


def _tool_call_id(tool_call: JsonObject) -> str:
    tool_call_id = tool_call.get("id")
    if isinstance(tool_call_id, str):
        return tool_call_id
    return "missing-tool-call-id"


def _tool_call_name(tool_call: JsonObject) -> str:
    function = tool_call.get("function")
    if not isinstance(function, dict):
        return ""
    name = function.get("name")
    return name if isinstance(name, str) else ""


def _tool_call_arguments(tool_call: JsonObject) -> JsonObject:
    function = tool_call.get("function")
    if not isinstance(function, dict):
        return {}
    raw_arguments = function.get("arguments")
    if raw_arguments is None:
        return {}
    if isinstance(raw_arguments, dict):
        return raw_arguments
    if not isinstance(raw_arguments, str):
        return {}
    try:
        arguments = cast("JsonValue", json.loads(raw_arguments))
    except json.JSONDecodeError as exc:
        return {"_parse_error": f"invalid tool argument JSON: {exc}"}
    return arguments if isinstance(arguments, dict) else {}


def _json_tool_result(result: JsonObject) -> str:
    content = json.dumps(result, ensure_ascii=False)
    if len(content) <= TOOL_RESULT_CHAR_LIMIT:
        return content
    preview = content[:TOOL_RESULT_CHAR_LIMIT]
    return json.dumps(
        {
            "truncated": True,
            "preview": preview,
        },
        ensure_ascii=False,
    )


def _http_json(method: str, url: str, api_key: str, body: JsonObject, timeout: int) -> JsonObject:
    request = Request(
        url,
        data=json.dumps(body).encode("utf-8"),
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
        body_text = exc.read().decode("utf-8", errors="replace")[:JSON_PREVIEW_LIMIT]
        raise LocalRepoAgentError(f"HTTP {exc.code} from local LLM endpoint: {body_text}") from exc
    except TimeoutError as exc:
        raise LocalRepoAgentError(f"timed out after {timeout} seconds waiting for local LLM endpoint at {url}") from exc
    except URLError as exc:
        raise LocalRepoAgentError(f"could not reach local LLM endpoint at {url}: {exc.reason}") from exc

    try:
        payload = cast("JsonValue", json.loads(raw_payload))
    except json.JSONDecodeError as exc:
        raise LocalRepoAgentError("local LLM endpoint returned invalid JSON") from exc
    if not isinstance(payload, dict):
        raise LocalRepoAgentError("local LLM endpoint returned a non-object JSON payload")
    return payload


def _openai_url(base_url: str, endpoint: str) -> str:
    normalized = base_url.rstrip("/")
    if normalized.endswith("/v1"):
        return f"{normalized}/{endpoint}"
    return f"{normalized}/v1/{endpoint}"


def _optional_str(value: JsonValue) -> str | None:
    return value if isinstance(value, str) else None


def _optional_int(value: JsonValue, default: int) -> int:
    return value if isinstance(value, int) else default


def _clamp_int(value: int, *, minimum: int, maximum: int) -> int:
    return max(minimum, min(value, maximum))


def _parse_args(argv: list[str] | None) -> ParsedArgs:
    parser = argparse.ArgumentParser(description="Run a read-only local repository review agent.")
    _ = parser.add_argument("request", nargs="*", help="Review request. Reads stdin when omitted.")
    _ = parser.add_argument(
        "--base-url",
        default=os.environ.get("OMYM2_LMSTUDIO_BASE_URL", DEFAULT_BASE_URL),
        help="OpenAI-compatible base URL for LM Studio or another local server.",
    )
    _ = parser.add_argument(
        "--api-key",
        default=os.environ.get("OMYM2_LOCAL_LLM_API_KEY", DEFAULT_API_KEY),
        help="API key for the OpenAI-compatible endpoint. Local servers usually accept a dummy value.",
    )
    _ = parser.add_argument(
        "--model",
        default=os.environ.get("OMYM2_REVIEW_MODEL", DEFAULT_MODEL),
        help="Local review model ID.",
    )
    _ = parser.add_argument("--timeout", type=int, default=DEFAULT_TIMEOUT_SECONDS, help="HTTP timeout in seconds.")
    _ = parser.add_argument(
        "--max-tool-iterations",
        type=int,
        default=DEFAULT_TOOL_ITERATIONS,
        help="Maximum read-only tool-call rounds.",
    )
    return parser.parse_args(argv, namespace=ParsedArgs())


def main(argv: list[str] | None = None) -> int:
    """Run the local repo agent from the command line."""
    args = _parse_args(argv)
    user_request = " ".join(args.request).strip() or sys.stdin.read().strip()
    if not user_request:
        _ = sys.stderr.write("local repo agent failed: no review request was provided\n")
        return 1
    try:
        result = run_local_repo_agent(
            user_request=user_request,
            base_url=args.base_url,
            api_key=args.api_key,
            model=args.model,
            timeout=args.timeout,
            max_tool_iterations=args.max_tool_iterations,
        )
    except LocalRepoAgentError as exc:
        _ = sys.stderr.write(f"local repo agent failed: {exc}\n")
        return 1
    _ = sys.stdout.write(f"{result.content}\n")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
