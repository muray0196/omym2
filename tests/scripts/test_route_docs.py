# ruff: noqa: INP001 -- Tests mirror standalone developer script internals.
"""
Summary: Tests deterministic docs catalog routing and route_docs.py CLI output.
Why: Keeps agent docs routing automatic, stable, and independent of local model availability.
"""

from __future__ import annotations

import importlib.util
import json
import sys
import textwrap
from pathlib import Path
from typing import Protocol, cast

import pytest

PROJECT_ROOT_NOT_FOUND_MESSAGE = "Unable to locate project root from test file."
MODULE_LOAD_ERROR_MESSAGE = "Unable to load route_docs.py"
EXIT_SUCCESS = 0


class Card(Protocol):
    """Typed subset of DocCard exercised by these tests."""

    path: str
    docs_path: str
    content_hash: str
    routing_text: str


class RouteModule(Protocol):
    """Typed subset of route_docs.py exercised by these tests."""

    def main(self, argv: list[str] | None = ...) -> int: ...

    def load_catalog(self, docs_root: Path, repo_root: Path) -> list[Card]: ...

    def route_query(self, query: str, docs_root: Path, repo_root: Path, limit: int = ...) -> dict[str, object]: ...


@pytest.fixture(name="route_module")
def route_module_fixture() -> RouteModule:
    """Load the standalone router script as an importable module."""
    return _load_route_module()


def test_catalog_discovers_concept_docs_with_repo_relative_paths(route_module: RouteModule, tmp_path: Path) -> None:
    """The catalog should include concept docs and exclude generated routers/logs."""
    docs_root = _fixture_docs(tmp_path)

    cards = route_module.load_catalog(docs_root, tmp_path)

    assert [card.path for card in cards] == [
        "docs/STORAGE.md",
        "docs/codebase/ports-uow.md",
        "docs/execution/apply.md",
    ]
    assert [card.docs_path for card in cards] == ["STORAGE.md", "codebase/ports-uow.md", "execution/apply.md"]
    assert all(card.content_hash for card in cards)
    assert all("index.md" not in card.path and "log.md" not in card.path for card in cards)


def test_route_injects_architecture_and_ranks_matching_docs(route_module: RouteModule, tmp_path: Path) -> None:
    """A task should get mandatory architecture reading plus ranked task docs."""
    docs_root = _fixture_docs(tmp_path)

    result = route_module.route_query(
        "How does apply record FileEvents with UnitOfWork?",
        docs_root=docs_root,
        repo_root=tmp_path,
        limit=3,
    )

    assert result["required_docs"] == [{"path": "ARCHITECTURE.md", "reason": "Required by AGENTS.md."}]
    docs_to_read = cast("list[dict[str, object]]", result["docs_to_read"])
    assert docs_to_read[0]["path"] == "docs/execution/apply.md"
    assert "docs/codebase/ports-uow.md" in [doc["path"] for doc in docs_to_read]
    assert result["confidence"] == "high"
    assert result["fallback_docs"] == []


def test_route_adds_docs_index_fallback_for_ambiguous_request(route_module: RouteModule, tmp_path: Path) -> None:
    """Low-signal requests should point agents at the docs router fallback."""
    docs_root = _fixture_docs(tmp_path)

    result = route_module.route_query("please help", docs_root=docs_root, repo_root=tmp_path)

    assert result["docs_to_read"] == []
    assert result["fallback_docs"] == ["docs/index.md"]
    assert result["confidence"] == "low"


def test_main_route_prints_json(
    route_module: RouteModule, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str], tmp_path: Path
) -> None:
    """The route command should print stable machine-readable JSON."""
    docs_root = _fixture_docs(tmp_path)
    monkeypatch.setattr(route_module, "_project_root", lambda: tmp_path)

    exit_code = route_module.main(["route", "FileEvent", "apply", "--docs-root", str(docs_root), "--limit", "1"])

    assert exit_code == EXIT_SUCCESS
    payload = cast("dict[str, object]", json.loads(capsys.readouterr().out))
    assert payload["required_docs"] == [{"path": "ARCHITECTURE.md", "reason": "Required by AGENTS.md."}]
    docs_to_read = cast("list[dict[str, object]]", payload["docs_to_read"])
    assert docs_to_read == [
        {
            "path": "docs/execution/apply.md",
            "priority": 1,
            "reason": "Matches filename, title, tags, description, headings.",
            "confidence": "high",
        }
    ]


