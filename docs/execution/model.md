# Execution Model

This document is authoritative for the common Plan-centered execution model, Plan / PlanAction / Run / FileEvent behavior, single-use Plan policy, blocked-vs-failed distinction, durable operation log principle, and FileEvent creation scope.

Task-specific behavior is in [add.md](add.md), [apply.md](apply.md), [organize.md](organize.md), [refresh.md](refresh.md), [undo.md](undo.md), [check.md](check.md), and [failure-policy.md](failure-policy.md).

## Plan-Centered Execution

Library music file mutations are not executed directly.

Read-only scans, metadata reads, hash calculations, inspections, and DB-only Library state updates do not require a Plan.

Library music file mutations must follow this flow:

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
    verify preconditions
    record file_event as pending
    execute Library music file mutation
    update file_event
    update track / plan_action
  ↓
finish run
```

This allows the CLI, GUI, and tests to share the same processing model.

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

A Run is created before processing PlanActions and before any Library music file mutation. It may succeed, fail, or partially fail.

A Run is the parent unit for FileEvents and the main unit used by history and undo.

If a failure occurs after some Library music file operations have succeeded, the Run becomes `partial_failed`.

## FileEvent Behavior

A FileEvent is a durable operation log entry for one Library music file mutation.

A FileEvent is created as `pending` before the Library music file mutation. After the mutation, it is updated to `succeeded` or `failed`.

FileEvents represent Library music file mutations only. DB-only state changes such as registering or updating Tracks are not FileEvents.

FileEvents are used for:

* run detail display
* diagnosing partial failures
* crash inspection
* undo plan creation

## Single-Use Plan Policy

A Plan is single-use in the initial version. Once apply starts, the same Plan must not be applied again.

If recovery or retry is needed, the user creates a new Plan from the current DB and filesystem state.

## Blocked Vs Failed

Issues detected during plan creation are represented as `blocked`.

Precondition failures detected during apply are represented as `failed`.

Action types and allowed status / reason values are cataloged in [../contracts/status-reason-catalog.md](../contracts/status-reason-catalog.md).

## Durable Operation Log

Library music file operations and DB transactions cannot be made fully atomic. Therefore, apply does not rely on one large transaction that covers the whole run.

FileEvents are the durable operation log. Each Library music file mutation records a FileEvent as `pending` before executing the mutation and updates it after the mutation succeeds or fails.

If the process crashes, pending or partially recorded FileEvents are used to inspect what may have happened. The initial recovery policy is conservative: report the state through `check` and require manual review rather than automatically repairing the filesystem.
