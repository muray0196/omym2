# Execution

This document is authoritative for Plan-centered execution semantics, Run behavior, FileEvent behavior, blocked vs failed behavior, and durable operation log behavior.

Domain concepts are defined in [domain.md](domain.md), command names are listed in [commands.md](commands.md), and DB consistency details are in [storage.md](storage.md).

## Plan-Centered Execution Model

Library music file mutations are not executed directly.

Read-only scans, metadata reads, hash calculations, inspections, and DB-only Library registration do not require a Plan.

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
user command     internal behavior
------------     -----------------
settings         read / write settings
organize         scan Library, create organize plan, or register clean Library
add              create add plan for a registered Library
refresh          create metadata refresh / relocate plan
apply            apply selected plan
check            compare DB, filesystem, and Library registration state
```

## Bootstrap Behavior

OMYM2 has no mandatory first-use initialization command.

Config files, DB files, and internal directories are created lazily when a command needs them.

Missing config or DB is not an error by itself. Missing required paths are errors only for commands that need those paths.

Path rules:

* Commands must not guess the Library path.
* Commands that need the Library path fail if it is not configured.
* `add` without a configured Incoming path fails unless a source directory is explicitly supplied.

## Library Registration Behavior

A registered Library means OMYM2 has accepted the configured Library under the current resolved Library root and current PathPolicy.

Registration is tied to:

* `library_root`
* `path_policy_hash` or an equivalent identity for the current PathPolicy

Registration is not defined by whether the `tracks` table has rows.

Minimum representative registration fields:

* `library_root`
* `path_policy_hash`
* `registered_at`
* `status`

Initial status examples:

* `registered`
* `unregistered`
* `stale`
* `blocked`

Changing PathPolicy invalidates prior Library registration. After a PathPolicy change, `add` refuses to create a plan until the Library is registered again under the new PathPolicy. The expected remedy is `omym2 organize`.

`organize` is the only supported path for an unregistered or unorganized Library to become usable by `add`.

## Add Plan Behavior

`add` is the daily entry point. It scans Incoming or a specified source directory, creates an add plan, and leaves the user to review and apply it.

`add` requires a registered Library. If the current Library is not registered under the current resolved Library root and current PathPolicy, `add` refuses to create an add plan. The user-facing remedy is `omym2 organize`.

`add` must not perform existing-Library organization and must not mix Incoming import actions with existing Library organization actions.

`add` should not perform a full Library-wide organizedness check every time. Its gate is Library registration, not repeated canonical path validation across the entire Library.

```text
Incoming folder
  ↓
scan
  ↓
create plan
  ↓
review
  ↓
apply
  ↓
Library
```

When direct execution is desired, `add --apply` creates and applies the plan in the same command. Confirmation skipping is represented by `ApplyOptions.yes` and shared by `apply` and commands that apply a created plan within the same command.

The add plan creation behavior includes:

* scan Incoming or specified source
* capture file snapshots
* generate target canonical paths
* check duplicate hashes against known DB state and skip duplicates with `duplicate_hash`
* block missing required metadata for incoming files
* block target conflicts
* persist Plan and PlanActions

## Apply Behavior

`apply` applies a reviewed Plan.

A Plan must contain enough information to apply the reviewed operations safely. Applying a Plan must use recorded PlanActions. It must not recalculate target paths from the latest AppConfig because the user may have reviewed a different plan.

`library_root_at_plan` is the resolved Library root used when the Plan was created. If the current resolved Library root differs at apply time, the Plan must not be applied in the initial version and should be marked `expired` or `failed` according to the failure point.

Expected apply flow:

```text
1. Create a run as running.
2. Mark the Plan as applying.
3. Process PlanActions in order:
   a. Leave blocked actions blocked.
   b. Mark skip actions as applied without creating a FileEvent or mutating files.
   c. For each planned move action, verify preconditions.
   d. If a precondition fails, mark the PlanAction as failed without executing a Library music file mutation.
   e. Record a file_event as pending.
   f. Execute the Library music file mutation.
   g. Update the file_event to succeeded or failed.
   h. Update tracks and plan_actions as needed.
