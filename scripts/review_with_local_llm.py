# ruff: noqa: EM101, EM102, INP001, PLR0913, S310, S603, TRY003 -- Local developer script calls configured HTTP and git/gh.
"""Run an OMYM2-focused review with a local OpenAI-compatible LLM."""

from __future__ import annotations

import argparse
import json
import os
import subprocess
import sys
import textwrap
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Any
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen

DEFAULT_BASE_URL = "http://172.22.1.207:1234/v1"
DEFAULT_API_KEY = "lm-studio"
DEFAULT_TIMEOUT_SECONDS = 120
DEFAULT_MAX_CHARS = 120_000
DEFAULT_TEMPERATURE = 0.1
DEFAULT_CONTEXT_FILES = (
    "AGENTS.md",
    "ARCHITECTURE.md",
    "docs/index.md",
    "docs/development.md",
)
DEFAULT_PROMPT_PATH = Path("docs/agent/local_llm_review_prompt.md")
DEFAULT_REVIEW_DIR = Path(".reviews")
EXCLUDED_DIFF_PATH_PREFIXES = (".reviews/", ".git/", "__pycache__/")
TEXT_FILE_SIZE_LIMIT_BYTES = 500_000


@dataclass(frozen=True, slots=True)
class ReviewInput:
    """Resolved review input."""

    source_label: str
    content: str
    output_path: Path


class ReviewError(RuntimeError):
    """Raised when a local review cannot be prepared or executed."""


def main(argv: list[str] | None = None) -> int:
    """Run the local LLM review command."""
    args = _parse_args(argv)
    try:
        review_input = _resolve_review_input(args)
        context = _load_context(args.context)
        system_prompt = _load_system_prompt(args.prompt)
        model = args.model or os.environ.get("OMYM2_LOCAL_LLM_MODEL")
        if model is None:
            model = _discover_first_model(args.base_url, args.api_key, args.timeout)
        review = _request_review(
            base_url=args.base_url,
            api_key=args.api_key,
            model=model,
            system_prompt=system_prompt,
            user_prompt=_build_user_prompt(review_input, context, args.max_chars),
            timeout=args.timeout,
            temperature=args.temperature,
        )
        _write_review(review_input.output_path, review_input, context, model, args.base_url, review)
    except ReviewError as exc:
        _ = sys.stderr.write(f"local LLM review failed: {exc}\n")
        return 1

    _ = sys.stdout.write(f"wrote {review_input.output_path}\n")
    return 0


