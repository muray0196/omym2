---
tracker:
  kind: linear
  api_key: $LINEAR_API_KEY
  project_slug: "omym2-0e0966d2478c"
  required_labels:
    - symphony
  active_states:
    - Todo
    - In Progress
  terminal_states:
    - Done
    - Canceled
    - Duplicate
polling:
  interval_ms: 30000
workspace:
  root: ~/code/omym2-symphony-workspaces
hooks:
  after_create: |
    git clone --branch develop git@github.com:muray0196/omym2.git .
    git config rerere.enabled true
    git config rerere.autoupdate true
    uv sync
    if [ -f web/package-lock.json ]; then
      cd web && npm ci
    fi
agent:
  max_concurrent_agents: 3
  max_turns: 20
codex:
  command: codex --config shell_environment_policy.inherit=all app-server
  approval_policy: never
  thread_sandbox: workspace-write
  turn_sandbox_policy:
    type: workspaceWrite
    networkAccess: true
---

You are working on Linear ticket `{{ issue.identifier }}` for OMYM2.

Issue context:
Identifier: {{ issue.identifier }}
Title: {{ issue.title }}
Current status: {{ issue.state }}
Labels: {{ issue.labels }}
URL: {{ issue.url }}

Description:
{% if issue.description %}
{{ issue.description }}
{% else %}
No description provided.
{% endif %}

## Operating contract

- This is an unattended Symphony session. Do not ask a human to do follow-up work unless a required external secret, permission, or service is missing.
- Work only inside the provided workspace clone.
- Read and follow `AGENTS.md` before task work. It owns OMYM2 repo rules, required reading, documentation routing, and work-tracking policy.
- Use exactly one persistent Linear comment headed `## Codex Workpad` for progress, plans, validation, blockers, and handoff notes.
- Do not create separate status-summary comments.
- Stop only when the ticket reaches `In Review`, a terminal state, or a true blocker is recorded in the workpad.

## Linear status map

- `Backlog`: out of scope. Do not modify the issue.
- `Todo`: transition to `In Progress`, create or refresh the workpad, then execute.
- `In Progress`: continue execution from the current workpad state.
- `In Review`: human review is pending. Do not code or modify ticket content.
- `Done`, `Canceled`, `Duplicate`: terminal. Do nothing.

Only issues in the OMYM2 project with the Linear label `symphony` are eligible for dispatch.

## Kickoff flow

1. Fetch the current issue from Linear by identifier.
2. Confirm the status and route through the status map above.
3. Find or create one active comment headed `## Codex Workpad`.
4. Reconcile the workpad before editing: check off completed items, remove stale assumptions, and add acceptance criteria from the issue body.
5. Record an environment stamp in the workpad:

```text
<hostname>:<abs-workdir>@<short-sha>
```

6. Reproduce or confirm the current behavior before changing code. Record the concrete signal in the workpad.
7. Sync with `origin/develop` before edits.
8. If no feature branch exists for this workspace, create one from `origin/develop` using a ticket-based name such as `symphony/HOW-123-short-topic`.

## Execution flow

- Keep the workpad checklist current after each meaningful milestone.
- If an out-of-scope improvement is discovered, create a separate Backlog issue in the same project instead of expanding scope.
- Use GitHub CLI or available GitHub tools to create or update one PR against `develop`.
- Apply the GitHub PR label `symphony`.
- Link the PR to the Linear issue using a Linear attachment/link when possible.
- Before moving to `In Review`, inspect all PR comments, inline review comments, review states, and check runs. Address actionable feedback or document a justified pushback in the relevant thread.
- Move the Linear issue to `In Review` only after validation is green, PR feedback is clear, and the workpad accurately reflects completed work.

## Validation

Run ticket-provided validation first when present. Otherwise use the scoped and final gates routed from `AGENTS.md` and `docs/development.md`.

Record every validation command and result in the workpad. If a required gate cannot run because of missing external tooling or auth, record the blocker and exact unblock action.

## Blocker policy

A true blocker is limited to missing required auth, permissions, secrets, or services that cannot be resolved in-session.

If blocked:

- Keep or move the issue to `In Review`.
- Update the `## Codex Workpad` with what is missing, why it blocks completion, and the exact human action needed.
- Do not add a separate blocker comment.

## Workpad template

Use this structure and update it in place:

````md
## Codex Workpad

```text
<hostname>:<abs-workdir>@<short-sha>
```

### Plan

- [ ] 1. Parent task
  - [ ] 1.1 Child task

### Acceptance Criteria

- [ ] Criterion

### Validation

- [ ] `<command>`

### Notes

- <short timestamped note>

### Confusions

- <only include when something was unclear>
````
