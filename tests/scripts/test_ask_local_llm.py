# ruff: noqa: INP001, PLR0913, SLF001 -- Tests mirror standalone developer script internals.
"""
Summary: Tests local LLM subtask prompt building, context path safety, and output normalization.
Why: Keeps delegated subtasks bounded to caller-provided input and stable JSON contracts.
"""

from __future__ import annotations

import importlib.util
import json
import sys
import textwrap
from pathlib import Path
from typing import TYPE_CHECKING, Protocol, cast

import pytest

if TYPE_CHECKING:
    from collections.abc import Callable

PROJECT_ROOT_NOT_FOUND_MESSAGE = "Unable to locate project root from test file."
MODULE_LOAD_ERROR_MESSAGE = "Unable to load ask_local_llm.py"
EXPECTED_KEY_POINT_CAP = 8
EXPECTED_OPEN_QUESTION_CAP = 4
EXPECTED_READINGS_CAP = 6
EXIT_SUCCESS = 0
EXIT_FAILURE = 1
EXIT_INVALID_JSON = 2


class AskModule(Protocol):
    """Typed subset of ask_local_llm.py exercised by these tests."""

    ReviewError: type[Exception]
    SYSTEM_PROMPT: str
    AskContextFile: Callable[[str, str], object]

    def main(self, argv: list[str] | None = ...) -> int: ...

    def _parse_args(self, argv: list[str] | None) -> object: ...

    def _build_user_prompt(self, args: object, context_files: list[object], stdin_text: str) -> str: ...

    def _normalize_ask_json(self, obj: dict[str, object], command: str) -> dict[str, object]: ...

    def _compact_ask_output(self, obj: dict[str, object], command: str) -> dict[str, object]: ...


@pytest.fixture(name="ask_module")
def ask_module_fixture(monkeypatch: pytest.MonkeyPatch) -> AskModule:
    """Load the script module without probing for a local LLM endpoint."""
    module = _load_ask_module()
    monkeypatch.setattr(module, "_default_base_url", lambda: "http://localhost:1234/v1")
    return module


def test_question_prompt_includes_file_block_question_and_stdin(ask_module: AskModule) -> None:
    """The model must see the caller-selected files, question, and stdin input."""
    args = ask_module._parse_args(  # pyright: ignore[reportPrivateUsage]
        ["question", "--ask", "Which layer records FileEvents?", "--files", "docs/STORAGE.md", "--stdin"]
    )
    context_file = ask_module.AskContextFile("docs/STORAGE.md", "stored paths are library-root-relative")

    prompt = ask_module._build_user_prompt(args, [context_file], "extra stdin evidence")  # pyright: ignore[reportPrivateUsage]

    assert '<file path="docs/STORAGE.md">' in prompt
    assert "stored paths are library-root-relative" in prompt
    assert "Which layer records FileEvents?" in prompt
    assert "extra stdin evidence" in prompt


def test_summarize_prompt_includes_focus(ask_module: AskModule) -> None:
    """An explicit focus must reach the model as a dedicated block."""
    args = ask_module._parse_args(["summarize", "--focus", "path identity", "--stdin"])  # pyright: ignore[reportPrivateUsage]

    prompt = ask_module._build_user_prompt(args, [], "some diff text")  # pyright: ignore[reportPrivateUsage]

    assert "<focus>\npath identity\n</focus>" in prompt
    assert "key_points" in prompt


def test_system_prompt_forbids_guessing_and_markdown(ask_module: AskModule) -> None:
    """The shared system prompt must pin grounding and JSON-only output."""
    assert "Return JSON only" in ask_module.SYSTEM_PROMPT
    assert '"unknown"' in ask_module.SYSTEM_PROMPT


