---
type: Storage Design
title: Storage
description: Defines application-root selection, TOML raw-revision and atomic-save ownership, artist-name storage boundaries, SQLite managed state, durable Operation and FileEvent storage, consistency, reproducibility, and path responsibilities.
tags: [storage, sqlite, toml, persistence, artist-names, desktop]
timestamp: 2026-07-15T20:47:24+09:00
---

# Storage

This document is authoritative for OMYM2 storage responsibilities, the TOML-vs-SQLite boundary, DB consistency principles, reproducibility principles, and high-level stored path policy.

Detailed contracts live in:

* [contracts/config.md](contracts/config.md) for AppConfig, TOML schema, defaults, validation, versioning, PathPolicyConfig, metadata policy, collision policy, and UI settings.
* [contracts/db-schema.md](contracts/db-schema.md) for SQLite tables, migrations, stored JSON fields, timestamp policy, and repository persistence boundaries.
* [contracts/operations.md](contracts/operations.md) for durable background Operation identity, lifecycle, idempotency, polling, retention, and restart reconciliation.
* [contracts/path-identity-storage.md](contracts/path-identity-storage.md) for Library identity, Track identity, relink behavior, Library-root-relative stored paths, PathResolver boundaries, and absolute-path exceptions.
* [contracts/status-reason-catalog.md](contracts/status-reason-catalog.md) for allowed status, reason, action type, event type, error code, and check issue values.

Domain concepts are defined in [DOMAIN.md](DOMAIN.md), and execution order is defined in [execution/](execution/).

## Storage Boundary

OMYM2 uses TOML for editable application settings and SQLite for managed state,
plans, runs, durable background Operations, durable FileEvent mutation logs,
and persisted check diagnostics.

| Concern | Store |
| --- | --- |
| Editable settings | TOML |
| Editable artist ID entries | TOML |
| Editable full artist display-name preferences | TOML |
| Config defaults and validation results | Config adapter / AppConfig |
| Raw Config revision and atomic replacement | Config adapter / TOML file |
| Managed Library and Track state | SQLite |
| Plans and PlanActions | SQLite |
| Runs and FileEvents | SQLite |
| Durable background Operations | SQLite |
| CheckRuns and CheckIssues | SQLite |
| Accepted provider artist names and provenance | SQLite |
| Actual music files | Filesystem, not DB |

Config and DB files are created lazily when an operation needs them. Desktop
startup creates its log directory and current log file. Missing Config or DB is
not an error by itself; missing required paths are errors only for operations
that need those paths.

Config files, internal DB files, and desktop logs stay under the selected
application root, excluding user-selected Library and Incoming paths.

## Application Root Selection

The CLI and packaged desktop application deliberately select different default
application roots:

| Surface | Default application root |
| --- | --- |
| CLI, including `omym2 settings` | Current working directory |
| Windows 11 x64 desktop application | `%LOCALAPPDATA%\OMYM2` |

The desktop root is stable and independent of the extracted PyInstaller
application directory. Its primary files are:

```text
%LOCALAPPDATA%\OMYM2\.config\config.toml
%LOCALAPPDATA%\OMYM2\.data\omym2.sqlite3
%LOCALAPPDATA%\OMYM2\.data\logs\omym2-desktop.log
```

Replacing, moving, or deleting an extracted desktop archive does not migrate,
replace, or delete this root. A later archive therefore reuses the same desktop
Config and SQLite state. Removing desktop state is a separate, explicit act of
deleting `%LOCALAPPDATA%\OMYM2`; package removal must not do it implicitly.

The CLI remains current-working-directory rooted. It does not automatically
discover or redirect to the desktop root, and the desktop application does not
adopt the CLI's working directory. A caller that needs one state set must use
the same explicit application-root selection rather than relying on package
location.

## TOML Responsibility

Settings are managed in TOML, not SQLite.

The exact settings file location, TOML schema, and PathPolicyConfig rules are authoritative in [contracts/config.md](contracts/config.md).

Domain and usecases do not read TOML directly. Config loading and saving are adapter concerns.

