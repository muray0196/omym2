# ruff: noqa: EM101, INP001, TRY003 -- Tests mirror standalone developer script internals.
"""
Summary: Tests deterministic docs catalog routing and route_docs.py CLI output.
Why: Keeps agent docs routing automatic, stable, and independent of local model availability.
"""

from __future__ import annotations

import importlib.util
import json
import re
import sys
import textwrap
from pathlib import Path
from typing import TYPE_CHECKING, Protocol, cast

import pytest

if TYPE_CHECKING:
    from collections.abc import Callable

PROJECT_ROOT_NOT_FOUND_MESSAGE = "Unable to locate project root from test file."
MODULE_LOAD_ERROR_MESSAGE = "Unable to load route_docs.py"
EXIT_SUCCESS = 0
EXPECTED_FIXTURE_DOC_COUNT = 3
LEXICAL_CANDIDATE_LIMIT = 40  # Mirrors route_docs.DEFAULT_LEXICAL_CANDIDATE_LIMIT.
MANY_DOCS_FIXTURE_COUNT = 25
WIDE_RECALL_DOC_COUNT = 130
EXPECTED_WIDE_RECALL_CANDIDATE_COUNT = 120
WIDE_RECALL_EMBEDDING_HIGH_START_INDEX = 50
EXPECTED_LMSTUDIO_TTL_SECONDS = 3600
DEFAULT_MODEL_BASE_URL_ATTR = "_default_model_base_url"
DEFAULT_LOCAL_MODEL_HOST_ATTR = "_default_local_model_host"
REQUEST_EMBEDDINGS_ATTR = "_request_embeddings"
CANDIDATES_BLOCK_PATTERN = re.compile(r"<candidates>\n(.*)\n</candidates>", re.DOTALL)


class Card(Protocol):
    """Typed subset of DocCard exercised by these tests."""

    path: str
    docs_path: str
    content_hash: str
    routing_text: str


class RouteModule(Protocol):
    """Typed subset of route_docs.py exercised by these tests."""

    RouteError: type[Exception]
    RouteOptions: Callable[..., object]

    def main(self, argv: list[str] | None = ...) -> int: ...

    def load_catalog(self, docs_root: Path, repo_root: Path) -> list[Card]: ...

    def route_query(
        self,
        query: str,
        docs_root: Path,
        repo_root: Path,
        limit: int = ...,
        options: object | None = ...,
    ) -> dict[str, object]: ...


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
    monkeypatch.setattr(route_module, "project_root", lambda: tmp_path)

    exit_code = route_module.main(
        ["route", "FileEvent", "apply", "--docs-root", str(docs_root), "--limit", "1", "--lexical-only"]
    )

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


def test_main_route_uses_full_local_model_pipeline_by_default(
    route_module: RouteModule,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
    tmp_path: Path,
) -> None:
    """The plain route command should use embeddings and selector before printing JSON."""
    docs_root = _fixture_docs(tmp_path)
    calls: list[str] = []
    monkeypatch.setattr(route_module, "project_root", lambda: tmp_path)

    def fake_embeddings(texts: list[str], _options: object) -> list[list[float]]:
        calls.append("embeddings")
        return [_embedding_for_text(text) for text in texts]

    def fake_chat_completion(**_kwargs: object) -> str:
        calls.append("selector")
        return json.dumps(
            {
                "docs_to_read": [
                    {"path": "docs/codebase/ports-uow.md", "reason": "UnitOfWork boundary", "confidence": "high"}
                ],
                "confidence": "high",
            }
        )

    monkeypatch.setattr(route_module, "_request_embeddings", fake_embeddings)
    monkeypatch.setattr(route_module, "_request_chat_completion", fake_chat_completion)

    exit_code = route_module.main(["route", "FileEvent", "apply", "UnitOfWork", "--docs-root", str(docs_root)])

    assert exit_code == EXIT_SUCCESS
    payload = cast("dict[str, object]", json.loads(capsys.readouterr().out))
    docs_to_read = cast("list[dict[str, object]]", payload["docs_to_read"])
    routing = cast("dict[str, object]", payload["routing"])
    assert docs_to_read[0]["path"] == "docs/codebase/ports-uow.md"
    assert routing["layers"] == ["lexical", "embeddings", "selector"]
    assert routing["warnings"] == []
    assert calls == ["embeddings", "embeddings", "selector"]


