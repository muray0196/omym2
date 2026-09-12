# OMYM2 Agent Instructions

Use this file for task routing and repository-wide conventions. Focused skills
carry operational checks; linked docs own the detailed contracts.

## Required Reading

Read [ARCHITECTURE.md](ARCHITECTURE.md) before changing `src/`, `web/`, or
`tests/`. Read it for architecture reviews too; other read-only, docs-only, and
issue-only tasks may skip it.

## Task Routing

Open only the skills matching the behavior being changed or reviewed. Mentioning
a domain entity or reading an existing config value does not by itself change
that contract. Read each skill once; follow its conditional doc links.

| Task or changed boundary | Skill |
| --- | --- |
| Execution state, apply/undo/refresh, or Library music file mutations | [plan-apply-safety](.agents/skills/plan-apply-safety/SKILL.md) |
| Stored paths, PathPolicy, Library/Track identity, registration or relink | [path-identity-safety](.agents/skills/path-identity-safety/SKILL.md) |
| SQLite schema, migrations, or repository persistence | [db-schema-change](.agents/skills/db-schema-change/SKILL.md) |
| Persisted AppConfig/TOML schema or settings save/load protocol | [config-schema-change](.agents/skills/config-schema-change/SKILL.md) |
| Production module placement, package structure, or imports between layers | [architecture-boundaries](.agents/skills/architecture-boundaries/SKILL.md) |
| React/Vite frontend, Web adapters, generated API or static packaging | [web-frontend-change](.agents/skills/web-frontend-change/SKILL.md) |
| Add or change tests | [write-tests](.agents/skills/write-tests/SKILL.md) |
| Change docs or behavior described there | [update-docs](.agents/skills/update-docs/SKILL.md) |
| Select or diagnose quality checks | [validate](.agents/skills/validate/SKILL.md) |
| Draft or create a Linear issue without implementing it | [linear-create-issue](.agents/skills/linear-create-issue/SKILL.md) |

## Scope and Decisions

Inspect the working tree before editing; preserve unrelated changes. Complete
authorized work, including supporting contract docs and tests. Skill guidance
does not override the user's explicit scope or require renewed approval for a
decision already authorized. When a real conflict remains unresolved, state the
exact rule and the missing decision; continue independent work where possible.

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

New code files need a brief, language-appropriate header comment. Keep existing
headers accurate when editing a file; do not sweep unrelated files to add them:

```text
Summary: <one-line description of the file's purpose>
Why: <one-line business, architectural, or bug-related reason the file exists>
```

Do not add headers to generated files, vendored files, migrations, empty
package-marker files, or file formats that do not support comments.

## Large Initiative Plans

Keep [ROADMAP.md](ROADMAP.md) tracked. Populate it only for large, multi-session
work with cross-cutting changes, material uncertainty, or ordered rollout.
Read an active roadmap before scoped work; keep it current, then clear it.
Record outcomes, material decisions/risks, ordering, and validation/rollback
requirements. Omit routine steps and progress logs; durable conclusions belong
in authoritative docs.

## Context Discipline

Locate the relevant heading first, then read only the needed section; do not
preload every linked document.

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

Mode selection is owned by the `validate` skill. Gate
definitions live in [docs/development/harness.md](docs/development/harness.md).
Read the relevant harness section only when changing it or resolving a gate
detail the skill does not cover. During implementation,
run the focused checks selected by the skill. When the repo-local `Stop` hook is
available, let it own the path-aware completion gate instead of repeating those
checks manually before handoff. Full aggregate validation remains a CI or
explicit-request concern.

## Knowledge Navigation

Use the router below for task-specific reading and `update-docs` for frontmatter
and generated indexes. Keep navigation links as relative Markdown links;
`tests/docs/` checks both the docs bundle and agent guidance.

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