The opaque raw `config_revision`, compare-and-set recheck, temporary-file
sync, and same-filesystem atomic replacement remain Config-adapter
responsibilities over the TOML file. They are not TOML keys, AppConfig fields,
or SQLite state. The authoritative protocol is
[Raw Storage Revision And Atomic Save](contracts/config.md#raw-storage-revision-and-atomic-save);
its shared lock is recorded in
[ADR 0003](decisions/0003-cross-process-exclusive-operation-lock.md).

Artist ID entries are application config. They are stored in TOML because they
are user-editable path/config values, not managed Library state.

Full artist display-name preferences are also application config and remain
separate from compact artist IDs. Positive automatic provider results are not
editable config: accepted names and their provenance are stored in SQLite so
the same source key resolves deterministically across later Plans.

## SQLite Responsibility

OMYM2 uses a single application database.

The DB records OMYM2's last known managed state, scheduled plans, execution
attempts, durable background-request Operations, durable Library music file
mutation logs, and persisted check diagnostics.

The DB is not used as the editable settings store. It is not the source of truth for the actual filesystem. The filesystem can diverge from the DB because users or external tools may move, delete, rename, or modify files. Such divergence is detected by `check`.

The DB stores Library identity and registration state. Registration is distinct from Track rows and is not defined by whether the `tracks` table has rows.

The exact database file location and schema are authoritative in [contracts/db-schema.md](contracts/db-schema.md). Main information to store:

```text
libraries
tracks
plans
plan_actions
runs
file_events
operations
check_runs
check_issues
accepted_artist_names
```

`accepted_artist_names` is a global sticky provider cache rather than a
Library-managed table. It does not carry `library_id`, does not replace raw
Track metadata, and does not authorize a repository to recalculate paths.

`check` replaces each Library's prior CheckRun and CheckIssues with its latest
diagnostics. It does not change Tracks, Plans, Runs, or Library music files.
The detailed persistence and browsing contract is in
[contracts/db-schema.md](contracts/db-schema.md#check_runs) and
[execution/check.md](execution/check.md).

## Durable Background Operations

An Operation is SQLite state for one accepted background request. It preserves
idempotent acceptance, progress, typed completion or failure, and interruption
evidence across a lost response or process restart. It may link to a Library,
Plan, or Run, but it never replaces those records.

A FileEvent has a narrower safety role: it is durable evidence for one attempted
Library music file mutation and is persisted as `pending` immediately before
that mutation. Operation progress or completion cannot stand in for a
FileEvent. The authoritative distinction and lifecycle are in
[Durable Operation Contract](contracts/operations.md#operation-versus-fileevent);
the persistence and polling decision is recorded in
[ADR 0002](decisions/0002-durable-operations-over-polling.md).

## Repository Boundary

The DB adapter persists and restores domain models. It must not contain business rules such as conflict judgment, duplicate judgment, canonical path calculation, metadata validation, or PlanAction status decisions.

Repositories must preserve `library_id` on Library-managed records and restore path fields according to [contracts/path-identity-storage.md](contracts/path-identity-storage.md).

Accepted artist-name persistence exposes exact lookup by an already-derived
source key and insert-if-absent semantics. Key derivation, lookup eligibility, provider
matching, precedence over raw metadata, and any decision to surface an
ambiguous result remain naming-feature rules above the repository.

## Track Stat Baselines

SQLite may store nullable Track `size` and `mtime` values associated with the last verified snapshot. The exact columns, constraints, and migration behavior are defined in [contracts/db-schema.md](contracts/db-schema.md#tracks). Existing rows remain ineligible for stat trust while either value is `NULL`.

Verified workflows populate or refresh the baseline when they persist a Track from a complete snapshot: organize does so while accepting a scanned candidate, and successful apply does so after its mandatory full source precondition for a move or `refresh_metadata` action. Reusing an already eligible baseline during opted-in organize preserves that same verified state.

Refresh plan creation and check never backfill or update Track baselines. A no-action refresh therefore leaves an existing null baseline unchanged; users can backfill through organize, while a later applied refresh action updates it through apply.

Stat trust is an explicit per-command runtime choice, not TOML application configuration. Its command-specific eligibility and risk rules are authoritative in [execution/organize.md](execution/organize.md), [execution/refresh.md](execution/refresh.md), and [execution/check.md](execution/check.md). Apply never honors stat trust.

## DB Consistency

The DB must preserve enough state to inspect interrupted or partially failed apply attempts:

* Apply acceptance atomically commits the Plan's `ready -> applying` claim, a
  running Run, and a queued Operation before worker dispatch
* a Run exists for the apply attempt
* the Plan records that apply has started
* each Library music file mutation has a pending FileEvent before the mutation starts
* FileEvents, PlanActions, Tracks, Runs, and Plans are updated as the apply attempt progresses

The exact acceptance transaction is defined in
[Atomic Apply Acceptance](contracts/db-schema.md#atomic-apply-acceptance). It
does not make later DB and filesystem mutation atomic.

If the process crashes, pending or partially recorded FileEvents remain available for inspection. Recovery behavior is defined in [execution/model.md](execution/model.md#durable-file-mutation-log).

Apply retains one lazily opened SQLite connection for the lifetime of one apply usecase. Every inner UnitOfWork block remains an independent `BEGIN` / commit-or-rollback transaction, including the commit that persists a PENDING FileEvent before its Library music file mutation. The connection is closed deterministically on the same thread when the usecase ends. UnitOfWork blocks outside that outer scope keep their close-per-transaction behavior; connections are not process-global or shared across Web requests or threads.

Connections enable `journal_mode = WAL` for read/write concurrency and explicitly set `synchronous = FULL`: SQLite build defaults may select NORMAL for WAL, which only guarantees a WAL fsync at the next checkpoint. Under NORMAL, a committed PENDING FileEvent could remain unsynced in the WAL file while the subsequent Library music file move already executed, reopening the crash-safety gap the pending-FileEvent-before-mutation ordering exists to close. Reusing the apply connection changes checkpoint timing only: normal WAL auto-checkpointing bounds growth, and deterministic final connection close allows SQLite's last-connection checkpoint. OMYM2 does not force an extra per-transaction or apply-end checkpoint.

WAL backs each database with a `-wal` and `-shm` shared-memory file, which can misbehave over Windows-mounted 9p/DrvFs paths (for example, running from `/mnt/c` under WSL2); the database should live on a native filesystem.

## Restart And Interruption

Before accepting another exclusive operation after startup, reconciliation
acquires the shared lock and atomically updates each retained unfinished
Operation together with any associated Apply Plan, Run, and PlanActions. It
never resumes or redispatches work. An interrupted Operation with a nonterminal
association remains eligible for an idempotent repair pass.

When an interrupted Apply already reserved a Run, reconciliation uses only
durable PlanAction and FileEvent evidence. It leaves every `pending` FileEvent
pending, applies planned skips, and marks unconfirmed planned move/metadata
actions with `operation_interrupted`. If all action/event evidence is
determinate it derives the normal terminal result;
otherwise it uses `partial_failed` only when an eligible action is durably
confirmed applied and `failed` when none is. It directs the user to Check plus
manual review and never infers a filesystem outcome.

The complete algorithm, including dispatch-failure handling, is authoritative
in
[Restart And Dispatch Reconciliation](contracts/operations.md#restart-and-dispatch-reconciliation).

## Reproducibility

The DB does not store editable settings. However, a Plan must preserve enough information to explain and safely apply the reviewed result.

In the initial version, this means:

* store concrete path references in PlanActions according to [contracts/path-identity-storage.md](contracts/path-identity-storage.md)
* store `config_hash` and `library_root_at_plan` in Plans
* apply recorded PlanActions instead of recalculating paths from the latest config
* reject or expire unapplied Plans when the owning Library root has changed since plan creation

Full config snapshots or path policy snapshots are deferred until long-lived unapplied Plans require stronger reproducibility.

## Path Representation Summary

This is a summary. The authoritative path and identity contract is [contracts/path-identity-storage.md](contracts/path-identity-storage.md).

Stored paths are separated from filesystem execution paths.

Library-managed paths are stored relative to the Library root. `libraries.root_path` is the current absolute filesystem location used by PathResolver at I/O boundaries.

Domain models and repositories do not resolve absolute paths. When filesystem I/O is required, PathResolver combines `libraries.root_path` with a Library-root-relative path to create an absolute path.
