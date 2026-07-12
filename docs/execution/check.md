---
type: Execution Spec
title: Check Execution
description: Defines persisted check diagnostics, point-in-time snapshot reuse, the explicit trust-stat optimization, unmanaged hashing, and the Track no-mutation boundary.
tags: [check, consistency, library-state, persistence]
timestamp: 2026-07-12T02:41:12+09:00
---

# Check Execution

This document is authoritative for check behavior, DB / filesystem inconsistency reporting, Library state reporting, CheckIssue scope, pending FileEvent reporting, and check findings persistence.

Common execution rules are in [model.md](model.md). CheckIssue values are cataloged in [../contracts/status-reason-catalog.md](../contracts/status-reason-catalog.md#checkissue-issue-type).

## Check Behavior

`check` never mutates Library music files, Tracks, Plans, or Runs. It reports inconsistencies between the DB and the filesystem and reports Library state.

`check` persists its own findings: each run replaces the owning Library's prior CheckRun and CheckIssues wholesale (see [../DOMAIN.md](../DOMAIN.md#checkrun) and [../contracts/db-schema.md](../contracts/db-schema.md#check_runs)). `omym2 check` (CLI) and `POST /api/check/run` (Web) both recompute and persist through the same usecase; every `GET /api/check*` endpoint reads only the persisted latest findings and performs no filesystem I/O. The Web API envelope, pagination, facet, and group-by shape for check browsing is authoritative in [../contracts/web-api.md](../contracts/web-api.md#check).

`check` may report whether the Library is `registered`, `unregistered`, `stale`, or `blocked`.

Within one check invocation, the first full snapshot observation for a filesystem path is reused across managed-Track and `ready` Plan source diagnostics. These phases therefore compare against one point-in-time observation instead of reading the same file at two different instants. Hash-only duplicate checks for unmanaged files remain separate from this full-snapshot reuse. Unmanaged duplicate-candidate detection hashes content directly and does not require readable metadata.

`check` is diagnostic. It does not replace `organize`, and `add` should not absorb full `check` responsibilities.

Reported issues include:

* missing DB files
* unmanaged files
* changed hashes
* path differences
* duplicate candidates
* pending FileEvents
* Library state issues

The CheckIssue model is defined in [../DOMAIN.md](../DOMAIN.md#checkissue).

## Trust-Stat Optimization

`omym2 check --trust-stat` is an explicit CLI-only performance opt-in. `POST /api/check/run` always performs the normal full-snapshot path.

Check scans the Library before managed-file diagnostics only in this opt-in mode so the same scan observations can drive both trust decisions and unmanaged-file reporting. A managed Track is eligible only when it is active, its `current_path` is unique among active Tracks in the Library, the logical and resolved observation paths match, both persisted `size` and `mtime` are non-null, and both exactly match the scan observation.

An eligible Track contributes a reconstructed FileSnapshot containing its last verified hashes and metadata. Check seeds the invocation's snapshot memo with that observation, so a `ready` Plan source at the same filesystem path reuses it. Null, missing, ambiguous, path-mismatching, or changed baselines fall back to a complete fresh snapshot. Default check retains its full-snapshot-before-scan observation order.

The opt-in can miss a content or metadata edit that preserves both size and modification time. Omit it for full integrity verification. Check remains diagnostic: it never updates Track hashes, metadata, size, or modification-time baselines, regardless of whether it used a trusted or complete snapshot. Unmanaged-file duplicate checks continue to hash content and never use Track stat trust.
