---
type: Execution Spec
title: Undo Execution
description: Undo eligibility, deduplication, reverse provenance, external restore targets, and companion/unprocessed reversal rules.
tags: [undo, eligibility, deduplication, file-event, companions, unprocessed, plan-creation, restore]
timestamp: 2026-07-18T12:00:00+09:00
---

# Undo Execution

Authoritative for Undo per Run: eligibility, deduplication, unsupported `refresh_metadata` history, reverse FileEvent tracing, Undo Plan provenance, source-observation blocks, external restore targets/conflicts, and Track/CompanionAsset removal for restored imports. Common rules: [model.md](model.md); apply rules: [apply.md](apply.md); path exceptions: [../contracts/path-identity-storage.md](../contracts/path-identity-storage.md#absolute-external-path-exceptions).

## Undo Behavior

Undo is performed per Run. Undo Plan creation requires a terminal source Run (a `running` Run's FileEvent history can still change). It rejects any source Run whose Plan contains a `refresh_metadata` action — that action updates Track metadata/hashes without a FileEvent, and the history model persists no before/after metadata state for reversal. It also rejects a source Run with no succeeded reversible FileEvent, and any `pending` FileEvent in the source Run or in any prior Undo Run sharing the same `source_run_id`: unknown outcomes are resolved by Check/manual review, never inferred during Undo.

Reversible event types: `move_file`, `move_lyrics_file`, `move_artwork_file`, `move_unprocessed_file`. Undo traces all succeeded reversible events in strict reverse source-event order and does not duplicate shared artwork.

Run details return `can_create_undo` with backend-authored disabled reasons:

| Condition | Code |
| --- | --- |
| source Run is not terminal | `run_not_terminal` |
| source Plan contains `refresh_metadata` | `undo_refresh_metadata_unsupported` |
| no succeeded reversible FileEvent exists | `nothing_to_undo` |
| a FileEvent is pending | `pending_file_event_requires_review` |
| an earlier Undo Plan is applying or applied | `already_undone_or_in_progress` |

These capabilities are presentation-only; Undo Plan generation revalidates every condition while holding the shared exclusive-operation lock.

## Undo Plan Provenance And Deduplication

Every Undo Plan persists `source_run_id`; every Undo PlanAction persists the source FileEvent identity in `reverses_event_id` (non-Undo records leave both null). The referenced event must be `succeeded`, belong to that source Run and Library, and identify the same Track as the reversal action. Creation queries that provenance inside its transaction:

* an existing `ready` Undo Plan is returned instead of creating a duplicate;
* an existing `cancelled` or `expired` Undo Plan started no Run, so a new Plan may be created from current durable state;
* an existing `applying` or `applied` Undo Plan causes `already_undone_or_in_progress`;
* after a `partial_failed` or `failed` Undo Plan, a new Plan may be generated only from current Track/FileEvent state and only when no pending event in the scope above exists. A source event is already reversed only when a prior Undo PlanAction with the same `reverses_event_id` has its own succeeded reversal FileEvent; that event is not scheduled again.

The Web request is a durable `undo_plan` Operation returning its status URL; the CLI may execute the same Operation inline. The Plan, its actions, `source_run_id`, retained `source_root_at_plan`, `reverses_event_id` values, companion ownership/dependency edges, and the Operation's `plan_created` result commit together when a new Plan is created; when a ready Plan already exists, the result links that Plan without claiming to create it.

Undo never modifies the filesystem directly: `omym2 undo <run-id>` creates the Plan, `--apply` applies it in the same command.

If the restore destination is already occupied during creation, the PlanAction is `blocked` with `target_exists` — never overwritten. A target appearing later is caught by apply's exclusive-create move and fails closed.

Source-observation failures become reviewed blocked actions instead of failing the durable Undo Operation: a source disappearing during snapshot capture is `source_missing`; a rejected Library-relative source path is `invalid_path`; an unstable snapshot, metadata-read failure, or other observation failure is `source_changed`. The Operation succeeds with `plan_created` so the user can inspect the blocked action.

When undo restores a file that originally came from outside the Library (add/import source), the Plan records the external restore destination as an absolute target. Applying it moves the file out of the Library and marks the managed Track `removed`; Track paths stay Library-root-relative and never store the external destination. The absolute target is permitted only when the succeeded FileEvent exactly matches its originating add/import PlanAction; the restore source is the Track's current Library path (which may differ from the original import target after later in-Library moves). Apply verifies the same provenance again against durable history before the external restore.

Undo uses Run and FileEvent history; stable `track_id` keeps Track state and FileEvents related even when paths, metadata, or hashes changed.

## Companion Undo

Each succeeded companion event produces the same semantic inverse action type with the same `companion_asset_id`, owner Track, and source event provenance. Planning captures only content/stat evidence; companion Undo never reads music metadata or supplies a metadata hash.

Companion history fails closed before Plan creation unless the terminal source Plan, Run, action, typed event, asset kind/status, owner, paths, timestamps, and every original audio dependency agree. Apply repeats this validation and also excludes source events already confirmed by a succeeded prior reversal event.

Undo reverses dependency direction: when the forward companion depended on an audio move, the inverse audio move depends on the inverse companion, restoring lyrics/artwork before moving or removing their owning audio file. `owner_action_id` still points from the inverse companion to the semantic inverse audio owner; persistence writes owner rows first to satisfy the same-Plan reference, independently from execution sort order.

For an external Add source, the inverse companion target is the recorded absolute source below the retained `source_root_at_plan`. Successful Apply moves it out of the Library and marks the CompanionAsset `removed`, retaining stable identity and last Library-relative managed paths. Restore collisions, missing/changed sources, and invalid rooted paths remain reviewable blocked actions, never overwrites.

### Recovered Companion Runs

A companion recovered by a later companion-only Add/Organize Run is undone only through that later Run's own Undo Plan; Undo never reaches across history to append it to the original audio Run's inverse. Each reversal stays tied to its own succeeded FileEvent with no inferred cross-Run outcomes.

The recovered forward action has no `owner_action_id` (its owner audio succeeded in the earlier Run). Its Undo provenance must first match that later Run's succeeded typed companion event, including action/type/source/target and `companion_asset_id`. The same-Library owner Track may then be `removed` if the original audio Run was undone first; forward recovery Apply and ordinary same-Plan-owned companion inverses continue to require an active owner Track.

## Unprocessed Undo

One exact unreversed succeeded `move_unprocessed_file` event creates one inverse `move_unprocessed` action. Undo proves the terminal source Plan/Run, event/action identity, timestamps, retained source root, content hash, null Track/companion/owner/metadata/diagnostic fields, and absence of dependencies, then swaps the recorded absolute source and target without consulting the current unprocessed toggle, directory, or preview limit.

Planning observes the collected target with a content-only reader anchored to the retained root. Missing content blocks with `source_missing`; content changed since the forward action blocks with `source_changed` — Undo must not move user-modified bytes merely because the path matches. Malformed or relabelled history fails closed rather than constructing an inverse.

Applying the inverse uses the same pending `move_unprocessed_file` and exclusive no-overwrite boundary as forward collection: it restores the exact original absolute path, creates or changes no Track or CompanionAsset, and does not remove empty directories under the collection destination. An occupied restore path remains a blocked or failed `target_exists` outcome, never an overwrite.
