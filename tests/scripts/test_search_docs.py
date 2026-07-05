# ruff: noqa: INP001 -- Tests mirror standalone developer script internals.
"""
Summary: Tests in-memory docs search ranking, snippets, and CLI output.
Why: Keeps the agent-facing docs search tool deterministic and citation-ready.
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
MODULE_LOAD_ERROR_MESSAGE = "Unable to load search_docs.py"
EXIT_SUCCESS = 0
EXIT_SEARCH_ERROR = 2


class SearchHit(Protocol):
    """Typed subset of SearchHit exercised by these tests."""

    score: int
    path: str
    line: int
    anchor: str
    section: str
    snippet: str


class SearchModule(Protocol):
    """Typed subset of search_docs.py exercised by these tests."""

    def main(self, argv: list[str] | None = ...) -> int: ...

    def search_docs(
        self,
        query: str,
        limit: int,
        doc_type: str | None,
        docs_root: Path,
    ) -> list[SearchHit]: ...


@pytest.fixture(name="search_module")
def search_module_fixture() -> SearchModule:
    """Load the standalone search script as an importable module."""
    return _load_search_module()


def test_search_prefers_matching_section_and_returns_citation_target(
    search_module: SearchModule,
    tmp_path: Path,
) -> None:
    """A query should resolve to the focused section path, line, and anchor."""
    docs_root = _fixture_docs(tmp_path)

    results = search_module.search_docs(
        "FileEvent pending before mutation",
        limit=3,
        doc_type=None,
        docs_root=docs_root,
    )

    assert results
    assert results[0].path == "docs/execution/apply.md"
    assert results[0].line == _heading_line(docs_root, "execution/apply.md", "## FileEvent Status")
    assert results[0].anchor == "fileevent-status"
    assert results[0].section == "FileEvent Status"
    assert "pending before the mutation starts" in results[0].snippet


def test_doc_metadata_boosts_only_the_best_section(search_module: SearchModule, tmp_path: Path) -> None:
    """A description match must not flood results with every section of the doc."""
    docs_root = _fixture_docs(tmp_path)

    results = search_module.search_docs("FileEvent", limit=10, doc_type=None, docs_root=docs_root)

    apply_hits = [result for result in results if result.path == "docs/execution/apply.md"]
    assert [hit.section for hit in apply_hits] == ["FileEvent Status"]
    assert results[0].path == "docs/execution/apply.md"
    assert results[0].score > results[1].score
    assert all("index.md" not in result.path for result in results)


def test_doc_level_only_match_returns_single_doc_hit(search_module: SearchModule, tmp_path: Path) -> None:
    """Frontmatter-only matches yield one citable hit at the doc's first heading."""
    docs_root = _fixture_docs(tmp_path)

    results = search_module.search_docs("reproducibility ledger", limit=10, doc_type=None, docs_root=docs_root)

    assert len(results) == 1
    assert results[0].path == "docs/STORAGE.md"
    assert results[0].line == _heading_line(docs_root, "STORAGE.md", "# Storage")
    assert results[0].anchor == "storage"


def test_search_type_filter_limits_results(search_module: SearchModule, tmp_path: Path) -> None:
    """The OKF type filter should exclude other document categories."""
    docs_root = _fixture_docs(tmp_path)

    results = search_module.search_docs("FileEvent", limit=10, doc_type="Contract", docs_root=docs_root)

    assert [result.path for result in results] == ["docs/contracts/status-reason-catalog.md"]


def test_fenced_code_headings_are_not_sections(search_module: SearchModule, tmp_path: Path) -> None:
    """Comment lines inside fenced shell examples must not become citation anchors."""
    docs_root = _fixture_docs(tmp_path)

    results = search_module.search_docs("FileEvent Fenced Heading", limit=10, doc_type=None, docs_root=docs_root)

    assert all(result.section != "FileEvent Fenced Heading" for result in results)
    assert all(result.anchor != "fileevent-fenced-heading" for result in results)


