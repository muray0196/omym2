# Execution

This document is authoritative for Plan-centered execution semantics, Run behavior, FileEvent behavior, blocked vs failed behavior, and durable operation log behavior.

Domain concepts are defined in [domain.md](domain.md), command names are listed in [commands.md](commands.md), and DB consistency details are in [storage.md](storage.md).

## Plan-Centered Execution Model

Library music file mutations are not executed directly.

Read-only scans, metadata reads, hash calculations, and inspections do not require a Plan.

They must follow this flow:

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
setup            initialize workspace and scan Library
add              create add plan
organize         create Library organize plan
refresh          create metadata refresh / relocate plan
apply            apply selected plan
check            compare DB and filesystem state
```

## Setup Behavior

`setup` creates config / DB and, unless disabled, scans the existing Library to register the current track state.

```text
setup
  ↓
create config / DB
  ↓
scan existing Library
  ↓
record tracks
```

`setup` does not move or mutate Library music files and does not require a Plan.

`setup` may register Tracks without creating a Plan because it does not perform Library music file mutations.

## Add Plan Behavior

`add` is the daily entry point. It scans Incoming or a specified source directory, creates an add plan, and leaves the user to review and apply it.

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
* skip duplicate hashes with `duplicate_hash`
* block missing required metadata
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
3. Ignore blocked actions and process each eligible planned move action:
   a. Verify preconditions.
   b. If a precondition fails, mark the PlanAction as failed without executing a Library music file mutation.
   c. Record a file_event as pending.
   d. Execute the Library music file mutation.
   e. Update the file_event to succeeded or failed.
   f. Update tracks and plan_actions as needed.
4. Mark the run as succeeded, failed, or partial_failed.
5. Mark the Plan as applied, failed, or partial_failed.
```

A Plan may be applied even if it contains blocked PlanActions. `apply` executes eligible planned actions and ignores blocked actions.

`apply` is the first implementation phase that mutates Library music files.

## Run Behavior

A Run is an execution attempt for applying a Plan.

A Run is created before executing Library music file mutations. It may succeed, fail, or partially fail.

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

`organize` creates a move plan for existing Library files whose current path differs from the canonical path.

`organize` can operate on the entire existing Library, so it is always plan-first in the initial state.

`organize` does not move files directly except through `--apply` orchestration.

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

`check` is read-only in the initial version. It reports inconsistencies between the DB and the filesystem.

Reported issues include:

* missing DB files
* unmanaged files
* changed hashes
* path differences
* duplicate candidates
* pending file_events

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

Apply verifies preconditions before each eligible planned action.

If a precondition fails before a Library music file mutation, the PlanAction is marked `failed` without executing a Library music file mutation.

Apply-time precondition failures include:

* source file missing at apply
* source hash changed after plan creation at apply
* current Library root differs from `library_root_at_plan`

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
| failure during move | mark file_event as failed and Run as partial_failed if prior Library music file mutations succeeded |
| tag mistake after apply | relocate with refresh |
| another file exists at undo destination | mark undo plan as conflict and do not overwrite automatically |
| DB and filesystem are out of sync | detect with check |
| pending file_event exists | report through check and require manual review |
