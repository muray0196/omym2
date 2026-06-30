---
name: linear-create-issue
description: Create Linear issues from user requests without starting local execution. Use when asked to create, file, open, or draft a Linear issue, ticket, or backlog item; do not use for executing an existing Linear ticket.
---

# Linear Create Issue

## Overview

Create a clear Linear issue and stop after reporting it. Treat issue creation as a handoff, not permission to edit local files, install dependencies, run implementation checks, create branches, or start the ticket execution workflow.

## Workflow

1. Read only the context needed to make the issue accurate.
2. Use Linear to find the relevant team, project, labels, statuses, and potential duplicates.
3. Create or update the Linear issue with:
   - concise title
   - scope and non-goals
   - implementation plan
   - acceptance criteria
   - validation expectations
   - links or attached-context references when useful
4. Report the issue identifier and URL.
5. Stop unless the user explicitly asks to execute the work locally.

## Local Boundary

Do not make local code or documentation changes for the issue being created. Do not scaffold implementation, add dependencies, run formatters, run tests, create commits, push branches, or create workpad comments.

Allowed local actions are read-only context gathering, such as reading user-attached files, relevant repo docs, existing issue references, or lightweight repository searches. If a command would change the worktree, dependency state, generated files, branches, or external ticket status beyond issue creation, do not run it.

Do not move the new issue to an active execution status unless the user explicitly asks to start work. Do not create a `## Codex Workpad` comment for a newly created issue unless entering an explicit ticket execution workflow.

If the same user request asks both to create the issue and execute the work locally, create the issue first, report it, then continue only because local execution was explicit.

## Issue Content

Use the user's language for scope boundaries when it is precise. Preserve "minimal", "docs-only", "no compatibility work", "no extra features", and similar constraints in the issue body.

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

Use the available Linear tools or app. If Linear tools are unavailable, state the blocker and ask the user to connect Linear; do not substitute local TODO files.

Search for near-duplicate issues before creating a new one when the title or topic is specific enough. If a matching issue already exists, update or report it instead of creating a duplicate.
