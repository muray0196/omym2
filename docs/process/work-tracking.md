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
| Durable technical decisions | [../decisions/](../decisions/) |
| Active specifications | [../../ARCHITECTURE.md](../../ARCHITECTURE.md) and task-relevant docs under [../](../) |

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

## Workflow

GitHub Project drafts are inbox ideas only. They can hold rough future work, but
they are not active work items and agents should not implement from them.

Before work moves to `Ready`:

* Convert or create a GitHub Issue.
* Fill the relevant issue template.
* Set required Project fields.
* Link direct blockers or blocked work.
* Assign a Milestone only for a real phase or release grouping.

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

1. [../../AGENTS.md](../../AGENTS.md)
2. [../index.md](../index.md)
3. the current GitHub Issue
4. directly linked authoritative docs
5. directly blocking or blocked-by issues
6. directly related PRs if the current issue references them

## Closing Rule

A PR should close the issue using GitHub linking keywords only when the issue is fully resolved.

If the PR partially resolves the issue, update the issue with remaining work instead of closing it.

## Repository Docs Boundary

Do not add Markdown progress ledgers such as `docs/implementation-progress.md` or `docs/progress/`.

Use repository docs for stable specifications, process schemas, and decision records. Use GitHub Issues, Projects, and Milestones for current status, backlog, assignment, blockers, and partial completion state.
