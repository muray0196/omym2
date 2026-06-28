# ruff: noqa: INP001, PLR0913, SLF001 -- Tests mirror standalone developer script internals.
"""
Summary: Tests local LLM review output handling and context path safety.
Why: Prevents metadata-only review files and unsafe caller-selected context reads.
"""

from __future__ import annotations

import importlib.util
import sys
from pathlib import Path
from typing import TYPE_CHECKING, Protocol, cast

import pytest

if TYPE_CHECKING:
    from collections.abc import Callable

PROJECT_ROOT_NOT_FOUND_MESSAGE = "Unable to locate project root from test file."
MODULE_LOAD_ERROR_MESSAGE = "Unable to load review_with_local_llm.py"
EXPECTED_MISSING_TEST_CASE_CAP = 6
EXPECTED_FLAKY_RISK_CAP = 4
EXPECTED_REVIEW_POINT_CAP = 5
EXPECTED_DO_NOT_CHANGE_CAP = 4


class ReviewModule(Protocol):
    """Typed subset of review_with_local_llm.py exercised by these tests."""

    ReviewError: type[Exception]
    EMPTY_REVIEW_MESSAGE: str
    ReviewSource: Callable[[str, str, tuple[str, ...], tuple[str, ...]], object]

    def _request_review(
        self,
        *,
        base_url: str,
        api_key: str,
        model: str,
        system_prompt: str,
        user_prompt: str,
        timeout: int,
        temperature: float,
        max_output_tokens: int = ...,
        use_response_format: bool = ...,
    ) -> str: ...

    def _extract_json_object(self, text: str) -> dict[str, object]: ...

    def _normalize_review_json(
        self,
        obj: dict[str, object],
        mode: str,
        existing_tests: str = ...,
    ) -> dict[str, object]: ...

    def _compact_review_output(self, obj: dict[str, object]) -> dict[str, object]: ...

    def _build_user_prompt(
        self,
        mode: str,
        source: object,
        context_files: list[object],
        args: object,
        existing_tests: str,
    ) -> str: ...

    def _validate_context_path(self, repo_root: Path, raw_path: str, tracked_files: set[str]) -> str | None: ...

    def _parse_args(self, argv: list[str] | None) -> object: ...


def test_direct_review_rejects_empty_model_content(monkeypatch: pytest.MonkeyPatch) -> None:
    """Blank direct chat content must fail before a metadata-only file is written."""
    module = _review_module()
    monkeypatch.setattr(module, "_http_json", _empty_chat_completion)

    with pytest.raises(module.ReviewError, match=module.EMPTY_REVIEW_MESSAGE):
        _ = module._request_review(  # pyright: ignore[reportPrivateUsage]
            base_url="http://localhost:1234/v1",
            api_key="lm-studio",
            model="omym2-review",
            system_prompt="system",
            user_prompt="user",
            timeout=1,
            temperature=0.1,
        )


def test_blank_json_mode_response_retries_without_response_format(monkeypatch: pytest.MonkeyPatch) -> None:
    """Some local endpoints accept JSON mode but return blank content."""
    module = _review_module()
    calls: list[dict[str, object]] = []

    def fake_http_json(
        _method: str,
        _url: str,
        _api_key: str,
        body: dict[str, object] | None,
        _timeout: int,
    ) -> dict[str, object]:
        calls.append(body or {})
        if len(calls) == 1:
            return {"choices": [{"message": {"content": ""}, "finish_reason": "length"}]}
        return {"choices": [{"message": {"content": '{"risk_level": "low"}'}}]}

    monkeypatch.setattr(module, "_http_json", fake_http_json)

    result = module._request_review(  # pyright: ignore[reportPrivateUsage]
        base_url="http://localhost:1234/v1",
        api_key="lm-studio",
        model="omym2-review",
        system_prompt="system",
        user_prompt="user",
        timeout=1,
        temperature=0.1,
        use_response_format=True,
    )

    assert result == '{"risk_level": "low"}'
    assert "response_format" in calls[0]
    assert "response_format" not in calls[1]


