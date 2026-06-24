# ruff: noqa: INP001 -- Tests cover standalone developer scripts without package markers.
"""
Summary: Tests the read-only local repository agent tools.
Why: Keeps model-facing repository access bounded and non-mutating.
"""

from __future__ import annotations

import importlib.util
import subprocess
import sys
from pathlib import Path
from typing import TYPE_CHECKING, Protocol, cast

if TYPE_CHECKING:
    from types import ModuleType

    from pytest_mock import MockerFixture

SAFE_START_LINE = 2
SAFE_END_LINE = 2
PROJECT_ROOT_NOT_FOUND_MESSAGE = "Unable to locate project root from test file."
MODULE_LOAD_ERROR_MESSAGE = "Unable to load local_repo_agent.py"
type JsonObject = dict[str, object]


class RepoTools(Protocol):
    """Subset of local repo tools exercised by these tests."""

    def list_files(self, substring: str | None = None, max_results: int = 200) -> JsonObject: ...

    def grep(self, pattern: str, max_matches: int = 80) -> JsonObject: ...

    def read_file(self, path: str, start_line: int = 1, max_lines: int = 160) -> JsonObject: ...

    def git_diff(self, base: str = "HEAD~1", max_chars: int = 120_000) -> JsonObject: ...

    def execute(self, name: str, arguments: JsonObject) -> JsonObject: ...


class RepoToolsFactory(Protocol):
    """Constructor shape for RepoReadOnlyTools loaded from the script file."""

    def __call__(self, repo_root: Path) -> RepoTools: ...


def test_list_files_returns_relative_text_paths_and_skips_ignored_dirs(tmp_path: Path) -> None:
    """Only safe readable repository files are listed."""
    _write_text(tmp_path / "src" / "app.py", "print('ok')\n")
    _write_text(tmp_path / ".reviews" / "private.md", "private\n")
    _write_text(tmp_path / "nested" / "note.md", "note\n")
    _write_binary(tmp_path / "image.bin", b"\x00\x01")
    tools = _repo_tools(tmp_path)

    result = tools.list_files(substring=".py", max_results=10)

    assert result["files"] == ["src/app.py"]
    assert result["count"] == 1


def test_grep_returns_bounded_regex_matches(tmp_path: Path) -> None:
    """Grep returns path, line, and short text for UTF-8 files only."""
    _write_text(tmp_path / "docs" / "one.md", "alpha\nbeta\n")
    _write_text(tmp_path / "docs" / "two.md", "alphabet\n")
    tools = _repo_tools(tmp_path)

    result = tools.grep(pattern="alpha", max_matches=1)

    assert result["matches"] == [{"path": "docs/one.md", "line": 1, "text": "alpha"}]
    assert result["truncated"] is True
    assert result["search_mode"] == "python-regex"


def test_read_file_rejects_paths_outside_repo_or_ignored_dirs(tmp_path: Path) -> None:
    """Read requests are validated against repo-relative path policy."""
    _write_text(tmp_path / "docs" / "safe.md", "one\ntwo\nthree\n")
    _write_text(tmp_path / ".git" / "config", "secret\n")
    tools = _repo_tools(tmp_path)

    safe_result = tools.read_file("docs/safe.md", start_line=SAFE_START_LINE, max_lines=1)
    absolute_result = tools.execute("read_file", {"path": str(tmp_path / "docs" / "safe.md")})
    traversal_result = tools.execute("read_file", {"path": "../outside.md"})
    ignored_result = tools.execute("read_file", {"path": ".git/config"})

    assert safe_result["path"] == "docs/safe.md"
    assert safe_result["start_line"] == SAFE_START_LINE
    assert safe_result["end_line"] == SAFE_END_LINE
    assert safe_result["content"] == "2: two"
    assert absolute_result["error"] == "absolute paths are not allowed"
    assert traversal_result["error"] == "path escapes repository root"
    assert ignored_result["error"] == "path is inside an ignored directory"


def test_read_file_rejects_binary_files(tmp_path: Path) -> None:
    """Binary files never become model-visible tool output."""
    _write_binary(tmp_path / "binary.dat", b"\x00\x01\x02")
    tools = _repo_tools(tmp_path)

    result = tools.read_file("binary.dat")

    assert result == {"error": "unsupported, binary, huge, or unreadable file: binary.dat"}


def test_git_diff_uses_no_ext_diff_and_bounded_review_paths(tmp_path: Path, mocker: MockerFixture) -> None:
    """Git diff avoids external diff tools and truncates output."""
    completed = subprocess.CompletedProcess(
        args=[],
        returncode=0,
        stdout="abcdef",
        stderr="",
    )
    run_mock = mocker.patch("subprocess.run", return_value=completed)
    tools = _repo_tools(tmp_path)

    result = tools.git_diff(base="HEAD", max_chars=3)

    command = cast("list[str]", run_mock.call_args.args[0])
    assert command[:6] == ["git", "-C", str(tmp_path.resolve()), "diff", "--no-ext-diff", "HEAD"]
    assert "--" in command
    assert "src" in command
    assert "tests" in command
    assert "docs" in command
    assert "scripts" in command
    assert result["diff"] == "abc"
    assert result["truncated"] is True


def _repo_tools(repo_root: Path) -> RepoTools:
    factory = cast("RepoToolsFactory", _agent_module().RepoReadOnlyTools)
    return factory(repo_root)


def _agent_module() -> ModuleType:
    module_path = _project_root() / "scripts" / "local_repo_agent.py"
    spec = importlib.util.spec_from_file_location("local_repo_agent", module_path)
    if spec is None or spec.loader is None:
        raise RuntimeError(MODULE_LOAD_ERROR_MESSAGE)
    module = importlib.util.module_from_spec(spec)
    sys.modules["local_repo_agent"] = module
    spec.loader.exec_module(module)
    return module


def _write_text(path: Path, content: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    _ = path.write_text(content, encoding="utf-8")


def _write_binary(path: Path, content: bytes) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    _ = path.write_bytes(content)


def _project_root() -> Path:
    current_file = Path(__file__).resolve()
    for parent in current_file.parents:
        if (parent / "pyproject.toml").is_file():
            return parent
    raise RuntimeError(PROJECT_ROOT_NOT_FOUND_MESSAGE)
