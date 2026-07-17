---
type: Execution Spec
title: Apply Execution
description: Apply acceptance and execution flow, status transitions, precondition failures, and interruption reconciliation.
tags: [apply, atomic-claim, plan-state, run, operation, file-event, companions, unprocessed]
timestamp: 2026-07-18T12:00:00+09:00
---

# Apply Execution

Authoritative for Apply acceptance and execution flow, Plan/PlanAction/Run/FileEvent transitions, interruption reconciliation, apply-time precondition failures, `library_root_at_plan` handling, and the recorded-PlanActions rule. Common execution rules: [model.md](model.md); cross-cutting failures: [failure-policy.md](failure-policy.md).

## Apply Behavior

Applying a Plan uses recorded PlanActions and never recalculates target paths from the latest AppConfig — the user may have reviewed a different plan. If the current `libraries.root_path` differs from `library_root_at_plan` at apply time, the Plan must not be applied; it is marked `expired` or `failed` according to the failure point.

Expected Apply flow:

```text
1. Acquire the shared cross-process exclusive-operation lock.
2. Verify the Plan is ready and the current Library root equals library_root_at_plan.
3. In one transaction, compare-and-set the Plan ready → applying, create its
   running Run, and reserve its queued Apply Operation.
4. Commit, then dispatch the worker (or run it inline for the CLI).
5. Mark the Operation running and process PlanActions in order:
   a. Leave blocked actions blocked.
   b. Mark skip actions applied without FileEvent or file mutation.
   c. Before observing a planned file/metadata action, require every durable
      same-Plan dependency to be applied.
   d. Verify the type-specific preconditions of each planned audio, companion,
      unprocessed move, or refresh_metadata action.
   e. On precondition failure, mark the PlanAction failed without a file mutation.
   f. For refresh_metadata, update the Track in place without a FileEvent.
   g. For an audio, companion, or unprocessed move, record its typed FileEvent as pending.
   h. Execute the recorded file mutation.
   i. Update the FileEvent and PlanAction, plus Track or CompanionAsset only
      when that action owns managed state.
6. In one final transaction, mark the Run and Plan terminal and store the
   Operation's run_completed result as succeeded.
7. Release the exclusive-operation lock.
```

The lock is held from validation through the worker and final transaction. No filesystem read, hashing pass, or mutation occurs while a DB transaction is open. The acceptance transaction is narrow; subsequent pending FileEvent commits are independent transactions immediately before their mutations.

If the ready-to-applying compare-and-set changes no row, acceptance fails with `409 plan_not_ready` and creates no Run, Operation, or FileEvent — Apply-vs-Apply and Apply-vs-Cancel have one winner even with stale display-time capabilities. A Plan may be applied while containing blocked PlanActions: apply executes eligible planned actions and ignores blocked ones. `apply` is the execution boundary that mutates reviewed audio, companion, and unprocessed files.

Every live apply-time source capture carries an ephemeral filesystem identity token (device, inode, size, mtime, ctime). Observation and mutation are separate retained-object boundaries: observation opens and verifies the live source before returning the token; after the pending FileEvent commit, mutation opens the source again and requires the same identity and content hash. A trusted snapshot reconstructed without live I/O has no token and cannot authorize a move; any token mismatch fails with `invalid_path`.