def test_main_catalog_prints_generated_catalog(
    route_module: RouteModule,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
    tmp_path: Path,
) -> None:
    """The catalog command should expose the generated cards for debugging."""
    docs_root = _fixture_docs(tmp_path)
    monkeypatch.setattr(route_module, "_project_root", lambda: tmp_path)

    exit_code = route_module.main(["catalog", "--docs-root", str(docs_root)])

    assert exit_code == EXIT_SUCCESS
    payload = cast("dict[str, object]", json.loads(capsys.readouterr().out))
    cards = cast("list[dict[str, object]]", payload["docs"])
    assert cards[0]["path"] == "docs/STORAGE.md"
    assert "routing_text" in cards[0]


def test_dry_prompt_prints_selector_prompt_without_model_call(
    route_module: RouteModule,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
    tmp_path: Path,
) -> None:
    """--dry-prompt should show the future selector prompt without changing output files."""
    docs_root = _fixture_docs(tmp_path)
    monkeypatch.setattr(route_module, "_project_root", lambda: tmp_path)

    exit_code = route_module.main(["route", "FileEvent", "apply", "--docs-root", str(docs_root), "--dry-prompt"])

    assert exit_code == EXIT_SUCCESS
    output = capsys.readouterr().out
    assert "You are OMYM2's docs router." in output
    assert "<candidates>" in output
    assert "docs/execution/apply.md" in output


def _fixture_docs(root: Path) -> Path:
    docs_root = root / "docs"
    _write_text(docs_root / "index.md", "# Core Documentation\n")
    _write_text(docs_root / "execution" / "log.md", "# Generated Log\n")
    _write_text(
        docs_root / "execution" / "apply.md",
        textwrap.dedent(
            """\
            ---
            type: Execution Spec
            title: Apply Execution
            description: Defines apply FileEvent recording and UnitOfWork durable operation log behavior.
            tags: [apply, file-event, unit-of-work]
            timestamp: 2026-07-05T02:00:00+09:00
            ---

            # Apply Execution

            ## FileEvent Recording

            FileEvents are persisted before Library music file mutation.
            """
        ),
    )
    _write_text(
        docs_root / "codebase" / "ports-uow.md",
        textwrap.dedent(
            """\
            ---
            type: Codebase Reference
            title: Ports And UnitOfWork
            description: Explains UnitOfWork boundaries and FileEvent operation log exceptions.
            tags: [ports, unit-of-work, file-event]
            timestamp: 2026-07-05T02:00:00+09:00
            ---

            # Ports And UnitOfWork

            ## Durable Operation Log Exception

            Apply and undo cannot use one atomic DB and filesystem transaction.
            """
        ),
    )
    _write_text(
        docs_root / "STORAGE.md",
        textwrap.dedent(
            """\
            ---
            type: Storage Design
            title: Storage
            description: Defines TOML and SQLite persistence boundaries.
            tags: [storage, sqlite]
            timestamp: 2026-07-05T02:00:00+09:00
            ---

            # Storage

            SQLite stores derived state.
            """
        ),
    )
    return docs_root


def _load_route_module() -> RouteModule:
    project_root = _project_root()
    scripts_path = str(project_root / "scripts")
    if scripts_path not in sys.path:
        sys.path.insert(0, scripts_path)
    module_path = project_root / "scripts" / "route_docs.py"
    spec = importlib.util.spec_from_file_location("route_docs", module_path)
    if spec is None or spec.loader is None:
        raise RuntimeError(MODULE_LOAD_ERROR_MESSAGE)
    module = importlib.util.module_from_spec(spec)
    sys.modules["route_docs"] = module
    spec.loader.exec_module(module)
    return cast("RouteModule", cast("object", module))


def _write_text(path: Path, content: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    _ = path.write_text(content, encoding="utf-8")


def _project_root() -> Path:
    current_file = Path(__file__).resolve()
    for parent in current_file.parents:
        if (parent / "pyproject.toml").is_file():
            return parent
    raise RuntimeError(PROJECT_ROOT_NOT_FOUND_MESSAGE)
