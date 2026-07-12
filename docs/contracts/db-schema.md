---
type: Contract
title: DB Schema Contract
description: Defines OMYM2's SQLite tables, nullable Track stat baselines, forward-only migrations, performance indexes, stored JSON boundaries, and timestamp policy.
tags: [database, sqlite, schema, migrations]
timestamp: 2026-07-12T02:41:12+09:00
---

# DB Schema Contract

This document is authoritative for the OMYM2 SQLite schema contract, table responsibilities, migrations, stored JSON fields, timestamp policy, and repository persistence boundaries.

Storage responsibility is summarized in [../STORAGE.md](../STORAGE.md). Path and identity representation rules are in [path-identity-storage.md](path-identity-storage.md).

Do not invent exact SQL here unless it exists in the implementation. When implementation evidence is missing, describe the required behavior as a contract.

## Responsibilities

As summarized in the storage overview, the DB records OMYM2's last known managed state, scheduled plans, execution attempts, and durable Library music file operation logs.

The DB is not:

* the editable settings store
* the source of truth for the actual filesystem
* responsible for reading music metadata
* responsible for scanning or moving files
* responsible for calculating canonical paths
* responsible for deciding conflicts, duplicates, metadata validity, or PlanAction status

Repositories persist and restore domain models. They must not invent business rules.

Every Library-managed record carries `library_id`.

Schema changes require migration and integration tests.

## Location

Expected SQLite DB:

```text
.data/omym2.sqlite3
```

The `.data/` directory is reserved for OMYM2 internal data under the application root.

## Tables

Main information to store:

```text
libraries
tracks
plans
plan_actions
runs
file_events
check_runs
check_issues
```

### libraries

Stores the current identity, root path, and acceptance state of each Library known to OMYM2.

Minimum representative fields:

* `library_id`
* `root_path`
* `path_policy_hash`
* `registered_at`
* `status`
* `created_at`
* `updated_at`

`library_id` is stable. `root_path` is mutable and represents the current filesystem location used for runtime path resolution.

### tracks

Stores the current managed state of files known to OMYM2.

Minimum representative fields:

* `track_id`
* `library_id`
* `current_path`
* `canonical_path`
* `content_hash`
* `metadata_hash`
* `size` nullable
* `mtime` nullable
* `metadata_json`
* `status`
* timestamps

The DB stores OMYM2's last known Library-root-relative paths and hashes. Nullable
`size` and `mtime` store the stat baseline associated with a verified snapshot;
existing rows without a baseline retain `NULL` in both columns. A non-null
`size` is constrained to be nonnegative. These values are optimization hints,
not Track identity or proof that the file still exists or remains unchanged.

### plans

Stores scheduled operations before execution.

Minimum representative fields:

* `plan_id`
* `library_id`
* `plan_type`
* `status`
* `created_at`
* `config_hash`
* `library_root_at_plan`
* `summary_json`

Storage must retain `config_hash` to preserve the reviewed configuration context and `library_root_at_plan` for the apply-time Library-root precondition.

### plan_actions

Stores each reviewed action inside a Plan.

Minimum representative fields:

* `action_id`
* `plan_id`
* `library_id`
* `track_id` nullable
* `action_type`
* `source_path`
* `target_path`
* `content_hash_at_plan`
* `metadata_hash_at_plan`
* `status`
* `reason`
* `sort_order`

`conflict` and `error` are not action types. They are represented by status and reason values.

### runs

Stores execution attempts for applying Plans.

Minimum representative fields:

* `run_id`
* `plan_id`
* `library_id`
* `status`
* `started_at`
* `completed_at`
* `error_summary`

A Run is created before applying PlanActions and before any Library music file mutation.

### file_events

Stores durable operation-log entries for attempted Library music file mutations.

Minimum representative fields:

* `event_id`
* `library_id`
* `run_id`
* `plan_action_id`
* `event_type`
* `source_path`
* `target_path`
* `status`
* `started_at`
* `completed_at`
* `error_code`
* `error_message`
* `sequence_no`

FileEvents are used for run detail display, diagnosing partial failures, crash inspection, and undo plan creation.

### check_runs

Stores one row per Library for that Library's latest completed check run.

Minimum representative fields:

* `check_run_id`
* `library_id`
* `checked_at`
* `total_count`

A Library has at most one `check_runs` row at a time: each new check run for a Library replaces that Library's prior row and prior `check_issues` rows. Check findings are therefore persisted latest-run-only, never accumulated across runs.

