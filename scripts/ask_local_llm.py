# ruff: noqa: EM101, EM102, INP001, TRY003 -- Standalone local tool mirrors review_with_local_llm conventions and raises descriptive CLI errors.
"""
Summary: Delegate one small bounded subtask (summarize, question, doc metadata) to a local OpenAI-compatible LLM.
Why: Let agents offload cheap context-compression work while Python keeps file access and output shape constrained.
"""

from __future__ import annotations

import argparse
import json
import os
import sys
import textwrap
from dataclasses import dataclass
from pathlib import Path
from typing import TYPE_CHECKING

# The sibling review script is the single owner of these helpers; importing its
# private names is the intended reuse seam for standalone developer scripts.
from review_with_local_llm import (
    DEFAULT_API_KEY,
    DEFAULT_MAX_FILE_CHARS,
    DEFAULT_MAX_OUTPUT_TOKENS,
    DEFAULT_REVIEW_MODEL,
    DEFAULT_TEMPERATURE,
    DEFAULT_TIMEOUT_SECONDS,
    ReviewError,
    _clip_middle,  # pyright: ignore[reportPrivateUsage]
    _dedupe_and_limit_list_field,  # pyright: ignore[reportPrivateUsage]
    _default_base_url,  # pyright: ignore[reportPrivateUsage]
    _extract_json_object,  # pyright: ignore[reportPrivateUsage]
    _normalize_relative_path_text,  # pyright: ignore[reportPrivateUsage]
    _print_dry_prompt,  # pyright: ignore[reportPrivateUsage]
    _read_text_file,  # pyright: ignore[reportPrivateUsage]
    _repo_root,  # pyright: ignore[reportPrivateUsage]
    _request_review,  # pyright: ignore[reportPrivateUsage]
    _tracked_file_set,  # pyright: ignore[reportPrivateUsage]
    _validate_context_path,  # pyright: ignore[reportPrivateUsage]
    _write_or_print_json,  # pyright: ignore[reportPrivateUsage]
    _xml_block,  # pyright: ignore[reportPrivateUsage]
)

if TYPE_CHECKING:
    from review_with_local_llm import JsonObject

DEFAULT_ASK_MAX_TOTAL_FILE_CHARS = 60_000
DEFAULT_ASK_MAX_INPUT_CHARS = 100_000
EMPTY_ANSWER_MESSAGE = "local LLM returned an empty answer"
SUMMARIZE_COMMAND = "summarize"
QUESTION_COMMAND = "question"
DOC_DESCRIPTION_COMMAND = "doc-description"
MAX_KEY_POINTS = 8
MAX_OPEN_QUESTIONS = 4
MAX_EVIDENCE_ITEMS = 6
MAX_UNKNOWNS = 4
MAX_TAGS = 5
MAX_DOC_DESCRIPTION_CHARS = 200
CONFIDENCE_LEVELS = frozenset({"low", "medium", "high"})


class ParsedArgs(argparse.Namespace):
    """Typed argparse result used after parser validation."""

    def __init__(self) -> None:
        super().__init__()
        self.command: str = SUMMARIZE_COMMAND
        self.files: list[str] = []
        self.stdin: bool = False
        self.focus: str | None = None
        self.ask: str | None = None
        self.output: Path | None = None
        self.base_url: str = _default_base_url()
        self.api_key: str = DEFAULT_API_KEY
        self.model: str | None = None
        self.timeout: int = DEFAULT_TIMEOUT_SECONDS
        self.max_input_chars: int = DEFAULT_ASK_MAX_INPUT_CHARS
        self.max_file_chars: int = DEFAULT_MAX_FILE_CHARS
        self.max_total_file_chars: int = DEFAULT_ASK_MAX_TOTAL_FILE_CHARS
        self.max_output_tokens: int = DEFAULT_MAX_OUTPUT_TOKENS
        self.temperature: float = DEFAULT_TEMPERATURE
        self.dry_prompt: bool = False
        self.no_response_format: bool = False


@dataclass(frozen=True, slots=True)
class AskContextFile:
    """A repository file explicitly provided as subtask input."""

    path: str
    content: str


@dataclass(frozen=True, slots=True)
class OutputSpec:
    """Required output keys and list caps for one subcommand."""

    text_keys: tuple[str, ...]
    list_limits: tuple[tuple[str, int], ...]


OUTPUT_SPECS: dict[str, OutputSpec] = {
    SUMMARIZE_COMMAND: OutputSpec(
        text_keys=("summary",),
        list_limits=(("key_points", MAX_KEY_POINTS), ("open_questions", MAX_OPEN_QUESTIONS)),
    ),
    QUESTION_COMMAND: OutputSpec(
        text_keys=("answer",),
        list_limits=(("evidence", MAX_EVIDENCE_ITEMS), ("unknowns", MAX_UNKNOWNS)),
    ),
    DOC_DESCRIPTION_COMMAND: OutputSpec(
        text_keys=("description",),
        list_limits=(("tags", MAX_TAGS),),
    ),
}

