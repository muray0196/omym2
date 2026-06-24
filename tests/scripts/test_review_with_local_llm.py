# ruff: noqa: INP001, PLR0913, SLF001 -- Tests mirror standalone developer script internals.
"""
Summary: Tests local LLM review output handling.
Why: Prevents metadata-only review files when the model returns no content.
"""

from __future__ import annotations

import importlib.util
import sys
from pathlib import Path
from typing import TYPE_CHECKING, Protocol, cast

import pytest

if TYPE_CHECKING:
    from pytest_mock import MockerFixture

PROJECT_ROOT_NOT_FOUND_MESSAGE = "Unable to locate project root from test file."
MODULE_LOAD_ERROR_MESSAGE = "Unable to load review_with_local_llm.py"


class ReviewModule(Protocol):
    """Typed subset of review_with_local_llm.py exercised by these tests."""

    ReviewError: type[Exception]
    EMPTY_REVIEW_MESSAGE: str

    def _format_agent_review(self, review: str, tool_iterations: int) -> str: ...

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
    ) -> str: ...


def test_agent_review_rejects_empty_model_content() -> None:
    """Blank final model content must not be accepted as a completed review."""
    module = _review_module()

    with pytest.raises(module.ReviewError, match=module.EMPTY_REVIEW_MESSAGE):
        _ = module._format_agent_review("", tool_iterations=8)  # pyright: ignore[reportPrivateUsage]  # Script helper validates the regression boundary.


def test_direct_review_rejects_empty_model_content(mocker: MockerFixture) -> None:
    """Blank direct chat content must fail before a metadata-only file is written."""
    module = _review_module()
    _ = mocker.patch.object(
        module,
        "_http_json",
        return_value={"choices": [{"message": {"content": "   "}}]},
    )

    with pytest.raises(module.ReviewError, match=module.EMPTY_REVIEW_MESSAGE):
        _ = module._request_review(  # pyright: ignore[reportPrivateUsage]  # Script helper validates the regression boundary.
            base_url="http://localhost:1234/v1",
            api_key="lm-studio",
            model="omym2-review",
            system_prompt="system",
            user_prompt="user",
            timeout=1,
            temperature=0.1,
        )


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


def _project_root() -> Path:
    current_file = Path(__file__).resolve()
    for parent in current_file.parents:
        if (parent / "pyproject.toml").is_file():
            return parent
    raise RuntimeError(PROJECT_ROOT_NOT_FOUND_MESSAGE)
