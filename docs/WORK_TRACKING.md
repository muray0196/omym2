# Work Tracking

This document is the operating contract for tracking OMYM2 work in GitHub.

Agents must be able to resume from one Issue, linked authoritative docs, and
linked PRs without reading the full Project board or chat history.

Repository docs store durable rules, contracts, and process. GitHub Issues,
Projects, PRs, and Milestones store live work state.

## Core Rules

1. Durable repository changes start from a GitHub Issue.
2. The Issue is the executable task boundary.
3. The Project stores queue state and planning metadata.
4. The PR stores review, verification, and change history.
5. Milestones group real phases or releases only.
6. Repository docs must not become progress ledgers.
7. Agents must leave enough GitHub state for safe handoff.
8. If a GitHub feature is unavailable, comment with the intended update.

## Sources Of Truth

| Concern | Source |
| --- | --- |
| Task boundary | Issue body |
| Queue/status | Project fields |
| Live progress | Issue or PR comments |
| Breakdown | Sub-issues |
| Blockers | Issue dependencies or `Blocked by #...` comments |
| Review/change record | PR |
| Phase/release grouping | Milestone |
| Durable rationale | `docs/decisions/` |
| Durable specs/process | `ARCHITECTURE.md`, `AGENTS.md`, `docs/` |
| Local progress ledger | Nowhere |

## Issue Requirement

Create or select an Issue before changing repository files, GitHub metadata, or
durable docs/process.

No Issue is needed for answer-only chat, read-only explanation, or quick
inspection that produces no durable change. If inspection leads to
implementation, create or select an Issue before editing.

Before creating an Issue, search open Issues and PRs for the same goal. Reuse a
suitable Issue; otherwise create a concise one from the user request.

## Issue Ready Contract

Set `Agent-ready = yes` only when the Issue has an explicit goal, checkable
acceptance criteria, required docs, known verification, risk classification,
and no unresolved blocker.

Required sections:

```markdown
## Goal
## Non-goals
## Context
## Authoritative docs to read
## Affected areas
## Invariants and constraints
## Acceptance criteria
## Verification
## Dependencies
## Notes for agents
```

Small docs/test tasks may be concise, but must still state goal, non-goals,
acceptance criteria, verification, and dependency state.

If a section is missing, infer and update it when safe. Ask the user only when
the gap changes scope or risk.

## Project Fields

Use only fields that change agent behavior:

- `Status`: `Backlog`, `Ready`, `In progress`, `Blocked`, `In review`, `Done`
- `Work type`: `feature`, `bug`, `refactor`, `test`, `docs`, `architecture`,
  `investigation`, `chore`
- `Area`: `product`, `architecture`, `domain`, `execution`, `storage`,
  `config`, `db`, `cli`, `web`, `testing`, `docs`, `agent`, `repo`
- `Risk`: `low`, `medium`, `high`
- `Needs docs`: `yes`, `no`
- `Needs decision record`: `yes`, `no`
- `Agent-ready`: `yes`, `no`

Status meanings:

| Status | Meaning |
| --- | --- |
| `Backlog` | Captured but not ready, not prioritized, or underspecified. |
| `Ready` | Issue is ready and unblocked. |
| `In progress` | Work has started. |
| `Blocked` | Work cannot continue. |
| `In review` | PR or equivalent review artifact is open. |
| `Done` | Acceptance criteria are satisfied and closure is valid. |

If Project updates are unavailable, comment with intended fields and do not
claim the Project changed.

## Agent Workflow

Read only the required context:

1. `AGENTS.md`
2. `ARCHITECTURE.md`
3. `docs/SUBAGENTS.md`
4. this document
5. the current Issue
6. task-specific docs linked by the Issue or docs router

Before editing:

- create or select the Issue;
- fill missing Issue sections;
- update Project fields or comment with intended fields;
- link blockers or record `none known`;
- split large work into sub-issues;
- set `Status = In progress` when starting immediately;
- branch as `<work-type>/<issue-number>-<short-slug>` when possible;
- leave a start comment for non-trivial work.

During work, comment only for status changes, blockers, scope or acceptance
criteria changes, material verification failures, handoff, or PR creation. If
scope expands, update the Issue first.

When blocked, set `Status = Blocked` when possible, add a dependency when
possible, comment with the minimum unblock condition, and stop unless
independent unblocked work remains.

Open a PR for code, test, configuration, or durable documentation changes unless
the repository owner requests direct commits. The PR body must include linked
Issue, summary, non-goals or deferred work, verification, docs impact, risk,
and closure intent. Use closing keywords only for full completion.

Move to `Done` only when acceptance criteria are satisfied or revised,
verification passed or the exception is recorded, required docs and decisions
are complete, blockers are gone, and the PR is merged or a final no-PR
resolution is recorded.

For partial completion, keep the Issue open, update remaining criteria, and do
not use closing keywords.

## Handoff

Handoff is required when stopping with unmerged work, unresolved verification,
or remaining scope. State branch or PR, completed work, incomplete work,
verification, blockers, and next safe action.

## Parent And Sub-Issues

Use parent Issues for coordinated goals and sub-issues for independently
reviewable slices. The parent owns the overall goal and done definition. Each
sub-issue owns its own acceptance criteria and verification.

## Milestones And Labels

Use Milestones only for real phases, releases, or meaningful batches. Labels
are discovery aids, not task state, blockers, or acceptance criteria. Do not
create labels that duplicate Project `Status`.

## Repository Documentation Boundary

Repository docs may store durable product behavior, architecture rules,
contracts, schemas, command semantics, testing policy, process rules, and
decision records.

Repository docs must not store active progress ledgers, per-Issue running logs,
Project status duplicates, or stale Issue checklists. Put temporary progress in
GitHub.

## Subagent Tracking

The main agent owns GitHub state. Pass subagents the Issue boundary, re-read
cited evidence before accepting findings, and record only material findings in
the Issue or PR.

## Capability Fallbacks

| Preferred operation | Fallback |
| --- | --- |
| Update Project field | Issue comment with intended field update |
| Add Issue dependency | Issue comment naming `Blocked by` or `Blocking` |
| Create sub-issue | New Issue linked from parent and child comments |
| Open PR | Branch or commit reference plus Issue handoff comment |
| Run verification | Exact command not run and reason |

Fallbacks must be explicit.

## Prohibited Behavior

Do not implement from Project drafts, treat chat as the lasting task boundary,
close Issues from partial PRs, expand scope before updating the Issue, mark work
done without verification evidence or a not-run reason, create repo-local
progress ledgers, rely on labels for required state, or read broad unrelated
GitHub history to compensate for an underspecified Issue.
