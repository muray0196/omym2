# OMYM2 Agent Instructions

Use this routing before reading task-specific docs.

## Docs Routing

Read `ARCHITECTURE.md` before starting any task, regardless of router
availability.

Ask the docs router for the reading list in natural language:

```bash
uv run python scripts/route_docs.py route "<task or docs question>"
```

Read `required_docs` first, then `docs_to_read` in priority order. Read
`fallback_docs` only when the result is low-confidence or the task remains
unclear. The router is the top-level docs navigation interface; agents do not
need to understand the `docs/` directory structure, start from `docs/index.md`,
or maintain a manual router table.

Use `scripts/search_docs.py "<query>"` only after routing, when you need
citable `path:line` or anchor targets inside the selected docs.

## Validation Shortcut

`scripts/checks.sh` wraps the quality gates from `docs/DEVELOPMENT.md`:
`changed` (edit loop, default), `all` (final gates), `py`, `web`, `docs`,
`arch`, and `test <pytest-target>`.

## Subagents

When the user allows subagents, route them automatically:

* Skip subagents for trivial one-file or command-only work.
* Use `explorer` before implementation when files, patterns, or dependencies are
  not clear.
* Use `coder` only after scope, target files, and approach are settled.
* Use `reviewer` after non-trivial implementation or before PR/commit review.
* The main agent owns orchestration, final judgment, repo-policy checks, and
  high-risk architecture, storage, path, or Plan decisions.

## Knowledge Navigation

`docs/` is a single OKF v0.1 knowledge bundle: every doc carries YAML
frontmatter (`type`, `title`, `description`, `tags`, `timestamp`), and each
directory has an `index.md` for progressive disclosure. When you edit a doc,
update its frontmatter `description` and `timestamp` and the matching
`index.md` entry; CI enforces conformance via the docs bundle test under
`tests/docs/`.
