# OMYM2 Agent Instructions

Use this routing before choosing task-specific docs.

## Required Reading

Read `ARCHITECTURE.md` before any task that touches `src/`, `web/`, or
`tests/`. Docs-only, issue-only, or purely read-only tasks may skip it.

## Read As Needed

Read `docs/DEVELOPMENT.md` for implementation, validation, quality gates,
suppressions, or runtime configuration work.

## Validation Shortcut

Mode selection is owned by `.agents/skills/validate/SKILL.md`. Gate
definitions live in `docs/DEVELOPMENT.md`.

## Knowledge Navigation

Use the docs router below for task-specific reading.
When you edit a doc, update its frontmatter `description` and `timestamp`; do not edit
`index.md` files by hand. Regenerate indexes with
`uv run python scripts/generate_docs_indexes.py --write`. CI enforces
conformance via the docs bundle test under `tests/docs/`.

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
