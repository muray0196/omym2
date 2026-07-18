---
type: Contract
title: DB Schema Contract
description: SQLite tables, constraints, indexes, migrations, JSON and timestamp policy for all persisted state.
tags: [database, sqlite, schema, migrations, artist-names, musicbrainz, companions, unprocessed, provenance]
timestamp: 2026-07-18T15:00:00+09:00
---

# DB Schema Contract

Authoritative for the SQLite schema contract, table responsibilities, migrations, stored JSON fields, timestamp policy, and repository persistence boundaries. Storage summary: [../STORAGE.md](../STORAGE.md); Operation lifecycle/retention: [operations.md](operations.md); path/identity representation: [path-identity-storage.md](path-identity-storage.md). Do not invent exact SQL here unless it exists in the implementation; describe required behavior as a contract when implementation evidence is missing.

## Responsibilities

The DB records last known managed state, scheduled plans, execution attempts, durable background-request state, durable Library music file operation logs, and persisted check diagnostics. The DB is not: the editable settings store; the source of truth for the filesystem; responsible for reading metadata, scanning or moving files, calculating canonical paths, or deciding conflicts, duplicates, metadata validity, or PlanAction status. Repositories persist and restore domain models without inventing business rules. Every Library-managed record carries `library_id`. Schema changes require migration and integration tests.

## Location

`.data/omym2.sqlite3`. The `.data/` directory is reserved for OMYM2 internal data under the application root.

## Tables

`libraries`, `tracks`, `companion_assets`, `plans`, `plan_actions`, `plan_action_dependencies`, `runs`, `file_events`, `operations`, `check_runs`, `check_issues`, `accepted_artist_names`, `provider_request_cadence`

### libraries

Current identity, root path, and acceptance state of each Library. Fields: `library_id`, `root_path`, `path_policy_hash`, `registered_at`, `status`, `created_at`, `updated_at`. `library_id` is stable; `root_path` is mutable and used for runtime path resolution.

### tracks

Current managed state of files known to OMYM2. Fields: `track_id`, `library_id`, `current_path`, `canonical_path`, `content_hash`, `metadata_hash`, nullable `size`, nullable `mtime`, `metadata_json`, `status`, timestamps.

Paths and hashes are OMYM2's last known Library-root-relative values. Nullable `size`/`mtime` store the stat baseline of a verified snapshot; rows without a baseline keep `NULL` in both. Non-null `size` is nonnegative. These are optimization hints, not Track identity or proof of existence/unchangedness.

### companion_assets

Last confirmed managed state of one lyrics or artwork file; separate from `tracks`, no metadata JSON or metadata hash. Fields: `companion_asset_id`, `library_id`, `kind`, `owner_track_id`, `current_path`, `canonical_path`, `content_hash`, nullable `size`/`mtime`, `status`, `first_seen_at`, `last_seen_at`, `updated_at`.

`library_id` and `owner_track_id` use restricted foreign keys so managed companion history is never silently orphaned. Paths are normalized Library-root-relative. Non-null size is nonnegative. Repository listing order is `current_path, companion_asset_id`.

### accepted_artist_names

The one editable mapping from original artist text to an English artist name. MusicBrainz populates positive rows automatically; users add, edit, or delete the same rows through Settings. Global feature data — no `library_id`.

Fields: `source_key` (non-empty derived lookup key, primary key), `source_name` (non-empty original metadata text), `resolved_name` (non-empty English display name), `provider` (`musicbrainz` | `user`, last writer), `provider_artist_id` (canonical MusicBrainz UUID for automatic rows, null for user rows), `selected_name_kind` (`alias` | `alias_sort_name` | `sort_name` for automatic rows, null for user rows), `selected_locale` (nullable; permitted only for alias/alias-sort-name selections), `accepted_at` (UTC timestamp of acceptance or latest user edit).

`selected_name_kind` records the exact MusicBrainz field used: `alias` = alias object's `name`; `alias_sort_name` = alias object's `sort-name`; `sort_name` = artist object's `sort-name`. Alias selections retain their MusicBrainz locale (e.g., `ja-Latn`) so Settings can distinguish a Japanese Latin alias from artist-level fallbacks. Selection never uses the artist object's own `name`: an artist-level Latin fallback is only ever accepted as `sort_name`, so the CHECK constraint does not carry a `name` value (`202607180001_drop_unused_artist_name_kind.sql` removed it after confirming no selection path ever produced it).

