# OMYM2 Agent Instructions

Current task-specific rules are maintained in the split documentation files under `docs/`.

## Required Reading

Before non-trivial implementation work, read:

* `ARCHITECTURE.md`
* `docs/index.md`
* `docs/development.md` for quality gates when code or tests change
* The task-relevant document listed in `docs/index.md`

Prefer the task-specific document listed in `docs/index.md`.

## Skills

You have these skills in this project

* `omym2-quality-triage`: use for CI/local check failures, quality gate execution, and environment-vs-code failure classification.
* `omym2-architecture-guardrails`: use for new modules, changed imports, layer responsibility checks, source file naming, and dependency boundary review.
* `omym2-plan-safety`: use for Plan, PlanAction, Run, FileEvent, apply, undo, refresh, organize, or any Library music file mutation behavior.
* `omym2-path-identity-storage`: use for stored paths, PathPolicy, Library identity, `library_id`, registration, relink, DB schema, and storage representation changes.

## Non-negotiable Rules

* Library music file mutations must go through a Plan.
* Apply must use recorded PlanActions, not recalculated target paths.
* FileEvents must be recorded before Library music file mutations.
* Domain and features must not depend on concrete adapters.
* Library identity is stable by `library_id`, not by root path.
* Stored Library-managed paths are Library-root-relative.
* Run the relevant checks before marking work complete.
