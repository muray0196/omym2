# Work Tracking

This document is the operating contract for tracking OMYM2 work in GitHub.

It is written for agents. A future agent must be able to open one GitHub Issue,
read the linked authoritative docs, and continue safely without reading the
whole project board or guessing from chat history.

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

| Concern | Source of truth | Notes |
| --- | --- | --- |
| Task boundary | GitHub Issue body | Goal, non-goals, acceptance criteria, verification, blockers. |
| Queue/status | GitHub Project fields | `Status`, `Work type`, `Area`, `Risk`, docs/decision flags. |
| Live progress | Issue or PR comments | Meaningful transitions only; no per-command logs. |
| Breakdown | GitHub sub-issues | Use for independently reviewable slices of a larger goal. |
| Blockers | GitHub issue dependencies | If unavailable, comment `Blocked by #...` explicitly. |
| Review/change record | Pull Request | Link issue, summarize scope, record verification. |
| Phase/release grouping | GitHub Milestone | Do not use as status or priority. |
| Durable rationale | `docs/decisions/` | Rationale only, not active status. |
| Durable specs/process | `ARCHITECTURE.md`, `AGENTS.md`, `docs/` | Current rules and contracts. |
| Local progress ledger | Nowhere | Do not create progress Markdown files. |

## When An Issue Is Required

Create or select a GitHub Issue before changing repository files when the task
changes code, tests, configuration, documentation, prompts, skills, process, or
GitHub metadata.

An issue is not required for answer-only chat, read-only explanation, or a quick
inspection that produces no durable repository or GitHub change. If inspection
discovers follow-up implementation work, create or select an issue before making
that change.

Before creating a new issue:

1. Search open issues and PRs for the same goal.
2. Use an existing issue when it already defines the task.
3. Create a new issue only when no suitable issue exists.
4. Link related issues or PRs from the body or first comment.

When the user requests a durable change without providing an issue, the agent
creates a concise issue from the request and starts from that issue.

## Issue Ready Contract

An issue is `Agent-ready = yes` only when another agent can execute from it
without reading unrelated issues or the full Project board.

Required sections:

```markdown
## Goal
One concrete outcome.

## Non-goals
Explicit exclusions and boundaries.

## Context
Why this is needed. Include the user request summary when agent-created.

## Authoritative docs to read
- `AGENTS.md`
- Task-specific docs only.

## Affected areas
Files, packages, commands, docs, or GitHub metadata likely to change.

## Invariants and constraints
Rules that must not be violated.

## Acceptance criteria
- [ ] Observable result 1
- [ ] Observable result 2

## Verification
Commands, checks, or review method required before completion.

## Dependencies
Blocked by: none / #...
Blocking: none / #...

## Notes for agents
Known risks, assumptions, and allowed scope inference.
```

For small documentation or test tasks, the issue may be concise, but it still
needs a goal, non-goals, acceptance criteria, verification, and dependency state.

Set `Agent-ready = yes` only when the goal is explicit, acceptance criteria are
checkable, required docs are listed, blockers are absent or closed, risk is
classified, and verification is known or explicitly not applicable.

If a required section is missing, update the issue from available evidence. Ask
the user only when the missing information changes scope or risk and cannot be
inferred safely.

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
| `Blocked` | Work cannot continue until linked blockers are resolved or missing information is provided. |
| `In review` | A PR or equivalent review artifact is open. |
| `Done` | Acceptance criteria are satisfied and the issue is closed or ready to close. |

If an agent cannot update Project fields because the available tool does not
support Projects, it must leave an issue comment like this:

```markdown
Project update unavailable to this agent.
Intended fields: Status=In progress, Work type=docs, Area=agent, Risk=low,
Needs docs=yes, Needs decision record=no, Agent-ready=yes.
```

Do not claim Project state was updated unless it was actually updated.

## Agent Workflow

### 1. Load Context

For non-trivial work, read:

1. `AGENTS.md`
2. `ARCHITECTURE.md`
3. `docs/SUBAGENTS.md`
4. this document
5. the current issue
6. only task-specific docs linked by the issue or docs router

Do not read all open issues, all closed issues, or the whole Project board just
to begin a task.

### 2. Select Or Create The Issue

Use a linked issue when the user provides one. Otherwise search for an existing
open issue with the same goal. Create a new issue only when no existing issue is
a correct task boundary.

An agent-created issue must include the user request summary, inferred scope,
non-goals, acceptance criteria, verification, known blockers, and authoritative
docs to read.

### 3. Normalize Before Editing

Before editing files:

- fill missing issue body sections;
- add or record intended Project fields;
- link blockers or record `none known`;
- create sub-issues if the work is too large for one reviewable PR;
- set `Status = In progress` when starting immediately.

### 4. Start Work

When possible, create a branch named with the issue number:

```text
<work-type>/<issue-number>-<short-slug>
```

Examples:

```text
docs/28-work-tracking-protocol
fix/31-apply-plan-status
```

Leave a short start comment for non-trivial work:

```markdown
### Agent start
- Branch: `docs/28-work-tracking-protocol`
- Scope: ...
- Docs read: ...
- Intended verification: ...
- Project update: Status=In progress
```

### 5. Update During Work

Keep updates sparse. Comment when status changes, a blocker appears or clears,
scope changes, acceptance criteria change, verification fails in a way the next
agent must know, work is handed off, or a PR is opened.

Do not comment for every command, minor edit, or local observation. If detailed
command output matters, summarize it in the PR.

