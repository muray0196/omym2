---
name: delegate-local-llm
description: Offload bounded, evidence-grounded subtasks (test review, missing-case ideas, file summaries, factual questions, OKF description drafts) to a local LLM via scripts/. Use to save context or parallelize low-risk analysis.
---

# Delegate To Local LLM

The local LLM (LM Studio, OpenAI-compatible, WSL host auto-detected) is a **bounded assistant, not an agent**: it gets only the context the script selects, has no tools, and cannot edit files. Delegate narrow analysis; keep all decisions and edits yourself.

## Task → command

| Subtask | Command |
| --- | --- |
| Test-focused review of your current changes | `uv run python scripts/review_with_local_llm.py review --worktree` |
| Test review of staged changes / a PR | `... review --staged` or `... review --pr <N>` |
| Missing-test-case ideas for a diff | `uv run python scripts/review_with_local_llm.py cases --base main` |
| Summarize files or a diff into a compact brief | `uv run python scripts/ask_local_llm.py summarize --files <path> [--focus "..."]` |
| Answer one factual question about specific files | `uv run python scripts/ask_local_llm.py question --ask "..." --files <path>` |
| Draft OKF frontmatter description/tags for a doc | `uv run python scripts/ask_local_llm.py doc-description --files docs/<file>.md` |
| Pick docs sections to read for a vague request | `uv run python scripts/ask_local_llm.py docs-search --ask "..."` (see `search-docs`) |

Both scripts accept `--stdin` (pipe a diff or log), `--output <file>`, and `--dry-prompt` (print the prompt without calling the LLM — use this to debug). Model/endpoint come from `OMYM2_LOCAL_LLM_BASE_URL`, `OMYM2_LOCAL_LLM_MODEL` / `OMYM2_REVIEW_MODEL`, defaulting to port 1234.

## What to delegate (decision rule)

Delegate when ALL are true:

1. The subtask is answerable from a small, explicit set of files or a diff.
2. A wrong answer is cheap: you will verify the output before acting on it.
3. It requires no repo-wide navigation, no tool use, and no design judgment.

Never delegate: architecture or safety decisions, anything touching Plan/apply/path-identity semantics, code edits, or final review sign-off.

## Consuming the output

- Output is JSON with a `confidence` field. Treat everything as **hints**.
- Discard any finding whose `evidence` you cannot verify in the actual files.
- Cross-check `missing_test_cases` against the real test files before writing tests.
- Never paste the output into a report or commit as-is; restate only what you verified.
- `docs-search` readings are pre-validated against parsed docs headings, but they are navigation hints — cite the Markdown you actually read.
- On timeout or connection error: the LM Studio server is probably not running — proceed without delegation rather than blocking the task.

## Failure handling

| Symptom | Action |
| --- | --- |
| `could not reach local LLM endpoint` | Skip delegation; note it and continue yourself |
| `model did not return valid JSON` (exit 2) | Retry once; then skip delegation |
| Empty/near-empty result | Normal — the model found nothing; do not re-prompt for more findings |
