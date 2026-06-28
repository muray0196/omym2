# DB Schema Contract

This document is authoritative for the OMYM2 SQLite schema contract, table responsibilities, migrations, stored JSON fields, timestamp policy, and repository persistence boundaries.

Storage responsibility is summarized in [../storage.md](../storage.md). Path and identity representation rules are in [path-identity-storage.md](path-identity-storage.md).

Do not invent exact SQL here unless it exists in the implementation. When implementation evidence is missing, describe the required behavior as a contract.

## Responsibilities

The DB records OMYM2's last known managed state, scheduled plans, execution attempts, and durable Library music file operation logs.

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
* `metadata_json`
* `status`
* timestamps

The DB stores OMYM2's last known Library-root-relative paths and hashes. It does not prove that the file still exists or that the content has not changed.

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

Storage must retain `config_hash` and `library_root_at_plan` so apply can enforce the execution contract.

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

## Migrations

Migrations must preserve existing managed state or fail explicitly before partially changing schema state.

Every schema change needs tests for:

* migration execution
* repository persistence and restore behavior
* path representation changes when affected
* foreign-key or uniqueness behavior when affected

## Stored JSON Fields

Stored JSON fields, such as `metadata_json` and `summary_json`, are persistence details. Repositories restore typed domain models from them and must not use JSON shape to decide business policy.

## Timestamp Policy

Timestamps are persisted to support history, inspection, and deterministic tests through the `Clock` port.

Adapters may serialize timestamps, but usecases decide when state transitions occur.