def test_snippet_comes_from_section_body_not_heading(search_module: SearchModule, tmp_path: Path) -> None:
    """A section-title hit should surface body evidence, not repeat the heading."""
    docs_root = _fixture_docs(tmp_path)

    results = search_module.search_docs("run status", limit=3, doc_type=None, docs_root=docs_root)

    assert results
    assert results[0].section == "Run Status"
    assert results[0].snippet == "Runs track apply attempts."


def test_main_prints_json_results(
    search_module: SearchModule,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
    tmp_path: Path,
) -> None:
    """--json output is compact machine-readable search evidence."""
    docs_root = _fixture_docs(tmp_path)
    monkeypatch.setattr(search_module, "project_root", lambda: tmp_path)

    exit_code = search_module.main(["FileEvent", "--json", "--limit", "1"])

    assert exit_code == EXIT_SUCCESS
    payload = cast("list[dict[str, object]]", json.loads(capsys.readouterr().out))
    assert payload[0]["path"] == "docs/execution/apply.md"
    assert payload[0]["line"] == _heading_line(docs_root, "execution/apply.md", "## FileEvent Status")


def test_missing_docs_root_fails_clearly(
    search_module: SearchModule,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
    tmp_path: Path,
) -> None:
    """A missing docs directory should fail with an actionable error."""
    monkeypatch.setattr(search_module, "project_root", lambda: tmp_path)

    exit_code = search_module.main(["FileEvent"])

    assert exit_code == EXIT_SEARCH_ERROR
    assert "does not exist" in capsys.readouterr().err


def _fixture_docs(root: Path) -> Path:
    docs_root = root / "docs"
    _write_text(
        docs_root / "index.md",
        "* [Apply Execution](execution/apply.md) - FileEvent behavior.\n",
    )
    _write_text(
        docs_root / "execution" / "apply.md",
        textwrap.dedent(
            """\
            ---
            type: Execution Spec
            title: Apply Execution
            description: Defines apply FileEvent behavior.
            tags: [apply, file-event]
            timestamp: 2026-07-05T02:00:00+09:00
            ---

            # Apply Execution

            ## FileEvent Status

            FileEvents are persisted as pending before the mutation starts.

            ```bash
            # FileEvent Fenced Heading
            ```

            ## Run Status

            Runs track apply attempts.
            """
        ),
    )
    _write_text(
        docs_root / "contracts" / "status-reason-catalog.md",
        textwrap.dedent(
            """\
            ---
            type: Contract
            title: Status And Reason Catalog
            description: Defines allowed status values.
            tags: [status, catalog]
            timestamp: 2026-07-05T02:00:00+09:00
            ---

            # Status And Reason Catalog

            ## FileEvent Status

            Allowed FileEvent status values are pending, succeeded, and failed.
            """
        ),
    )
    _write_text(
        docs_root / "STORAGE.md",
        textwrap.dedent(
            """\
            ---
            type: Storage Model
            title: Storage
            description: Explains the reproducibility ledger boundary.
            tags: [ledger]
            timestamp: 2026-07-05T02:00:00+09:00
            ---

            # Storage

            SQLite holds derived state.
            """
        ),
    )
    return docs_root


def _heading_line(docs_root: Path, relative_path: str, heading: str) -> int:
    lines = (docs_root / relative_path).read_text(encoding="utf-8").splitlines()
    return lines.index(heading) + 1


def _load_search_module() -> SearchModule:
    project_root = _project_root()
    scripts_path = str(project_root / "scripts")
    if scripts_path not in sys.path:
        sys.path.insert(0, scripts_path)
    module_path = project_root / "scripts" / "search_docs.py"
    spec = importlib.util.spec_from_file_location("search_docs", module_path)
    if spec is None or spec.loader is None:
        raise RuntimeError(MODULE_LOAD_ERROR_MESSAGE)
    module = importlib.util.module_from_spec(spec)
    sys.modules["search_docs"] = module
    spec.loader.exec_module(module)
    return cast("SearchModule", cast("object", module))


def _write_text(path: Path, content: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    _ = path.write_text(content, encoding="utf-8")


def _project_root() -> Path:
    current_file = Path(__file__).resolve()
    for parent in current_file.parents:
        if (parent / "pyproject.toml").is_file():
            return parent
    raise RuntimeError(PROJECT_ROOT_NOT_FOUND_MESSAGE)
