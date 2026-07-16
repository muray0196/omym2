---
type: Execution Spec
title: Check Execution
description: Defines diagnostic Check execution for Tracks, CompanionAssets, trackless unprocessed evidence, ready Plan sources, and pending events, including persisted findings and trust-stat scope.
tags: [check, operation, consistency, library-state, companions, unprocessed, persistence]
timestamp: 2026-07-16T04:51:16+09:00
---

# Check Execution

This document is authoritative for Check execution, DB / filesystem
inconsistency and Library-state reporting, CheckIssue scope, pending FileEvent
reporting, and Check findings persistence.

Common execution rules are in [model.md](model.md). CheckIssue values are cataloged in [../contracts/status-reason-catalog.md](../contracts/status-reason-catalog.md#checkissue-issue-type).

## Check Behavior

`check` never mutates Library files, Tracks, CompanionAssets, Plans, or Runs.
It reports inconsistencies between recorded managed state or reviewed mutation
evidence and the filesystem.

`check` persists its own findings: each run replaces the owning Library's prior
CheckRun and CheckIssues wholesale (see [../DOMAIN.md](../DOMAIN.md#checkrun)
and [../contracts/db-schema.md](../contracts/db-schema.md#check_runs)).

`omym2 check` (CLI) and `POST /api/check/run` (Web) recompute through the same
usecase while holding the shared exclusive-operation lock. The Web request
requires an idempotency key and returns `202` plus a durable `check` Operation;
the CLI records the same Operation and may run its worker inline. The completed
Check replacement and the Operation's `check_completed` result commit together.
Another state-changing operation conflicts immediately rather than queueing.

Every `GET /api/check*` endpoint reads only persisted latest findings, remains
available during an exclusive operation, and performs no filesystem I/O. The
Web API envelope, pagination, facet, and group-by shape is authoritative in
[../contracts/web-api.md](../contracts/web-api.md#check-endpoints).

`check` may report whether the Library is `registered`, `unregistered`, `stale`, or `blocked`.

Within one check invocation, the first full snapshot observation for a filesystem path is reused across managed-Track and `ready` Plan source diagnostics. These phases therefore compare against one point-in-time observation instead of reading the same file at two different instants. Hash-only duplicate checks for unmanaged files remain separate from this full-snapshot reuse. Unmanaged duplicate-candidate detection hashes content directly and does not require readable metadata.

Active CompanionAssets are checked with rooted content-only observations, not
music metadata reads. Check reports a missing companion file, changed content
hash, current/canonical path difference, or missing active owner Track with the
stable `companion_asset_id`. Removed assets are not treated as current
Library files.

When `companions.enabled` is true, the complete regular-file inventory is also
classified with the shared companion policy. A recognized associated
lyrics/artwork path without an active managed asset produces
`unmanaged_companion_exists`; it is not also treated as an ordinary unmanaged
audio file. Disabling the toggle suppresses only this unmanaged discovery.
Ready external Add companion sources are revalidated below the Plan's exact
`source_root_at_plan`, and source drift retains the asset ID on
`plan_source_changed` regardless of the current toggle.

Ready `move_unprocessed` sources are also revalidated through rooted
content-only observations below the Plan's exact `source_root_at_plan`. Check
uses the recorded action shape and hash, not the current unprocessed toggle,
directory, or preview limit. It never reads music metadata for these actions.

Check also identifies a recoverable source left by a definitive companion
failure. `failed_companion_source_exists` requires a terminal failed or
partially failed Plan, non-pending failure evidence, succeeded owner-audio
provenance, an active same-Library owner Track, and a source that still exists
under its authorized root. External Add sources are validated against the
exact recorded `source_root_at_plan`; Library-relative Organize sources are
validated against the current Library root. The finding recommends a new Add
or Organize Plan respectively. Its `detail` is the stable command scope `add`
or `organize`; grouping does not infer scope from platform-specific absolute
path syntax. It never repairs automatically, and a pending event is excluded
because its outcome remains unknown.

For each unreversed succeeded `move_unprocessed_file` event with exact
Plan/action provenance, Check observes the recorded target below the retained
source root. A missing target produces `unprocessed_file_missing`; a different
content hash produces `unprocessed_content_hash_changed`. Only one exact,
terminal succeeded inverse event suppresses this forward diagnostic; malformed,
duplicate, nonterminal, or hash/path-mismatched reversal evidence does not.

Both findings are `error` severity and recommend History (`omym2 history`).
They never recommend Refresh or Add and never repair automatically because no
Track or CompanionAsset owns the file. Changed collected content also causes a
later Undo PlanAction to be blocked with `source_changed` rather than moving
bytes that differ from the successful forward event.

`check` is diagnostic. It does not replace `organize`, and `add` should not absorb full `check` responsibilities.

Reported issues include:

* missing DB files
* unmanaged files
* changed hashes
* path differences
* missing, changed, ownerless, misplaced, or unmanaged companions
* definitively failed companion sources eligible for reviewed replanning
* missing or content-changed targets from unreversed successful unprocessed
  moves
* duplicate candidates
* pending FileEvents
* Library state issues

The CheckIssue model is defined in [../DOMAIN.md](../DOMAIN.md#checkissue).

## Trust-Stat Optimization

`omym2 check --trust-stat` is an explicit CLI-only performance opt-in. `POST /api/check/run` always performs the normal full-snapshot path.

Check scans the Library before managed-file diagnostics only in this opt-in mode so the same scan observations can drive both trust decisions and unmanaged-file reporting. A managed Track is eligible only when it is active, its `current_path` is unique among active Tracks in the Library, the logical and resolved observation paths match, both persisted `size` and `mtime` are non-null, and both exactly match the scan observation.

An eligible Track contributes a reconstructed FileSnapshot containing its last verified hashes and metadata. Check seeds the invocation's snapshot memo with that observation, so a `ready` Plan source at the same filesystem path reuses it. Null, missing, ambiguous, path-mismatching, or changed baselines fall back to a complete fresh snapshot. Default check retains its full-snapshot-before-scan observation order.

The opt-in can miss a content or metadata edit that preserves both size and modification time. Omit it for full integrity verification. Check remains diagnostic: it never updates Track hashes, metadata, size, or modification-time baselines, regardless of whether it used a trusted or complete snapshot. Unmanaged-file duplicate checks continue to hash content and never use Track stat trust.

Trust-stat applies only to managed Track full snapshots. Companion and
unprocessed checks continue to use content-only observation and never update
their recorded hash/stat state.
