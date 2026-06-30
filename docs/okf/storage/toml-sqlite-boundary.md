---
type: OMYM2 Knowledge Card
title: TOML and SQLite Boundary
description: Storage responsibility split between editable settings and managed state.
resource: "../../storage.md#storage-boundary"
tags: [storage, toml, sqlite, config]
authoritative: false
---

# TOML and SQLite Boundary

Authoritative source: [docs/storage.md#Storage Boundary](../../storage.md#storage-boundary).

## Relationships

* TOML stores editable application settings.
* SQLite stores managed Library and Track state, Plans, PlanActions, Runs, and FileEvents.
* The filesystem remains the location of actual music files and may diverge from DB state.

## Agent Notes

* Do not move AppConfig or runtime state into OKF/Markdown; use [contracts/config.md](../../contracts/config.md) and [contracts/db-schema.md](../../contracts/db-schema.md).
