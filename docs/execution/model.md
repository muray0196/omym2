---
type: Execution Spec
title: Execution Model
description: Defines Plan-centered audio, companion, and unprocessed-file execution, durable dependencies and FileEvents, shared exclusion, single-use Plans, and blocked-versus-failed behavior.
tags: [execution-model, operation, plan, run, file-event, companions, unprocessed, exclusion]
timestamp: 2026-07-16T22:15:00+09:00
---

# Execution Model

This document is authoritative for the common Plan-centered execution model,
Operation / Plan / PlanAction / Run / FileEvent responsibilities, shared
exclusive-operation boundary, single-use Plan policy, blocked-vs-failed
distinction, and FileEvent creation scope.

Task-specific behavior is in [add.md](add.md), [apply.md](apply.md), [organize.md](organize.md), [refresh.md](refresh.md), [undo.md](undo.md), [check.md](check.md), and [failure-policy.md](failure-policy.md).

## Plan-Centered Execution

Audio, companion, and unprocessed-file mutations are not executed directly.

Read-only scans, metadata reads, hash calculations, inspections, and DB-only Library state updates do not require a Plan.

Reviewed file mutations must follow this flow:

```text
scan
  ↓
create plan
  ↓
review
  ↓
start run
  ↓
for each plan action:
    require every recorded dependency
    verify preconditions
    record FileEvent as pending
    execute recorded file mutation
    update FileEvent
    update PlanAction and, when applicable, Track or CompanionAsset
  ↓
finish run
```

Plan actions that do not mutate files, such as `skip` and
`refresh_metadata`, follow the same Plan and Run flow but omit the FileEvent
steps. `move_lyrics` and `move_artwork` are ordinary reviewed file
mutations and therefore retain the pending-before-mutation guarantee.
`move_unprocessed` is likewise a reviewed mutation, but it is trackless,
content-only, dependency-free, and leaves no managed-state row.

Companion `owner_action_id` records semantic ownership; durable dependency
edges record execution order. Apply never derives either from `sort_order`.
Every dependency must be an applied same-Plan action before the dependent
action is observed or mutated.

This allows the CLI, Web UI, and tests to share the same processing model.

## Durable Background Operations

Add, Organize, Refresh, Check, Apply, and Undo Plan generation are represented
by durable Operations when executed as long-running state-changing work. The
Web dispatches accepted work after returning `202`; the CLI may run the worker
inline, but it persists the same Operation lifecycle and holds the same lock.

An Operation records request acceptance, idempotency, lifecycle status, terminal
result, and interruption. It is not evidence that a particular
Library-managed file mutation happened. FileEvents remain the only mutation
log and preserve
their pending-before-mutation ordering.

Operation lifecycle, retention, and restart reconciliation are authoritative in
[../contracts/operations.md](../contracts/operations.md).

## Shared Exclusive Operation

Web and CLI use one application-root cross-process lock for every state-changing
operation, including Config writes, Plan generation, Check, Apply, ready-Plan
Cancel, Undo Plan generation, and Operation cleanup/reconciliation. Read-only
snapshot requests remain available while the lock is held.

A conflicting state-changing request fails immediately rather than queueing.
The lock is held for the full worker lifetime, not merely while accepting an
HTTP request or opening a transaction. Its mechanism and conflict matrix are
recorded in
[../decisions/0003-cross-process-exclusive-operation-lock.md](../decisions/0003-cross-process-exclusive-operation-lock.md).

User-facing commands should be purpose-based. Internal Plan concepts should not dominate primary command names.

```text
user command             internal behavior
------------             -----------------
settings                 read / write settings
organize --library PATH  register, reconcile, or organize a Library
organize                 organize the only unambiguous known Library
add                      create add plan for the only registered Library
refresh                  create metadata refresh / relocate plan
apply                    apply selected plan
check                    compare DB, filesystem, and Library state
```

## Bootstrap Behavior

OMYM2 has no mandatory first-use initialization command.

Config files, DB files, and internal directories are created lazily when a command needs them.

Missing config or DB is not an error by itself. Missing required paths are errors only for commands that need those paths.

Path rules:

* Commands must not guess the Library path or Library identity.
* Commands that need a Library fail if no Library can be selected unambiguously.
* `add` without a configured Incoming path fails unless a source directory is explicitly supplied.

## Run Behavior

A Run is an execution attempt for applying a Plan.

A Run is created before processing PlanActions and before any Library-managed file mutation. It may succeed, fail, or partially fail.

A Run is the parent unit for FileEvents and the main unit used by history and undo.

A Run becomes `partial_failed` when at least one eligible audio move,
companion move, unprocessed move, or `refresh_metadata` action succeeds and at least one
eligible action fails.
`refresh_metadata` counts even though it creates no FileEvent and does not
mutate a file. Blocked and `skip` actions do not count. If no
eligible action succeeds, an eligible-action failure makes the Run `failed`.

## FileEvent Behavior

A FileEvent is a durable mutation-log entry for one reviewed audio, companion,
or unprocessed-file mutation.

A FileEvent is created as `pending` before the file mutation.
After the process observes the mutation result, it is updated to `succeeded` or
`failed`; a crash or otherwise unobserved result remains `pending`.

FileEvents represent file mutations only. DB-only state changes such as
registering a canonical Track or CompanionAsset are not FileEvents. Applying a
`refresh_metadata` action updates the Track in place without moving files, so
it becomes `applied` without a FileEvent. Companion events retain their
stable asset ID and distinct lyrics/artwork event type.
Unprocessed events use their distinct type and absolute retained-root paths,
with null managed identity.

FileEvents are used for:

* run detail display
* diagnosing partial failures
* crash inspection
* undo plan creation

## Single-Use Plan Policy

A Plan is single-use in the initial version. Once apply starts, the same Plan must not be applied again.

Apply starts only through an atomic claim that transitions the ready Plan,
creates its running Run, and reserves its queued Operation in one transaction
while the shared lock is held. Worker dispatch occurs only after that commit.

If recovery or retry is needed, the user creates a new Plan from the current DB and filesystem state.

## Blocked Vs Failed

Issues detected during plan creation are represented as `blocked`.

Precondition failures detected during apply are represented as `failed`.

Action types and allowed status / reason values are cataloged in [../contracts/status-reason-catalog.md](../contracts/status-reason-catalog.md).

## Durable File-Mutation Log

Library-managed file operations and DB transactions cannot be made fully atomic. Therefore, apply does not rely on one large transaction that covers the whole run.

FileEvents are the durable reviewed file-mutation log. Each mutation
records a FileEvent as `pending` before executing the mutation and updates it
only after the process observes success or a definite failure.

If the process crashes or cannot observe the result, the FileEvent remains
`pending`; it is not rewritten to `failed` merely to make the Run terminal.
Restart reconciliation marks the durable Operation `interrupted` and makes its
Plan/Run terminal from confirmed evidence only. `check` reports pending events
and requires manual review rather than automatically repairing the filesystem.
