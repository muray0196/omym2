# OMYM2 Agent Instructions

Current task-specific rules are maintained in the split documentation files under `docs/`.

## Required Reading

Before non-trivial OMYM2 work:

* Read `ARCHITECTURE.md`.

When code or tests change, read:

* `docs/development.md`

Follow the smallest task-specific document set from the docs router below.

## Work Tracking

Linear is the issue source. Symphony may dispatch Codex against Linear issues.
Keep active progress, queue state, blockers, and handoff notes out of repository
docs.

## Docs Router

| Path | Use |
| --- | --- |
| `docs/architecture/` | Detailed architecture rules for source layout, dependencies, ports, and naming. |
| `docs/commands.md` | CLI command surface and command behavior. |
| `docs/contracts/` | Config, DB schema, path identity, storage representation, and status values. |
| `docs/development.md` | Development commands, quality gates, suppressions, and runtime configuration. |
| `docs/domain.md` | Domain concepts, invariants, and ID behavior. |
| `docs/execution/` | Plan, apply, undo, refresh, organize, check, and failure semantics. |
| `docs/product.md` | Product scope, non-goals, and UI role. |
| `docs/storage.md` | Storage responsibilities and persisted-state boundaries. |
| `docs/testing.md` | Test policy and coverage expectations. |
