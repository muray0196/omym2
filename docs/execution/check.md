---
type: Execution Spec
title: Check Execution
description: Defines the check command that reports DB/filesystem inconsistencies, Library state, and CheckIssue scope, and persists its findings for browsing without mutating Library music files, Tracks, Plans, or Runs.
tags: [check, consistency, library-state, persistence]
timestamp: 2026-07-10T09:00:00+09:00
---

# Check Execution

This document is authoritative for check behavior, DB / filesystem inconsistency reporting, Library state reporting, CheckIssue scope, pending FileEvent reporting, and check findings persistence.

Common execution rules are in [model.md](model.md). CheckIssue values are cataloged in [../contracts/status-reason-catalog.md](../contracts/status-reason-catalog.md#checkissue-issue-type).

## Check Behavior

`check` never mutates Library music files, Tracks, Plans, or Runs. It reports inconsistencies between the DB and the filesystem and reports Library state.

`check` persists its own findings: each run replaces the owning Library's prior CheckRun and CheckIssues wholesale (see [../DOMAIN.md](../DOMAIN.md#checkrun) and [../contracts/db-schema.md](../contracts/db-schema.md#check_runs)). `omym2 check` (CLI) and `POST /api/check/run` (Web) both recompute and persist through the same usecase; every `GET /api/check*` endpoint reads only the persisted latest findings and performs no filesystem I/O. The Web API envelope, pagination, facet, and group-by shape for check browsing is authoritative in [../contracts/web-api.md](../contracts/web-api.md#check).

`check` may report whether the Library is `registered`, `unregistered`, `stale`, or `blocked`.

`check` is diagnostic. It does not replace `organize`, and `add` should not absorb full `check` responsibilities.

Reported issues include:

* missing DB files
* unmanaged files
* changed hashes
* path differences
* duplicate candidates
* pending file_events
* Library state issues

The CheckIssue model is defined in [../DOMAIN.md](../DOMAIN.md#checkissue).