If scope expands, update the issue before implementing the expanded scope. If the
scope becomes too large, split it into sub-issues.

### 6. Handle Blockers

When blocked:

1. Set `Status = Blocked` when possible.
2. Add an issue dependency when possible.
3. Comment with the minimum unblock condition.
4. Stop implementation unless independent unblocked work remains.

Blocked comment format:

```markdown
### Blocked
- Blocked by: #...
- Minimum unblock condition: ...
- Safe remaining work: none / ...
- Project update: Status=Blocked
```

### 7. Open A Pull Request

Open a PR for code, test, configuration, or durable documentation changes unless
the repository owner explicitly requests direct commits.

The PR body must include:

- linked issue;
- summary of changes;
- non-goals or deferred work;
- verification run and result;
- docs impact;
- risk notes;
- closure intent.

Use `Closes #...`, `Fixes #...`, or `Resolves #...` only when the PR fully
satisfies the issue. Use `Refs #...`, `Partially addresses #...`, or manual
linkage when the issue should remain open.

Set `Status = In review` when a PR is open.

### 8. Complete Or Continue

An issue may move to `Done` and close only when:

- all acceptance criteria are satisfied or explicitly revised with rationale;
- verification passed, or the reason it was not run is recorded;
- required docs and decision records are updated;
- no remaining blocker affects the stated goal;
- the PR is merged or the issue contains a final no-PR resolution comment.

For partial completion, leave the issue open, check off completed acceptance
criteria, rewrite remaining criteria, keep or reset `Status`, and do not use PR
closing keywords.

### 9. Handoff

A handoff is required when an agent stops with unmerged work, unresolved
verification, or remaining scope.

Handoff comment format:

```markdown
### Handoff
- Current branch / PR: ...
- Completed: ...
- Not completed: ...
- Verification run: ...
- Verification not run: ...
- Known blockers: ...
- Next safe action: ...
```

The next agent should be able to resume from the issue, linked PR, and linked
docs without reconstructing context from chat.

## Sub-Issues And Parent Issues

Use a parent issue for a goal that needs coordination across multiple reviewable
changes. Use sub-issues for independently reviewable slices.

Parent issue:

- contains the overall goal, non-goals, invariants, and done definition;
- does not track line-by-line implementation progress;
- stays open until required sub-issues are complete or intentionally removed.

Sub-issue:

- has its own acceptance criteria and verification;
- can be implemented and reviewed independently;
- links back to the parent through GitHub sub-issue relationships when possible;
- does not duplicate the full parent context.

## Milestones And Labels

Use Milestones only for real phases, releases, or externally meaningful batches.
An issue may have no Milestone.

Labels are secondary discovery aids. They must not be the only place where task
state, blockers, or acceptance criteria exist. Do not create labels that
duplicate Project `Status`.

## Repository Documentation Boundary

Allowed repository documentation changes:

- durable product behavior;
- architecture rules;
- contracts and schemas;
- command semantics;
- testing policy;
- process rules such as this document;
- decision records under `docs/decisions/`.

Forbidden repository documentation changes:

- `docs/progress.md`;
- `docs/implementation-progress.md`;
- `docs/progress/`;
- per-issue running logs;
- status tables that duplicate GitHub Projects;
- stale checklists copied from issues.

If a progress fact matters only until the issue or PR is complete, put it in
GitHub, not in repository docs.

## Subagent Tracking

The main agent owns GitHub state.

When using subagents, the main agent must pass the current issue boundary,
re-read cited files or evidence before accepting findings, record only material
findings in the issue or PR, and update blockers, acceptance criteria, or PR
notes when subagent findings change the work state.

## Capability Fallbacks

Agents may not always have the same GitHub permissions or tool support.

| Preferred operation | Fallback |
| --- | --- |
| Update Project field | Issue comment with intended field update. |
| Add issue dependency | Issue comment naming `Blocked by` or `Blocking`. |
| Create sub-issue | New issue linked from parent and child bodies/comments. |
| Open PR | Branch or commit reference plus issue handoff comment. |
| Run verification | Record exact command not run and reason. |

Fallbacks must be explicit. Silent failure to update tracking state is not
allowed.

## Prohibited Agent Behavior

Agents must not:

- implement from a Project draft item without converting or replacing it with an
  Issue;
- treat chat-only context as the lasting task boundary after changing repository
  files;
- close an issue from a PR that only partially resolves it;
- expand scope without updating the issue first;
- mark work done without verification evidence or an explicit reason verification
  was not run;
- create repository-local progress ledgers;
- rely on labels when required issue body or Project fields are missing;
- read broad unrelated GitHub history to compensate for an underspecified issue.

## Minimal Checklists

Before editing:

- [ ] Issue selected or created.
- [ ] Goal and non-goals are clear.
- [ ] Acceptance criteria are checkable.
- [ ] Required docs are listed.
- [ ] Blockers are linked or recorded as none.
- [ ] Project fields are updated or fallback comment is posted.

Before opening PR:

- [ ] Issue is linked.
- [ ] Scope matches issue.
- [ ] Verification is run or not-run reason is recorded.
- [ ] Docs impact is stated.
- [ ] Closure intent is correct.

Before closing issue:

- [ ] All acceptance criteria are satisfied or explicitly revised.
- [ ] Required verification is recorded.
- [ ] Required docs or decision records are complete.
- [ ] Remaining work is none, or issue remains open.
