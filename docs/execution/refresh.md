---
type: Execution Spec
title: Refresh Execution
description: Defines refresh target re-evaluation with artist-name resolution diagnostics, move versus metadata actions, stable Track identity, and the explicit size+mtime trust-stat optimization and fallback rules.
tags: [refresh, metadata, artist-names, plan-creation, track-id]
timestamp: 2026-07-16T00:44:26+09:00
---

# Refresh Execution

This document is authoritative for refresh after external tag correction, file / directory / all targets, metadata reload, canonical path recalculation, relocation plan creation, metadata-only refresh action selection, and stable `track_id` preservation.

Common execution rules are in [model.md](model.md). Apply rules are in [apply.md](apply.md).

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
create plan if needed
  ↓
apply
  ↓
update DB
```

For each selected Track without a review-time issue, plan creation chooses one outcome:

* If the recalculated canonical path differs from the Track's current path, refresh plans a `move` action.
* If the canonical path is unchanged but the content hash or metadata hash differs from the managed Track, refresh plans a `refresh_metadata` action that reingests Track metadata and hashes without moving the file. Applying it updates the Track in place without creating a FileEvent, as described in [apply.md](apply.md).
* If neither the path nor the hashes changed, refresh plans no action for that Track.

Before that choice, refresh sends the selected snapshots' raw artist and
album-artist values through the shared `ArtistNameResolutionReader` and passes
the aligned projections to PathPolicy. Existing Track metadata remains the
album-context input and is not rewritten. Track selection finishes in a short
read transaction; snapshot capture and name resolution occur before the final
Plan persistence transaction.

Every Refresh action whose candidate reached resolution records the aligned
artist and album-artist source, resolved value, provenance, and issue. A
candidate blocked before resolution has no diagnostic pair. Both move and
`refresh_metadata` actions retain this plan-time review evidence.

`refresh` does not move files directly. As a rule, it creates a Plan.

Stable `track_id` allows refresh to treat tag changes and canonical path changes as changes to the same managed Track, not as removal of one Track and creation of another.

Only when `--apply` is specified is the created plan applied within the same command.

## Trust-Stat Optimization

`omym2 refresh ... --trust-stat` is an explicit CLI-only performance opt-in. The Web refresh route always uses full snapshot capture.

A selected Track is eligible only when it is active, its `current_path` is unique among active Tracks in the Library, the single-file stat observation identifies the resolved source path, both persisted `size` and `mtime` are non-null, and both values exactly match the current observation. Refresh may then reconstruct the snapshot from the stat observation plus that Track's last verified hashes and metadata.

Missing sources retain the existing `source_missing` PlanAction behavior. Every null, ambiguous, path-mismatching, or changed baseline receives a complete fresh snapshot with metadata and content hashing. The opt-in can miss an edit that preserves both size and modification time; omit it when full re-ingestion is required.

Refresh Plan creation never writes Tracks, including when it performed a full capture and created no action. It therefore does not ad-hoc backfill existing null baselines. Organize can backfill them, and applying a move or `refresh_metadata` action persists the mandatory full apply snapshot as the new baseline. `refresh --apply --trust-stat` affects only Plan creation; apply itself never trusts stat data.
