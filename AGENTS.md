# OMYM2 Agent Instructions

Current task-specific rules are maintained in the split documentation files under `docs/`.

## Required Reading

Before non-trivial OMYM2 work:

* Read `ARCHITECTURE.md`.
* Read `docs/SUBAGENTS.md`.
* Read `docs/WORK_TRACKING.md`.

When code or tests change, read:

* `docs/development.md`

Follow the smallest task-specific document set from the docs router below.

## Subagents

Subagents are always allowed for OMYM2 work. Use them whenever they improve
evidence gathering, focused patching, contract checks, test triage, or risk
review.

## Docs Router

| Path | Use |
| --- | --- |
| `docs/SUBAGENTS.md` | Codex subagent routing, model choice, and handoff policy. |
| `docs/WORK_TRACKING.md` | GitHub Issues, Projects, Milestones, blockers, and active-work process. |
| `docs/architecture/` | Detailed architecture rules for source layout, dependencies, ports, and naming. |
| `docs/commands.md` | CLI command surface and command behavior. |
| `docs/contracts/` | Config, DB schema, path identity, storage representation, and status values. |
| `docs/decisions/` | Accepted durable product or architecture rationale. |
| `docs/development.md` | Development commands, quality gates, suppressions, and runtime configuration. |
| `docs/domain.md` | Domain concepts, invariants, and ID behavior. |
| `docs/execution/` | Plan, apply, undo, refresh, organize, check, and failure semantics. |
| `docs/product.md` | Product scope, non-goals, and UI role. |
| `docs/storage.md` | Storage responsibilities and persisted-state boundaries. |
| `docs/testing.md` | Test policy and coverage expectations. |

## Skills

You have these skills in this project

* `omym2-quality-triage`: use for CI/local check failures, quality gate execution, and environment-vs-code failure classification.
* `omym2-architecture-guardrails`: use for new modules, changed imports, layer responsibility checks, source file naming, and dependency boundary review.
* `omym2-plan-safety`: use for Plan, PlanAction, Run, FileEvent, apply, undo, refresh, organize, or any Library music file mutation behavior.
* `omym2-path-identity-storage`: use for stored paths, PathPolicy, Library identity, `library_id`, registration, relink, DB schema, and storage representation changes.
* `omym2-docs-update`: use for docs restructuring, redundancy cleanup, authoritative-home routing, stale-link cleanup.

## Decision records

Use `docs/decisions/` only when changing or challenging a durable product or
architecture rule.

Decision records are rationale, not active specifications. Current rules live in
`ARCHITECTURE.md` and the relevant documents under `docs/`.