### check_issues

Stores the findings of one check run.

Minimum representative fields:

* `issue_seq`
* `check_run_id`
* `library_id`
* `issue_type`
* `path` nullable
* `track_id` nullable
* `plan_id` nullable
* `detail` nullable

`issue_seq` is an auto-incrementing sequence that preserves the insertion order of one check run's findings and backs keyset pagination for check browsing. Rows are removed when their owning `check_runs` row is replaced or deleted.

## Migrations

Migrations must preserve existing managed state or fail explicitly before partially changing schema state.

Every schema change needs tests for:

* migration execution
* repository persistence and restore behavior
* path representation changes when affected
* foreign-key or uniqueness behavior when affected

### Migration Safety Rules

* Applied migrations are tracked by filename: `schema_migrations` has
  `migration_name` as its `PRIMARY KEY`. Never edit or rename a migration
  file that may already be applied; doing so silently diverges existing
  databases from what OMYM2 believes is applied. Fix forward with a new
  migration file instead.
* Migrations run in strict lexicographic filename order.
  `load_packaged_migrations` sorts the packaged `*.sql` resources by
  filename before applying any of them, so a new migration's filename must
  sort after every existing one to take effect.
* Each migration file and its `schema_migrations` marker apply inside a
  single transaction (`migration_runner.py`'s `_apply_migration` wraps the
  script and the insert in one `BEGIN`/`commit`, rolling back on
  `sqlite3.DatabaseError`), so a migration is never recorded as applied
  unless it fully succeeded; there are no silent partial migrations.

## Indexes

Indexes exist to keep the Web API's list, facet, and group-by endpoints (authoritative in [web-api.md](web-api.md)) fast at scale. They are persistence details: they change lookup cost, never table responsibilities or stored data.

`202607090001_browsing_indexes.sql` adds:

* `idx_tracks_current_path` on `tracks (current_path, track_id)` — backs Track list ordering and keyset pagination (`GET /api/tracks`).
* `idx_tracks_status` on `tracks (library_id, status)` — backs Track status filtering and status facet counts scoped to one Library.
* `idx_plan_actions_status` on `plan_actions (plan_id, status)` — backs PlanAction status filtering within one Plan.
* `idx_plan_actions_type` on `plan_actions (plan_id, action_type)` — backs PlanAction type filtering within one Plan.
* `idx_runs_started` on `runs (started_at, run_id)` — backs Run history ordering and keyset pagination.

`202607090002_check_results.sql` adds:

* `idx_check_issues_library_type` on `check_issues (library_id, issue_type, issue_seq)` — backs CheckIssue Library/issue_type filtering, ordering, and keyset pagination (`GET /api/check`).

`202607100001_plan_browsing_index.sql` adds:

* `idx_plans_created` on `plans (created_at, plan_id)` — backs Plan list ordering and keyset pagination (`GET /api/plans`).
* `idx_plans_library_created` on `plans (library_id, created_at, plan_id)` — backs Library-scoped Plan ordering and keyset pagination.

`202607110001_performance_indexes.sql` adds:

* `idx_check_issues_check_run_id` on `check_issues (check_run_id)` — backs foreign-key lookup and cascade cleanup when replacing a CheckRun.
* `idx_file_events_library_status` on `file_events (library_id, status, sequence_no)` — backs ordered pending-FileEvent lookup for one Library during `check`.

The same migration removes two redundant single-column indexes whose lookup prefixes are covered by existing composite indexes:

* `idx_tracks_library_id`, superseded by indexes beginning with `tracks.library_id`.
* `idx_plans_library_id`, superseded by `idx_plans_library_created`.

`202607110002_track_stat_baseline.sql` adds:

* nullable `tracks.size`, constrained to nonnegative integer values when present
* nullable `tracks.mtime`, stored as timestamp text when present

The migration does not backfill existing rows. Both values therefore remain
`NULL` until a later verified snapshot is persisted for that Track.

## Stored JSON Fields

Stored JSON fields, such as `metadata_json` and `summary_json`, are persistence details. Repositories restore typed domain models from them and must not use JSON shape to decide business policy.

## Timestamp Policy

Timestamps are persisted to support history, inspection, and deterministic tests through the `Clock` port. A non-null Track `mtime` baseline follows the same UTC timestamp serialization as other persisted timestamps.

Adapters may serialize timestamps, but usecases decide when state transitions occur.