@pytest.mark.parametrize(
    ("raw_path", "reason"),
    [
        ("../etc/passwd", "path escapes repository root"),
        (".env", "sensitive-looking paths are not allowed"),
    ],
)
def test_unsafe_context_paths_are_rejected(
    ask_module: AskModule,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
    tmp_path: Path,
    raw_path: str,
    reason: str,
) -> None:
    """Caller-selected context file reads stay bounded by path safety checks."""
    monkeypatch.setattr(ask_module, "_repo_root", lambda: tmp_path)
    monkeypatch.setattr(ask_module, "_tracked_file_set", set)

    exit_code = ask_module.main(["summarize", "--files", raw_path, "--dry-prompt"])

    assert exit_code == EXIT_FAILURE
    assert reason in capsys.readouterr().err


def test_normalize_fills_defaults_and_coerces_confidence(ask_module: AskModule) -> None:
    """Missing keys get defaults and invalid values are made deterministic."""
    result = ask_module._normalize_ask_json(  # pyright: ignore[reportPrivateUsage]
        {"confidence": "certain", "open_questions": "not a list"},
        "summarize",
    )

    assert result["summary"] == ""
    assert result["key_points"] == []
    assert result["open_questions"] == []
    assert result["confidence"] == "low"


def test_normalize_dedupes_and_caps_lists(ask_module: AskModule) -> None:
    """Overlong or repeated model output should be trimmed deterministically."""
    result = ask_module._normalize_ask_json(  # pyright: ignore[reportPrivateUsage]
        {
            "summary": "s",
            "key_points": ["repeat", "repeat", *(f"point {index}" for index in range(10))],
            "open_questions": [f"question {index}" for index in range(6)],
            "confidence": "high",
        },
        "summarize",
    )

    key_points = cast("list[object]", result["key_points"])
    assert key_points[:2] == ["repeat", "point 0"]
    assert len(key_points) == EXPECTED_KEY_POINT_CAP
    assert len(cast("list[object]", result["open_questions"])) == EXPECTED_OPEN_QUESTION_CAP
    assert result["confidence"] == "high"


def test_compact_output_skips_empty_lists(ask_module: AskModule) -> None:
    """Script output should be lean enough to feed directly to another agent."""
    normalized = ask_module._normalize_ask_json(  # pyright: ignore[reportPrivateUsage]
        {"answer": "unknown", "evidence": [], "unknowns": ["input lacks the apply flow"]},
        "question",
    )

    result = ask_module._compact_ask_output(normalized, "question")  # pyright: ignore[reportPrivateUsage]

    assert result == {"answer": "unknown", "unknowns": ["input lacks the apply flow"], "confidence": "low"}


def test_question_without_ask_is_rejected(ask_module: AskModule) -> None:
    """The question subcommand requires exactly one --ask value."""
    with pytest.raises(SystemExit):
        _ = ask_module._parse_args(["question", "--stdin"])  # pyright: ignore[reportPrivateUsage]


def test_missing_input_sources_fail_clearly(ask_module: AskModule, capsys: pytest.CaptureFixture[str]) -> None:
    """Every subcommand needs at least one of --files or --stdin, even with --dry-prompt."""
    exit_code = ask_module.main(["summarize", "--dry-prompt"])

    assert exit_code == EXIT_FAILURE
    assert "no input provided" in capsys.readouterr().err


def test_doc_description_requires_exactly_one_file(ask_module: AskModule, capsys: pytest.CaptureFixture[str]) -> None:
    """The doc metadata contract targets a single docs markdown file."""
    exit_code = ask_module.main(["doc-description", "--stdin", "--dry-prompt"])

    assert exit_code == EXIT_FAILURE
    assert "exactly one --files entry" in capsys.readouterr().err


def test_main_dry_prompt_prints_prompt_without_request(
    ask_module: AskModule,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
    tmp_path: Path,
) -> None:
    """--dry-prompt must render the full prompt without touching the network."""
    _write_text(tmp_path / "notes.md", "# Notes\napply records FileEvents before mutation\n")
    monkeypatch.setattr(ask_module, "_repo_root", lambda: tmp_path)
    monkeypatch.setattr(ask_module, "_tracked_file_set", set)
    monkeypatch.setattr(ask_module, "_request_review", _fail_if_called)

    exit_code = ask_module.main(["doc-description", "--files", "notes.md", "--dry-prompt"])

    assert exit_code == EXIT_SUCCESS
    output = capsys.readouterr().out
    assert "<system_prompt>" in output
    assert '<file path="notes.md">' in output
    assert "apply records FileEvents before mutation" in output


