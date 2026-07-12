---
type: Execution Spec
title: Undo Execution
description: Defines Undo eligibility and deduplication, reverse FileEvent tracing, Undo Plan provenance, restore conflicts, and external restore Track removal.
tags: [undo, eligibility, deduplication, file-event, plan-creation, restore]
timestamp: 2026-07-13T00:31:39+09:00
---

# Undo Execution

This document is authoritative for Undo per Run, eligibility, deduplication,
unsupported `refresh_metadata` history, reverse FileEvent tracing, Undo Plan
provenance, external restore targets/conflicts, and Track removal for restored
imports.

Common execution rules are in [model.md](model.md). Apply rules are in [apply.md](apply.md). Path exceptions are in [../contracts/path-identity-storage.md](../contracts/path-identity-storage.md#absolute-external-path-exceptions).

## Undo Behavior

Undo is performed per Run.

Undo Plan creation requires the source Run to be terminal. A `running` Run must be rejected because its FileEvent history can still change.

Undo Plan creation must reject any source Run whose Plan contains a `refresh_metadata` action. `refresh_metadata` updates Track metadata and hashes without a FileEvent, and the initial history model does not persist before/after metadata state for reversal.

Undo Plan creation also rejects a source Run that has no succeeded reversible
FileEvent. It rejects any `pending` FileEvent in the source Run or in every
prior Undo Run whose Plan has the same `source_run_id`. An empty Undo Plan is
not useful, and an unknown original or reversal outcome must be resolved by
Check/manual review rather than inferred during Undo.

Run details return `can_create_undo` and backend-authored disabled reasons. The
initial refusal codes are:

| Condition | Code |
| --- | --- |
| source Run is not terminal | `run_not_terminal` |
| source Plan contains `refresh_metadata` | `undo_refresh_metadata_unsupported` |
| no succeeded reversible FileEvent exists | `nothing_to_undo` |
| a FileEvent is pending | `pending_file_event_requires_review` |
| an earlier Undo Plan is applying or applied | `already_undone_or_in_progress` |

These capabilities are for presentation only. Undo Plan generation revalidates
every condition while holding the shared exclusive-operation lock.

## Undo Plan Provenance And Deduplication

Every Undo Plan persists `source_run_id`, and every Undo PlanAction persists
the source FileEvent identity in `reverses_event_id`; non-Undo records leave
those fields null. The referenced event must be `succeeded`, belong to that
source Run and Library, and identify the same Track as the reversal action.
Undo Plan creation queries that provenance inside its creation transaction:

* an existing `ready` Undo Plan is returned as the result instead of creating a
  duplicate;
* an existing `cancelled` or `expired` Undo Plan did not start a Run, so a new
  Undo Plan may be created from current durable state;
* an existing `applying` or `applied` Undo Plan causes
  `already_undone_or_in_progress`;
* after a `partial_failed` or `failed` Undo Plan, a new Plan may be generated
  only from the current Track/FileEvent state and only when none of the pending
  events in the scope above exists. A source event is already reversed only
  when a prior Undo PlanAction with the same `reverses_event_id` has its own
  succeeded reversal FileEvent; that event must not be scheduled again.

The Web request is a durable `undo_plan` Operation and returns its status URL;
the CLI may execute the same Operation inline. The Plan, its actions,
`source_run_id`, `reverses_event_id` values, and the Operation's
`plan_created` result commit together when a new Plan is created. When a ready
Plan already exists, the Operation result links that pre-existing Plan without
claiming to create or recommit it.

```text
run
  ↓
trace succeeded FileEvents in reverse order
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

If the restore destination is already occupied during undo Plan creation, the
corresponding PlanAction is `blocked` with reason `target_exists`; it is not
overwritten automatically. A target that appears later is caught by apply's
exclusive-create move and fails closed, requiring manual review.

When undo restores a file that originally came from outside the Library, such as an add/import source, the undo Plan records the external restore destination as an absolute target path. Applying that undo moves the file out of the Library and marks the managed Track as `removed`; Track paths remain Library-root-relative and do not store the external destination.

Undo Plan creation permits that absolute target only when the succeeded FileEvent exactly matches its originating add/import PlanAction. The restore source is the Track's current Library path, which may differ from the original import target after later in-Library moves; that relocation does not invalidate the undo. Apply verifies the same provenance again against durable history before attempting the external restore, matching the restore destination to the FileEvent's external source and the restore source to the Track's current Library path.

Undo uses Run and FileEvent history. Stable `track_id` keeps the relationship between Track state and FileEvents even when paths, metadata, or hashes have changed.
