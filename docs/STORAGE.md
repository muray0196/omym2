---
type: Storage Design
title: Storage
description: TOML-vs-SQLite storage boundary, application-root selection, durable-state responsibilities, and DB consistency rules.
tags: [storage, sqlite, toml, persistence, artist-names, musicbrainz, companions, unprocessed, desktop]
timestamp: 2026-07-18T12:00:00+09:00
---

# Storage

Authoritative for storage responsibilities, the TOML-vs-SQLite boundary, DB consistency, reproducibility, and high-level stored path policy. Detailed contracts: [contracts/config.md](contracts/config.md) (TOML schema, PathPolicyConfig), [contracts/db-schema.md](contracts/db-schema.md) (tables, migrations), [contracts/operations.md](contracts/operations.md) (durable Operations), [contracts/path-identity-storage.md](contracts/path-identity-storage.md) (identity, stored paths), [contracts/status-reason-catalog.md](contracts/status-reason-catalog.md) (allowed values). Domain concepts: [DOMAIN.md](DOMAIN.md); execution order: [execution/](execution/).

## Storage Boundary

TOML holds editable settings; SQLite holds managed state, plans, runs, durable Operations, FileEvent mutation logs, and check diagnostics.

| Concern | Store |
| --- | --- |
| Editable settings | TOML |
| Automatic artist-ID generation tunables | TOML |
| Editable romanized artist-name mappings | SQLite |
| Config defaults and validation results | Config adapter / AppConfig |
| Raw Config revision and atomic replacement | Config adapter / TOML file |
| Managed Library, Track, and CompanionAsset state | SQLite |
| Plans, PlanActions, and action dependencies | SQLite |
| Runs and FileEvents | SQLite |
| Durable background Operations | SQLite |
| CheckRuns and CheckIssues | SQLite |
| Artist-name mappings and optional provider provenance | SQLite |
| Provider request cadence reservations | SQLite |
| Actual audio, companion, and unprocessed files | Filesystem, not DB |

Config and DB files are created lazily; missing Config or DB is not an error by itself — missing required paths are errors only for operations that need them. Config, internal DB, and desktop logs stay under the selected application root, excluding user-selected Library and Incoming paths.

## Application Root Selection

| Surface | Default application root |
| --- | --- |
| CLI, including `omym2 settings` | Current working directory |
| Windows 11 x64 desktop application | `%LOCALAPPDATA%\OMYM2` |

The desktop root is stable and independent of the extracted PyInstaller directory; its primary files are `.config\config.toml`, `.data\omym2.sqlite3`, and `.data\logs\omym2-desktop.log` under `%LOCALAPPDATA%\OMYM2`. Replacing, moving, or deleting an extracted desktop archive never migrates, replaces, or deletes this root; removing desktop state is only the explicit deletion of `%LOCALAPPDATA%\OMYM2`. The CLI stays CWD-rooted; neither surface adopts the other's root — a caller needing one state set must select the same application root explicitly.

## TOML Responsibility

Settings live in TOML, not SQLite. Schema, file location, and PathPolicyConfig rules: [contracts/config.md](contracts/config.md). Domain and usecases never read TOML directly; load/save is a Config-adapter concern.

