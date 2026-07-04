# OMYM2 Agent Instructions

Use this routing before choosing task-specific docs.

## Required Reading

Read `ARCHITECTURE.md` before starting any task:

## Read As Needed

Read `docs/DEVELOPMENT.md` for implementation, validation, quality gates,
suppressions, or runtime configuration work.

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
directory has an `index.md` for progressive disclosure. Start at
`docs/index.md`. When you edit a doc, update its frontmatter `description`
and `timestamp` and the matching `index.md` entry; CI enforces conformance
via the docs bundle test under `tests/docs/`.

## Docs Router

| Path | Use |
| --- | --- |
| [docs/PRODUCT.md](docs/PRODUCT.md) | Product scope, non-goals, and UI role. |
| [docs/DOMAIN.md](docs/DOMAIN.md) | Domain concepts, invariants, and ID behavior. |
| [docs/COMMANDS.md](docs/COMMANDS.md) | CLI command surface and command behavior. |
| [docs/STORAGE.md](docs/STORAGE.md) | Storage responsibilities and persisted-state boundaries. |
| [docs/DEVELOPMENT.md](docs/DEVELOPMENT.md) | Development commands, quality gates, suppressions, and runtime configuration. |
| [docs/TESTING.md](docs/TESTING.md) | Test policy and coverage expectations. |
| [docs/codebase/index.md](docs/codebase/index.md) | Detailed source layout, dependency, port, and naming rules. |
| [docs/contracts/index.md](docs/contracts/index.md) | Config, DB schema, path identity, storage representation, and status values. |
| [docs/execution/index.md](docs/execution/index.md) | Plan, apply, undo, refresh, organize, check, and failure semantics. |
