---
type: Execution Spec
title: Apply Execution
description: Defines the apply flow and the Plan, PlanAction, Run, and FileEvent state transitions, including library_root_at_plan checks and apply-time precondition failures.
tags: [apply, plan-state, run, file-event]
timestamp: 2026-07-04T12:54:48+09:00
---

# Apply Execution

This document is authoritative for apply flow, Plan state transitions, PlanAction state transitions, Run state transitions, FileEvent state transitions, apply-time precondition failures, `library_root_at_plan` handling, and the rule that apply uses recorded PlanActions.

Common execution rules are in [model.md](model.md). Cross-cutting failure cases are in [failure-policy.md](failure-policy.md).

## Apply Behavior

`apply` applies a reviewed Plan.

A Plan must contain enough information to apply the reviewed operations safely. Applying a Plan must use recorded PlanActions. It must not recalculate target paths from the latest AppConfig because the user may have reviewed a different plan.

`library_root_at_plan` is the owning Library root used when the Plan was created. If the current `libraries.root_path` for the Plan's `library_id` differs at apply time, the Plan must not be applied in the initial version and should be marked `expired` or `failed` according to the failure point.

Expected apply flow:

```text
1. Create a run as running.
2. Mark the Plan as applying.
3. Process PlanActions in order:
   a. Leave blocked actions blocked.
   b. Mark skip actions as applied without creating a FileEvent or mutating files.
   c. For each planned move or refresh_metadata action, verify preconditions.
   d. If a precondition fails, mark the PlanAction as failed without executing a Library music file mutation.
   e. For a refresh_metadata action, update the Track in place and mark the action applied without creating a FileEvent or mutating files.
   f. For a move action, record a file_event as pending.
   g. Execute the Library music file mutation.
   h. Update the file_event to succeeded or failed.
   i. Update tracks and plan_actions as needed.
4. Mark the run as succeeded, failed, or partial_failed.
5. Mark the Plan as applied, failed, or partial_failed.
```

A Plan may be applied even if it contains blocked PlanActions. `apply` executes eligible planned actions and ignores blocked actions.

`apply` is the first implementation area that mutates Library music files.

## Plan Status

| From | Condition | To | Notes |
| --- | --- | --- | --- |
| `ready` | Apply request passes initial validation and a Run is created | `applying` | This makes the Plan single-use before any Library music file mutation starts. |
| `ready` | Current Library root differs from `library_root_at_plan` before a Run is created | `expired` | No Run or FileEvent is required because no apply attempt begins. |
| `applying` | All eligible move and refresh_metadata actions succeed, or the Plan has no eligible move or refresh_metadata actions | `applied` | This includes skip-only and blocked-only Plans. Blocked actions remain blocked, and skip actions are marked applied. |
| `applying` | At least one eligible move or refresh_metadata action succeeds and at least one eligible move or refresh_metadata action fails | `partial_failed` | The Run should also become `partial_failed`. |
| `applying` | No eligible move or refresh_metadata action succeeds and at least one eligible move or refresh_metadata action fails | `failed` | This includes precondition failures that prevent all eligible mutations. |
| `ready` | User cancels a not-yet-started Plan | `cancelled` | Cancellation is a DB-only state change and does not create FileEvents. |

Any terminal Plan status (`applied`, `partial_failed`, `failed`, `cancelled`, or `expired`) must not be applied again. Recovery or retry requires creating a new Plan from the current DB and filesystem state.

## PlanAction Status

