---
name: omym2-docs-update
description: Update OMYM2 documentation safely. Use for docs restructuring, redundancy cleanup, AGENTS.md routing changes, folder-index routing, stale-link cleanup, skill-doc synchronization, and deciding whether documentation content is live, duplicated, or dead.
---

# OMYM2 Docs Update

## Inputs
- changed_docs
- requested_doc_goal
- whether code or tests also changed
- suspected duplicate, stale, or dead content

## Read first
- The authoritative home for the rule being changed
- Neighbor docs that summarize, route to, or link to that authoritative home

## Read when workflow, tracking, or skill guidance is in scope
- docs/development.md
- docs/WORK_TRACKING.md
- docs/SUBAGENTS.md
- .agents/skills/*/SKILL.md

## Steps
1. Treat `AGENTS.md`, `ARCHITECTURE.md`, `docs/SUBAGENTS.md`, and `docs/WORK_TRACKING.md` as the common reading path. Do not repeat their rules in lower-level docs unless the local file explicitly needs a short summary.
2. Classify each sentence or section before editing:
   - authoritative rule
   - local summary
   - navigation / routing
   - process schema
   - decision rationale
   - dead planning or progress content
3. Keep one authoritative home per rule. If a non-authoritative doc repeats the rule, replace it with a short pointer unless the reader needs a local summary to avoid opening another file.
4. Preserve information before removing text. For every removed rule, verify that the same fact remains in the authoritative home or add it there before replacing the duplicate with a link.
5. Use expected agent reading order to judge duplication:
   - common required docs can be assumed
   - task-specific docs should add detail, not restate common context
   - router docs should route, not explain the target content
   - skill docs should list task-specific resources, not common required docs
6. When deleting, moving, or splitting docs, update every router and durable pointer in the same change:
   - AGENTS.md
   - ARCHITECTURE.md
   - affected docs under `docs/`
   - affected folder indexes under `docs/`
   - affected `.agents/skills/*/SKILL.md`
7. Keep active progress, backlog, blockers, assignment, and partial completion state out of repository docs. Route that content to GitHub Issues, Projects, and Milestones.
8. Use `docs/decisions/` only for durable rationale when changing or challenging a product or architecture rule. Do not use decision records as active specifications.
9. Keep docs-only work docs-only unless the user explicitly expands scope to code or tests.

## Verification
- Search for stale paths and old file names after moves or deletes.
- Run a Markdown relative-link existence check when links change.
- Run a duplicate-prose scan when doing redundancy cleanup.
- Run `git diff --check` for docs-only edits.
- If code or tests changed, use the relevant quality gates from `docs/development.md`.

## Checks
- No rule is removed unless it still exists in an authoritative home or is confirmed dead.
- Summaries are marked or written as summaries and point to the owner.
- `AGENTS.md` stays the first-hop docs router and common reading path.
- Folder indexes route only within their folder.
- Skills keep `Read first` lists task-specific and do not repeat common required reading.
- Completed plan/checklist docs are not preserved as durable specs by default.

## Outputs
- docs update verdict
- files changed
- authoritative homes touched
- duplicated or dead content removed
- stale references fixed
- verification commands run