def test_main_normalizes_mocked_model_output(
    ask_module: AskModule,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
    tmp_path: Path,
) -> None:
    """End-to-end run with a mocked request must print normalized compact JSON."""
    _write_text(tmp_path / "notes.md", "# Notes\ncontent\n")
    monkeypatch.setattr(ask_module, "_repo_root", lambda: tmp_path)
    monkeypatch.setattr(ask_module, "_tracked_file_set", set)
    monkeypatch.setattr(ask_module, "_request_review", _duplicated_evidence_answer)

    exit_code = ask_module.main(["question", "--ask", "Is it documented?", "--files", "notes.md"])

    assert exit_code == EXIT_SUCCESS
    payload = cast("object", json.loads(capsys.readouterr().out))
    assert payload == {"answer": "yes", "evidence": ["notes.md"], "confidence": "low"}


def test_main_reports_invalid_model_json_with_exit_code_two(
    ask_module: AskModule,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
    tmp_path: Path,
) -> None:
    """A non-JSON model reply is a distinct failure class for calling agents."""
    _write_text(tmp_path / "notes.md", "# Notes\ncontent\n")
    monkeypatch.setattr(ask_module, "_repo_root", lambda: tmp_path)
    monkeypatch.setattr(ask_module, "_tracked_file_set", set)
    monkeypatch.setattr(ask_module, "_request_review", _non_json_answer)

    exit_code = ask_module.main(["summarize", "--files", "notes.md"])

    assert exit_code == EXIT_INVALID_JSON
    assert "did not return valid JSON" in capsys.readouterr().err


def test_docs_search_dry_prompt_includes_catalog_and_request(
    ask_module: AskModule,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
    tmp_path: Path,
) -> None:
    """docs-search needs no --files/--stdin and renders the catalog without network use."""
    docs_root = _fixture_docs(tmp_path)
    monkeypatch.setattr(ask_module, "_repo_root", lambda: tmp_path)
    monkeypatch.setattr(ask_module, "_tracked_file_set", set)
    monkeypatch.setattr(ask_module, "_request_review", _fail_if_called)

    exit_code = ask_module.main(
        ["docs-search", "--ask", "ファイルイベントはいつ記録される?", "--docs-root", str(docs_root), "--dry-prompt"]
    )

    assert exit_code == EXIT_SUCCESS
    output = capsys.readouterr().out
    assert "<docs_catalog>" in output
    assert "path: guide.md" in output
    assert "- #apply-flow Apply Flow" in output
    assert "ファイルイベントはいつ記録される?" in output


def test_docs_search_drops_hallucinated_readings_and_fills_lines(
    ask_module: AskModule,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
    tmp_path: Path,
) -> None:
    """Invented paths and anchors are dropped; line and section come from the parsed docs."""
    docs_root = _fixture_docs(tmp_path)
    monkeypatch.setattr(ask_module, "_repo_root", lambda: tmp_path)
    monkeypatch.setattr(ask_module, "_tracked_file_set", set)
    canned = json.dumps(
        {
            "readings": [
                {"path": "guide.md", "anchor": "apply-flow", "why": "records timing"},
                {"path": "ghost.md", "anchor": "apply-flow", "why": "invented path"},
                {"path": "guide.md", "anchor": "no-such-anchor", "why": "invented anchor"},
            ],
            "confidence": "high",
        }
    )
    monkeypatch.setattr(ask_module, "_request_review", _canned_answer(canned))

    exit_code = ask_module.main(["docs-search", "--ask", "event timing", "--docs-root", str(docs_root)])

    assert exit_code == EXIT_SUCCESS
    payload = cast("dict[str, object]", json.loads(capsys.readouterr().out))
    assert payload["readings"] == [
        {
            "path": "guide.md",
            "line": _heading_line(docs_root, "guide.md", "## Apply Flow"),
            "anchor": "apply-flow",
            "section": "Apply Flow",
            "why": "records timing",
        }
    ]
    assert payload["confidence"] == "high"


