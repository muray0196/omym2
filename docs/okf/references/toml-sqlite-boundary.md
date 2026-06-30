---
type: OMYM2 Storage Reference
title: TOML and SQLite boundary
description: Storage responsibility split between settings, managed state, and music files.
tags: [storage, config, sqlite, filesystem]
authoritative: false
canonical_docs:
  - ../../storage.md#storage-boundary
  - ../../contracts/config.md#responsibilities
  - ../../contracts/db-schema.md#responsibilities
---

# TOML and SQLite Boundary

TOML stores editable settings, SQLite stores managed Library and Track state plus Plans, PlanActions, Runs, and FileEvents, and actual music files remain on the filesystem. OKF-lite files are navigation documents, not a runtime format or storage format.

## Authoritative sources

- [Storage boundary](../../storage.md#storage-boundary)
- [Config responsibilities](../../contracts/config.md#responsibilities)
- [DB responsibilities](../../contracts/db-schema.md#responsibilities)

## Relationships

- [AppConfig](../concepts/app-config.md) is the in-memory settings representation.
- [Track](../concepts/track.md) is managed state stored in SQLite.
- [FileEvent](../concepts/file-event.md) is durable operation-log state stored in SQLite.

## Agent notes

- Do not make OKF-lite files executable state, application config, or generated storage.
- Do not use SQLite as the editable settings store.
