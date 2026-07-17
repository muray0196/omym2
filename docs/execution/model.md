---
type: Execution Spec
title: Execution Model
description: "Common Plan/Run/FileEvent model: shared exclusive lock, single-use Plans, blocked-vs-failed, durable mutation log."
tags: [execution-model, operation, plan, run, file-event, companions, unprocessed, exclusion]
timestamp: 2026-07-18T12:00:00+09:00
---

# Execution Model

Authoritative for the common Plan-centered execution model: Operation / Plan /
PlanAction / Run / FileEvent responsibilities, shared exclusive-operation
boundary, single-use Plan policy, blocked-vs-failed, and FileEvent creation
scope. Task-specific behavior: [add.md](add.md), [apply.md](apply.md),
[organize.md](organize.md), [refresh.md](refresh.md), [undo.md](undo.md),
[check.md](check.md), [failure-policy.md](failure-policy.md).

## Plan-Centered Execution

Audio, companion, and unprocessed-file mutations are never executed directly.
Read-only scans, metadata reads, hash calculations, inspections, and DB-only
Library state updates need no Plan.

Reviewed file mutations follow:

```text
scan → create plan → review → start run
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

* Non-mutating action types (`skip`, `refresh_metadata`) follow the same
  Plan/Run flow but omit the FileEvent steps.
* `move_lyrics` and `move_artwork` are ordinary reviewed file mutations and
  retain the pending-before-mutation guarantee.
* `move_unprocessed` is a reviewed mutation that is trackless, content-only,
  dependency-free, and leaves no managed-state row.
* Companion `owner_action_id` records semantic ownership; durable dependency
  edges record execution order. Apply never derives either from `sort_order`.
  Every dependency must be an applied same-Plan action before the dependent
  action is observed or mutated.

## Durable Background Operations

Add, Organize, Refresh, Check, Apply, and Undo Plan generation are durable
Operations when executed as long-running state-changing work. The Web
dispatches accepted work after returning `202`; the CLI may run the worker
inline but persists the same Operation lifecycle and holds the same lock.

An Operation records request acceptance, idempotency, lifecycle status,
terminal result, and interruption. It is never evidence that a file mutation
happened; FileEvents remain the only mutation log with their
pending-before-mutation ordering. Lifecycle, retention, and restart
reconciliation: [../contracts/operations.md](../contracts/operations.md).

## Shared Exclusive Operation

Web and CLI share one application-root cross-process lock for every
state-changing operation, including Config writes, Plan generation, Check,
Apply, ready-Plan Cancel, Undo Plan generation, and Operation
cleanup/reconciliation. Read-only snapshot requests remain available while the
lock is held.

A conflicting state-changing request fails immediately rather than queueing.
The lock is held for the full worker lifetime, not merely while accepting an
HTTP request or opening a transaction. Mechanism and conflict matrix:
[../decisions/0003-cross-process-exclusive-operation-lock.md](../decisions/0003-cross-process-exclusive-operation-lock.md).

User-facing commands are purpose-based; internal Plan concepts must not
dominate primary command names. Command syntax and the command list:
[../COMMANDS.md](../COMMANDS.md).

## Bootstrap Behavior

There is no mandatory first-use initialization command. Config files, DB
files, and internal directories are created lazily when a command needs them.
Missing config or DB is not an error by itself; missing required paths are
errors only for commands that need those paths.

Path rules:

* Commands must not guess the Library path or Library identity.
* Commands that need a Library fail if none can be selected unambiguously.
* `add` without a configured Incoming path fails unless a source directory is
  explicitly supplied.

## Run Behavior

A Run is one execution attempt for applying a Plan. It is created before
PlanAction processing and before any Library-managed file mutation, and is the
parent unit for FileEvents and the main unit for history and undo.

A Run becomes `partial_failed` when at least one eligible audio move, companion
move, unprocessed move, or `refresh_metadata` action succeeds and at least one
eligible action fails. `refresh_metadata` counts even though it creates no
FileEvent and mutates no file. Blocked and `skip` actions do not count. If no
eligible action succeeds, an eligible-action failure makes the Run `failed`.

## FileEvent Behavior

A FileEvent is a durable mutation-log entry for one reviewed audio, companion,
or unprocessed-file mutation. It is created `pending` before the mutation and
updated to `succeeded` or `failed` only after the process observes the result;
a crash or unobserved result leaves it `pending`.

FileEvents represent file mutations only. DB-only state changes — registering
a canonical Track or CompanionAsset, applying `refresh_metadata` — create no
FileEvent. Companion events retain their stable asset ID and distinct
lyrics/artwork event type. Unprocessed events use their distinct type and
absolute retained-root paths with null managed identity.

FileEvents serve run detail display, partial-failure diagnosis, crash
inspection, and undo plan creation.

## Single-Use Plan Policy

A Plan is single-use. Once apply starts, the same Plan must not be applied
again. Apply starts only through an atomic claim that transitions the ready
Plan, creates its running Run, and reserves its queued Operation in one
transaction while the shared lock is held; worker dispatch occurs only after
that commit. Recovery or retry requires a new Plan from current DB and
filesystem state.

## Blocked Vs Failed

Issues detected during plan creation are `blocked`. Precondition failures
detected during apply are `failed`. Action types and allowed status/reason
values: [../contracts/status-reason-catalog.md](../contracts/status-reason-catalog.md).

## Durable File-Mutation Log

Library-managed file operations and DB transactions cannot be made atomic
together, so apply never relies on one whole-run transaction. FileEvents are
the durable reviewed file-mutation log: each mutation records a `pending`
FileEvent before executing and updates it only after the process observes
success or a definite failure.

An unobserved result stays `pending`; it is never rewritten to `failed` merely
to make the Run terminal. Restart reconciliation marks the durable Operation
`interrupted` and makes its Plan/Run terminal from confirmed evidence only.
`check` reports pending events and requires manual review; it never
automatically repairs the filesystem.
