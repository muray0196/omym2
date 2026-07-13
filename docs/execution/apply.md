---
type: Execution Spec
title: Apply Execution
description: Defines atomic Apply acceptance, descriptor-anchored source and target verification, state transitions, Track baseline writes, FileEvent ordering, interruption, and Library-root preconditions.
tags: [apply, atomic-claim, plan-state, run, operation, file-event]
timestamp: 2026-07-13T17:24:07+09:00
---

# Apply Execution

This document is authoritative for Apply acceptance and execution flow, Plan /
PlanAction / Run / FileEvent transitions, interruption reconciliation,
apply-time precondition failures, `library_root_at_plan` handling, and the rule
that Apply uses recorded PlanActions.

Common execution rules are in [model.md](model.md). Cross-cutting failure cases are in [failure-policy.md](failure-policy.md).

## Apply Behavior

`apply` applies a reviewed Plan.

A Plan must contain enough information to apply the reviewed operations safely. Applying a Plan must use recorded PlanActions. It must not recalculate target paths from the latest AppConfig because the user may have reviewed a different plan.

`library_root_at_plan` is the owning Library root used when the Plan was created. If the current `libraries.root_path` for the Plan's `library_id` differs at apply time, the Plan must not be applied in the initial version and should be marked `expired` or `failed` according to the failure point.

Expected Apply flow:

```text
1. Acquire the shared cross-process exclusive-operation lock.
2. Verify the Plan is ready and the current Library root equals library_root_at_plan.
3. In one transaction, compare-and-set the Plan ready → applying, create its
   running Run, and reserve its queued Apply Operation.
4. Commit, then dispatch the worker (or run it inline for the CLI).
5. Mark the Operation running and process PlanActions in order:
   a. Leave blocked actions blocked.
   b. Mark skip actions as applied without creating a FileEvent or mutating files.
   c. For each planned move or refresh_metadata action, verify preconditions.
   d. If a precondition fails, mark the PlanAction as failed without executing a Library music file mutation.
   e. For a refresh_metadata action, update the Track in place and mark the action applied without creating a FileEvent or mutating files.
   f. For a move action, record a FileEvent as pending.
   g. Execute the Library music file mutation.
   h. Update the FileEvent to succeeded or failed.
   i. Update Tracks and PlanActions as needed.
6. In one final transaction, mark the Run and Plan terminal and store the
   Operation's run_completed result as succeeded.
7. Release the exclusive-operation lock.
```

The lock is held from validation through the worker and final transaction. No
filesystem read, hashing pass, or mutation occurs while a DB transaction is
open. The atomic acceptance transaction is narrow; subsequent pending
FileEvent commits remain independent transactions immediately before their
mutations.

If the ready-to-applying compare-and-set changes no row, acceptance fails with
`409 plan_not_ready` and creates no Run, Operation, or FileEvent. Apply versus
Apply and Apply versus Cancel therefore have one winner even if display-time
capabilities were stale.

A Plan may be applied even if it contains blocked PlanActions. `apply` executes eligible planned actions and ignores blocked actions.

`apply` is the first implementation area that mutates Library music files.

Every live apply-time source capture carries an ephemeral filesystem identity
token comprising device, inode, size, modification time, and change time.
Apply carries the exact token across the pending FileEvent commit to the
filesystem mutation boundary. A trusted snapshot reconstructed without live
I/O has no token and cannot authorize a move; any token mismatch fails with
`invalid_path`.

Library-relative move sources and targets are independently anchored to the
open Library root. Descendant directories are opened without following
symlinks, parent-directory segments are rejected inside the boundary itself,
the source file and its parent descriptor remain open, and the final target is
created exclusively relative to its verified directory descriptor. The mover
rechecks the complete source state and root containment before unlinking the
source through the retained parent descriptor. External add sources are still
copied from retained descriptors, and absolute Undo restore targets use only
the separately verified external-target exception. A symlinked Library
descendant or any pathname, metadata, or source-parent replacement before
mutation must fail with `invalid_path` instead of redirecting or claiming a
file outside the reviewed boundary.

