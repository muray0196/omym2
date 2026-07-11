---
type: Execution Spec
title: Add Execution
description: Defines add plan creation from an Incoming/source scan against the sole registered Library, including duplicate-hash skips, missing-metadata and target-conflict blocks, and add --apply orchestration.
tags: [add, plan-creation, library-registration, apply]
timestamp: 2026-07-11T21:33:40+09:00
---

# Add Execution

This document is authoritative for add plan creation, Incoming/source scan behavior, the registered Library gate, duplicate-hash skips, missing-metadata blocks, target-conflict blocks, and `add --apply` orchestration.

Common execution rules are in [model.md](model.md). Apply rules are in [apply.md](apply.md). Command syntax is summarized in [../COMMANDS.md](../COMMANDS.md).

## Add Plan Behavior

`add` is the daily entry point. It scans Incoming or a specified source directory, creates an add plan, and leaves the user to review and apply it.

In the MVP, `add` targets the sole registered Library. If no registered Library exists or Library selection is ambiguous, `add` refuses to create an add plan. The user-facing remedy is `omym2 organize --library PATH`.

`add` must not perform existing-Library organization and must not mix Incoming import actions with existing Library organization actions. It must not register, reconcile, or relink a Library.

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

## Plan Creation

The add plan creation behavior includes:

* scan Incoming or specified source
* capture file snapshots
* generate target canonical paths
* check duplicate hashes against known active Library tracks and skip duplicates with `duplicate_hash`
* block missing required metadata for incoming files
* block target conflicts according to [Target Collision Safety](#target-collision-safety)
* persist Plan and PlanActions

REMOVED Library tracks are excluded from duplicate-hash and target-conflict judgment, matching refresh, check, and album-year resolution.

## Target Collision Safety

This section is authoritative for add-time target-conflict checks. The
[Path Identity And Storage Contract](../contracts/path-identity-storage.md#pathresolver-boundary)
owns stored target-path representation and normalized comparison; [apply.md](apply.md)
owns the final no-overwrite guard and its state transitions.

For an add candidate that is otherwise a planned `move`, the candidate becomes
a `blocked` PlanAction with reason `target_exists` when any of the following is
true:

| Planning observation | Required result |
| --- | --- |
| An active Track in the target Library has the same normalized `current_path` as the generated target. | Block the candidate. REMOVED Tracks do not occupy a target for this DB check. |
| Two or more otherwise eligible move candidates in the same add batch resolve to the same normalized target. | Block every candidate that claims that target. |
| A filesystem entry already exists at the generated target after it is resolved against the Library root. | Block the candidate, even when no Track records that path. |

The logical comparisons are exact normalized Library-root-relative string
matches. They intentionally do not fold case or Unicode; the path contract
defines that boundary. Add never renames a candidate or overwrites a target to
resolve a collision.

Plan-time checks can become stale. Apply therefore atomically claims the
recorded target through its exclusive-create FileMover before moving a file. A
target that exists or appears after planning fails closed: the move's FileEvent
and PlanAction become failed with `target_exists`; [failure-policy.md](failure-policy.md)
defines the resulting Run and Plan outcome.

## Registered Library Gate

`add` requires exactly one selectable registered Library in the initial version.

No registered Library, stale Library state after a PathPolicy change, or ambiguous Library selection rejects add plan creation. This creates no Plan, Run, or FileEvent.

## Direct Apply Orchestration

When direct execution is desired, `add --apply` creates and applies the plan in the same command. Confirmation skipping is represented by `ApplyOptions.yes` and shared by `apply` and commands that apply a created plan within the same command.

`add --apply` is orchestration. Add plan creation remains separate from apply behavior.