def _parse_args(argv: list[str] | None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Review OMYM2 diffs or logs with a local OpenAI-compatible LLM.")
    source_group = parser.add_mutually_exclusive_group()
    source_group.add_argument(
        "--worktree",
        action="store_true",
        help="Review current staged, unstaged, and untracked changes.",
    )
    source_group.add_argument("--pr", type=int, help="Review a GitHub pull request diff through gh pr diff.")
    source_group.add_argument("--stdin", action="store_true", help="Read review input from stdin.")
    source_group.add_argument("--diff-file", type=Path, help="Read review input from a diff file.")
    source_group.add_argument("--log", type=Path, help="Read a failure log and ask for failure classification.")
    parser.add_argument(
        "--repo",
        default=None,
        help="Optional GitHub repository for gh pr diff, for example owner/name.",
    )
    parser.add_argument(
        "--context",
        action="append",
        default=list(DEFAULT_CONTEXT_FILES),
        help="Context file to include.",
    )
    parser.add_argument("--prompt", type=Path, default=DEFAULT_PROMPT_PATH, help="System prompt markdown path.")
    parser.add_argument("--output", type=Path, default=None, help="Review output path.")
    parser.add_argument(
        "--base-url",
        default=os.environ.get("OMYM2_LOCAL_LLM_BASE_URL", DEFAULT_BASE_URL),
        help="OpenAI-compatible base URL. LM Studio default: http://localhost:1234/v1.",
    )
    parser.add_argument(
        "--api-key",
        default=os.environ.get("OMYM2_LOCAL_LLM_API_KEY", DEFAULT_API_KEY),
        help="API key for the OpenAI-compatible client. Local servers usually accept a dummy value.",
    )
    parser.add_argument("--model", default=None, help="Model ID. If omitted, the script tries GET /models.")
    parser.add_argument("--timeout", type=int, default=DEFAULT_TIMEOUT_SECONDS, help="HTTP timeout in seconds.")
    parser.add_argument("--max-chars", type=int, default=DEFAULT_MAX_CHARS, help="Maximum review input characters.")
    parser.add_argument("--temperature", type=float, default=DEFAULT_TEMPERATURE, help="LLM sampling temperature.")
    return parser.parse_args(argv)


def _resolve_review_input(args: argparse.Namespace) -> ReviewInput:
    if args.pr is not None:
        content = _load_pr_diff(args.pr, args.repo)
        return ReviewInput(
            source_label=f"pr-{args.pr}",
            content=content,
            output_path=args.output or DEFAULT_REVIEW_DIR / f"pr-{args.pr}-local.md",
        )
    if args.stdin:
        return ReviewInput(
            source_label="stdin",
            content=sys.stdin.read(),
            output_path=args.output or DEFAULT_REVIEW_DIR / "stdin-local.md",
        )
    if args.diff_file is not None:
        return ReviewInput(
            source_label=f"diff-file:{args.diff_file}",
            content=_read_text_file(args.diff_file),
            output_path=args.output or DEFAULT_REVIEW_DIR / "diff-local.md",
        )
    if args.log is not None:
        return ReviewInput(
            source_label=f"log:{args.log}",
            content=_read_text_file(args.log),
            output_path=args.output or DEFAULT_REVIEW_DIR / "log-local.md",
        )
    return ReviewInput(
        source_label="worktree",
        content=_load_worktree_diff(),
        output_path=args.output or DEFAULT_REVIEW_DIR / "worktree-local.md",
    )


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
    raise ReviewError("no staged, unstaged, or untracked changes were found")


def _run_git_diff(args: list[str]) -> str:
    return _run_command(["git", *args], allow_exit_codes={0, 1})


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


def _run_command(command: list[str], allow_exit_codes: set[int] | None = None) -> str:
    allowed = {0} if allow_exit_codes is None else allow_exit_codes
    try:
        result = subprocess.run(command, check=False, capture_output=True, text=True)
    except FileNotFoundError as exc:
        raise ReviewError(f"required command was not found: {command[0]}") from exc
    if result.returncode not in allowed:
        stderr = result.stderr.strip()
        raise ReviewError(f"command failed ({' '.join(command)}): {stderr or result.returncode}")
    return result.stdout


def _load_context(context_paths: list[str]) -> list[tuple[str, str]]:
    context: list[tuple[str, str]] = []
    seen: set[str] = set()
    for raw_path in context_paths:
        if raw_path in seen:
            continue
        seen.add(raw_path)
        path = Path(raw_path)
        if path.is_file():
            context.append((raw_path, _read_text_file(path)))
    return context


def _load_system_prompt(prompt_path: Path) -> str:
    if prompt_path.is_file():
        return _read_text_file(prompt_path)
    return textwrap.dedent(
        """
        You are reviewing OMYM2 changes. Focus on design invariants, architecture boundaries,
        durable Plan/Run/FileEvent semantics, path handling, test sufficiency, and harness risk.
        Do not nitpick formatting unless it affects maintainability. Mark uncertain findings as needs human check.
        """
    ).strip()


def _read_text_file(path: Path) -> str:
    try:
        return path.read_text(encoding="utf-8")
    except OSError as exc:
        raise ReviewError(f"failed to read {path}: {exc}") from exc


def _discover_first_model(base_url: str, api_key: str, timeout: int) -> str:
    payload = _http_json("GET", _openai_url(base_url, "models"), api_key, None, timeout)
    data = payload.get("data")
    if not isinstance(data, list) or len(data) == 0:
        raise ReviewError("no model was configured and GET /models returned no models")
    first_model = data[0]
    if not isinstance(first_model, dict) or not isinstance(first_model.get("id"), str):
        raise ReviewError("no model was configured and GET /models returned an unsupported response")
    return first_model["id"]


def _request_review(
    *,
    base_url: str,
    api_key: str,
    model: str,
    system_prompt: str,
    user_prompt: str,
    timeout: int,
    temperature: float,
) -> str:
    request_body = {
        "model": model,
        "messages": [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": user_prompt},
        ],
        "temperature": temperature,
        "stream": False,
    }
    payload = _http_json("POST", _openai_url(base_url, "chat/completions"), api_key, request_body, timeout)
    try:
        content = payload["choices"][0]["message"]["content"]
    except (KeyError, IndexError, TypeError) as exc:
        raise ReviewError("chat completion response did not contain choices[0].message.content") from exc
    if not isinstance(content, str):
        raise ReviewError("chat completion content was not text")
    return _strip_outer_markdown_fence(content.strip())


def _http_json(method: str, url: str, api_key: str, body: dict[str, Any] | None, timeout: int) -> dict[str, Any]:
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
        with urlopen(request, timeout=timeout) as response:
            raw_payload = response.read().decode("utf-8")
    except HTTPError as exc:
        body_text = exc.read().decode("utf-8", errors="replace")[:1000]
        raise ReviewError(f"HTTP {exc.code} from local LLM endpoint: {body_text}") from exc
    except URLError as exc:
        raise ReviewError(f"could not reach local LLM endpoint at {url}: {exc.reason}") from exc
    try:
        payload = json.loads(raw_payload)
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


def _build_user_prompt(review_input: ReviewInput, context: list[tuple[str, str]], max_chars: int) -> str:
    context_blocks = "\n\n".join(f"## {path}\n\n```text\n{content}\n```" for path, content in context)
    input_content = review_input.content
    truncated_notice = ""
    if len(input_content) > max_chars:
        input_content = input_content[:max_chars]
        truncated_notice = f"\n\nInput was truncated to {max_chars} characters. Call out that limitation."

    return "\n".join(
        [
            f"Review source: {review_input.source_label}",
            "",
            "Project context:",
            "",
            context_blocks,
            "",
            "Review input:",
            "",
            "```diff",
            input_content,
            "```",
            "",
            "Produce Markdown with exactly these sections:",
            "",
            "# Local LLM Review",
            "## Verdict",
            "## Blocking",
            "## Major",
            "## Minor",
            "## Missing Tests",
            "## OMYM2 Invariant Risks",
            "## Suggested Agent Prompt",
            "",
            "Keep findings grounded in the provided context and input. Do not invent files or behavior not shown.",
            truncated_notice.strip(),
        ]
    ).strip()


def _strip_outer_markdown_fence(content: str) -> str:
    lines = content.splitlines()
    if len(lines) < 2:
        return content
    first = lines[0].strip().lower()
    last = lines[-1].strip()
    if first in {"```", "```md", "```markdown"} and last == "```":
        return "\n".join(lines[1:-1]).strip()
    return content


def _write_review(
    output_path: Path,
    review_input: ReviewInput,
    context: list[tuple[str, str]],
    model: str,
    base_url: str,
    review: str,
) -> None:
    output_path.parent.mkdir(parents=True, exist_ok=True)
    generated_at = datetime.now(UTC).isoformat()
    context_list = "\n".join(f"- {path}" for path, _ in context) or "- none"
    output = "\n".join(
        [
            "---",
            f"source: {json.dumps(review_input.source_label)}",
            f"model: {json.dumps(model)}",
            f"base_url: {json.dumps(base_url.rstrip('/'))}",
            f"generated_at: {json.dumps(generated_at)}",
            "---",
            "",
            "Context files:",
            context_list,
            "",
            review.strip(),
            "",
        ]
    )
    output_path.write_text(output, encoding="utf-8")


if __name__ == "__main__":
    raise SystemExit(main())
