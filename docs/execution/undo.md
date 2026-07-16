---
type: Execution Spec
title: Undo Execution
description: Defines Undo eligibility and deduplication for audio, companions, and trackless unprocessed moves, including exact reverse provenance, changed-content blocks, and restore conflicts.
tags: [undo, eligibility, deduplication, file-event, companions, unprocessed, plan-creation, restore]
timestamp: 2026-07-16T04:51:16+09:00
---

# Undo Execution

This document is authoritative for Undo per Run, eligibility, deduplication,
unsupported `refresh_metadata` history, reverse FileEvent tracing, Undo Plan
provenance, source-observation blocks, external restore targets/conflicts, and
Track/CompanionAsset removal for restored imports.

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

Reversible event types are `move_file`, `move_lyrics_file`,
`move_artwork_file`, and `move_unprocessed_file`. Undo traces all succeeded
reversible events in strict reverse source-event order; it does not duplicate
shared artwork.

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
`source_run_id`, retained `source_root_at_plan`, `reverses_event_id`
values, companion ownership/dependency edges, and the Operation's
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

Undo Plan creation converts source-observation failures into reviewed blocked
actions instead of failing the durable Undo Operation wholesale. A source that
disappears during snapshot capture is `source_missing`; a rejected
Library-relative source path is `invalid_path`; and an unstable snapshot,
metadata-read failure, or other filesystem observation failure is
`source_changed`. The Operation succeeds with a `plan_created` result so the
user can inspect the blocked action before deciding what to do next.

When undo restores a file that originally came from outside the Library, such as an add/import source, the undo Plan records the external restore destination as an absolute target path. Applying that undo moves the file out of the Library and marks the managed Track as `removed`; Track paths remain Library-root-relative and do not store the external destination.

Undo Plan creation permits that absolute target only when the succeeded FileEvent exactly matches its originating add/import PlanAction. The restore source is the Track's current Library path, which may differ from the original import target after later in-Library moves; that relocation does not invalidate the undo. Apply verifies the same provenance again against durable history before attempting the external restore, matching the restore destination to the FileEvent's external source and the restore source to the Track's current Library path.

Undo uses Run and FileEvent history. Stable `track_id` keeps the relationship between Track state and FileEvents even when paths, metadata, or hashes have changed.

## Companion Undo

Each succeeded companion event produces the same semantic inverse action type
with the same `companion_asset_id`, owner Track, and source event provenance.
Planning captures only content/stat evidence; companion Undo never reads music
metadata or supplies a metadata hash.

Companion history fails closed before Plan creation unless the terminal source
Plan, Run, action, typed event, asset kind/status, owner, paths, timestamps,
and every original audio dependency agree. Apply repeats this strong
provenance validation and also excludes source events already confirmed by a
succeeded prior reversal event.

Undo reverses dependency direction: when the forward companion depended on an
audio move, the inverse audio move depends on the inverse companion. This
restores lyrics/artwork before moving or removing their owning audio file.
`owner_action_id` still points from the inverse companion to the semantic
inverse audio owner; persistence writes owner rows first to satisfy the
same-Plan reference, independently from execution sort order.

For an external Add source, the inverse companion target is the recorded
absolute source below the retained `source_root_at_plan`. Successful Apply
moves it out of the Library and marks the CompanionAsset `removed`, retaining
its stable identity and last Library-relative managed paths. Restore
collisions, missing/changed sources, and invalid rooted paths remain reviewable
blocked actions and are never overwritten.

### Recovered Companion Runs

A companion recovered by a later companion-only Add/Organize Run is undone
only through that later Run's own Undo Plan. Undo never reaches across history
to append the recovered companion to the original audio Run's inverse. This
keeps each reversal tied to its own succeeded FileEvent and prevents inferred
cross-Run outcomes.

The recovered forward action has no `owner_action_id`; its owner audio already
succeeded in the earlier Run. Its Undo provenance must first match that later
Run's succeeded typed companion event, including action/type/source/target and
`companion_asset_id`. The same-Library owner Track may then be `removed` if the
original audio Run was undone first. Forward recovery Apply and ordinary
same-Plan-owned companion inverses continue to require an active owner Track.

## Unprocessed Undo

One exact unreversed succeeded `move_unprocessed_file` event creates one
inverse `move_unprocessed` action. Undo proves the terminal source Plan/Run,
event/action identity, timestamps, retained source root, content hash, null
Track/companion/owner/metadata/diagnostic fields, and absence of dependencies.
It then swaps the recorded absolute source and target without consulting the
current unprocessed toggle, directory, or preview limit.

Planning observes the collected target with a content-only reader anchored to
the retained root. Missing content is blocked with `source_missing`; content
that changed since the forward action is blocked with `source_changed`. The
latter is deliberate: Undo must not move user-modified bytes merely because
the path still matches. Malformed or relabelled history fails closed rather
than constructing an inverse.

Applying the inverse uses the same pending `move_unprocessed_file` and
exclusive no-overwrite boundary as forward collection. It restores the exact
original absolute path, creates or changes no Track or CompanionAsset, and does
not remove empty directories left under the collection destination. An
occupied restore path remains a blocked or failed `target_exists` outcome,
never an overwrite.