Library-relative move sources and targets are independently anchored to the opened Library root: no-follow traversal, parent-segment rejection inside the boundary, and retained root/parent/source/claimed-target objects until the mutation finishes. The mover rechecks complete source state and root containment before deleting the exact retained source object. External Add sources are still copied from a retained source object; absolute Undo restore targets use only the separately verified external-target exception. A link-like Library descendant or any pathname, metadata, or source-parent replacement before mutation fails with `invalid_path` instead of redirecting. Platform mechanics: [Path Identity And Storage Contract](../contracts/path-identity-storage.md#retained-observation-and-mutation-boundary).

An absolute move target is accepted only for an Undo PlanAction whose `reverses_event_id` identifies a succeeded external add/import FileEvent for the same Track: the action's target must equal that FileEvent's external source and the action's source must equal the Track's current Library path (which may differ from the original import target after later in-Library moves). Other absolute targets fail before FileEvent creation with `invalid_path`.

### Companion Apply

`move_lyrics`/`move_artwork` actions require a preallocated `companion_asset_id`. Apply validates every recorded dependency before any companion observation; missing, cross-Plan, or non-applied dependency/owner evidence fails the action with `companion_dependency_failed` and creates no FileEvent.

Companion verification uses a metadata-free content snapshot anchored to the Library root or, for an external Add source, the exact `source_root_at_plan`. Recorded content hash and live filesystem identity must match. A new asset may be absent before its first successful import; existing assets must match the action's Library, kind, owner Track, active status, and recorded source path.

Apply then commits `move_lyrics_file`/`move_artwork_file` as pending before invoking the same exclusive, no-overwrite FileMover. Success creates or advances the stable CompanionAsset with the verified content/stat snapshot; failure updates only the event/action and never advances managed companion state.

Companion Undo is additionally revalidated from the terminal source Plan/Run/event, action/event type, asset/owner identity, original dependencies, inverse dependency edges, timestamps, source root, and prior reversal history. An external Add restore must stay below the retained source root. On success the asset becomes `removed` while retaining its last Library-relative current/canonical paths.

A companion-only recovery Plan belongs to its later Add/Organize Run. Its action can name an existing owner Track without `owner_action_id` or audio dependencies because the owning audio move succeeded in the earlier Run; forward recovery Apply still requires that owner Track to be active. When Undoing the later recovery Run, Apply first verifies the recovered action's own succeeded typed FileEvent (source, target, asset, action identity). Only that owner-action-free inverse may accept the same-Library owner Track after it has become `removed`; same-Plan-owned inverses still require an active owner. No status is inferred across Runs.

### Unprocessed Apply

`move_unprocessed` is authorized entirely by the recorded Plan/action shape; Apply never reads the current unprocessed toggle, directory, preview limit, or other Config to recalculate it. Disabling collection after planning does not disable a reviewed action.

Before observation, Apply requires the exact retained source root, same Plan and Library identity, planned trackless action, null companion/owner/metadata/diagnostic fields, no dependencies, and both absolute paths. A forward Add target must be exactly `<source-root>/<recorded-portable-directory>/<source-relative-path>` and must not enter the Plan's recorded Library root. An Undo action must prove and swap the exact paths of one unreversed succeeded `move_unprocessed_file` event. Malformed, cross-root, relabelled, or Library-overlapping evidence fails with `invalid_path` before observation or FileEvent creation.

Apply then captures a rooted content-only snapshot and compares its hash and live filesystem identity with `content_hash_at_plan`, commits a `move_unprocessed_file` event as pending, and invokes the exclusive-create no-overwrite mover with both boundaries anchored to `source_root_at_plan`. Success advances only the FileEvent and PlanAction — no Track or CompanionAsset. A late target collision records `target_exists` on the failed typed event/action and preserves both user files. An unobserved outcome remains pending. Neither forward nor inverse Apply removes newly empty source directories.

## Plan Status

| From | Condition | To |
| --- | --- | --- |
| `ready` | Atomic claim commits the Plan, running Run, and queued Operation | `applying` (single-use before dispatch or any mutation) |
| `ready` | Current Library root differs from `library_root_at_plan` before a Run is created | `expired` (no Run or FileEvent) |
| `applying` | All eligible actions succeed, or none are eligible (skip-only/blocked-only included; blocked stay blocked, skips become applied) | `applied` |
| `applying` | At least one eligible action succeeds and at least one fails | `partial_failed` (Run also `partial_failed`) |
| `applying` | No eligible action succeeds and at least one fails (including precondition/dependency failures) | `failed` |
| `ready` | User cancels a not-yet-started Plan through lock-protected CAS (synchronous DB-only; no Operation or FileEvent) | `cancelled` |

Any terminal Plan status (`applied`, `partial_failed`, `failed`, `cancelled`, `expired`) must not be applied again; recovery requires a new Plan from current DB and filesystem state.

## PlanAction Status

| From | Condition | To |
| --- | --- | --- |
| none | Plan creation schedules a filesystem move, associated lyrics/artwork (with stable asset, owner, dependency evidence), or an unprocessed leftover (exact source-root layout and content hash, no managed identity) | `planned` |
| none | Plan creation detects a review-time issue (target conflict, invalid path, missing required metadata, missing/changed source) | `blocked` |
| none | Plan creation records a duplicate-hash skip (`skip` action type) or a metadata-only reingest for an unchanged path (`refresh_metadata`) | `planned` |
| `planned` | Apply or restart reconciliation processes a skip action | `applied` (no FileEvent or mutation) |
| `planned` | A precondition fails before mutation | `failed` (no FileEvent) |
| `planned` | A companion dependency or semantic owner is invalid or not applied | `failed`, reason `companion_dependency_failed` (no observation or FileEvent) |
| `planned` | Restart/dispatch reconciliation cannot confirm an action | `failed`, reason `operation_interrupted`; a related pending FileEvent stays pending and authoritative |
| `planned` | refresh_metadata preconditions pass | `applied` (Track updated in place; no FileEvent) |
| `planned` | Pending FileEvent recorded and the move succeeds | `applied` (Track updated; CompanionAsset created/advanced only for companion success; unprocessed advances no managed state) |
| `planned` | Pending FileEvent recorded and the move fails | `failed` (FileEvent records failure details) |
| `blocked` | Apply processes the Plan | `blocked` (ignored by apply) |

`skip` is an action type, not a status: a reviewed non-mutating decision (e.g., `duplicate_hash`) that becomes `applied` without FileEvent. `refresh_metadata` is an action type for Tracks whose recalculated canonical path is unchanged but whose content or metadata hash changed; it updates the Track in place without FileEvent or file mutation.

## Run Status

| From | Condition | To |
| --- | --- | --- |
| none | The atomic Apply claim commits (Run and queued Operation created together, before dispatch/processing/mutation) | `running` |
| `running` | All eligible actions succeed, or none are eligible (blocked and skip actions never fail the Run) | `succeeded` |
| `running` | At least one eligible action succeeds and at least one fails | `partial_failed` |
| `running` | No eligible action succeeds and at least one fails | `failed` |

No Run or Apply Operation is created when Apply is rejected before the atomic claim (Plan not `ready`, or Library-root mismatch detected first). If the mismatch is detected after the claim committed, the worker stops without creating a FileEvent for the mismatch; Run and Plan become `failed` or `partial_failed` per confirmed earlier successes, and the Operation becomes `failed`.

## FileEvent Status

| From | Condition | To |
| --- | --- | --- |
| none | An audio, companion, or unprocessed mutation is about to be attempted | `pending` (persisted before the mutation starts) |
| `pending` | The mutation succeeds | `succeeded` |
| `pending` | The process observes a definite mutation failure | `failed` (error fields capture the failure; unobserved/crash outcomes stay pending) |

FileEvents exist only for attempted audio, companion, or unprocessed mutations. Blocked actions, skip actions, refresh_metadata actions, and pre-mutation precondition failures create none — a Run may succeed with zero FileEvents. A crash or lost mutation result leaves the FileEvent `pending`; reconciliation must not infer success or failure from filesystem state.

## Dispatch Failure And Restart

Worker dispatch occurs only after the atomic claim commits. If dispatch fails, or a restart finds the Apply Operation queued/running, the Operation becomes `interrupted` and is never resumed automatically.

Reconciliation uses only durable evidence: every `pending` FileEvent stays pending (Check/manual review); planned `skip` actions become `applied`; blocked actions stay blocked; planned `move`, `move_lyrics`, `move_artwork`, `move_unprocessed`, and `refresh_metadata` actions become `failed` with `operation_interrupted` — that reason records inability to confirm processing, not the pending mutation's outcome.

If every eligible action is determinate and no event is pending, derive the normal Plan/Run result; otherwise `partial_failed` when at least one eligible action is durably confirmed applied, `failed` when none is. The interruption summary must not describe a pending mutation as failed or roll the Plan back to `ready`.

## Apply-Time Precondition Failures

Apply verifies apply-level preconditions before starting a Run and verifies dependencies plus per-action preconditions before each eligible action.

| Case | Policy |
| --- | --- |
| current Library root differs from `library_root_at_plan` before Run creation | mark Plan expired; no Run or FileEvent |
| current Library root differs from `library_root_at_plan` after Run creation | stop apply; mark Run and Plan failed or partial_failed; no FileEvent for the mismatch |

Per-action precondition failures (PlanAction marked `failed`, no file or managed-state update): source missing at apply; source hash changed after plan creation; absolute target not verified external-import undo history; companion asset/owner/dependency/source-root provenance changed after planning; unprocessed action not the exact trackless content-only layout below its retained source root, or its target enters the recorded Library root. The Run becomes `failed` or `partial_failed` depending on prior eligible successes.

## Mandatory Source Verification And Track Baseline

Apply has no stat-trust mode. Before every eligible audio `move` or `refresh_metadata` action it captures a complete fresh source snapshot and compares content and metadata hashes with the recorded PlanAction. Both `content_hash_at_plan` and `metadata_hash_at_plan` are mandatory for either type; a missing or mismatched value fails the action as `source_changed` before any FileEvent, mutation, or Track update. Matching persisted Track size/mtime never bypasses this gate.

Companion actions capture a rooted `FileContentSnapshot` instead: recorded content hash and live filesystem identity required, intentionally no metadata hash. Matching persisted companion stat values never bypass the gate. Unprocessed actions use the same rooted content-only observation with no persisted stat baseline or managed-state update; both forward and inverse observations anchor to `source_root_at_plan`.

Apply passes the live snapshot's filesystem identity and content hash to the FileMover after the pending FileEvent commit; the mover verifies retained source bytes and, for copy fallback, the exclusively claimed target bytes against that hash before unlinking the source. A mismatch fails the move and removes the claimed target.

After a successful audio move or `refresh_metadata` action, the Track update persists the complete snapshot's `size` and `mtime` with its hashes and metadata; a successful companion move persists the content snapshot's hash/stat baseline on its CompanionAsset. Failed preconditions and failed mutations update neither baseline.
