---
type: Execution Spec
title: Check Execution
description: Diagnostic Check execution, CheckIssue scope, findings persistence, and trust-stat scope.
tags: [check, operation, consistency, library-state, companions, unprocessed, persistence]
timestamp: 2026-07-18T12:00:00+09:00
---

# Check Execution

Authoritative for Check execution, DB/filesystem inconsistency and Library-state reporting, CheckIssue scope, pending FileEvent reporting, and findings persistence. Common rules: [model.md](model.md); CheckIssue values: [../contracts/status-reason-catalog.md](../contracts/status-reason-catalog.md#checkissue-issue-type).

## Check Behavior

`check` never mutates Library files, Tracks, CompanionAssets, Plans, or Runs. It reports inconsistencies between recorded managed state or reviewed mutation evidence and the filesystem, and persists its own findings: each run replaces the owning Library's prior CheckRun and CheckIssues wholesale ([../DOMAIN.md](../DOMAIN.md#checkrun), [../contracts/db-schema.md](../contracts/db-schema.md#check_runs)).

`omym2 check` (CLI) and `POST /api/check/run` (Web) recompute through the same usecase while holding the shared exclusive-operation lock. The Web request requires an idempotency key and returns `202` plus a durable `check` Operation; the CLI records the same Operation and may run its worker inline. The completed Check replacement and the Operation's `check_completed` result commit together. Another state-changing operation conflicts immediately rather than queueing. Every `GET /api/check*` endpoint reads only persisted latest findings, remains available during an exclusive operation, and performs no filesystem I/O ([../contracts/web-api.md](../contracts/web-api.md#check-endpoints)).

`check` may report the Library as `registered`, `unregistered`, `stale`, or `blocked`.

Within one invocation, the first full snapshot observation for a filesystem path is reused across managed-Track and `ready` Plan source diagnostics, so those phases compare against one point-in-time observation. Hash-only duplicate checks for unmanaged files stay separate from this reuse; unmanaged duplicate-candidate detection hashes content directly and needs no readable metadata.

Active CompanionAssets are checked with rooted content-only observations, never music metadata reads. Check reports a missing companion file, changed content hash, current/canonical path difference, or missing active owner Track with the stable `companion_asset_id`; removed assets are not treated as current Library files.

When `companions.enabled` is true, the complete regular-file inventory is also classified with the shared companion policy: a recognized associated lyrics/artwork path without an active managed asset produces `unmanaged_companion_exists` (not also an ordinary unmanaged audio file). Disabling the toggle suppresses only this unmanaged discovery. Ready external Add companion sources are revalidated below the Plan's exact `source_root_at_plan`; source drift retains the asset ID on `plan_source_changed` regardless of the current toggle.

Ready `move_unprocessed` sources are revalidated through rooted content-only observations below the Plan's exact `source_root_at_plan`, using the recorded action shape and hash — never the current unprocessed toggle, directory, or preview limit, and never music metadata.

Check also identifies a recoverable source left by a definitive companion failure. `failed_companion_source_exists` requires a terminal failed or partially failed Plan, non-pending failure evidence, succeeded owner-audio provenance, an active same-Library owner Track, and a source that still exists under its authorized root. External Add sources validate against the exact recorded `source_root_at_plan`; Library-relative Organize sources validate against the current Library root. The finding recommends a new Add or Organize Plan respectively; its `detail` is the stable command scope `add` or `organize` (grouping never infers scope from path syntax). It never repairs automatically, and a pending event is excluded because its outcome is unknown.

For each unreversed succeeded `move_unprocessed_file` event with exact Plan/action provenance, Check observes the recorded target below the retained source root: a missing target produces `unprocessed_file_missing`; a different content hash produces `unprocessed_content_hash_changed`. Only one exact, terminal succeeded inverse event suppresses the forward diagnostic; malformed, duplicate, nonterminal, or hash/path-mismatched reversal evidence does not. Both findings are `error` severity, recommend History (`omym2 history`), and never recommend Refresh/Add or repair automatically because no Track or CompanionAsset owns the file. Changed collected content also blocks a later Undo PlanAction with `source_changed`.

`check` is diagnostic: it does not replace `organize`, and `add` should not absorb full `check` responsibilities. Reported issues include missing DB files, unmanaged files, changed hashes, path differences, missing/changed/ownerless/misplaced/unmanaged companions, definitively failed companion sources eligible for reviewed replanning, missing or content-changed targets from unreversed successful unprocessed moves, duplicate candidates, pending FileEvents, and Library state issues. CheckIssue model: [../DOMAIN.md](../DOMAIN.md#checkissue).

## Trust-Stat Optimization

`omym2 check --trust-stat` is an explicit CLI-only performance opt-in; `POST /api/check/run` always performs the normal full-snapshot path.

Only in this mode does Check scan the Library before managed-file diagnostics, so the same scan observations drive both trust decisions and unmanaged-file reporting. A managed Track is eligible only when active, its `current_path` unique among active Tracks, logical and resolved observation paths matching, both persisted `size`/`mtime` non-null, and both exactly matching the scan observation. An eligible Track contributes a reconstructed FileSnapshot with its last verified hashes and metadata; Check seeds the invocation's snapshot memo with it so a `ready` Plan source at the same path reuses it. Null, missing, ambiguous, path-mismatching, or changed baselines fall back to a complete fresh snapshot. Default check retains its full-snapshot-before-scan observation order.

The opt-in can miss a content or metadata edit preserving both size and mtime; omit it for full integrity verification. Check remains diagnostic: it never updates Track hashes, metadata, or stat baselines regardless of snapshot kind. Unmanaged-file duplicate checks continue to hash content and never use Track stat trust. Trust-stat applies only to managed Track full snapshots; companion and unprocessed checks stay content-only and never update recorded hash/stat state.
