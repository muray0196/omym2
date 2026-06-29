# Work Tracking

This document is the operating contract for tracking OMYM2 work in GitHub.

It is written for agents. A future agent must be able to open one GitHub Issue,
read the linked authoritative docs, and continue safely without reading the
whole Project board or chat history.

Active progress does **not** live in repository Markdown files. Repository docs
store durable rules, contracts, and process. GitHub Issues, Projects, Pull
Requests, and Milestones store live work state.

## Non-Negotiable Rules

1. Durable repository changes start from a GitHub Issue.
2. The Issue is the executable task boundary.
3. The Project stores queue state and planning metadata.
4. The Pull Request stores review, verification, and change history.
5. Milestones group real phases or releases only.
6. Repository docs must not become progress ledgers.
7. Agents must leave enough GitHub state for the next agent to resume safely.
8. If a preferred GitHub tracking feature is unavailable, record the intended
   update in an Issue or PR comment.

## Sources Of Truth

| Concern | Source of truth |
| --- | --- |
| Task boundary | GitHub Issue body |
| Queue/status | GitHub Project fields |
| Live progress | Issue or PR comments |
| Breakdown | GitHub sub-issues |
| Blockers | GitHub issue dependencies, or an explicit `Blocked by #...` comment |
| Review/change record | Pull Request |
| Phase/release grouping | GitHub Milestone |
| Durable rationale | `docs/decisions/` |
| Durable specs/process | `ARCHITECTURE.md`, `AGENTS.md`, `docs/` |
| Local progress ledger | Nowhere |

## Issue Requirement

Create or select a GitHub Issue before changing repository files. This applies
to code, tests, configuration, documentation, prompts, skills, process, and
GitHub metadata.

An Issue is not required for answer-only chat, read-only explanation, or quick
inspection that produces no durable repository or GitHub change. If inspection
discovers follow-up implementation work, create or select an Issue before
making that change.

Before creating an Issue, search open Issues and PRs for the same goal. Reuse a
suitable Issue; create a new one only when no existing Issue is the correct task
boundary.

When the user requests a durable change without providing an Issue, create a
concise Issue from the request and start from it.

## Issue Ready Contract

An Issue is `Agent-ready = yes` only when another agent can execute from it
without unrelated Issues or the full Project board.

Required Issue body sections:

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

For small documentation or test tasks, the body may be concise, but it still
needs a goal, non-goals, acceptance criteria, verification, and dependency
state.

Set `Agent-ready = yes` only when the goal is explicit, acceptance criteria are
checkable, required docs are listed, blockers are absent or closed, risk is
classified, and verification is known or explicitly not applicable.

If a required section is missing, update it from available evidence. Ask the
user only when missing information changes scope or risk and cannot be inferred
safely.

## Project Fields

Use the smallest field set that changes agent behavior. Do not add Project
fields for data that already has a GitHub-native home, such as assignee, labels,
or milestone.

Required fields:

| Field | Values |
| --- | --- |
| `Status` | `Backlog`, `Ready`, `In progress`, `Blocked`, `In review`, `Done` |
| `Work type` | `feature`, `bug`, `refactor`, `test`, `docs`, `architecture`, `investigation`, `chore` |
| `Area` | `product`, `architecture`, `domain`, `execution`, `storage`, `config`, `db`, `cli`, `web`, `testing`, `docs`, `agent`, `repo` |
| `Risk` | `low`, `medium`, `high` |
| `Needs docs` | `yes`, `no` |
| `Needs decision record` | `yes`, `no` |
| `Agent-ready` | `yes`, `no` |

Status meanings:

| Status | Meaning |
| --- | --- |
| `Backlog` | Captured but not ready, not prioritized, or underspecified. Draft Project items may exist only here. |
| `Ready` | Issue exists, `Agent-ready = yes`, and no open blockers exist. |
| `In progress` | An agent or human has started execution. |
| `Blocked` | Work cannot continue until blockers resolve or required information is provided. |
| `In review` | A PR or equivalent review artifact is open. |
| `Done` | Acceptance criteria are satisfied and the Issue is closed or ready to close. |

If Project updates are unavailable, leave an Issue comment with the intended
fields and do not claim the Project changed.

## Agent Workflow

### 1. Load Context

For non-trivial work, read:

1. `AGENTS.md`
2. `ARCHITECTURE.md`
3. `docs/SUBAGENTS.md`
4. this document
5. the current Issue
6. only task-specific docs linked by the Issue or docs router