def test_main_route_falls_back_to_lexical_when_default_model_pipeline_fails(
    route_module: RouteModule,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
    tmp_path: Path,
) -> None:
    """A default model-pipeline failure should return pure lexical routing without later model calls."""
    docs_root = _fixture_docs(tmp_path)
    monkeypatch.setattr(route_module, "project_root", lambda: tmp_path)

    def fail_embeddings(_texts: list[str], _options: object) -> list[list[float]]:
        raise route_module.RouteError("endpoint offline")

    def fail_if_called(*_args: object, **_kwargs: object) -> object:
        raise AssertionError("later model layer should not run after default model pipeline failure")

    monkeypatch.setattr(route_module, "_request_embeddings", fail_embeddings)
    monkeypatch.setattr(route_module, "_request_chat_completion", fail_if_called)

    exit_code = route_module.main(["route", "FileEvent", "apply", "--docs-root", str(docs_root), "--limit", "1"])

    assert exit_code == EXIT_SUCCESS
    payload = cast("dict[str, object]", json.loads(capsys.readouterr().out))
    docs_to_read = cast("list[dict[str, object]]", payload["docs_to_read"])
    routing = cast("dict[str, object]", payload["routing"])
    assert docs_to_read[0]["path"] == "docs/execution/apply.md"
    assert routing["layers"] == ["lexical"]
    assert routing["warnings"] == ["model routing unavailable: embedding unavailable: endpoint offline"]