def test_docs_search_dedupes_and_caps_readings(
    ask_module: AskModule,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
    tmp_path: Path,
) -> None:
    """Duplicate (path, anchor) pairs collapse and output stays within the readings cap."""
    docs_root = _fixture_docs(tmp_path)
    monkeypatch.setattr(ask_module, "_repo_root", lambda: tmp_path)
    monkeypatch.setattr(ask_module, "_tracked_file_set", set)
    anchors = [
        ("guide.md", "apply-guide"),
        ("guide.md", "apply-guide"),
        ("guide.md", "apply-flow"),
        ("guide.md", "undo-flow"),
        ("guide.md", "check-flow"),
        ("guide.md", "history-flow"),
        ("contracts/plan.md", "plan-contract"),
        ("contracts/plan.md", "planaction"),
    ]
    canned = json.dumps(
        {
            "readings": [{"path": path, "anchor": anchor, "why": "relevant"} for path, anchor in anchors],
            "confidence": "medium",
        }
    )
    monkeypatch.setattr(ask_module, "_request_review", _canned_answer(canned))

    exit_code = ask_module.main(["docs-search", "--ask", "everything", "--docs-root", str(docs_root)])

    assert exit_code == EXIT_SUCCESS
    payload = cast("dict[str, object]", json.loads(capsys.readouterr().out))
    readings = cast("list[dict[str, object]]", payload["readings"])
    assert len(readings) == EXPECTED_READINGS_CAP
    assert len({(reading["path"], reading["anchor"]) for reading in readings}) == EXPECTED_READINGS_CAP


def test_docs_search_empty_anchor_falls_back_to_first_heading(
    ask_module: AskModule,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
    tmp_path: Path,
) -> None:
    """A doc-level reading without an anchor resolves to the doc's first heading."""
    docs_root = _fixture_docs(tmp_path)
    monkeypatch.setattr(ask_module, "_repo_root", lambda: tmp_path)
    monkeypatch.setattr(ask_module, "_tracked_file_set", set)
    canned = json.dumps(
        {"readings": [{"path": "contracts/plan.md", "anchor": "", "why": "overview"}], "confidence": "medium"}
    )
    monkeypatch.setattr(ask_module, "_request_review", _canned_answer(canned))

    exit_code = ask_module.main(["docs-search", "--ask", "plan overview", "--docs-root", str(docs_root)])

    assert exit_code == EXIT_SUCCESS
    payload = cast("dict[str, object]", json.loads(capsys.readouterr().out))
    assert payload["readings"] == [
        {
            "path": "contracts/plan.md",
            "line": _heading_line(docs_root, "contracts/plan.md", "# Plan Contract"),
            "anchor": "plan-contract",
            "section": "Plan Contract",
            "why": "overview",
        }
    ]


def test_docs_search_empty_readings_keeps_suggested_queries(
    ask_module: AskModule,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
    tmp_path: Path,
) -> None:
    """A no-match reply compacts to fallback queries agents can feed to search_docs.py."""
    docs_root = _fixture_docs(tmp_path)
    monkeypatch.setattr(ask_module, "_repo_root", lambda: tmp_path)
    monkeypatch.setattr(ask_module, "_tracked_file_set", set)
    canned = json.dumps({"readings": [], "suggested_queries": ["plan apply"], "confidence": "low"})
    monkeypatch.setattr(ask_module, "_request_review", _canned_answer(canned))

    exit_code = ask_module.main(["docs-search", "--ask", "unrelated topic", "--docs-root", str(docs_root)])

    assert exit_code == EXIT_SUCCESS
    payload = cast("object", json.loads(capsys.readouterr().out))
    assert payload == {"suggested_queries": ["plan apply"], "confidence": "low"}