| From | Condition | To | Notes |
| --- | --- | --- | --- |
| none | Plan creation schedules a filesystem move | `planned` | The action is eligible for apply. |
| none | Plan creation detects a review-time issue | `blocked` | Examples include target conflicts, invalid paths, missing required metadata, missing sources, or changed sources. |
| none | Plan creation records a duplicate hash skip | `planned` | The action type is `skip`; apply reports it but does not create a FileEvent or mutate files. |
| none | Plan creation schedules a metadata-only reingest for an unchanged path | `planned` | The action type is `refresh_metadata`; apply updates the Track in place but does not create a FileEvent or mutate files. |
| `planned` | Apply processes a skip action | `applied` | No FileEvent is created, and no Track mutation or Library music file mutation is performed. |
| `planned` | Move or refresh_metadata precondition fails during apply before mutation | `failed` | No FileEvent is created when no Library music file mutation is attempted. |
| `planned` | Apply processes a refresh_metadata action and its preconditions pass | `applied` | Track hashes and metadata are updated in place; no FileEvent is created and no Library music file mutation is performed. |
| `planned` | Pending FileEvent is recorded and the move succeeds | `applied` | Track state is updated after the mutation succeeds. |
| `planned` | Pending FileEvent is recorded and the move fails | `failed` | The FileEvent records the mutation failure details. |
| `blocked` | Apply processes the Plan | `blocked` | Blocked actions are ignored by apply and remain blocked. |

`skip` is an action type, not a status. A skip action records a reviewed non-mutating decision, such as `duplicate_hash`. During apply, it becomes `applied` without FileEvent creation.

`refresh_metadata` is an action type for Tracks whose recalculated canonical path is unchanged but whose content hash or metadata hash changed after external tag correction. During apply, it verifies the same source preconditions as a move, then updates the Track hashes and metadata in place and becomes `applied` without FileEvent creation or Library music file mutation.

## Run Status

| From | Condition | To | Notes |
| --- | --- | --- | --- |
| none | Apply attempt starts | `running` | The Run is created before processing PlanActions and before any Library music file mutation. |
| `running` | All eligible move and refresh_metadata actions succeed, or the Plan has no eligible move or refresh_metadata actions | `succeeded` | This includes skip-only and blocked-only Plans. Blocked and skip actions do not make the Run fail. |
| `running` | At least one eligible move or refresh_metadata action succeeds and at least one eligible move or refresh_metadata action fails | `partial_failed` | This preserves evidence for history, check, and undo. |
| `running` | No eligible move or refresh_metadata action succeeds and at least one eligible move or refresh_metadata action fails | `failed` | This includes apply attempts stopped by precondition failures after the Run exists. |

A Run is not created when apply is rejected before starting, such as when the Plan is not `ready` or the Library root mismatch is detected before the apply attempt begins. If the Library root mismatch is detected only after a Run has already been created, the apply attempt stops without creating a FileEvent for that mismatch; the Run and Plan are marked `failed` or `partial_failed` depending on whether any earlier eligible move or refresh_metadata action succeeded.

## FileEvent Status

| From | Condition | To | Notes |
| --- | --- | --- | --- |
| none | A Library music file mutation is about to be attempted | `pending` | This must be persisted before the mutation starts. |
| `pending` | The mutation succeeds | `succeeded` | The corresponding PlanAction can then become `applied`. |
| `pending` | The mutation fails or its result cannot be confirmed | `failed` | The error fields should capture the observable failure. |

FileEvents are only for attempted Library music file mutations. Blocked actions, skip actions, refresh_metadata actions, and precondition failures before mutation do not create FileEvents. A refresh_metadata action becomes `applied` through a DB-only Track update, so a Run may succeed without creating any FileEvent.

## Apply-Time Precondition Failures

Apply verifies apply-level preconditions before starting a Run and verifies per-action preconditions before each eligible planned move or refresh_metadata action.

Apply-level precondition failures include:

| Case | Policy |
| --- | --- |
| current Library root differs from `library_root_at_plan` before Run creation | mark Plan as expired; do not create Run or FileEvent |
| current Library root differs from `library_root_at_plan` after Run creation | stop apply; mark Run and Plan as failed or partial_failed; do not create FileEvent for the mismatch |

If a per-action precondition fails before a Library music file mutation, the PlanAction is marked `failed` without executing a Library music file mutation or Track update.

Per-action apply-time precondition failures include:

* source file missing at apply
* source hash changed after plan creation at apply

The Run is marked `failed` or `partial_failed` depending on whether prior eligible move or refresh_metadata actions succeeded.