SYSTEM_PROMPT = """
You are OMYM2's local LLM subtask assistant.

Hard scope:
- Complete only the requested subtask. Do not review, refactor, plan, or advise beyond it.
- Ground every statement in the provided files, stdin input, and instructions.
- When the provided input does not answer something, write "unknown" instead of guessing.
- Do not invent file paths, APIs, behavior, or facts that the input does not show.

Output rules:
- Return JSON only. No Markdown. No code fences. No commentary outside JSON.
""".strip()

TASK_INSTRUCTIONS: dict[str, str] = {
    SUMMARIZE_COMMAND: textwrap.dedent(
        """
        Task: summarize
        Goal: Compress the provided files and stdin input so another agent can act on them without reading them.
        - Prioritize contracts, invariants, decisions, and anything surprising.
        - When a <focus> block is present, weight the summary toward that focus.
        - key_points must be standalone statements grounded in the provided input.
        - open_questions are only things the provided input leaves genuinely unclear.
        """
    ).strip(),
    QUESTION_COMMAND: textwrap.dedent(
        """
        Task: question
        Goal: Answer the single question in the <question> block using only the provided input.
        - Every evidence item must cite a file path or a quoted snippet from the provided input.
        - If the input cannot answer the question, set answer to "unknown" and explain the gap in unknowns.
        - unknowns list what the provided input does not settle.
        """
    ).strip(),
    DOC_DESCRIPTION_COMMAND: textwrap.dedent(
        f"""
        Task: doc-description
        Goal: Draft docs frontmatter metadata (description and tags) for the single provided docs markdown file.
        - description: exactly one sentence, at most {MAX_DOC_DESCRIPTION_CHARS} characters, summarizing what the doc specifies.
        - tags: 3 to 5 kebab-case topic tags.
        - Base the description and tags only on the provided file content.
        """
    ).strip(),
}

JSON_OUTPUT_CONTRACTS: dict[str, str] = {
    SUMMARIZE_COMMAND: f"""
Return exactly one JSON object with this shape:
{{
  "summary": "string",
  "key_points": ["string"],
  "open_questions": ["string"],
  "confidence": "low | medium | high"
}}

Limits:
- key_points: max {MAX_KEY_POINTS} items
- open_questions: max {MAX_OPEN_QUESTIONS} items
""".strip(),
    QUESTION_COMMAND: f"""
Return exactly one JSON object with this shape:
{{
  "answer": "string",
  "evidence": ["file path or quoted snippet from the provided input"],
  "unknowns": ["string"],
  "confidence": "low | medium | high"
}}

Limits:
- evidence: max {MAX_EVIDENCE_ITEMS} items; each item must cite a file path or quoted snippet from the input
- unknowns: max {MAX_UNKNOWNS} items
""".strip(),
    DOC_DESCRIPTION_COMMAND: f"""
Return exactly one JSON object with this shape:
{{
  "description": "one sentence of at most {MAX_DOC_DESCRIPTION_CHARS} characters",
  "tags": ["kebab-case-topic"],
  "confidence": "low | medium | high"
}}

Limits:
- tags: 3 to 5 kebab-case items
""".strip(),
}


def main(argv: list[str] | None = None) -> int:
    """Run one local LLM subtask command."""
    try:
        args = _parse_args(argv)
        _validate_subcommand_inputs(args)
        repo_root = _repo_root()
        stdin_text = sys.stdin.read() if args.stdin else ""
        context_files = _load_context_files(args, repo_root)
        user_prompt = _build_user_prompt(args, context_files, stdin_text)
        if args.dry_prompt:
            _print_dry_prompt(SYSTEM_PROMPT, user_prompt)
            return 0
        answer = _request_review(
            base_url=args.base_url,
            api_key=args.api_key,
            model=args.model or DEFAULT_REVIEW_MODEL,
            system_prompt=SYSTEM_PROMPT,
            user_prompt=user_prompt,
            timeout=args.timeout,
            temperature=args.temperature,
            max_output_tokens=args.max_output_tokens,
            use_response_format=not args.no_response_format,
            empty_message=EMPTY_ANSWER_MESSAGE,
        )
        result = _compact_ask_output(_normalize_ask_json(_extract_json_object(answer), args.command), args.command)
        _write_or_print_json(result, args.output)
    except ReviewError as exc:
        _ = sys.stderr.write(f"local LLM subtask failed: {exc}\n")
        return 1
    except json.JSONDecodeError as exc:
        _ = sys.stderr.write(f"local LLM subtask failed: model did not return valid JSON: {exc}\n")
        return 2
    return 0