4. Mark the run as succeeded, failed, or partial_failed.
5. Mark the Plan as applied, failed, or partial_failed.
```

A Plan may be applied even if it contains blocked PlanActions. `apply` executes eligible planned actions and ignores blocked actions.

`apply` is the first implementation phase that mutates Library music files.

## Apply State Transitions

State transitions are part of the apply contract. Implementations should reject transitions not listed here unless a later document explicitly extends the model.

### Plan status

| From | Condition | To | Notes |
| --- | --- | --- | --- |
| `ready` | Apply request passes initial validation and a Run is created | `applying` | This makes the Plan single-use before any Library music file mutation starts. |
| `ready` | Current resolved Library root differs from `library_root_at_plan` before a Run is created | `expired` | No Run or FileEvent is required because no apply attempt begins. |
| `applying` | All eligible move actions succeed, or the Plan has no eligible move actions | `applied` | This includes skip-only and blocked-only Plans. Blocked actions remain blocked, and skip actions are marked applied. |
| `applying` | At least one eligible move action succeeds and at least one eligible move action fails | `partial_failed` | The Run should also become `partial_failed`. |
| `applying` | No eligible move action succeeds and at least one eligible move action fails | `failed` | This includes precondition failures that prevent all eligible mutations. |
| `ready` | User cancels a not-yet-started Plan | `cancelled` | Cancellation is a DB-only state change and does not create FileEvents. |

Any terminal Plan status (`applied`, `partial_failed`, `failed`, `cancelled`, or `expired`) must not be applied again. Recovery or retry requires creating a new Plan from the current DB and filesystem state.

### PlanAction status

| From | Condition | To | Notes |
| --- | --- | --- | --- |
| none | Plan creation schedules a filesystem move | `planned` | The action is eligible for apply. |
| none | Plan creation detects a review-time issue | `blocked` | Examples include target conflicts, invalid paths, missing required metadata, missing sources, or changed sources. |
| none | Plan creation records a duplicate hash skip | `planned` | The action type is `skip`; apply reports it but does not create a FileEvent or mutate files. |
| `planned` | Apply processes a skip action | `applied` | No FileEvent is created, and no Track mutation or Library music file mutation is performed. |
| `planned` | Move precondition fails during apply before mutation | `failed` | No FileEvent is created when no Library music file mutation is attempted. |
| `planned` | Pending FileEvent is recorded and the move succeeds | `applied` | Track state is updated after the mutation succeeds. |
| `planned` | Pending FileEvent is recorded and the move fails | `failed` | The FileEvent records the mutation failure details. |
| `blocked` | Apply processes the Plan | `blocked` | Blocked actions are ignored by apply and remain blocked. |

`skip` is an action type, not a status. A skip action records a reviewed non-mutating decision, such as `duplicate_hash`. During apply, it becomes `applied` without FileEvent creation.

### Run status

| From | Condition | To | Notes |
| --- | --- | --- | --- |
| none | Apply attempt starts | `running` | The Run is created before processing PlanActions and before any Library music file mutation. |
| `running` | All eligible move actions succeed, or the Plan has no eligible move actions | `succeeded` | This includes skip-only and blocked-only Plans. Blocked and skip actions do not make the Run fail. |
| `running` | At least one eligible move action succeeds and at least one eligible move action fails | `partial_failed` | This preserves evidence for history, check, and undo. |
| `running` | No eligible move action succeeds and at least one eligible move action fails | `failed` | This includes apply attempts stopped by precondition failures after the Run exists. |

A Run is not created when apply is rejected before starting, such as when the Plan is not `ready` or the Library root mismatch is detected before the apply attempt begins. If the Library root mismatch is detected only after a Run has already been created, the apply attempt stops without creating a FileEvent for that mismatch; the Run and Plan are marked `failed` or `partial_failed` depending on whether any earlier eligible move action succeeded.

### FileEvent status

| From | Condition | To | Notes |
| --- | --- | --- | --- |
| none | A Library music file mutation is about to be attempted | `pending` | This must be persisted before the mutation starts. |
| `pending` | The mutation succeeds | `succeeded` | The corresponding PlanAction can then become `applied`. |
| `pending` | The mutation fails or its result cannot be confirmed | `failed` | The error fields should capture the observable failure. |

FileEvents are only for attempted Library music file mutations. Blocked actions, skip actions, and precondition failures before mutation do not create FileEvents.

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

## Refresh Behavior

`refresh` is an operation for re-evaluation and relocation after tag correction.

Targets can be file / directory / all.

```bash
omym2 refresh <file>
omym2 refresh <dir>
omym2 refresh --all
```

Expected flow:

```text
Correct tags with an external tag editor
  ↓
omym2 refresh <file>
  ↓
reload metadata
  ↓
recalculate canonical path
  ↓
create move plan if needed
  ↓
apply
  ↓
update DB
```

`refresh` does not move files directly. As a rule, it creates a Plan.

Stable `track_id` allows refresh to treat tag changes and canonical path changes as changes to the same managed Track, not as removal of one Track and creation of another.

Only when `--apply` is specified is the created plan applied within the same command.

## Organize Behavior

`organize` scans the configured Library read-only and computes canonical paths under the current PathPolicy.

If files need to move or blocking actions must be reviewed, `organize` creates an organize Plan. `organize` does not move files directly except through `--apply` orchestration.

If no moves are needed and no blocking issues exist, `organize` can register the Library without creating a mutation Plan because DB-only registration is not a Library music file mutation.

If the organize Plan is applied successfully and no blocking Library-state issues remain, the Library becomes registered. Registering the Library after apply is a DB-only state change and does not create a FileEvent.

If blocked actions remain, the Library must not become registered.

Blocking issues include:

* missing required metadata
* canonical path conflicts
* invalid paths
* missing source files
* other problems preventing safe acceptance

## Undo Behavior

Undo is performed per Run.

```text
run
  ↓