An absolute move target is accepted only for an Undo PlanAction whose
`reverses_event_id` identifies a succeeded external add/import FileEvent for the
same Track: the action's target must equal that FileEvent's external source,
and the action's source must equal the Track's current Library path. The current
path may differ from the original import target after later in-Library moves;
that relocation does not invalidate the undo. Other absolute targets fail
before FileEvent creation with `invalid_path`.

## Plan Status

| From | Condition | To | Notes |
| --- | --- | --- | --- |
| `ready` | Atomic claim commits the Plan, running Run, and queued Operation | `applying` | This makes the Plan single-use before worker dispatch or any Library music file mutation. |
| `ready` | Current Library root differs from `library_root_at_plan` before a Run is created | `expired` | No Run or FileEvent is required because no apply attempt begins. |
| `applying` | All eligible move and refresh_metadata actions succeed, or the Plan has no eligible move or refresh_metadata actions | `applied` | This includes skip-only and blocked-only Plans. Blocked actions remain blocked, and skip actions are marked applied. |
| `applying` | At least one eligible move or refresh_metadata action succeeds and at least one eligible move or refresh_metadata action fails | `partial_failed` | The Run should also become `partial_failed`. |
| `applying` | No eligible move or refresh_metadata action succeeds and at least one eligible move or refresh_metadata action fails | `failed` | This includes precondition failures that prevent all eligible mutations. |
| `ready` | User cancels a not-yet-started Plan through lock-protected CAS | `cancelled` | Cancellation is a synchronous DB-only state change and creates no Operation or FileEvent. |

Any terminal Plan status (`applied`, `partial_failed`, `failed`, `cancelled`, or `expired`) must not be applied again. Recovery or retry requires creating a new Plan from the current DB and filesystem state.

## PlanAction Status

| From | Condition | To | Notes |
| --- | --- | --- | --- |
| none | Plan creation schedules a filesystem move | `planned` | The action is eligible for apply. |
| none | Plan creation detects a review-time issue | `blocked` | Examples include target conflicts, invalid paths, missing required metadata, missing sources, or changed sources. |
| none | Plan creation records a duplicate hash skip | `planned` | The action type is `skip`; apply reports it but does not create a FileEvent or mutate files. |
| none | Plan creation schedules a metadata-only reingest for an unchanged path | `planned` | The action type is `refresh_metadata`; apply updates the Track in place but does not create a FileEvent or mutate files. |
| `planned` | Apply processes a skip action | `applied` | No FileEvent is created, and no Track mutation or Library music file mutation is performed. |
| `planned` | Restart/dispatch reconciliation processes a recorded skip | `applied` | The no-mutation decision is determinate even though the Operation was interrupted. |
| `planned` | Move or refresh_metadata precondition fails during apply before mutation | `failed` | No FileEvent is created when no Library music file mutation is attempted. |
| `planned` | Restart/dispatch reconciliation cannot confirm a move or refresh_metadata action | `failed` | Reason is `operation_interrupted`; a related pending FileEvent remains pending and authoritative for unknown mutation outcome. |
| `planned` | Apply processes a refresh_metadata action and its preconditions pass | `applied` | Track hashes and metadata are updated in place; no FileEvent is created and no Library music file mutation is performed. |
| `planned` | Pending FileEvent is recorded and the move succeeds | `applied` | Track state is updated after the mutation succeeds. |
| `planned` | Pending FileEvent is recorded and the move fails | `failed` | The FileEvent records the mutation failure details. |
| `blocked` | Apply processes the Plan | `blocked` | Blocked actions are ignored by apply and remain blocked. |

`skip` is an action type, not a status. A skip action records a reviewed non-mutating decision, such as `duplicate_hash`. During apply, it becomes `applied` without FileEvent creation.