Do not read all open Issues, all closed Issues, or the whole Project board just
to begin a task.

### 2. Normalize Before Editing

Before editing files:

- create or select the Issue;
- fill missing Issue body sections;
- add Project fields, or comment with intended fields if unavailable;
- link blockers or record `none known`;
- split large work into sub-issues;
- set `Status = In progress` when starting immediately.

When possible, create a branch named:

```text
<work-type>/<issue-number>-<short-slug>
```

Leave a short start comment for non-trivial work with branch, scope, docs read,
intended verification, and Project update status.

### 3. Update During Work

Keep updates sparse. Comment only when status changes, a blocker appears or
clears, scope or acceptance criteria change, verification fails in a way the
next agent must know, work is handed off, or a PR is opened.

If scope expands, update the Issue before implementing the expanded scope. If
the scope becomes too large, split it into sub-issues.

### 4. Handle Blockers

When blocked:

1. Set `Status = Blocked` when possible.
2. Add an Issue dependency when possible.
3. Comment with the minimum unblock condition.
4. Stop implementation unless independent unblocked work remains.

The blocked comment must state the blocker, minimum unblock condition, safe
remaining work, and Project update status.

### 5. Open A Pull Request

Open a PR for code, test, configuration, or durable documentation changes unless
the repository owner explicitly requests direct commits.

The PR body must include the linked Issue, summary, non-goals or deferred work,
verification result, docs impact, risk notes, and closure intent.

Use closing keywords only when the PR fully satisfies the Issue. Use `Refs`,
`Partially addresses`, or manual linkage when the Issue should remain open.

Set `Status = In review` when a PR is open.

### 6. Complete Or Continue

An Issue may move to `Done` and close only when acceptance criteria are
satisfied or explicitly revised, verification passed or the exception is
recorded, required docs and decision records are updated, no stated blocker
remains, and the PR is merged or the Issue contains a final no-PR resolution
comment.

For partial completion, leave the Issue open, check off completed acceptance
criteria, rewrite remaining criteria, keep or reset `Status`, and do not use PR
closing keywords.

## Handoff

A handoff is required when an agent stops with unmerged work, unresolved
verification, or remaining scope. The comment must state current branch or PR,
completed work, incomplete work, verification run or not run, blockers, and the
next safe action.

The next agent should be able to resume from the Issue, linked PR, and linked
docs without reconstructing context from chat.

## Parent And Sub-Issues

Use a parent Issue for a goal that needs coordination across multiple
reviewable changes. Use sub-issues for independently reviewable slices.

The parent owns the overall goal, non-goals, invariants, and done definition.
Each sub-issue owns its own acceptance criteria and verification, links back to
the parent, and avoids duplicating full parent context.

## Milestones And Labels

Use Milestones only for real phases, releases, or externally meaningful
batches. Labels are secondary discovery aids; they must not be the only place
where task state, blockers, or acceptance criteria exist. Do not create labels
that duplicate Project `Status`.

## Repository Documentation Boundary

Repository docs may store durable product behavior, architecture rules,
contracts, schemas, command semantics, testing policy, process rules, and
decision records.

Repository docs must not store active progress ledgers, per-Issue running logs,
Project status duplicates, or stale checklists copied from Issues. If a fact
matters only until an Issue or PR is complete, put it in GitHub.

## Subagent Tracking

The main agent owns GitHub state. When using subagents, pass the current Issue
boundary, re-read cited evidence before accepting findings, and record only
material findings in the Issue or PR.

## Capability Fallbacks

Agents may not always have the same GitHub permissions or tool support. Use
explicit fallbacks:

| Preferred operation | Fallback |
| --- | --- |
| Update Project field | Issue comment with intended field update |
| Add Issue dependency | Issue comment naming `Blocked by` or `Blocking` |
| Create sub-issue | New Issue linked from parent and child comments |
| Open PR | Branch or commit reference plus Issue handoff comment |
| Run verification | Record exact command not run and reason |

Silent failure to update tracking state is not allowed.

## Prohibited Agent Behavior

Agents must not implement from a Project draft item without an Issue, treat chat
as the lasting task boundary after repository changes, close an Issue from a
partial PR, expand scope without updating the Issue, mark work done without
verification evidence or an explicit not-run reason, create repository-local
progress ledgers, rely on labels for required state, or read broad unrelated
GitHub history to compensate for an underspecified Issue.