The opaque raw `config_revision`, compare-and-set recheck, temporary-file sync, and same-filesystem atomic replacement are Config-adapter responsibilities over the TOML file — not TOML keys, AppConfig fields, or SQLite state. Protocol: [Raw Storage Revision And Atomic Save](contracts/config.md#raw-storage-revision-and-atomic-save); shared lock: [ADR 0003](decisions/0003-cross-process-exclusive-operation-lock.md).

Per-artist compact IDs are internal PathPolicy output, not config or user-editable data. Romanized artist-name mappings are not config: automatic MusicBrainz results and user corrections share SQLite `accepted_artist_names` so one derived source key resolves deterministically without a second preference layer.

## SQLite Responsibility

One application database. The packaged schema starts from one 2026-07-16 clean baseline; earlier pre-release databases are not upgraded — delete the SQLite file and restart when the migration runner reports unsupported state.

The DB records last known managed state, scheduled plans, execution attempts, durable Operations, durable mutation logs, and check diagnostics. It is not the settings store and not the source of truth for the filesystem; divergence is detected by `check`. Library registration state is distinct from `tracks` rows.

Schema and file location: [contracts/db-schema.md](contracts/db-schema.md). Tables: `libraries`, `tracks`, `companion_assets`, `plans`, `plan_actions`, `plan_action_dependencies`, `runs`, `file_events`, `operations`, `check_runs`, `check_issues`, `accepted_artist_names`, `provider_request_cadence`.

* `accepted_artist_names` is the global editable romanized-name mapping: no `library_id`, does not replace raw Track metadata, and does not authorize path recalculation. Only accepted positive automatic results and explicit user mappings are stored — never misses, ambiguous matches, or provider failures. A row created during planning does not imply a Track or file mutation.
* PlanActions store the artist/album-artist resolution diagnostics observed while calculating their reviewed targets — bounded snapshots that explain a recorded action without becoming a negative provider cache or authorizing later resolution.
* `companion_assets` stores the last confirmed Library-managed lyrics/artwork state independently from Tracks. PlanAction ownership and dependency rows preserve reviewed association and ordering before an asset exists. `plans.source_root_at_plan` retains the exact external Add root anchoring later companion observation, Apply, Check, and Undo; an inverse Undo Plan copies it.
* Unprocessed collection has no managed-state table: its durable contract is the retained Add root plus trackless `move_unprocessed` PlanActions and `move_unprocessed_file` FileEvents, retaining content hash, absolute source/target shape, status, and reversal provenance without inventing a Track or CompanionAsset.
* `check` replaces each Library's prior CheckRun and CheckIssues with its latest diagnostics and mutates nothing else. Details: [contracts/db-schema.md](contracts/db-schema.md#check_runs), [execution/check.md](execution/check.md).

## Durable Background Operations

An Operation is SQLite state for one accepted background request: idempotent acceptance, lifecycle status, typed completion or failure, interruption evidence. It may link to a Library, Plan, or Run but never replaces them. A FileEvent is narrower: durable evidence for one attempted audio, companion, or unprocessed-file mutation, persisted `pending` immediately before that mutation — Operation status can never stand in for it. Authoritative: [Operation Versus FileEvent](contracts/operations.md#operation-versus-fileevent); decision: [ADR 0002](decisions/0002-durable-operations-over-polling.md).

## Repository Boundary

The DB adapter persists and restores domain models; it contains no business rules (conflict judgment, duplicate judgment, canonical path calculation, metadata validation, PlanAction status decisions). Repositories preserve `library_id` on Library-managed records and restore path fields per [contracts/path-identity-storage.md](contracts/path-identity-storage.md).

Artist-name persistence exposes lookup by an already-derived source key, automatic insert-if-absent, deterministic listing, user upsert, and deletion. Key derivation, batch deduplication, eligibility, provider matching, precedence over raw metadata, and ambiguity surfacing are naming-feature rules above the repository: [Artist Name Batch Resolution](DOMAIN.md#artist-name-batch-resolution).

## Artist-Name Mapping Transactions

No SQLite transaction stays open while MusicBrainz is contacted. A resolver reads accepted rows for its distinct unresolved source keys in one short transaction, closes it before any provider work, and commits a later short transaction only for newly accepted positive results. Automatic persistence uses `insert_if_absent`; when another writer already accepted the same source key, the resolver adopts the persisted winner over its newer provider response. Negative outcomes are never cached. A Settings save compares the complete mapping revision, then applies additions, edits, and deletions in one short transaction under the shared exclusive lock. UnitOfWork choreography: [Ports And UnitOfWork](codebase/ports-uow.md#artist-name-mapping-coordination).

## Provider Request Cadence

SQLite stores each provider's last reserved request timestamp so separate CLI, Web, or desktop processes and restarts share the same minimum MusicBrainz cadence. A caller opens a short `BEGIN IMMEDIATE` transaction, reads the provider row, reserves the current permitted slot or rolls back with the remaining delay, closes the connection before sleeping, and retries afterward. No transaction or exclusive-operation lock is held during the wait or HTTP request. The reservation limits attempts (including retries) but never claims success and creates no negative cache entries. Unavailable cadence storage fails the provider call closed to the resolver's ordinary local fallback.

## Track Stat Baselines

Nullable Track `size` and `mtime` record the last verified snapshot (columns and migration behavior: [contracts/db-schema.md](contracts/db-schema.md#tracks)). Rows with either value `NULL` stay ineligible for stat trust. Verified workflows populate or refresh the baseline when persisting a Track from a complete snapshot: organize while accepting a scanned candidate, and successful apply after its mandatory full source precondition for a move or `refresh_metadata` action. Reusing an already eligible baseline during opted-in organize preserves that verified state. Refresh plan creation and check never backfill or update baselines. Stat trust is a per-command runtime choice, not TOML config; eligibility and risk rules: [execution/organize.md](execution/organize.md), [execution/refresh.md](execution/refresh.md), [execution/check.md](execution/check.md). Apply never honors stat trust.

## Companion State

Companion snapshots contain file content/stat evidence, no music metadata or metadata hash. An already canonical companion can become managed state during Organize without a FileEvent because no mutation occurs. Relocations create or update the CompanionAsset only after the pending FileEvent's mutation succeeds; failed or unknown mutations never advance the row.

An external Add Undo keeps the CompanionAsset row and stable ID, marks it `removed`, and retains its last Library-relative current/canonical paths; the external restore destination is preserved by Plan/FileEvent history, not managed state. A definitive failed companion mutation leaves no advanced state; its PlanAction, owner-audio provenance, source root, and failed FileEvent remain the durable inputs for a later reviewed recovery Plan. A pending event never converts into recovery permission.

## Unprocessed File Evidence

A collected leftover remains an ordinary external file; SQLite stores no current-row projection for it. The forward Add PlanAction and succeeded FileEvent retain the exact source root, absolute source/target paths, and content hash needed for History, Check, and Undo. A confirmed inverse event retires that forward evidence for current-target Check diagnostics without deleting history. Apply and Undo read the recorded shape even when current unprocessed Config differs. Missing or changed collected content persists only as a CheckIssue; Check never promotes or repairs it.

## DB Consistency

The DB preserves enough state to inspect interrupted or partially failed apply attempts:

* apply acceptance atomically commits the Plan's `ready -> applying` claim, a running Run, and a queued Operation before worker dispatch ([Atomic Apply Acceptance](contracts/db-schema.md#atomic-apply-acceptance)); this does not make later DB and filesystem mutation atomic
* each audio, companion, or unprocessed-file mutation has a pending FileEvent committed before the mutation starts
* FileEvents, PlanActions, Tracks or CompanionAssets, Runs, and Plans update as the attempt progresses; after a crash, pending or partially recorded FileEvents stay inspectable, with recovery per [execution/model.md](execution/model.md#durable-file-mutation-log)

Apply retains one lazily opened SQLite connection for the lifetime of one apply usecase. Every inner UnitOfWork block remains an independent `BEGIN` / commit-or-rollback transaction, including the commit persisting a PENDING FileEvent before its mutation. The connection closes deterministically on the same thread when the usecase ends; UnitOfWork blocks outside that scope keep close-per-transaction behavior. Connections are never process-global or shared across Web requests or threads.

Connections enable `journal_mode = WAL` and explicitly set `synchronous = FULL`: WAL builds may default to NORMAL, under which a committed PENDING FileEvent could remain unsynced in the WAL while the file move already executed, reopening the crash-safety gap the pending-before-mutation ordering closes. No extra per-transaction or apply-end checkpoint is forced; WAL auto-checkpointing plus deterministic final close bound growth. WAL's `-wal`/`-shm` files can misbehave on Windows-mounted 9p/DrvFs paths (for example `/mnt/c` under WSL2); keep the database on a native filesystem.

## Restart And Interruption

Before accepting another exclusive operation after startup, reconciliation acquires the shared lock and atomically updates each retained unfinished Operation together with any associated Apply Plan, Run, and PlanActions. It never resumes or redispatches work; an interrupted Operation with a nonterminal association stays eligible for an idempotent repair pass.

When an interrupted Apply already reserved a Run, reconciliation uses only durable PlanAction and FileEvent evidence: it leaves `pending` FileEvents pending, applies planned skips, and marks unconfirmed planned actions `operation_interrupted`. With determinate evidence it derives the normal terminal result; otherwise `partial_failed` only when an eligible action is durably confirmed applied, `failed` when none is. It directs the user to Check plus manual review and never infers a filesystem outcome. Full algorithm: [Restart And Dispatch Reconciliation](contracts/operations.md#restart-and-dispatch-reconciliation).

## Reproducibility

The DB stores no editable settings, but a Plan preserves enough to explain and safely apply the reviewed result:

* concrete path references in PlanActions per [contracts/path-identity-storage.md](contracts/path-identity-storage.md)
* plan-time artist and album-artist resolution diagnostics on each PlanAction that reached name resolution
* `config_hash`, `library_root_at_plan`, and nullable external `source_root_at_plan` on Plans
* companion identity, semantic owner, and every same-Plan execution dependency stored explicitly, never inferred from sort order
* every unprocessed action, including rows beyond the presentation preview limit, with its exact root-anchored content-only path shape
* apply executes recorded PlanActions, never recalculating paths from the latest config
* unapplied Plans are rejected or expired when the owning Library root changed since plan creation

Full config or path-policy snapshots are deferred until long-lived unapplied Plans need stronger reproducibility.

## Path Representation Summary

Authoritative contract: [contracts/path-identity-storage.md](contracts/path-identity-storage.md). Library-managed paths are stored Library-root-relative; `libraries.root_path` is the current absolute filesystem location. Domain models and repositories never resolve absolute paths; PathResolver combines `libraries.root_path` with a relative path at I/O boundaries.
