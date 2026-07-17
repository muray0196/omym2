---
name: linear-create-issue
description: Create Linear issues from user requests without starting local execution. Use when asked to create, file, open, or draft a Linear issue, ticket, or backlog item; do not use for executing an existing Linear ticket.
---

# Linear Create Issue

## Local boundary

Issue creation authorizes the Linear mutation and read-only context gathering only. Do not edit the worktree, install dependencies, run implementation checks, create branches or commits, change the issue to an active execution status, or create a workpad unless the user explicitly requests local execution.

## Issue Content

Preserve precise user constraints such as "minimal", "docs-only", "no compatibility work", and "no extra features".

Prefer this compact structure:

```markdown
## Goal
...

## Scope
- ...

## Plan
1. ...

## Acceptance Criteria
- ...

## Validation
- ...
```

Omit sections that would be empty. Keep the issue specific enough that a later agent can execute it without relying on the chat transcript.

## Linear Handling

Use the available Linear tools or app. Search for near-duplicates before creating an issue. If Linear is unavailable, report the blocker; do not create a local substitute.

Create or update the issue using the compact structure above, including links or attached-context references when useful.