trace succeeded file_events in reverse order
  ↓
create undo plan
  ↓
apply
  ↓
restore to original paths
```

Undo does not modify the filesystem directly. It goes through a Plan.

```bash
omym2 undo <run-id>
omym2 apply <undo-plan-id>
```

Only when applying within the same command is `--apply` used.

```bash
omym2 undo <run-id> --apply
```

If the restore destination is already occupied during undo, it is not overwritten automatically. It stops as a conflict and requires manual review.

Undo uses Run and FileEvent history. Stable `track_id` keeps the relationship between Track state and FileEvents even when paths, metadata, or hashes have changed.

## Check Behavior

`check` is read-only in the initial version. It reports inconsistencies between the DB and the filesystem and reports Library registration state.

`check` may report whether the Library is `registered`, `unregistered`, `stale`, or `blocked`.

`check` is diagnostic. It does not replace `organize`, and `add` should not absorb full `check` responsibilities.

Reported issues include:

* missing DB files
* unmanaged files
* changed hashes
* path differences
* duplicate candidates
* pending file_events
* registration state issues

CheckIssue is not persisted as primary state in the initial version. It is calculated by `check` from the DB and filesystem observations.

## Single-Use Plan Policy

A Plan is single-use in the initial version. Once apply starts, the same Plan must not be applied again.

If recovery or retry is needed, the user creates a new Plan from the current DB and filesystem state.

## Blocked vs Failed Behavior

Issues detected during plan creation are represented as `blocked`.

Precondition failures detected during apply are represented as `failed`.

Blocked reason examples:

* target_exists
* missing_required_metadata
* invalid_path
* source_missing
* source_changed

Skip reason examples:

* duplicate_hash

`conflict` and `error` are not action types. They are represented as status and reason.

## Apply-Time Precondition Failure Behavior

Apply verifies apply-level preconditions before starting a Run and verifies per-action preconditions before each eligible planned move action.

Apply-level precondition failures include:

| Case | Policy |
| --- | --- |
| current Library root differs from `library_root_at_plan` before Run creation | mark Plan as expired; do not create Run or FileEvent |
| current Library root differs from `library_root_at_plan` after Run creation | stop apply; mark Run and Plan as failed or partial_failed; do not create FileEvent for the mismatch |

If a per-action precondition fails before a Library music file mutation, the PlanAction is marked `failed` without executing a Library music file mutation.

Per-action apply-time precondition failures include:

* source file missing at apply
* source hash changed after plan creation at apply

The Run is marked `failed` or `partial_failed` depending on whether prior Library music file mutations succeeded.

## Durable Operation Log Behavior

Library music file operations and DB transactions cannot be made fully atomic. Therefore, apply does not rely on one large transaction that covers the whole run.

FileEvents are the durable operation log. Each Library music file mutation records a FileEvent as `pending` before executing the mutation and updates it after the mutation succeeds or fails.

If the process crashes, pending or partially recorded FileEvents are used to inspect what may have happened. The initial recovery policy is conservative: report the state through `check` and require manual review rather than automatically repairing the filesystem.

## Failure Policy

| Case | Policy |
| --- | --- |
| target path exists | conflict. Do not overwrite automatically |
| metadata is insufficient during plan creation | block the PlanAction |
| duplicate hash exists | skip candidate with `duplicate_hash` as the reason |
| source file missing during plan creation | block the PlanAction |
| source file missing at apply | fail the PlanAction and mark Run as failed or partial_failed |
| source hash changed during plan creation | block the PlanAction |
| source hash changed after plan creation at apply | fail the PlanAction and mark Run as failed or partial_failed |
| current Library root differs from `library_root_at_plan` before Run creation | mark Plan as expired; do not create Run or FileEvent |
| current Library root differs from `library_root_at_plan` after Run creation | stop apply; mark Run and Plan as failed or partial_failed; do not create FileEvent for the mismatch |
| failure during move | mark file_event as failed and Run as partial_failed if prior Library music file mutations succeeded |
| tag mistake after apply | relocate with refresh |
| another file exists at undo destination | mark undo plan as conflict and do not overwrite automatically |
| DB and filesystem are out of sync | detect with check |
| pending file_event exists | report through check and require manual review |
| add requested for unregistered or stale Library | reject add plan creation; no Plan, Run, or FileEvent |
| PathPolicy changed after Library registration | mark or report registration as stale; require organize before add |
