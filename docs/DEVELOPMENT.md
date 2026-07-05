---
type: Development Guide
title: Development Harness
description: Specifies developer quality commands, the checks.sh wrapper, docs search and model-assisted routing scripts, local model policy, suppression rules, and Python runtime configuration policy.
tags: [development, tooling, quality-gates, validation]
timestamp: 2026-07-05T23:38:08+09:00
---

# Development Harness

This document is authoritative for developer quality commands, validation gates, suppressions, and Python runtime configuration policy.

Product command behavior is defined in [COMMANDS.md](COMMANDS.md). Test design is defined in [TESTING.md](TESTING.md). Application config and stored path policy are defined in [STORAGE.md](STORAGE.md) and [contracts/](contracts/).

Keep this file limited to commands and validation policy.

## Edit-Loop Commands

During implementation, check only Python files changed in the current task.
Avoid project-wide diagnostics during the edit loop unless the change crosses
many modules or the failure cannot be understood from changed-file checks.

Use this command group after editing Python files. Replace <py-files>
with the Python files changed in the current task:

```bash
uv run ruff check <py-files> --fix --output-format=concise
uv run ruff format <py-files> -q
uv run basedpyright <py-files> --level error
```

Ruff auto-fix runs before formatting. Basedpyright reports errors only. Do not
use verbose, statistics, JSON output, or full-project diagnostics during the edit
loop.

Use this command group after editing the React Web UI:

```bash
cd web
npm ci
npm run format:check
npm run lint
npm run build
```

## Final Quality Gates

Run these commands in order before marking implementation work complete:

```bash
cd web
npm ci
npm run format:check
npm run lint
npm run build
cd ..
uv run ruff check . --output-format=concise
uv run ruff format . --check -q
uv run basedpyright
uv run pytest -q --maxfail=1 --tb=line --show-capture=stdout
```

All gates must pass:

* Frontend installation fails if `package-lock.json` is out of sync.
* Frontend formatting fails if Prettier would change any file.
* Frontend linting fails if ESLint reports any issue.
* Frontend build fails if TypeScript or the Next.js production build fails.
* Linting fails if any lint error remains.
* Formatting fails if Ruff would change any file.
* Type checking fails if `basedpyright` reports any error or warning.
* Tests fail if any test fails.

If the Python project skeleton or tool configuration does not exist yet, report the commands as not runnable instead of inventing replacement commands.

## Wrapper Script

`scripts/checks.sh` wraps the command groups in this document so they can be run with one call:

```bash
scripts/checks.sh [changed|py|web|all|docs|arch]
scripts/checks.sh test <pytest-target>
```

* `changed` (default): edit-loop checks on Python files changed vs `HEAD`
* `py`: full Python gates
* `web`: frontend gates
* `all`: web + py, the final quality gates
* `docs`: docs bundle conformance tests
* `arch`: architecture tests
* `test <pytest-target>`: focused failure inspection

The command groups in this document remain authoritative; the script must stay in sync with them.

## Docs Search And Routing Scripts

`scripts/generate_docs_indexes.py` regenerates directory `index.md` files from docs frontmatter.
`scripts/search_docs.py` parses docs frontmatter, headings, and section bodies in memory at query
time and returns file, line, and anchor targets for citation-ready docs navigation. There is no
generated search artifact; results can never go stale.
`scripts/route_docs.py` builds on the same parsed catalog and returns JSON reading guidance for a
natural-language task, always including `ARCHITECTURE.md` as required context. By default the
`route` command uses the supported LM Studio local-model pipeline: lexical top 40 plus embedding
top 80 recall, combined-score prompt ordering, then prompt-guided selector. If that pipeline is
unavailable, routing falls back to deterministic lexical routing and reports a warning.

Run deterministic lexical routing explicitly with `--lexical-only`:

```bash
uv run python scripts/route_docs.py route "How does apply record FileEvents?"
uv run python scripts/route_docs.py route "How does apply record FileEvents?" --lexical-only
uv run python scripts/route_docs.py refresh
```

The default model identifiers are:

* `OMYM2_DOC_EMBED_MODEL=text-embedding-qwen3-embedding-0.6b`
* `OMYM2_LOCAL_LLM_MODEL=qwen/qwen3-4b-2507`

Endpoint base URLs and API keys come from the corresponding `OMYM2_DOC_*`,
`OMYM2_LMSTUDIO_BASE_URL`, `OMYM2_LOCAL_LLM_*`, or `LLM_*` environment variables. Without an
override, the router probes reachable WSL host candidates before falling back to
`http://localhost:1234/v1`. Model requests include an LM Studio `ttl` so JIT-loaded models remain
available during routing. The embedding cache is local-only under `.doc-router/embeddings.sqlite`
and is ignored by git.
If a model endpoint is unavailable during routing, the script returns the deterministic fallback
with a warning.

`scripts/eval_docs_router.py` measures lexical routing cases from `tests/fixtures/docs_routing_cases.jsonl`.

## Local Model Policy

General-purpose local LLM delegation is intentionally unavailable. `scripts/ask_local_llm.py` and `scripts/review_with_local_llm.py` were removed; do not reintroduce local-model helpers for summaries, one-off Q&A, doc-description drafting, docs-search, test review, or missing-test-case generation. Use `scripts/route_docs.py` for docs routing and read files directly for other reasoning tasks.

## Test Commands

Use these pytest commands by intent:

```bash
# Inspect a focused failure.
uv run pytest <test-target> -q --tb=short --show-capture=all

# Deep debug a focused failure.
uv run pytest <test-target> -q --tb=long -s --show-capture=all
```

Replace `<test-target>` with a test file, test class, test function, or pytest node id.

## Suppressions

Use suppressions sparingly.

Allowed suppression forms:

* `# pyright: ignore[...]`
* `# ruff: noqa: RULE`

Each suppression must include a brief justification comment explaining why the warning or rule is intentionally suppressed.

## Runtime Configuration

Python/runtime configuration uses environment variables only.

This does not change OMYM2 application configuration. Application config remains TOML-based and is governed by [contracts/config.md](contracts/config.md).