def _parse_args(argv: list[str] | None) -> ParsedArgs:
    parser = argparse.ArgumentParser(
        description="Delegate one small bounded subtask to a local OpenAI-compatible LLM. No agent/tool calls and no file edits.",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=textwrap.dedent(
            """
            Examples:
              python scripts/ask_local_llm.py summarize --files docs/STORAGE.md --focus "stored path policy"
              python scripts/ask_local_llm.py question --files docs/execution/apply.md --ask "When are FileEvents recorded?"
              python scripts/ask_local_llm.py doc-description --files docs/execution/apply.md
              git diff | python scripts/ask_local_llm.py summarize --stdin
            """
        ),
    )
    subcommands = parser.add_subparsers(dest="command", required=True)
    summarize = subcommands.add_parser(SUMMARIZE_COMMAND, help="Compress the provided input for another agent.")
    _ = summarize.add_argument("--focus", default=None, help="Optional topic that steers the summary.")
    question = subcommands.add_parser(QUESTION_COMMAND, help="Answer one specific question about the provided input.")
    _ = question.add_argument("--ask", required=True, help="The single question to answer.")
    doc_description = subcommands.add_parser(
        DOC_DESCRIPTION_COMMAND,
        help="Draft docs frontmatter description and tags for one docs markdown file.",
    )
    for subparser in (summarize, question, doc_description):
        _add_common_args(subparser)
    return parser.parse_args(argv, namespace=ParsedArgs())


def _add_common_args(parser: argparse.ArgumentParser) -> None:
    _ = parser.add_argument(
        "--files", action="append", default=[], help="Repo-relative context file to include. May be repeated."
    )
    _ = parser.add_argument("--stdin", action="store_true", help="Read extra input from stdin.")
    _ = parser.add_argument(
        "--max-file-chars",
        type=int,
        default=DEFAULT_MAX_FILE_CHARS,
        help="Maximum characters read from a single context file.",
    )
    _ = parser.add_argument(
        "--max-total-file-chars",
        type=int,
        default=DEFAULT_ASK_MAX_TOTAL_FILE_CHARS,
        help="Maximum total characters read from context files.",
    )
    _ = parser.add_argument(
        "--max-input-chars",
        type=int,
        default=DEFAULT_ASK_MAX_INPUT_CHARS,
        help="Maximum stdin characters included in prompts.",
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
        "--temperature", type=float, default=DEFAULT_TEMPERATURE, help="Subtask sampling temperature."
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


def _validate_subcommand_inputs(args: ParsedArgs) -> None:
    if not args.files and not args.stdin:
        raise ReviewError("no input provided: pass --files and/or --stdin")
    if args.command == DOC_DESCRIPTION_COMMAND and len(args.files) != 1:
        raise ReviewError("doc-description requires exactly one --files entry")


def _load_context_files(args: ParsedArgs, repo_root: Path) -> list[AskContextFile]:
    tracked_files = _tracked_file_set()
    context: list[AskContextFile] = []
    total_chars = 0
    seen: set[str] = set()
    for raw_path in args.files:
        normalized = _normalize_relative_path_text(raw_path)
        if normalized in seen:
            continue
        seen.add(normalized)
        rejection = _validate_context_path(repo_root, raw_path, tracked_files, allow_untracked=True)
        if rejection is not None:
            raise ReviewError(f"rejected context file {raw_path!r}: {rejection}")
        remaining = max(0, args.max_total_file_chars - total_chars)
        if remaining <= 0:
            break
        content = _read_text_file(repo_root / normalized, max_chars=args.max_file_chars)
        clipped = _clip_middle(content, remaining)
        total_chars += len(clipped)
        context.append(AskContextFile(normalized, clipped))
    return context


def _build_user_prompt(args: ParsedArgs, context_files: list[AskContextFile], stdin_text: str) -> str:
    file_blocks = (
        "\n\n".join(_xml_block("file", file.content, {"path": file.path}) for file in context_files)
        or "[No context files were loaded.]"
    )
    sections = [TASK_INSTRUCTIONS[args.command], JSON_OUTPUT_CONTRACTS[args.command]]
    if args.command == QUESTION_COMMAND:
        sections.append(_xml_block("question", args.ask or ""))
    elif args.command == SUMMARIZE_COMMAND and args.focus:
        sections.append(_xml_block("focus", args.focus))
    sections.extend(
        (
            _xml_block("stdin_input", _clip_middle(stdin_text, args.max_input_chars) or "[no stdin input supplied]"),
            _xml_block("context_files", file_blocks),
            'Use only the input above. If it is insufficient, lower confidence and write "unknown" rather than guessing.',
        )
    )
    return "\n\n".join(sections)


def _normalize_ask_json(obj: JsonObject, command: str) -> JsonObject:
    spec = OUTPUT_SPECS[command]
    for key in spec.text_keys:
        if not isinstance(obj.setdefault(key, ""), str):
            obj[key] = ""
    for key, limit in spec.list_limits:
        _ = obj.setdefault(key, [])
        _dedupe_and_limit_list_field(obj, key, limit)
    if obj.setdefault("confidence", "low") not in CONFIDENCE_LEVELS:
        obj["confidence"] = "low"
    return obj


def _compact_ask_output(obj: JsonObject, command: str) -> JsonObject:
    """Keep only fields useful when another agent reads the script output."""
    spec = OUTPUT_SPECS[command]
    output: JsonObject = {}
    for key in spec.text_keys:
        value = obj.get(key)
        if isinstance(value, str):
            output[key] = value
    for key, _limit in spec.list_limits:
        value = obj.get(key)
        if isinstance(value, list) and value:
            output[key] = value
    confidence = obj.get("confidence")
    if isinstance(confidence, str):
        output["confidence"] = confidence
    return output


if __name__ == "__main__":
    raise SystemExit(main())
