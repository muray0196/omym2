---
type: Storage Design
title: Storage
description: Defines the TOML-vs-SQLite boundary, repository and Track stat-baseline responsibilities, SQLite durability rules, reproducibility, and Library-relative path policy.
tags: [storage, sqlite, toml, persistence]
timestamp: 2026-07-11T10:21:41+09:00
---

# Storage

This document is authoritative for OMYM2 storage responsibilities, the TOML-vs-SQLite boundary, DB consistency principles, reproducibility principles, and high-level stored path policy.

Detailed contracts live in:

* [contracts/config.md](contracts/config.md) for AppConfig, TOML schema, defaults, validation, versioning, PathPolicyConfig, metadata policy, collision policy, and UI settings.
* [contracts/db-schema.md](contracts/db-schema.md) for SQLite tables, migrations, stored JSON fields, timestamp policy, and repository persistence boundaries.
* [contracts/path-identity-storage.md](contracts/path-identity-storage.md) for Library identity, Track identity, relink behavior, Library-root-relative stored paths, PathResolver boundaries, and absolute-path exceptions.
* [contracts/status-reason-catalog.md](contracts/status-reason-catalog.md) for allowed status, reason, action type, event type, error code, and check issue values.

Domain concepts are defined in [DOMAIN.md](DOMAIN.md), and execution order is defined in [execution/](execution/).

## Storage Boundary

OMYM2 uses TOML for editable application settings and SQLite for managed state, plans, runs, and durable operation logs.

| Concern | Store |
| --- | --- |
| Editable settings | TOML |
| Editable artist ID entries | TOML |
| Config defaults and validation results | Config adapter / AppConfig |
| Managed Library and Track state | SQLite |
| Plans and PlanActions | SQLite |
| Runs and FileEvents | SQLite |
| Actual music files | Filesystem, not DB |

Config files, DB files, and internal directories are created lazily when commands need them. Missing config or DB is not an error by itself; missing required paths are errors only for commands that need those paths.

Config files and internal DB files must stay under the application root so OMYM2 remains portable, excluding user-selected Library and Incoming paths.

## TOML Responsibility

Settings are managed in TOML, not SQLite.

The exact settings file location, TOML schema, and PathPolicyConfig rules are authoritative in [contracts/config.md](contracts/config.md).

Domain and usecases do not read TOML directly. Config loading and saving are adapter concerns.

Artist ID entries are application config. They are stored in TOML because they
are user-editable path/config values, not managed Library state.

## SQLite Responsibility

OMYM2 uses a single application database.

The DB records OMYM2's last known managed state, scheduled plans, execution attempts, and durable Library music file operation logs.

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
```

## Repository Boundary

The DB adapter persists and restores domain models. It must not contain business rules such as conflict judgment, duplicate judgment, canonical path calculation, metadata validation, or PlanAction status decisions.

Repositories must preserve `library_id` on Library-managed records and restore path fields according to [contracts/path-identity-storage.md](contracts/path-identity-storage.md).

## Track Stat Baselines

SQLite may store nullable Track `size` and `mtime` values associated with the last verified snapshot. The exact columns, constraints, and migration behavior are defined in [contracts/db-schema.md](contracts/db-schema.md#tracks). Existing rows remain ineligible for stat trust while either value is `NULL`.

Verified workflows populate or refresh the baseline when they persist a Track from a complete snapshot: organize does so while accepting a scanned candidate, and successful apply does so after its mandatory full source precondition for a move or `refresh_metadata` action. Reusing an already eligible baseline during opted-in organize preserves that same verified state.

Refresh plan creation and check never backfill or update Track baselines. A no-action refresh therefore leaves an existing null baseline unchanged; users can backfill through organize, while a later applied refresh action updates it through apply.

Stat trust is an explicit per-command runtime choice, not TOML application configuration. Its command-specific eligibility and risk rules are authoritative in [execution/organize.md](execution/organize.md), [execution/refresh.md](execution/refresh.md), and [execution/check.md](execution/check.md). Apply never honors stat trust.

## DB Consistency

The DB must preserve enough state to inspect interrupted or partially failed apply attempts:

* a Run exists for the apply attempt
* the Plan records that apply has started
* each Library music file mutation has a pending FileEvent before the mutation starts
* FileEvents, PlanActions, Tracks, Runs, and Plans are updated as the apply attempt progresses

If the process crashes, pending or partially recorded FileEvents remain available for inspection. Recovery behavior is defined in [execution/model.md](execution/model.md#durable-operation-log).

Apply retains one lazily opened SQLite connection for the lifetime of one apply usecase. Every inner UnitOfWork block remains an independent `BEGIN` / commit-or-rollback transaction, including the commit that persists a PENDING FileEvent before its Library music file mutation. The connection is closed deterministically on the same thread when the usecase ends. UnitOfWork blocks outside that outer scope keep their close-per-transaction behavior; connections are not process-global or shared across Web requests or threads.

Connections enable `journal_mode = WAL` for read/write concurrency, but `synchronous` stays at its FULL default rather than being lowered to NORMAL: NORMAL only guarantees a WAL fsync at the next checkpoint, so a committed PENDING FileEvent could remain unsynced in the WAL file while the subsequent Library music file move already executed, reopening the crash-safety gap the pending-FileEvent-before-mutation ordering exists to close. Reusing the apply connection changes checkpoint timing only: normal WAL auto-checkpointing bounds growth, and deterministic final connection close allows SQLite's last-connection checkpoint. OMYM2 does not force an extra per-transaction or apply-end checkpoint.

WAL backs each database with a `-wal` and `-shm` shared-memory file, which can misbehave over Windows-mounted 9p/DrvFs paths (for example, running from `/mnt/c` under WSL2); the database should live on a native filesystem.

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
