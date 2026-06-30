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
* check duplicate hashes against known DB state and skip duplicates with `duplicate_hash`
* block missing required metadata for incoming files
* block target conflicts
* persist Plan and PlanActions

## Registered Library Gate

`add` requires exactly one selectable registered Library in the initial version.

No registered Library, stale Library state after a PathPolicy change, or ambiguous Library selection rejects add plan creation. This creates no Plan, Run, or FileEvent.

## Direct Apply Orchestration

When direct execution is desired, `add --apply` creates and applies the plan in the same command. Confirmation skipping is represented by `ApplyOptions.yes` and shared by `apply` and commands that apply a created plan within the same command.

`add --apply` is orchestration. Add plan creation remains separate from apply behavior.
