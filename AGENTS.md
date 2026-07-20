# OMYM2 Agent Instructions

Use this routing before choosing task-specific docs. `ARCHITECTURE.md` is the
always-read safety cache; focused docs own the detailed, task-specific contract.

## Required Reading

Read `ARCHITECTURE.md` before any task that touches `src/`, `web/`, or
`tests/`. Keep its non-negotiable rules active throughout the task. Docs-only,
issue-only, or purely read-only tasks may skip it.

## Implementation Conventions

### Compatibility

OMYM2 is unreleased. Do not preserve backward compatibility unless the current
task explicitly requires it.

### Constants and Config

Centralize operationally tunable application production values in
`src/omym2/config.py`. Keep standalone repository-script tunables in
`scripts/config.py`. Define tunables in this form:

```python
UPPER_SNAKE_NAME = literal_default  # description, units, valid range
```

Do not move test inputs, expected values, protocol constants, or domain
constants into either `config.py` merely to avoid literals.

### File Headers

Add a brief, language-appropriate header comment to each code file with this
content:

```text
Summary: <one-line description of the file's purpose>
Why: <one-line business, architectural, or bug-related reason the file exists>
```

Do not add headers to generated files, vendored files, migrations, empty
package-marker files, or file formats that do not support comments.

## Large Initiative Plans

Keep the root `ROADMAP.md` tracked. Populate it only for large, multi-session work
with cross-cutting changes, material uncertainty, or ordered rollout/verification—not
ordinary focused changes. If it contains a roadmap, read it before scoped work;
keep it current and clear it when no longer needed rather than deleting it.
Record only the outcome, material decisions or risks, ordering constraints, and
validation or rollback requirements. Do not list routine steps, progress logs,
or completed checklists, or duplicate authoritative docs; move durable
conclusions to their authoritative docs.

## Read As Needed

For an implementation task, start with
`.agents/skills/implement-change/SKILL.md`; it selects the safety checklist and
focused documentation for the change. Do not replace those focused checks with
the Architecture summary.

Use `.agents/skills/validate/SKILL.md` for ordinary implementation and
validation. Read only the relevant section of `docs/development/harness.md`
when changing the harness, suppressions, runtime configuration, or a gate detail
not covered by the skill.

## Context Discipline

Treat `ARCHITECTURE.md` and matching skills as operational safety caches. Follow
their conditional documentation routes; do not preload every linked document.
Locate the relevant heading first, then read only the bounded section needed for
the task.

Start repository searches with paths, filenames, or counts (`rg --files`,
`rg -l`, or `rg -c`). Scope by directory and glob before requesting matching
lines, and inspect only targeted ranges around relevant matches. Never emit an
unbounded repo-wide search into the conversation.

Inspect large source and test files by symbol or line range. Do not read lockfiles,
generated clients, OpenAPI output, bundled static assets, or other generated
artifacts in full; use the owning generator, drift check, hashes, or a focused
diff instead.

Across long runs, report milestone deltas only. Do not repeat unchanged plans,
commands, prior diagnostics, or earlier status summaries in later turns.

## Validation Shortcut

Mode selection is owned by `.agents/skills/validate/SKILL.md`. Gate
definitions live in `docs/development/harness.md`. During Codex implementation,
run the focused checks selected by the skill. When the repo-local `Stop` hook is
available, let it own the path-aware completion gate instead of repeating those
checks manually before handoff. Full aggregate validation remains a CI or
explicit-request concern.

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
| [docs/codebase/index.md](docs/codebase/index.md) | Detailed source layout, dependency, port, naming, and Web frontend rules. |
| [docs/contracts/index.md](docs/contracts/index.md) | Config, DB, Operation, path identity, status, and Web API contracts. |
| [docs/decisions/index.md](docs/decisions/index.md) | Accepted architecture decisions and their rationale and consequences. |
| [docs/development/index.md](docs/development/index.md) | Development harness, quality gates, test policy, and benchmark procedure. |
| [docs/execution/index.md](docs/execution/index.md) | Plan, apply, undo, refresh, organize, check, and failure semantics. |
