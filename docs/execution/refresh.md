---
type: Execution Spec
title: Refresh Execution
description: Refresh re-evaluation after tag correction, relocation and metadata-only actions, companion movement, and trust-stat rules.
tags: [refresh, metadata, artist-names, companions, plan-creation, track-id]
timestamp: 2026-07-18T12:00:00+09:00
---

# Refresh Execution

Authoritative for Refresh after external tag correction: file/directory/all targets, metadata reload, canonical relocation, associated companion movement, metadata-only action selection, and stable Track/CompanionAsset identity. Common rules: [model.md](model.md); apply rules: [apply.md](apply.md).

## Refresh Behavior

`refresh` re-evaluates and relocates after tag correction. Targets: `<file>`, `<dir>`, or `--all`. Flow: reload metadata → recalculate canonical path → create plan if needed → (apply) → update DB.

For each selected Track without a review-time issue, plan creation chooses one outcome:

* Recalculated canonical path differs from current path → plan a `move` action.
* Canonical path unchanged but content or metadata hash differs from the managed Track → plan a `refresh_metadata` action (reingests metadata and hashes without moving; applying updates the Track in place without a FileEvent, per [apply.md](apply.md)).
* Neither changed → no action.

Before that choice, refresh sends the selected snapshots' raw artist and album-artist values through the shared `ArtistNameResolutionReader` and passes the aligned projections to PathPolicy; existing Track metadata remains the album-context input and is not rewritten. Track selection finishes in a short read transaction; snapshot capture and name resolution occur before the final Plan persistence transaction. Every action whose candidate reached resolution records the aligned source, resolved value, provenance, and issue; candidates blocked before resolution record no pair.

An executable Refresh action cannot introduce a resolved artist name while leaving another active Track at an obsolete canonical artist path: a partial Refresh that would do so is refused and requires Organize to reconcile the whole Library. Selected candidates with no action or a blocked action still count as unreconciled; a full Refresh proceeds when every affected Track has an executable action or is already at its resolved target. A newly accepted provider result may already be committed to the resolver cache before this refusal, but no Refresh Plan or PlanAction is persisted; Organize then consumes the sticky result.

`refresh` never moves files directly — it creates a Plan, applied within the same command only with `--apply`. Stable `track_id` makes tag and canonical-path changes updates to the same managed Track, never removal-plus-creation.

## Companion Relocation

When `companions.enabled` is true and a selected audio Track relocates, Refresh applies the shared [Companion Association](../DOMAIN.md#companion-association) policy across the Library inventory and active managed companions. A discovered or managed lyrics/artwork file that must follow becomes a content-only `move_lyrics`/`move_artwork` action, following all relevant audio actions through durable dependencies and recording its semantic owner separately. An existing asset keeps `companion_asset_id`; a newly discovered one preallocates an ID without creating managed state during planning. Active audio and companion paths, batch targets, and live filesystem entries all participate in no-overwrite collision judgment.

A `refresh_metadata` action with no audio relocation does not move companions. Disabled companion processing leaves previously managed state unchanged. Companion snapshots never use the Track `--trust-stat` shortcut and carry no metadata hash.

## Trust-Stat Optimization

`refresh ... --trust-stat` is an explicit CLI-only performance opt-in; the Web refresh route always uses full snapshot capture.

A selected Track is eligible only when it is active, its `current_path` is unique among active Tracks in the Library, the single-file stat observation identifies the resolved source path, both persisted `size` and `mtime` are non-null, and both exactly match the current observation. Refresh may then reconstruct the snapshot from the stat observation plus the Track's last verified hashes and metadata. Missing sources retain the existing `source_missing` PlanAction behavior; every null, ambiguous, path-mismatching, or changed baseline receives a complete fresh snapshot. The opt-in can miss an edit that preserves both size and mtime; omit it when full re-ingestion is required.

Refresh Plan creation never writes Tracks — including after a full capture with no action — so it never ad-hoc backfills null baselines. Organize can backfill them, and applying a move or `refresh_metadata` action persists the mandatory full apply snapshot as the new baseline. `refresh --apply --trust-stat` affects only Plan creation; apply itself never trusts stat data.