def test_empty_model_content_reports_finish_reason(monkeypatch: pytest.MonkeyPatch) -> None:
    """Blank final content should expose endpoint finish metadata when present."""
    module = _review_module()
    monkeypatch.setattr(module, "_http_json", _empty_length_chat_completion)

    with pytest.raises(module.ReviewError, match=r"finish_reason=length"):
        _ = module._request_review(  # pyright: ignore[reportPrivateUsage]
            base_url="http://localhost:1234/v1",
            api_key="lm-studio",
            model="omym2-review",
            system_prompt="system",
            user_prompt="user",
            timeout=1,
            temperature=0.1,
            use_response_format=False,
        )


def test_extract_json_object_accepts_outer_fence() -> None:
    """Local models often wrap JSON in a fence despite the instruction."""
    module = _review_module()

    result = module._extract_json_object('```json\n{"risk_level": "low"}\n```')  # pyright: ignore[reportPrivateUsage]

    assert result == {"risk_level": "low"}


def test_compact_review_output_removes_metadata_scope_and_empty_fields() -> None:
    """Script output should be lean enough to feed directly to another agent."""
    module = _review_module()
    normalized = module._normalize_review_json(  # pyright: ignore[reportPrivateUsage]
        {
            "summary": "",
            "risk_level": "medium",
            "findings": [],
            "missing_test_cases": [{"name": "covers blank response"}],
            "review_points": ["agent should verify the reported case"],
            "metadata": {"model": "local", "base_url": "http://localhost:1234/v1"},
        },
        "review",
    )

    result = module._compact_review_output(normalized)  # pyright: ignore[reportPrivateUsage]

    assert result == {
        "mode": "review",
        "risk_level": "medium",
        "confidence": "low",
        "missing_test_cases": [{"name": "covers blank response"}],
        "review_points": ["agent should verify the reported case"],
    }


def test_prompt_includes_noise_filters_and_existing_test_inventory() -> None:
    """The model should see dedupe context before inventing missing cases."""
    module = _review_module()
    args = module._parse_args(["review", "--stdin"])  # pyright: ignore[reportPrivateUsage]
    source_factory = module.ReviewSource
    # The prompt builder is the intentional unit seam for this standalone script.
    build_prompt = module._build_user_prompt  # pyright: ignore[reportPrivateUsage]
    source = source_factory(
        "stdin",
        "diff --git a/tests/scripts/test_review_with_local_llm.py b/tests/scripts/test_review_with_local_llm.py",
        ("tests/scripts/test_review_with_local_llm.py",),
        (),
    )

    prompt = build_prompt(
        "review",
        source,
        [],
        args,
        "tests/scripts/test_review_with_local_llm.py::test_prompt_includes_noise_filters_and_existing_test_inventory",
    )

    assert "<existing_tests>" in prompt
    assert "tests/scripts/test_review_with_local_llm.py::test_" in prompt
    assert "omit if there is no concrete defect" in prompt
    assert "missing_test_cases must explain why existing tests do not already cover the case" in prompt


def test_normalize_review_json_deduplicates_and_caps_noisy_lists() -> None:
    """Overlong or repeated model output should be trimmed deterministically."""
    module = _review_module()
    duplicate_finding = {"evidence": "same evidence"}

    result = module._normalize_review_json(  # pyright: ignore[reportPrivateUsage]
        {
            "findings": [
                duplicate_finding,
                duplicate_finding,
                *({"evidence": f"evidence {index}"} for index in range(8)),
            ],
            "missing_test_cases": [{"name": f"case {index}"} for index in range(8)],
            "flaky_risks": [{"risk": f"risk {index}", "evidence": f"evidence {index}"} for index in range(6)],
            "review_points": [f"point {index}" for index in range(7)],
            "do_not_change": [f"area {index}" for index in range(6)],
        },
        "review",
    )

    assert result["findings"] == [
        {"evidence": "same evidence"},
        {"evidence": "evidence 0"},
        {"evidence": "evidence 1"},
        {"evidence": "evidence 2"},
        {"evidence": "evidence 3"},
        {"evidence": "evidence 4"},
    ]
    assert len(cast("list[object]", result["missing_test_cases"])) == EXPECTED_MISSING_TEST_CASE_CAP
    assert len(cast("list[object]", result["flaky_risks"])) == EXPECTED_FLAKY_RISK_CAP
    assert len(cast("list[object]", result["review_points"])) == EXPECTED_REVIEW_POINT_CAP
    assert len(cast("list[object]", result["do_not_change"])) == EXPECTED_DO_NOT_CHANGE_CAP


