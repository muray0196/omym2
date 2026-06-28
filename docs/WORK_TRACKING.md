# Work Tracking

This document defines how OMYM2 development work is tracked.

It is not a progress ledger. Active progress lives in GitHub Issues, GitHub Projects, and GitHub Milestones.

Repository documentation stores durable specifications and process schemas only.

## Source Of Truth

| Concern | Source |
| --- | --- |
| Active work item | GitHub Issue |
| Idea inbox | GitHub Project draft item |
| Work breakdown | GitHub sub-issues |
| Blockers | GitHub issue dependencies |
| Planning metadata | GitHub Project fields |
| Phase or release grouping | GitHub Milestones |
| Durable technical decisions | [decisions/](decisions/) |
| Active specifications | [../ARCHITECTURE.md](../ARCHITECTURE.md) and task-relevant docs under this directory |

## Work Types

Use these `Work type` values in issue templates and the GitHub Project field:

* feature
* bug
* refactor
* test
* docs
* architecture
* storage
* execution
* agent

OMYM2 does not require GitHub native issue types. The issue form body and
Project fields are the tracking contract.

## Operational Flow

Use this flow whenever work is driven through GitHub Projects.

Default agent-driven work starts by creating or selecting a GitHub Issue. If the
user asks for implementation, review, or documentation work without linking an
issue, the agent creates the issue first and then works from that issue.

### 1. Capture Ideas

Capture uncertain or future work as a GitHub Project draft item with `Status = Backlog`.

Drafts are inbox items only. They can hold rough future work, but they are not
active work items and agents must not implement from them.

If the user request is only an idea and does not contain a concrete goal, the
agent may create a draft item and stop. Do not implement from a draft.

### 2. Prepare Ready Work

Before work moves to `Ready`:

* Convert the draft to a GitHub Issue or create a new GitHub Issue.
* Fill the relevant issue template.
* Add the issue to the GitHub Project and set all required Project fields.
* Link direct blockers or blocked work.
* Create sub-issues when the work is too large for one reviewable PR.
* Assign a Milestone only for a real phase or release grouping.

Set `Agent-ready = yes` only after the issue has enough context for an agent to
start without reading the whole project board or unrelated issues. Set
`Status = Ready` only when direct blockers are closed or none exist.

If direct blockers remain open, keep `Agent-ready = no`, set `Status = Blocked`,
and link the blocking issue.

### 3. Create Agent-Started Work

When an agent receives a concrete request without an existing issue:

* Create a GitHub Issue before editing code or durable docs.
* Choose the issue template that matches the work type.
* Fill the issue from the user request, `AGENTS.md`, and task-specific docs.
* State inferred scope explicitly in the issue body.
* Add the issue to the GitHub Project and set all required Project fields.
* Set `Agent-ready = yes` only if the issue is complete enough to execute.
* Set `Status = In progress` when the agent will start immediately.
* Link blockers or create blocker issues before implementation if the work
  cannot proceed independently.

For small direct requests, the issue may be concise, but it still must include
the goal, non-goals, authoritative docs, acceptance criteria, verification, and
blocking or blocked-by issues.

### 4. Start Agent Work

An agent may start only from a GitHub Issue with `Agent-ready = yes` and no
open blockers.

At start:

* Move `Status` to `In progress`.
* Read only the context listed in [Agent Context Budget](#agent-context-budget).
* Treat the issue body as the task boundary.
* Use sub-issues only for the current issue's direct breakdown.

If required context is missing, update the issue or ask for clarification before
implementation. Do not infer scope from Project draft text.

### 5. Implement

During implementation:

* Work against the issue goal, non-goals, invariants, acceptance criteria, and
  verification commands.
* Keep status and scope discussion on the GitHub Issue or PR, not in repository
  docs.
* If scope changes, update the issue before expanding the implementation.
* If the task becomes blocked, move `Status` to `Blocked`, link the blocker, and
  comment with the minimum unblock condition.

### 6. Open Review

When a branch is ready for review:

* Open a PR linked to the issue.
* Fill the PR template with scope, verification, docs impact, and closure
  intent.
* Move `Status` to `In review`.
* Use `Closes #` only when the PR fully resolves the issue.
* Use `Partially addresses #` when remaining work should stay on the issue.

### 7. Complete Or Continue

After review and merge:

* Move `Status` to `Done` only when the issue is fully resolved.
* Close the issue only when the PR or final issue comment records full
  resolution.
* For partial work, leave the issue open, update the remaining acceptance
  criteria, and keep or reset the Project status to match the next action.

Work becomes active only after a GitHub Issue exists. Use sub-issues for
breakdown and issue dependencies for blockers.

## Implementation Issue Body

Every implementation issue should include:

* Goal
* Non-goals
* Authoritative docs to read
* Affected areas
* Expected code paths
* Expected test paths
* Invariants that must not be violated
* Acceptance criteria
* Verification commands
* Documentation updates required
* Blocking / blocked-by issues

## Project Fields

Required Project fields:

| Field | Values |
| --- | --- |
| Status | Backlog, Ready, In progress, Blocked, In review, Done |
| Work type | feature, bug, refactor, test, docs, architecture, storage, execution, agent |
| Area | architecture, product, domain, execution, storage, config, db, cli, web, testing, docs, agent |
| Risk | low, medium, high |
| Needs docs | yes, no |
| Needs ADR | yes, no |
| Agent-ready | yes, no |

`Backlog` may include draft ideas or issues. `Ready`, `In progress`,
`Blocked`, `In review`, and `Done` are issue-only states.

## Agent Context Budget

Agents must not read the whole project board, all historical issues, or all closed issues.

For a task, an agent should read only:

1. [../AGENTS.md](../AGENTS.md)
2. the current GitHub Issue
3. directly linked authoritative docs
4. directly blocking or blocked-by issues
5. directly related PRs if the current issue references them

## Closing Rule

A PR should close the issue using GitHub linking keywords only when the issue is fully resolved.

If the PR partially resolves the issue, update the issue with remaining work instead of closing it.

## Repository Docs Boundary

Do not add Markdown progress ledgers such as `docs/implementation-progress.md` or `docs/progress/`.

Use repository docs for stable specifications, process schemas, and decision records. Use GitHub Issues, Projects, and Milestones for current status, backlog, assignment, blockers, and partial completion state.