def test_docs_search_requires_ask(ask_module: AskModule) -> None:
    """The docs-search subcommand requires exactly one --ask value."""
    with pytest.raises(SystemExit):
        _ = ask_module._parse_args(["docs-search"])  # pyright: ignore[reportPrivateUsage]


def test_docs_search_missing_docs_root_fails_clearly(
    ask_module: AskModule,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
    tmp_path: Path,
) -> None:
    """A missing docs directory is an advisory failure, not a crash."""
    monkeypatch.setattr(ask_module, "_repo_root", lambda: tmp_path)
    monkeypatch.setattr(ask_module, "_tracked_file_set", set)

    exit_code = ask_module.main(
        ["docs-search", "--ask", "anything", "--docs-root", str(tmp_path / "missing"), "--dry-prompt"]
    )

    assert exit_code == EXIT_FAILURE
    assert "does not exist" in capsys.readouterr().err


def _fail_if_called(**_kwargs: object) -> str:
    message = "the LLM request function must not be called in this test"
    raise AssertionError(message)


def _duplicated_evidence_answer(**_kwargs: object) -> str:
    return '{"answer": "yes", "evidence": ["notes.md", "notes.md"], "confidence": "certain"}'


def _non_json_answer(**_kwargs: object) -> str:
    return "not json at all"


def _canned_answer(answer: str) -> Callable[..., str]:
    def _respond(**_kwargs: object) -> str:
        return answer

    return _respond


def _fixture_docs(root: Path) -> Path:
    docs_root = root / "docs"
    _write_text(
        docs_root / "guide.md",
        textwrap.dedent(
            """\
            ---
            type: Execution Spec
            title: Apply Guide
            description: Defines the apply flow.
            tags: [apply]
            timestamp: 2026-07-05T02:00:00+09:00
            ---

            # Apply Guide

            ## Apply Flow

            FileEvents are recorded before mutation.

            ## Undo Flow

            Undo reverses the last run.

            ## Check Flow

            Check reports issues.

            ## History Flow

            History lists runs.
            """
        ),
    )
    _write_text(
        docs_root / "contracts" / "plan.md",
        textwrap.dedent(
            """\
            ---
            type: Contract
            title: Plan Contract
            description: Defines PlanAction states.
            tags: [plan]
            timestamp: 2026-07-05T02:00:00+09:00
            ---

            # Plan Contract

            ## PlanAction

            PlanAction states are pending and applied.
            """
        ),
    )
    return docs_root


def _heading_line(docs_root: Path, relative_path: str, heading: str) -> int:
    lines = (docs_root / relative_path).read_text(encoding="utf-8").splitlines()
    return lines.index(heading) + 1


def _load_ask_module() -> AskModule:
    project_root = _project_root()
    scripts_path = str(project_root / "scripts")
    if scripts_path not in sys.path:
        sys.path.insert(0, scripts_path)
    module_path = project_root / "scripts" / "ask_local_llm.py"
    spec = importlib.util.spec_from_file_location("ask_local_llm", module_path)
    if spec is None or spec.loader is None:
        raise RuntimeError(MODULE_LOAD_ERROR_MESSAGE)
    module = importlib.util.module_from_spec(spec)
    sys.modules["ask_local_llm"] = module
    spec.loader.exec_module(module)
    return cast("AskModule", cast("object", module))


def _write_text(path: Path, content: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    _ = path.write_text(content, encoding="utf-8")


def _project_root() -> Path:
    current_file = Path(__file__).resolve()
    for parent in current_file.parents:
        if (parent / "pyproject.toml").is_file():
            return parent
    raise RuntimeError(PROJECT_ROOT_NOT_FOUND_MESSAGE)