`refresh_metadata` is an action type for Tracks whose recalculated canonical path is unchanged but whose content hash or metadata hash changed after external tag correction. During apply, it verifies the same source preconditions as a move, then updates the Track hashes and metadata in place and becomes `applied` without FileEvent creation or Library music file mutation.

## Run Status

| From | Condition | To | Notes |
| --- | --- | --- | --- |
| none | The atomic Apply claim commits | `running` | The Run and queued Operation are created together before worker dispatch, PlanAction processing, or mutation. |
| `running` | All eligible move and refresh_metadata actions succeed, or the Plan has no eligible move or refresh_metadata actions | `succeeded` | This includes skip-only and blocked-only Plans. Blocked and skip actions do not make the Run fail. |
| `running` | At least one eligible move or refresh_metadata action succeeds and at least one eligible move or refresh_metadata action fails | `partial_failed` | This preserves evidence for history, check, and undo. |
| `running` | No eligible move or refresh_metadata action succeeds and at least one eligible move or refresh_metadata action fails | `failed` | This includes apply attempts stopped by precondition failures after the Run exists. |

A Run and Apply Operation are not created when Apply is rejected before the
atomic claim, such as when the Plan is not `ready` or the Library root mismatch
is detected first. If the mismatch is detected only after the claim committed,
the worker stops without creating a FileEvent for that mismatch; the Run and
Plan become `failed` or `partial_failed` depending on confirmed earlier
eligible successes, and the Operation becomes `failed`.

## FileEvent Status

| From | Condition | To | Notes |
| --- | --- | --- | --- |
| none | A Library music file mutation is about to be attempted | `pending` | This must be persisted before the mutation starts. |
| `pending` | The mutation succeeds | `succeeded` | The corresponding PlanAction can then become `applied`. |
| `pending` | The process observes a definite mutation failure | `failed` | The error fields capture the observable failure. An unobserved/crash outcome remains pending. |

FileEvents are only for attempted Library music file mutations. Blocked actions,
skip actions, refresh_metadata actions, and precondition failures before
mutation do not create FileEvents. A refresh_metadata action becomes `applied`
through a DB-only Track update, so a Run may succeed without creating any
FileEvent. A process crash or lost mutation result leaves the FileEvent
`pending`; reconciliation must not infer success or failure from filesystem
state.

## Dispatch Failure And Restart

Worker dispatch occurs only after the atomic claim commits. If dispatch fails,
or a restart finds the Apply Operation queued/running, the Operation becomes
`interrupted` and is never resumed automatically.

Reconciliation uses only durable evidence. Every `pending` FileEvent remains
pending and requires Check/manual review. Planned `skip` actions become
`applied`; blocked actions remain blocked. Planned `move` and
`refresh_metadata` actions become `failed` with `operation_interrupted`; that
reason records inability to confirm processing, not the pending mutation's
outcome.

If every eligible action is already determinate and no event is pending, derive
the normal Plan/Run result. Otherwise the Plan and Run become `partial_failed`
when at least one eligible action is durably confirmed applied, and `failed`
when none is. The interruption summary must not describe a pending mutation as
failed or roll the Plan back to `ready`.

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
* absolute target is not verified external-import undo history

The Run is marked `failed` or `partial_failed` depending on whether prior eligible move or refresh_metadata actions succeeded.

## Mandatory Source Verification And Track Baseline

Apply has no stat-trust mode. Before every eligible move or `refresh_metadata`
action, it captures a complete fresh source snapshot and compares its content
and metadata hashes with the recorded PlanAction. Both
`content_hash_at_plan` and `metadata_hash_at_plan` are mandatory for either
eligible action type; a missing or mismatched value fails the action as
`source_changed` before any FileEvent, file mutation, or Track update. A
matching persisted Track size and modification time never bypasses this gate.

After a successful move or `refresh_metadata` action, the Track update persists the complete snapshot's `size` and `mtime` together with its hashes and metadata. A successful move uses the pre-mutation source snapshot because the confirmed move preserves that file state at the recorded target. Failed preconditions and failed mutations do not update the Track baseline.
