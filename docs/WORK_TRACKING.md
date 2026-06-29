# Work Tracking

This document defines the GitHub state agents must maintain for OMYM2 work.

## Musts

1. Start durable repository changes from a GitHub Issue.
2. Treat the Issue as the executable task boundary.
3. Use the Project for queue state and planning metadata.
4. Use the PR for review, verification, and change history.
5. Use Milestones only for real phases or releases.
6. Keep active progress out of repository Markdown.
7. Leave enough GitHub state for the next agent to resume.
8. If a GitHub feature is unavailable, comment with the intended update.

## State Homes

| State | Home |
| --- | --- |
| Task boundary | Issue body |
| Queue/status | Project fields |
| Live progress | Issue or PR comments |
| Work breakdown | Sub-issues |
| Blockers | Issue dependencies or `Blocked by #...` comments |
| Review/change record | PR |
| Phase/release group | Milestone |
| Durable rationale | `docs/decisions/` |
| Durable specs/process | `ARCHITECTURE.md`, `AGENTS.md`, `docs/` |
| Local progress ledger | Nowhere |

## Issue Rules

Create or select an Issue before changing repository files, GitHub metadata, or
durable docs/process. No Issue is needed for answer-only chat, read-only
explanation, or inspection that produces no durable change.

Before creating an Issue, search open Issues and PRs. Reuse a suitable Issue;
otherwise create one from the user request.

Set `Agent-ready = yes` only when goal, acceptance criteria, docs, verification,
risk, and blockers are clear.

Required Issue sections: `Goal`, `Non-goals`, `Context`, `Authoritative docs to
read`, `Affected areas`, `Invariants and constraints`, `Acceptance criteria`,
`Verification`, `Dependencies`, `Notes for agents`.

Small docs/test tasks may be concise, but must still state goal, non-goals,
acceptance criteria, verification, and dependency state.

## Project Fields

Use only these behavior-changing fields:

| Field | Values |
| --- | --- |
| `Status` | `Backlog`, `Ready`, `In progress`, `Blocked`, `In review`, `Done` |
| `Work type` | `feature`, `bug`, `refactor`, `test`, `docs`, `architecture`, `investigation`, `chore` |
| `Area` | `product`, `architecture`, `domain`, `execution`, `storage`, `config`, `db`, `cli`, `web`, `testing`, `docs`, `agent`, `repo` |
| `Risk` | `low`, `medium`, `high` |
| `Needs docs` | `yes`, `no` |
| `Needs decision record` | `yes`, `no` |
| `Agent-ready` | `yes`, `no` |

`Status` meanings:

| Status | Meaning |
| --- | --- |
| `Backlog` | Captured but not ready, not prioritized, or underspecified. |
| `Ready` | Ready and unblocked. |
| `In progress` | Work has started. |
| `Blocked` | Work cannot continue. |
| `In review` | PR or equivalent review artifact is open. |
| `Done` | Acceptance criteria are satisfied and closure is valid. |

Do not claim Project fields changed unless they changed. If unavailable,
comment with intended fields.

## Agent Rules

Before editing: select/create the Issue, fill missing required sections, update
or comment intended Project fields, record blockers, split oversized work, set
`Status = In progress` when starting, branch as
`<work-type>/<issue-number>-<short-slug>` when possible, and leave a start
comment for non-trivial work.

During work, comment only for status changes, blockers, scope or acceptance
criteria changes, material verification failures, handoff, or PR creation.
Update the Issue before expanding scope.

When blocked, set `Status = Blocked` when possible, add a dependency when
possible, comment with the minimum unblock condition, and stop unless
independent unblocked work remains.

Open a PR for code, test, configuration, or durable documentation changes unless
the repository owner requests direct commits. Include linked Issue, summary,
non-goals/deferred work, verification, docs impact, risk, and closure intent.
Use closing keywords only for full completion.

Move to `Done` only when acceptance criteria are satisfied or revised,
verification passed or the exception is recorded, required docs and decisions
are complete, blockers are gone, and the PR is merged or final no-PR resolution
is recorded.

For partial completion, keep the Issue open, update remaining criteria, and do
not use closing keywords.

Handoff is required when stopping with unmerged work, unresolved verification,
or remaining scope. State branch/PR, completed work, incomplete work,
verification, blockers, and next safe action.

Use parent Issues for coordinated goals and sub-issues for independently
reviewable slices.

Use labels only for discovery. Do not use labels as task state, blockers, or
acceptance criteria, and do not create labels that duplicate Project `Status`.

## Fallbacks

| Preferred operation | Fallback |
| --- | --- |
| Update Project field | Issue comment with intended field update |
| Add Issue dependency | Issue comment naming `Blocked by` or `Blocking` |
| Create sub-issue | New Issue linked from parent and child comments |
| Open PR | Branch or commit reference plus Issue handoff comment |
| Run verification | Exact command not run and reason |

## Prohibited

- Implementing from Project drafts.
- Treating chat as the durable task boundary.
- Closing Issues from partial PRs.
- Expanding scope before updating the Issue.
- Marking work done without verification evidence or a not-run reason.
- Creating repository-local progress ledgers.
- Relying on labels for required state.
- Reading broad unrelated GitHub history to compensate for an underspecified
  Issue.