The naming feature derives every lookup/insertion key via the pure [ArtistNameSourceKey](../DOMAIN.md#artistnamesourcekey) contract before repository access; the repository compares keys exactly. Missing or whitespace-only source text produces no key and must not reach the repository. Automatic insertion is sticky: `insert_if_absent` does nothing and returns false when `source_key` exists, so Plan creation never overwrites an accepted row because MusicBrainz later returns different data. Revision-checked Settings saves may upsert user rows or delete mappings; an edited automatic row becomes a `user` row and clears provider-specific fields. `provider_artist_id` is not unique (multiple source keys may map to one provider artist).

### provider_request_cadence

One durable cross-process request reservation per provider — operational coordination, not result cache. Fields: `provider` (non-empty primary key, e.g., `musicbrainz`), `last_request_at` (UTC timestamp of the most recently reserved slot). Reservation uses a short `BEGIN IMMEDIATE` transaction; a too-early caller rolls back, closes the connection, sleeps, retries, and each retry reserves its own slot. No transaction stays open during waiting or HTTP I/O. Storage failure makes the provider unavailable rather than allowing an uncoordinated request.

### plans

Scheduled operations before execution. Fields: `plan_id`, `library_id`, nullable `source_run_id`, `plan_type`, `status`, `created_at`, `config_hash`, `library_root_at_plan`, nullable `source_root_at_plan`, `summary_json`.

`config_hash` preserves the reviewed configuration context; `library_root_at_plan` backs the apply-time Library-root precondition. `source_root_at_plan` records the exact external source root for Add Plans and is copied to an Undo Plan reversing such an import; nullable because Organize/Refresh sources are Library-relative. Apply, Check, and Undo use it to anchor external companion and unprocessed paths rather than inferring a root from a stored absolute path.

`source_run_id` references `runs.run_id` for Undo Plans only (ordinary Plans store `NULL`): durable Undo provenance plus the deduplication query finding an existing `ready`/`applying`/`applied` Undo Plan for one source Run. Not globally unique — a terminal unsuccessful or cancelled Undo Plan does not prohibit a later reviewed attempt ([Undo Execution](../execution/undo.md)). Deleting a source Run is restricted while any Undo Plan references it; persistence must never silently null `source_run_id` or orphan provenance.

### plan_actions

Each reviewed action inside a Plan. Fields: `action_id`, `plan_id`, `library_id`, nullable `track_id`, `action_type`, `source_path`, `target_path`, nullable `reverses_event_id`, nullable `companion_asset_id`, nullable `owner_action_id`, `content_hash_at_plan`, `metadata_hash_at_plan`, nullable `artist_name_diagnostics_json`, `status`, `reason`, `sort_order`.

`conflict` and `error` are not action types; they are status/reason values.

`artist_name_diagnostics_json` is `NULL` when the action did not pass through artist-name resolution (pre-resolution blocked actions, Undo actions). Otherwise it stores one typed object with `artist` and `album_artist` members, each recording nullable source and resolved values, resolution provenance, and the nullable resolution issue observed during Plan creation. Repositories restore it as the domain diagnostic pair without re-resolving or judging acceptability.

`reverses_event_id` references the succeeded source `file_events.event_id` for each Undo PlanAction; `NULL` for every non-Undo action. Durable event identity: Undo eligibility and regeneration must not infer reversal from matching paths or Track IDs. Non-null values are unique within one Plan. Deleting a source FileEvent is restricted while any Undo PlanAction references it; the migration must not use `SET NULL` or silently cascade away provenance.

`companion_asset_id` is nullable with no foreign key: planning preallocates a stable asset identity before successful Apply creates managed state. `owner_action_id` optionally identifies the semantic audio owner when that owner has an action in the same Plan; otherwise `track_id` identifies an already managed owner. The self-reference uses `ON DELETE SET NULL`; insert/update triggers reject cross-Plan ownership. Writers persist an owner row before a companion row even when reverse Undo execution processes the companion first.

A `move_unprocessed` row uses this table with no new managed-state table: `track_id`, `companion_asset_id`, `owner_action_id`, metadata hash, diagnostics, and dependency rows are absent; source and target are absolute content-only values validated against `plans.source_root_at_plan`. Every candidate is stored regardless of the presentation preview limit.

### plan_action_dependencies

Immutable same-Plan execution edges, independent of semantic ownership and sort order. Fields: `plan_id`, `action_id`, `depends_on_action_id`. Primary key `(action_id, depends_on_action_id)`; self-dependency rejected. Composite foreign keys require both actions to belong to `plan_id` and cascade only when the owning PlanAction is deleted. Reads order by `depends_on_action_id` for stable inspection lists.

### runs

Execution attempts for applying Plans. Fields: `run_id`, `plan_id`, `library_id`, `status`, `started_at`, `completed_at`, `error_summary`. A Run is created before applying PlanActions and before any Library-managed mutation. The single-use Plan contract permits at most one Run per Plan.

### operations

Durable state for accepted background requests; distinct from FileEvents (acceptance, idempotency, polling, retention, restart reconciliation vs. mutation evidence).

Fields: `operation_id`, nullable `library_id`/`plan_id`/`run_id`, `kind`, `status`, `idempotency_key`, `request_fingerprint`, nullable `result_kind`/`result_json`/`error_code`/`error_json`, `requested_at`, nullable `started_at`, `updated_at`, nullable `completed_at`/`result_expires_at`/`tombstone_expires_at`.

`idempotency_key` is globally unique in the application database. `request_fingerprint` represents the validated canonical request; the raw body is not persisted. The nullable references record associations when the kind created or selected those resources without replacing their identities. `kind`/`status` are constrained to the closed catalogs in [Durable Operation Contract](operations.md#identity-and-kinds) and [Operation Lifecycle](operations.md#lifecycle). Typed success/failure persistence requires a discriminant (`result_kind` or `error_code`) with its validated redacted payload; untyped JSON alone is not a business-policy boundary. Pre-release progress columns were removed. Terminal writes derive `result_expires_at` (+24 h) and `tombstone_expires_at` (+30 d) from `completed_at`; payloads may clear at result expiry, but the minimal Operation and idempotency tombstone remain until tombstone expiry ([Retention And Lookup](operations.md#retention-and-lookup)). Decision: [ADR 0002](../decisions/0002-durable-operations-over-polling.md).

#### Atomic Apply Acceptance

While the shared exclusive-operation lock is held:

1. Verify the current Library root against `library_root_at_plan`.
2. In one SQLite transaction, classify the idempotency key before touching the Plan: an exact retained kind/fingerprint returns that Operation; a mismatch conflicts; only a new key proceeds.
3. For a new key, compare-and-set the Plan `ready` → `applying`, insert its `running` Run, and insert the reserved `queued` Operation linked to that Plan and Run.
4. Commit all three writes before dispatching the worker.

If the compare-and-set or either insert fails, the transaction rolls back all three writes; no competing request may observe a Run or Operation without the single-use Plan claim. The transaction does not include later filesystem mutation — pending FileEvent ordering stays authoritative in [Apply Execution](../execution/apply.md). Lock mechanism: [ADR 0003](../decisions/0003-cross-process-exclusive-operation-lock.md).

### file_events

Durable operation-log entries for attempted Library-managed audio or companion mutations. Fields: `event_id`, `library_id`, `run_id`, `plan_action_id`, `event_type`, `source_path`, `target_path`, `status`, `started_at`, `completed_at`, `error_code`, `error_message`, `sequence_no`, nullable `companion_asset_id`.

`companion_asset_id` is durable mutation provenance without a foreign key because the pending event must exist before a new asset row. A `move_unprocessed_file` row keeps it null and retains the trackless action's absolute rooted paths. FileEvents back run detail display, partial-failure diagnosis, crash inspection, Check, and undo plan creation.

### check_runs

One row per Library for that Library's latest completed check run. Fields: `check_run_id`, `library_id`, `checked_at`, `total_count`. Each new check run replaces that Library's prior row and prior `check_issues` rows — findings are latest-run-only, never accumulated.

### check_issues

Findings of one check run. Fields: `issue_seq`, `check_run_id`, `library_id`, `issue_type`, nullable `path`/`track_id`/`plan_id`/`companion_asset_id`/`detail`. `issue_seq` auto-increments, preserving insertion order and backing keyset pagination. Rows are removed when their owning `check_runs` row is replaced or deleted.

## Migrations

The pre-release clean-slate cutover on 2026-07-16 starts history at `202607160001_baseline.sql`. Forward migrations: `202607170001_editable_artist_name_mappings.sql` (user-supplied mappings, nullable provider provenance), `202607170002_artist_sort_name_mapping.sql` (adds `sort_name` to the automatic-selection catalog), `202607170003_artist_alias_sort_name_provenance.sql` (separates an alias object's `sort-name` from its `name`), `202607180001_drop_unused_artist_name_kind.sql` (removes the `name` selection kind from the CHECK constraint after confirming no selection path ever produces it); each preserves existing rows.

The runner rejects an existing database with application tables lacking migration metadata, application tables with no applied migration, or applied migration names that are not an exact prefix of the packaged history; the error instructs deleting the SQLite file and restarting. It never adopts or rewrites unsupported pre-release state.

Every future schema change needs tests for migration execution, resulting complete schema, repository persistence, transactional rollback, packaged resources, and affected constraints or path representations.

### Migration Safety Rules

* Applied migrations are tracked by filename: `schema_migrations` has `migration_name` as `PRIMARY KEY`. Never edit or rename a migration file that may already be applied — that silently diverges existing databases. Fix forward with a new migration file.
* Migrations run in strict lexicographic filename order (`load_packaged_migrations` sorts packaged `*.sql` by filename), so a new migration's filename must sort after every existing one.
* Each migration file and its `schema_migrations` marker apply inside a single transaction (`migration_runner.py`'s `_apply_migration` wraps script and insert in one `BEGIN`/commit, rolling back on `sqlite3.DatabaseError`), so a migration is never recorded as applied unless it fully succeeded.

## Indexes

Indexes keep the Web API's list, facet, and group-by endpoints ([web-api.md](web-api.md)) fast at scale; they are persistence details that never change table responsibilities or stored data.

Operation indexes: `uq_operations_idempotency_key` unique on `(idempotency_key)`; `uq_operations_single_active` unique expression index on `1` where status is `queued`/`running` (at most one active Operation per database); `idx_operations_status_updated` on `(status, updated_at, operation_id)`; `idx_operations_result_expiry` on `(result_expires_at, operation_id)` and `idx_operations_tombstone_expiry` on `(tombstone_expires_at, operation_id)` for retention cleanup; `idx_operations_plan` on `(plan_id, operation_id)` and `idx_operations_run` on `(run_id, operation_id)`.

Single-use and Undo provenance indexes: `uq_runs_plan_id` unique on `runs (plan_id)` (one Run per single-use Plan); `idx_plans_source_run_status` on `plans (source_run_id, status, created_at, plan_id)`; `uq_plans_active_undo_source_run` unique partial on `plans (source_run_id)` where non-null and status in (`ready`, `applying`, `applied`); `idx_plan_actions_reverse_event_status` on `plan_actions (reverses_event_id, status, action_id)`; `uq_plan_actions_plan_reverse_event` unique partial on `plan_actions (plan_id, reverses_event_id)` where non-null. These unique constraints are defense in depth behind the cross-process lock and compare-and-set usecases.

Browsing indexes: `idx_tracks_current_path` on `tracks (current_path, track_id)` (`GET /api/tracks` ordering/keyset); `idx_tracks_status` on `tracks (library_id, status)` (status filter and facet counts per Library); `idx_plan_actions_status` on `plan_actions (plan_id, status)`; `idx_plan_actions_type` on `plan_actions (plan_id, action_type)`; `idx_runs_started` on `runs (started_at, run_id)`; `idx_check_issues_library_type` on `check_issues (library_id, issue_type, issue_seq)` (`GET /api/check`); `idx_plans_created` on `plans (created_at, plan_id)` (`GET /api/plans`); `idx_plans_library_created` on `plans (library_id, created_at, plan_id)`.

Supporting indexes: `idx_check_issues_check_run_id` on `check_issues (check_run_id)` (FK lookup and cascade cleanup); `idx_file_events_library_status` on `file_events (library_id, status, sequence_no)` (ordered pending-FileEvent lookup during `check`); `idx_companion_assets_library_current_path`; `idx_companion_assets_library_content_hash`; `uq_plan_actions_action_plan` (composite same-Plan references); `idx_plan_action_dependencies_depends_on` (reverse dependency lookup); `idx_check_issues_companion_asset` on `check_issues (companion_asset_id, issue_seq)`.

Deliberately omitted as redundant: `idx_tracks_library_id` (covered by composites starting with `tracks.library_id`) and `idx_plans_library_id` (covered by `idx_plans_library_created`).

## Stored JSON Fields

Stored JSON fields (`metadata_json`, `summary_json`, typed Operation result/error payloads) are persistence details. Explicit discriminants select a validated typed model; repositories must not inspect arbitrary JSON shape to decide business policy. The raw Operation request body is not a stored JSON field.

## Timestamp Policy

Timestamps support history, inspection, retention, and deterministic tests through the `Clock` port. Non-null Track `mtime` baselines, Operation expiry timestamps (derived from terminal `completed_at`), and `accepted_at` all use the same UTC serialization. Adapters may serialize timestamps, but usecases decide when state transitions occur.