def test_default_model_base_url_prefers_lmstudio_env(
    route_module: RouteModule,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """A single LM Studio base URL env var should configure every model layer by default."""
    monkeypatch.delenv("OMYM2_DOC_EMBED_BASE_URL", raising=False)
    monkeypatch.delenv("OMYM2_LOCAL_LLM_BASE_URL", raising=False)
    monkeypatch.delenv("LLM_BASE_URL", raising=False)
    monkeypatch.setenv("OMYM2_LMSTUDIO_BASE_URL", "http://host.example:1234/v1")

    assert _default_model_base_url(route_module)("OMYM2_DOC_EMBED_BASE_URL") == "http://host.example:1234/v1"


def test_default_model_base_url_uses_reachable_wsl_host(
    route_module: RouteModule,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """WSL should use the first reachable host-side LM Studio candidate instead of assuming localhost."""
    monkeypatch.delenv("OMYM2_DOC_EMBED_BASE_URL", raising=False)
    monkeypatch.delenv("OMYM2_LMSTUDIO_BASE_URL", raising=False)
    monkeypatch.delenv("OMYM2_LOCAL_LLM_BASE_URL", raising=False)
    monkeypatch.delenv("LLM_BASE_URL", raising=False)
    monkeypatch.setattr(route_module, "_is_wsl", lambda: True)
    monkeypatch.setattr(route_module, "_wsl_host_candidates", lambda: ["localhost", "172.28.32.1"])

    def fake_can_connect(host: str, _port: int) -> bool:
        return host == "172.28.32.1"

    monkeypatch.setattr(route_module, "_can_connect", fake_can_connect)

    assert _default_model_base_url(route_module)("OMYM2_DOC_EMBED_BASE_URL") == "http://172.28.32.1:1234/v1"


def test_default_local_model_host_stays_localhost_outside_wsl(
    route_module: RouteModule,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Native local runs should keep the conventional localhost LM Studio endpoint."""
    monkeypatch.setattr(route_module, "_is_wsl", lambda: False)

    def fail_can_connect(_host: str, _port: int) -> bool:
        raise AssertionError("non-WSL should not probe hosts")

    monkeypatch.setattr(route_module, "_can_connect", fail_can_connect)

    assert _default_local_model_host(route_module)() == "localhost"


def test_embedding_request_includes_lmstudio_ttl(
    route_module: RouteModule,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Model requests should ask LM Studio to keep JIT-loaded models available for the route."""
    captured_bodies: list[dict[str, object]] = []

    def fake_http_json(
        _method: str,
        _url: str,
        _api_key: str,
        body: dict[str, object] | None,
        _timeout: int,
    ) -> dict[str, object]:
        assert body is not None
        captured_bodies.append(body)
        return {"data": [{"index": 0, "embedding": [1.0, 0.0]}]}

    monkeypatch.setattr(route_module, "_http_json", fake_http_json)
    options = route_module.RouteOptions(embedding_base_url="http://embed.test/v1")

    assert _request_embeddings(route_module)(["query"], options) == [[1.0, 0.0]]
    assert captured_bodies[0]["ttl"] == EXPECTED_LMSTUDIO_TTL_SECONDS


def test_main_catalog_prints_generated_catalog(
    route_module: RouteModule,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
    tmp_path: Path,
) -> None:
    """The catalog command should expose the generated cards for debugging."""
    docs_root = _fixture_docs(tmp_path)
    monkeypatch.setattr(route_module, "project_root", lambda: tmp_path)

    exit_code = route_module.main(["catalog", "--docs-root", str(docs_root)])

    assert exit_code == EXIT_SUCCESS
    payload = cast("dict[str, object]", json.loads(capsys.readouterr().out))
    cards = cast("list[dict[str, object]]", payload["docs"])
    assert cards[0]["path"] == "docs/STORAGE.md"
    assert "routing_text" in cards[0]


def test_dry_prompt_prints_real_candidate_metadata_without_model_call(
    route_module: RouteModule,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
    tmp_path: Path,
) -> None:
    """--dry-prompt should show the real selector prompt: full card metadata, not placeholder cards."""
    docs_root = _fixture_docs(tmp_path)
    monkeypatch.setattr(route_module, "project_root", lambda: tmp_path)

    exit_code = route_module.main(["route", "FileEvent", "apply", "--docs-root", str(docs_root), "--dry-prompt"])

    assert exit_code == EXIT_SUCCESS
    output = capsys.readouterr().out
    assert "You are OMYM2's docs router." in output
    assert "there is no fixed target count" in output
    assert "Include authoritative docs and useful supporting docs" in output
    assert "<candidates>" in output
    candidates = _extract_candidates(output)
    assert len(candidates) <= LEXICAL_CANDIDATE_LIMIT
    apply_candidate = next(item for item in candidates if item["path"] == "docs/execution/apply.md")
    assert apply_candidate["title"] == "Apply Execution"
    assert "FileEvent recording" in cast("str", apply_candidate["description"])


def test_dry_prompt_does_not_apply_selector_candidate_limit(
    route_module: RouteModule,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
    tmp_path: Path,
) -> None:
    """--dry-prompt should include every lexical candidate up to the lexical recall pool."""
    docs_root = _write_many_matching_docs(tmp_path, MANY_DOCS_FIXTURE_COUNT)
    monkeypatch.setattr(route_module, "project_root", lambda: tmp_path)

    exit_code = route_module.main(["route", "zephyr", "widget", "--docs-root", str(docs_root), "--dry-prompt"])

    assert exit_code == EXIT_SUCCESS
    output = capsys.readouterr().out
    candidates = _extract_candidates(output)
    assert len(candidates) == MANY_DOCS_FIXTURE_COUNT


def test_model_route_uses_wide_recall_pools_without_selector_cap(
    route_module: RouteModule,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
    tmp_path: Path,
) -> None:
    """The selector should receive merged lexical top 40 plus embedding top 80 candidates."""
    docs_root = _write_many_matching_docs(tmp_path, WIDE_RECALL_DOC_COUNT)
    captured_candidates: list[dict[str, object]] = []
    monkeypatch.setattr(route_module, "project_root", lambda: tmp_path)

    def fake_embeddings(texts: list[str], _options: object) -> list[list[float]]:
        return [_wide_recall_embedding_for_text(text) for text in texts]

    def fake_chat_completion(**kwargs: object) -> str:
        user_prompt = kwargs["user_prompt"]
        assert isinstance(user_prompt, str)
        captured_candidates.extend(_extract_candidates(user_prompt))
        return json.dumps({"docs_to_read": [captured_candidates[0]["path"]], "confidence": "high"})

    monkeypatch.setattr(route_module, "_request_embeddings", fake_embeddings)
    monkeypatch.setattr(route_module, "_request_chat_completion", fake_chat_completion)

    exit_code = route_module.main(["route", "zephyr", "widget", "--docs-root", str(docs_root)])

    assert exit_code == EXIT_SUCCESS
    _ = capsys.readouterr()
    candidate_paths = [item["path"] for item in captured_candidates]
    assert len(candidate_paths) == EXPECTED_WIDE_RECALL_CANDIDATE_COUNT
    assert "docs/many/doc-000.md" in candidate_paths
    assert "docs/many/doc-039.md" in candidate_paths
    assert "docs/many/doc-050.md" in candidate_paths
    assert "docs/many/doc-129.md" in candidate_paths
    assert "docs/many/doc-040.md" not in candidate_paths


def test_merged_candidates_are_ordered_by_combined_score(
    route_module: RouteModule,
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    """A strong embedding-only candidate should not outrank stronger lexical evidence."""
    docs_root = _combined_scoring_fixture_docs(tmp_path)
    captured_candidates: list[dict[str, object]] = []

    def fake_embeddings(texts: list[str], _options: object) -> list[list[float]]:
        return [_combined_score_embedding_for_text(text) for text in texts]

    def fake_chat_completion(**kwargs: object) -> str:
        user_prompt = kwargs["user_prompt"]
        assert isinstance(user_prompt, str)
        captured_candidates.extend(_extract_candidates(user_prompt))
        return json.dumps({"docs_to_read": [captured_candidates[0]["path"]], "confidence": "high"})

    monkeypatch.setattr(route_module, "_request_embeddings", fake_embeddings)
    monkeypatch.setattr(route_module, "_request_chat_completion", fake_chat_completion)
    options = route_module.RouteOptions(
        use_embeddings=True, use_selector=True, selector_base_url="http://selector.test/v1"
    )

    result = route_module.route_query("alpha", docs_root=docs_root, repo_root=tmp_path, options=options)

    docs_to_read = cast("list[dict[str, object]]", result["docs_to_read"])
    assert docs_to_read[0]["path"] == "docs/alpha-guide.md"
    assert [item["path"] for item in captured_candidates] == ["docs/alpha-guide.md", "docs/semantic-guide.md"]


def test_generic_command_token_does_not_overboost_commands_doc(
    route_module: RouteModule,
    tmp_path: Path,
) -> None:
    """Generic command wording should not outrank the docs validation authority."""
    docs_root = _command_scoring_fixture_docs(tmp_path)

    result = route_module.route_query("What command should I run for docs validation?", docs_root, tmp_path)

    docs_to_read = cast("list[dict[str, object]]", result["docs_to_read"])
    assert docs_to_read[0]["path"] == "docs/DEVELOPMENT.md"


def test_cli_command_query_keeps_commands_doc_high(route_module: RouteModule, tmp_path: Path) -> None:
    """Specific CLI command queries should still route to the command surface reference."""
    docs_root = _command_scoring_fixture_docs(tmp_path)

    result = route_module.route_query("What CLI commands are available?", docs_root, tmp_path)

    docs_to_read = cast("list[dict[str, object]]", result["docs_to_read"])
    assert docs_to_read[0]["path"] == "docs/COMMANDS.md"


def test_broad_token_scores_damped_below_full_weight_domain_match(route_module: RouteModule, tmp_path: Path) -> None:
    """A broad query token ("run") must keep damped recall without outranking full-weight domain matches."""
    docs_root = _damped_scoring_fixture_docs(tmp_path)

    result = route_module.route_query("run storage", docs_root=docs_root, repo_root=tmp_path, limit=5)

    docs_to_read = cast("list[dict[str, object]]", result["docs_to_read"])
    paths = [cast("str", doc["path"]) for doc in docs_to_read]
    assert paths[0] == "docs/storage-notes.md"
    assert "docs/run-lifecycle.md" in paths
    assert paths.index("docs/run-lifecycle.md") > paths.index("docs/storage-notes.md")


def test_embedding_route_uses_cache_for_doc_embeddings(
    route_module: RouteModule,
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    """Embedding routing should cache doc vectors and only re-embed the query on reuse."""
    docs_root = _fixture_docs(tmp_path)
    calls: list[str] = []

    def fake_embeddings(texts: list[str], _options: object) -> list[list[float]]:
        calls.extend(texts)
        return [_embedding_for_text(text) for text in texts]

    monkeypatch.setattr(route_module, "_request_embeddings", fake_embeddings)
    options = route_module.RouteOptions(use_embeddings=True, embedding_base_url="http://embed.test/v1")

    first = route_module.route_query("semantic request", docs_root=docs_root, repo_root=tmp_path, options=options)

    docs_to_read = cast("list[dict[str, object]]", first["docs_to_read"])
    assert docs_to_read[0]["path"] == "docs/execution/apply.md"
    assert any("Path: docs/execution/apply.md" in text for text in calls)

    calls.clear()
    second = route_module.route_query("semantic request", docs_root=docs_root, repo_root=tmp_path, options=options)

    docs_to_read = cast("list[dict[str, object]]", second["docs_to_read"])
    assert docs_to_read[0]["path"] == "docs/execution/apply.md"
    assert calls
    assert all("Path:" not in text for text in calls)


def test_embedding_failure_falls_back_to_lexical_with_warning(
    route_module: RouteModule,
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    """Unavailable embedding endpoints should not break deterministic routing."""
    docs_root = _fixture_docs(tmp_path)

    def fail_embeddings(_texts: list[str], _options: object) -> list[list[float]]:
        raise route_module.RouteError("endpoint offline")

    monkeypatch.setattr(route_module, "_request_embeddings", fail_embeddings)
    options = route_module.RouteOptions(use_embeddings=True, embedding_base_url="http://embed.test/v1")

    result = route_module.route_query("FileEvent apply", docs_root=docs_root, repo_root=tmp_path, options=options)

    docs_to_read = cast("list[dict[str, object]]", result["docs_to_read"])
    assert docs_to_read[0]["path"] == "docs/execution/apply.md"
    routing = cast("dict[str, object]", result["routing"])
    warnings = cast("list[str]", routing["warnings"])
    assert warnings == ["embedding unavailable: endpoint offline"]


def test_selector_drops_invented_paths(
    route_module: RouteModule,
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    """The final selector must only return docs from the candidate set."""
    docs_root = _fixture_docs(tmp_path)
    canned = json.dumps(
        {
            "docs_to_read": [
                {"path": "docs/codebase/ports-uow.md", "reason": "UnitOfWork boundary", "confidence": "high"},
                {"path": "docs/ghost.md", "reason": "invented", "confidence": "high"},
            ],
            "confidence": "high",
        }
    )

    def fake_chat_completion(**_kwargs: object) -> str:
        return canned

    monkeypatch.setattr(route_module, "_request_chat_completion", fake_chat_completion)
    options = route_module.RouteOptions(use_selector=True, selector_base_url="http://selector.test/v1")

    result = route_module.route_query(
        "FileEvent apply UnitOfWork",
        docs_root=docs_root,
        repo_root=tmp_path,
        limit=3,
        options=options,
    )

    docs_to_read = cast("list[dict[str, object]]", result["docs_to_read"])
    assert [item["path"] for item in docs_to_read] == ["docs/codebase/ports-uow.md"]
    assert docs_to_read[0]["reason"] == "Matches selector: UnitOfWork boundary, title, tags, description, headings."


def test_selector_accepts_plain_path_list(
    route_module: RouteModule,
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    """Small selector models may return docs_to_read as plain strings; valid paths should still count."""
    docs_root = _fixture_docs(tmp_path)
    canned = json.dumps(
        {
            "docs_to_read": ["docs/codebase/ports-uow.md", "docs/ghost.md"],
            "confidence": "high",
        }
    )

    def fake_chat_completion(**_kwargs: object) -> str:
        return canned

    monkeypatch.setattr(route_module, "_request_chat_completion", fake_chat_completion)
    options = route_module.RouteOptions(use_selector=True, selector_base_url="http://selector.test/v1")

    result = route_module.route_query(
        "FileEvent apply UnitOfWork",
        docs_root=docs_root,
        repo_root=tmp_path,
        limit=3,
        options=options,
    )

    docs_to_read = cast("list[dict[str, object]]", result["docs_to_read"])
    assert [item["path"] for item in docs_to_read] == ["docs/codebase/ports-uow.md"]
    assert docs_to_read[0]["reason"] == "Matches selector: final selector, title, tags, description, headings."


def test_refresh_command_populates_and_reuses_embedding_cache(
    route_module: RouteModule,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
    tmp_path: Path,
) -> None:
    """The refresh command should materialize local doc embeddings and reuse unchanged rows."""
    docs_root = _fixture_docs(tmp_path)
    calls: list[str] = []
    monkeypatch.setattr(route_module, "project_root", lambda: tmp_path)

    def fake_embeddings(texts: list[str], _options: object) -> list[list[float]]:
        calls.extend(texts)
        return [_embedding_for_text(text) for text in texts]

    monkeypatch.setattr(route_module, "_request_embeddings", fake_embeddings)

    first_exit = route_module.main(
        ["refresh", "--docs-root", str(docs_root), "--embedding-base-url", "http://e.test/v1"]
    )
    first = cast("dict[str, object]", json.loads(capsys.readouterr().out))
    calls.clear()
    second_exit = route_module.main(
        ["refresh", "--docs-root", str(docs_root), "--embedding-base-url", "http://e.test/v1"]
    )
    second = cast("dict[str, object]", json.loads(capsys.readouterr().out))

    assert first_exit == EXIT_SUCCESS
    assert second_exit == EXIT_SUCCESS
    assert first["embedded"] == EXPECTED_FIXTURE_DOC_COUNT
    assert first["reused"] == 0
    assert second["embedded"] == 0
    assert second["reused"] == EXPECTED_FIXTURE_DOC_COUNT
    assert calls == []


def _embedding_for_text(text: str) -> list[float]:
    if "semantic request" in text or "Apply Execution" in text:
        return [1.0, 0.0]
    if "Ports And UnitOfWork" in text:
        return [0.8, 0.2]
    return [0.0, 1.0]


def _wide_recall_embedding_for_text(text: str) -> list[float]:
    if "Request:" in text:
        return [1.0, 0.0]
    match = re.search(r"Zephyr Widget (\d+)", text)
    if match is not None and int(match.group(1)) >= WIDE_RECALL_EMBEDDING_HIGH_START_INDEX:
        return [1.0, 0.0]
    return [0.1, 1.0]


def _combined_score_embedding_for_text(text: str) -> list[float]:
    if "Request:" in text or "Semantic Guide" in text:
        return [1.0, 0.0]
    if "Alpha Guide" in text:
        return [0.1, 1.0]
    return [0.0, 1.0]


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


def _damped_scoring_fixture_docs(root: Path) -> Path:
    docs_root = root / "docs"
    _write_text(
        docs_root / "run-lifecycle.md",
        textwrap.dedent(
            """\
            ---
            type: Execution Spec
            title: Run Lifecycle
            description: Explains run states and run retries.
            tags: [run]
            timestamp: 2026-07-05T02:00:00+09:00
            ---

            # Run Lifecycle

            Run rows track execution progress.
            """
        ),
    )
    _write_text(
        docs_root / "storage-notes.md",
        textwrap.dedent(
            """\
            ---
            type: Storage Design
            title: Storage Notes
            description: Explains storage boundaries.
            tags: [storage]
            timestamp: 2026-07-05T02:00:00+09:00
            ---

            # Storage Notes

            Storage boundaries for derived state.
            """
        ),
    )
    return docs_root


def _write_many_matching_docs(root: Path, count: int) -> Path:
    docs_root = root / "docs"
    for index in range(count):
        _write_text(
            docs_root / "many" / f"doc-{index:03d}.md",
            textwrap.dedent(
                f"""\
                ---
                type: Reference
                title: Zephyr Widget {index:03d}
                description: Zephyr widget reference number {index:03d} for candidate cap testing.
                tags: [zephyr, widget]
                timestamp: 2026-07-05T02:00:00+09:00
                ---

                # Zephyr Widget {index:03d}

                Zephyr widget behavior number {index:03d}.
                """
            ),
        )
    return docs_root


def _combined_scoring_fixture_docs(root: Path) -> Path:
    docs_root = root / "docs"
    _write_text(
        docs_root / "alpha-guide.md",
        textwrap.dedent(
            """\
            ---
            type: Reference
            title: Alpha Guide
            description: Alpha project routing guide.
            tags: [alpha]
            timestamp: 2026-07-05T02:00:00+09:00
            ---

            # Alpha Guide

            Alpha routing details.
            """
        ),
    )
    _write_text(
        docs_root / "semantic-guide.md",
        textwrap.dedent(
            """\
            ---
            type: Reference
            title: Semantic Guide
            description: Related project routing guide.
            tags: [semantic]
            timestamp: 2026-07-05T02:00:00+09:00
            ---

            # Semantic Guide

            Related routing details.
            """
        ),
    )
    return docs_root


def _command_scoring_fixture_docs(root: Path) -> Path:
    docs_root = root / "docs"
    _write_text(
        docs_root / "COMMANDS.md",
        textwrap.dedent(
            """\
            ---
            type: Command Reference
            title: Commands
            description: Lists CLI commands available in OMYM2.
            tags: [cli, commands]
            timestamp: 2026-07-05T02:00:00+09:00
            ---

            # Commands

            The CLI command surface includes config and settings commands.
            """
        ),
    )
    _write_text(
        docs_root / "DEVELOPMENT.md",
        textwrap.dedent(
            """\
            ---
            type: Development Guide
            title: Development Harness
            description: Specifies docs validation through checks.sh docs.
            tags: [development, validation]
            timestamp: 2026-07-05T02:00:00+09:00
            ---

            # Development Harness

            ## Docs Validation

            Run checks.sh docs for docs validation.
            """
        ),
    )
    return docs_root


def _extract_candidates(output: str) -> list[dict[str, object]]:
    match = CANDIDATES_BLOCK_PATTERN.search(output)
    if match is None:
        message = "dry-prompt output did not contain a <candidates> block"
        raise AssertionError(message)
    return cast("list[dict[str, object]]", json.loads(match.group(1)))


def _default_model_base_url(route_module: RouteModule) -> Callable[[str], str]:
    return cast("Callable[[str], str]", getattr(route_module, DEFAULT_MODEL_BASE_URL_ATTR))


def _default_local_model_host(route_module: RouteModule) -> Callable[[], str]:
    return cast("Callable[[], str]", getattr(route_module, DEFAULT_LOCAL_MODEL_HOST_ATTR))


def _request_embeddings(route_module: RouteModule) -> Callable[[list[str], object], list[list[float]]]:
    return cast("Callable[[list[str], object], list[list[float]]]", getattr(route_module, REQUEST_EMBEDDINGS_ATTR))


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
