---
type: Contract
title: DB Schema Contract
description: Defines OMYM2's SQLite tables, clean baseline migration, reset policy, indexes, constraints, JSON, timestamps, and persisted companion and unprocessed evidence.
tags: [database, sqlite, schema, migrations, artist-names, musicbrainz, companions, unprocessed, provenance]
timestamp: 2026-07-16T22:15:00+09:00
---

# DB Schema Contract

This document is authoritative for the OMYM2 SQLite schema contract, table responsibilities, migrations, stored JSON fields, timestamp policy, and repository persistence boundaries.

Storage responsibility is summarized in [../STORAGE.md](../STORAGE.md). Durable
Operation lifecycle and retention behavior are authoritative in
[operations.md](operations.md). Path and identity representation rules are in
[path-identity-storage.md](path-identity-storage.md).

Do not invent exact SQL here unless it exists in the implementation. When implementation evidence is missing, describe the required behavior as a contract.

## Responsibilities

As summarized in the storage overview, the DB records OMYM2's last known
managed state, scheduled plans, execution attempts, durable background-request
state, durable Library music file operation logs, and persisted check
diagnostics.

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
companion_assets
plans
plan_actions
plan_action_dependencies
runs
file_events
operations
check_runs
check_issues
accepted_artist_names
provider_request_cadence
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

### companion_assets

Stores the last confirmed managed state of one lyrics or artwork file. It is
separate from `tracks`; no metadata JSON or metadata hash is stored.

Minimum representative fields:

* `companion_asset_id`
* `library_id`
* `kind`
* `owner_track_id`
* `current_path`
* `canonical_path`
* `content_hash`
* `size` and `mtime` nullable
* `status`
* `first_seen_at`, `last_seen_at`, and `updated_at`

`library_id` and `owner_track_id` use restricted foreign keys so managed
companion history is not silently orphaned. Paths remain normalized
Library-root-relative values. A non-null size is nonnegative. Repository
listing order is `current_path, companion_asset_id`.

### accepted_artist_names

Stores positive external-provider artist display names that the naming feature
has accepted, including the provider identity and selected-field provenance.
This is a global provider cache rather than a Library-managed record, so it has
no `library_id` and does not duplicate the editable preference mapping stored
in TOML.

Fields:

* `source_key`, the non-empty derived lookup key and primary key
* `source_name`, the non-empty original metadata text associated with that key
* `resolved_name`, the non-empty accepted display name
* `provider`, currently `musicbrainz`
* `provider_artist_id`, the canonical UUID MusicBrainz artist identity
* `selected_name_kind`, either `alias` or `name`
* `selected_locale`, nullable and permitted only for an alias selection
* `accepted_at`, the UTC acceptance timestamp