def test_normalize_review_json_removes_unsupported_noise() -> None:
    """Weak local-model items should be removed before another agent reads them."""
    module = _review_module()
    existing_tests = "tests/features/test_apply_execution.py::test_apply_marks_skip_action_applied_without_file_event"

    result = module._normalize_review_json(  # pyright: ignore[reportPrivateUsage]
        {
            "findings": [
                {"evidence": ""},
                {"evidence": "tests/features/test_apply_execution.py verifies the apply transition"},
            ],
            "missing_test_cases": [
                {"name": "test_apply_marks_skip_action_applied_without_file_event"},
                {"name": "test_apply_records_move_failure"},
            ],
            "flaky_risks": [
                {"risk": "SQLite might conflict", "evidence": None},
                {"risk": "shared database file", "evidence": "Both tests use /tmp/shared.sqlite3"},
            ],
        },
        "review",
        existing_tests,
    )

    assert result["findings"] == [{"evidence": "tests/features/test_apply_execution.py verifies the apply transition"}]
    assert result["missing_test_cases"] == [{"name": "test_apply_records_move_failure"}]
    assert result["flaky_risks"] == [{"risk": "shared database file", "evidence": "Both tests use /tmp/shared.sqlite3"}]


@pytest.mark.parametrize("legacy_mode", ["tests", "missing-tests"])
def test_legacy_mode_option_is_rejected(legacy_mode: str) -> None:
    """The script accepts only current subcommands."""
    module = _review_module()

    with pytest.raises(SystemExit):
        _ = module._parse_args(["--mode", legacy_mode, "--worktree"])  # pyright: ignore[reportPrivateUsage]


def test_failure_subcommand_is_rejected() -> None:
    """Only review and cases modes remain."""
    module = _review_module()

    with pytest.raises(SystemExit):
        _ = module._parse_args(["failure", "--stdin"])  # pyright: ignore[reportPrivateUsage]


def test_context_path_validation_rejects_model_escape_and_sensitive_paths(tmp_path: Path) -> None:
    """Caller-selected context file reads stay bounded by path safety checks."""
    module = _review_module()
    _write_text(tmp_path / "tests" / "test_safe.py", "def test_safe():\n    pass\n")
    _write_text(tmp_path / ".env", "TOKEN=secret\n")
    tracked = {"tests/test_safe.py", ".env"}

    assert module._validate_context_path(tmp_path, "tests/test_safe.py", tracked) is None  # pyright: ignore[reportPrivateUsage]
    assert module._validate_context_path(tmp_path, "../outside.py", tracked) == "path escapes repository root"  # pyright: ignore[reportPrivateUsage]
    assert (
        module._validate_context_path(  # pyright: ignore[reportPrivateUsage]
            tmp_path,
            str(tmp_path / "tests" / "test_safe.py"),
            tracked,
        )
        == "absolute paths are not allowed"
    )
    assert module._validate_context_path(tmp_path, ".env", tracked) == "sensitive-looking paths are not allowed"  # pyright: ignore[reportPrivateUsage]


def _empty_chat_completion(*_args: object, **_kwargs: object) -> dict[str, object]:
    return {"choices": [{"message": {"content": "   "}}]}


def _empty_length_chat_completion(*_args: object, **_kwargs: object) -> dict[str, object]:
    return {"choices": [{"message": {"content": ""}, "finish_reason": "length"}]}


def _review_module() -> ReviewModule:
    project_root = _project_root()
    scripts_path = str(project_root / "scripts")
    if scripts_path not in sys.path:
        sys.path.insert(0, scripts_path)
    module_path = project_root / "scripts" / "review_with_local_llm.py"
    spec = importlib.util.spec_from_file_location("review_with_local_llm", module_path)
    if spec is None or spec.loader is None:
        raise RuntimeError(MODULE_LOAD_ERROR_MESSAGE)
    module = importlib.util.module_from_spec(spec)
    sys.modules["review_with_local_llm"] = module
    spec.loader.exec_module(module)
    return cast("ReviewModule", cast("object", module))


def _write_text(path: Path, content: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    _ = path.write_text(content, encoding="utf-8")


def _project_root() -> Path:
    current_file = Path(__file__).resolve()
    for parent in current_file.parents:
        if (parent / "pyproject.toml").is_file():
            return parent
    raise RuntimeError(PROJECT_ROOT_NOT_FOUND_MESSAGE)
