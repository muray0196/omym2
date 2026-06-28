# OMYM2 Agent Instructions

Current task-specific rules are maintained in the split documentation files under `docs/`.

## Required Reading

Before non-trivial implementation work:

* Read `ARCHITECTURE.md`.
* Read `docs/index.md`, then follow only the smallest task-specific document set it routes to.

When code or tests change, read:

* `docs/development.md`

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