The naming feature derives every lookup and insertion key with the pure
[ArtistNameSourceKey](../DOMAIN.md#artistnamesourcekey) contract before
repository access; the repository compares the supplied key exactly. Missing
or whitespace-only source text produces no key and must not reach the
repository. The stored `source_name` preserves the exact source text from the
first accepted insertion even when another canonically equivalent or
whitespace-equivalent value derives the same key. Insertion is sticky:
`insert_if_absent` does nothing and returns false when `source_key` already
exists. Ordinary Plan creation must not overwrite an accepted row merely
because MusicBrainz later returns different data. More than one source key may
refer to the same provider artist identity, so `provider_artist_id` is not
unique.

### provider_request_cadence

Stores one durable cross-process request reservation per provider. It is
operational coordination, not provider-result cache state.

Fields:

* `provider`, the non-empty primary key such as `musicbrainz`
* `last_request_at`, the UTC timestamp of the most recently reserved request
  slot

Reservation uses a short `BEGIN IMMEDIATE` transaction. A caller that is too
early rolls back, closes the connection, sleeps, and retries; no SQLite
transaction remains open while waiting or performing HTTP I/O. Each retry
reserves its own slot. Storage failure makes the provider unavailable to the
resolver instead of allowing an uncoordinated request.

### plans

Stores scheduled operations before execution.

Minimum representative fields:

* `plan_id`
* `library_id`
* `source_run_id` nullable
* `plan_type`
* `status`
* `created_at`
* `config_hash`
* `library_root_at_plan`
* `source_root_at_plan` nullable
* `summary_json`

Storage must retain `config_hash` to preserve the reviewed configuration context and `library_root_at_plan` for the apply-time Library-root precondition.

`source_root_at_plan` records the exact external source root for Add Plans and
is copied to an Undo Plan that reverses such an import. It is nullable because
Organize and Refresh sources are Library-relative. Apply, Check, and Undo use
it to anchor external companion and unprocessed paths rather than inferring a
root from a stored absolute path.

`source_run_id` is a nullable reference to `runs.run_id`. It records the
source Run only for an Undo Plan; ordinary Plans store `NULL`. It provides
durable Undo provenance and supports the deduplication query that finds an
existing `ready`, `applying`, or `applied` Undo Plan for one source Run. It
is not globally unique because a terminal unsuccessful or cancelled Undo Plan
does not prohibit a later reviewed attempt. Undo behavior remains authoritative
in [Undo Execution](../execution/undo.md).

Deleting a source Run is restricted while any Undo Plan references it.
Persistence must never silently set `source_run_id` to null or orphan that
provenance.

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
* `reverses_event_id` nullable
* `companion_asset_id` nullable
* `owner_action_id` nullable
* `content_hash_at_plan`
* `metadata_hash_at_plan`
* `artist_name_diagnostics_json` nullable
* `status`
* `reason`
* `sort_order`

`conflict` and `error` are not action types. They are represented by status and reason values.

`artist_name_diagnostics_json` is `NULL` when the action did not pass through
artist-name resolution, including pre-resolution blocked actions and Undo
actions. Otherwise it stores one typed object with `artist` and `album_artist`
members. Each member records the nullable source and resolved values, the
resolution provenance, and the nullable resolution issue observed during Plan
creation. Repositories restore this JSON as the domain diagnostic pair without
re-resolving names or deciding whether the result was acceptable.

`reverses_event_id` references the succeeded source `file_events.event_id` for
each Undo PlanAction and is `NULL` for every non-Undo action. It is durable
event identity: Undo eligibility and regeneration must not infer reversal from
matching paths or Track IDs. Non-null values are unique within one Plan.

Deleting a source FileEvent is restricted while any Undo PlanAction references
it. A future history-deletion feature would need an explicit safe whole-
dependency contract; the initial migration must not use `SET NULL` or silently
cascade away provenance.

`companion_asset_id` is deliberately nullable and has no foreign key:
planning preallocates a stable asset identity before successful Apply creates
managed state. `owner_action_id` optionally identifies the semantic audio
owner when that owner also has an action in the same Plan; otherwise
`track_id` identifies an already managed owner. The self-reference uses
`ON DELETE SET NULL`, while insert/update triggers reject cross-Plan
ownership. Writers therefore persist an owner row before a companion row even
when reverse Undo execution order processes the companion first.

A `move_unprocessed` row uses the same table without a new managed-state
table. `track_id`, `companion_asset_id`, `owner_action_id`, metadata hash,
artist-name diagnostics, and dependency rows are absent; source and target are
absolute, content-only values validated against `plans.source_root_at_plan`.
Every candidate is stored regardless of the presentation preview limit.

### plan_action_dependencies

Stores immutable same-Plan execution edges independently from semantic
ownership and sort order.

Fields:

* `plan_id`
* `action_id`
* `depends_on_action_id`

The primary key is `(action_id, depends_on_action_id)`; self-dependency is
rejected. Composite foreign keys require both actions to belong to
`plan_id` and cascade only when their owning PlanAction is deleted. Reads
order by `depends_on_action_id` so inspection surfaces expose a stable list.

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

A Run is created before applying PlanActions and before any Library-managed
audio or companion mutation. The single-use Plan contract permits at most one
Run per Plan.

### operations

Stores durable state for accepted background requests. An
Operation is distinct from a FileEvent: it supports acceptance, idempotency,
status polling, retention, and restart reconciliation, while a FileEvent is
evidence for one attempted Library-managed audio or companion mutation.

Minimum representative fields:

* `operation_id`
* `library_id` nullable
* `plan_id` nullable
* `run_id` nullable
* `kind`
* `status`
* `idempotency_key`
* `request_fingerprint`
* `result_kind` nullable
* `result_json` nullable
* `error_code` nullable
* `error_json` nullable
* `requested_at`
* `started_at` nullable
* `updated_at`
* `completed_at` nullable
* `result_expires_at` nullable
* `tombstone_expires_at` nullable

`operation_id` is the Operation identity. `idempotency_key` is globally
unique in the application database. `request_fingerprint` represents the
validated canonical request; the raw request body is not persisted for
idempotency. `library_id`, `plan_id`, and `run_id` are nullable references
that record associations when the Operation kind has created or selected those
resources, but they do not replace the resources' own identities.

`kind` and `status` are constrained to the closed catalogs in
[Durable Operation Contract](operations.md#identity-and-kinds) and
[Operation Lifecycle](operations.md#lifecycle). Typed success and failure
persistence requires a discriminant (`result_kind` or `error_code`) together
with its validated, redacted payload; an untyped JSON payload alone is not a
business-policy boundary. The pre-release progress columns were removed
because no runtime producer existed; the row stores only lifecycle state the
application can produce.

Terminal writes derive `result_expires_at` at 24 hours and
`tombstone_expires_at` at 30 days after `completed_at`. Result/error payloads
may be cleared at result expiry, but the minimal Operation and globally unique
idempotency tombstone remain until tombstone expiry. The authoritative lookup
behavior is in [Retention And Lookup](operations.md#retention-and-lookup).

The persistence-versus-mutation distinction is recorded in
[ADR 0002](../decisions/0002-durable-operations-over-polling.md).

#### Atomic Apply Acceptance

Apply acceptance occurs while the shared exclusive-operation lock is held:

1. Verify the current Library root against `library_root_at_plan`.
2. In one SQLite transaction, classify the idempotency key before touching the
   Plan. An exact retained kind/fingerprint returns that Operation; a mismatch
   conflicts; only a new key proceeds.
3. For a new key, compare-and-set the Plan from `ready` to `applying`, insert
   its `running` Run, and insert the reserved `queued` Operation linked to that
   Plan and Run.
4. Commit all three writes before dispatching the worker.

If the compare-and-set or either insert fails, the transaction rolls back all
three writes. No competing request may observe a Run or Operation without the
single-use Plan claim. The database transaction does not include later
filesystem mutation; pending FileEvent ordering remains authoritative in
[Apply Execution](../execution/apply.md). The lock mechanism and rationale are
recorded in
[ADR 0003](../decisions/0003-cross-process-exclusive-operation-lock.md).

### file_events

Stores durable operation-log entries for attempted Library-managed audio or
companion mutations.

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
* `companion_asset_id` nullable

`companion_asset_id` is retained as durable mutation provenance without a
foreign key because the pending event must exist before a new asset row. A
`move_unprocessed_file` row keeps it null and retains the trackless action's
absolute rooted paths. FileEvents are used for run detail display, diagnosing
partial failures, crash inspection, Check, and undo plan creation.

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
* `companion_asset_id` nullable
* `detail` nullable

`issue_seq` is an auto-incrementing sequence that preserves the insertion order of one check run's findings and backs keyset pagination for check browsing. Rows are removed when their owning `check_runs` row is replaced or deleted.

## Migrations

OMYM2 performed a pre-release clean-slate schema cutover on 2026-07-16. The
packaged history contains exactly one current baseline:
`202607160001_baseline.sql`. It creates every table, index, trigger, foreign
key, check constraint, and closed-value constraint described by this contract.
There are no backfills, table-rebuild upgrades, or inferred Undo provenance.

A fresh database file is the only supported starting point. The runner rejects
an existing database when it finds application tables without migration
metadata, application tables with no applied migration, or applied migration
names that are not an exact prefix of the packaged history. The error instructs
the developer to delete the SQLite file and restart OMYM2. It never adopts or
rewrites unsupported pre-release state.

Every future schema change needs tests for migration execution, the resulting
complete schema, repository persistence, transactional rollback, packaged
resources, and affected constraints or path representations.

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

The baseline creates these Operation indexes:

* `uq_operations_idempotency_key`, a unique index on
  `operations (idempotency_key)`.
* `uq_operations_single_active`, a unique expression index on `1` where status
  is `queued` or `running`; this enforces at most one active Operation in the
  application database.
* `idx_operations_status_updated` on
  `operations (status, updated_at, operation_id)` for active and unfinished
  Operation lookup.
* `idx_operations_result_expiry` on
  `operations (result_expires_at, operation_id)` and
  `idx_operations_tombstone_expiry` on
  `operations (tombstone_expires_at, operation_id)` for retention cleanup.
* `idx_operations_plan` on `operations (plan_id, operation_id)` and
  `idx_operations_run` on `operations (run_id, operation_id)` for association
  lookup.

The baseline creates these single-use and Undo provenance indexes:

* `uq_runs_plan_id`, a unique index on `runs (plan_id)` that enforces at most
  one Run for a single-use Plan.
* `idx_plans_source_run_status` on
  `plans (source_run_id, status, created_at, plan_id)` for prior Undo Plan and
  deduplication lookup.
* `uq_plans_active_undo_source_run`, a unique partial index on
  `plans (source_run_id)` where `source_run_id` is non-null and status is
  `ready`, `applying`, or `applied`.
* `idx_plan_actions_reverse_event_status` on
  `plan_actions (reverses_event_id, status, action_id)` for prior reversal
  lookup.
* `uq_plan_actions_plan_reverse_event`, a unique partial index on
  `plan_actions (plan_id, reverses_event_id)` where `reverses_event_id` is
  non-null.

These unique constraints are defense in depth behind the cross-process lock
and compare-and-set usecases.

The baseline creates these Track, action, and Run browsing indexes:

* `idx_tracks_current_path` on `tracks (current_path, track_id)` — backs Track list ordering and keyset pagination (`GET /api/tracks`).
* `idx_tracks_status` on `tracks (library_id, status)` — backs Track status filtering and status facet counts scoped to one Library.
* `idx_plan_actions_status` on `plan_actions (plan_id, status)` — backs PlanAction status filtering within one Plan.
* `idx_plan_actions_type` on `plan_actions (plan_id, action_type)` — backs PlanAction type filtering within one Plan.
* `idx_runs_started` on `runs (started_at, run_id)` — backs Run history ordering and keyset pagination.

The baseline creates this CheckIssue browsing index:

* `idx_check_issues_library_type` on `check_issues (library_id, issue_type, issue_seq)` — backs CheckIssue Library/issue_type filtering, ordering, and keyset pagination (`GET /api/check`).

The baseline creates these Plan browsing indexes:

* `idx_plans_created` on `plans (created_at, plan_id)` — backs Plan list ordering and keyset pagination (`GET /api/plans`).
* `idx_plans_library_created` on `plans (library_id, created_at, plan_id)` — backs Library-scoped Plan ordering and keyset pagination.

The baseline creates these supporting indexes:

* `idx_check_issues_check_run_id` on `check_issues (check_run_id)` — backs foreign-key lookup and cascade cleanup when replacing a CheckRun.
* `idx_file_events_library_status` on `file_events (library_id, status, sequence_no)` — backs ordered pending-FileEvent lookup for one Library during `check`.

The baseline omits two redundant single-column indexes whose lookup prefixes are covered by composite indexes:

* `idx_tracks_library_id`, superseded by indexes beginning with `tracks.library_id`.
* `idx_plans_library_id`, superseded by `idx_plans_library_created`.

The baseline defines:

* nullable `tracks.size`, constrained to nonnegative integer values when present
* nullable `tracks.mtime`, stored as timestamp text when present

Both values remain `NULL` until a verified snapshot is persisted for that Track.

The baseline also creates:

* `idx_companion_assets_library_current_path` for stable Library/path reads
* `idx_companion_assets_library_content_hash` for Library-scoped hash lookup
* `uq_plan_actions_action_plan` for composite same-Plan references
* `idx_plan_action_dependencies_depends_on` for reverse dependency lookup

It creates `idx_check_issues_companion_asset` on
`check_issues (companion_asset_id, issue_seq)`.

## Stored JSON Fields

Stored JSON fields, such as `metadata_json`, `summary_json`, and typed
Operation result/error payloads, are persistence details. Their explicit
discriminants select a validated typed model; repositories must not inspect
arbitrary JSON shape to decide business policy. The raw Operation request body
is not a stored JSON field.

## Timestamp Policy

Timestamps are persisted to support history, inspection, retention, and deterministic tests through the `Clock` port. A non-null Track `mtime` baseline follows the same UTC timestamp serialization as other persisted timestamps. Operation expiry timestamps are derived from its terminal `completed_at` through that same clock boundary. Accepted artist-name `accepted_at` values use the same UTC serialization.

Adapters may serialize timestamps, but usecases decide when state transitions occur.
