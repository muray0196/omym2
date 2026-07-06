# OMYM2 Agent Instructions

Use this routing before choosing task-specific docs.

## Required Reading

Read `ARCHITECTURE.md` before starting any task:

## Prohibited Reading

Never open or read `WORKFLOW.md` under any circumstances.

## Read As Needed

Read `docs/DEVELOPMENT.md` for implementation, validation, quality gates,
suppressions, or runtime configuration work.

## Validation Shortcut

`scripts/checks.sh` wraps the quality gates from `docs/DEVELOPMENT.md`:
`changed` (edit loop, default), `all` (final gates), `py`, `web`, `docs`,
`arch`, and `test <pytest-target>`.

## Subagents

You are the orchestrator.
Focus on planning, delegation, review, and synthesis. Do not do the execution work yourself unless necessary.
Delegate implementation, investigation, editing, testing, and detailed analysis to subagents.

* Skip subagents for trivial one-file or command-only work.
* Use `explorer` before implementation when files, patterns, or dependencies are
  not clear.
* Use `coder` only after scope, target files, and approach are settled.
* Use `reviewer` after non-trivial implementation or before PR/commit review.
* The main agent owns orchestration, final judgment, repo-policy checks, and
  high-risk architecture, storage, path, or Plan decisions.

### Briefing a Subagent

Subagents start with zero context. Every dispatch must be self-contained:

1. Goal — one sentence stating the outcome.
2. Scope — exact files, symbols, or directories, plus what is out of bounds.
3. Constraints — the repo rules that apply: which `.agents/skills/` entries to
   follow, never read `WORKFLOW.md`, and the check command to run
   (`scripts/checks.sh changed` or `scripts/checks.sh test <target>`).
4. Expected output — the exact report shape needed back (paths with line
   numbers, diff summary, or verdict).

### Working the Pipeline

* Default flow for non-trivial changes: `explorer` → `coder` → `reviewer`.
* Forward evidence verbatim: paste explorer's paths, line numbers, and pattern
  examples into the coder brief, never a summary of a summary.
* One change per coder dispatch. Split large work into sequential scoped
  dispatches; never run two coders that could touch the same files.
* Independent explorer questions may run in parallel.
* If a subagent stops on ambiguity or repeated failure, resolve the gap first
  (directly or with another explorer pass), then re-dispatch with a tighter
  brief; do not retry the same prompt.
* Read the resulting diff before accepting it; feed reviewer must-fix findings
  back as a new scoped coder dispatch.

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
