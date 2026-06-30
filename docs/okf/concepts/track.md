---
type: OMYM2 Domain Concept
title: Track
description: Current managed state of one music file known to OMYM2.
tags: [domain, storage, identity]
authoritative: false
canonical_docs:
  - ../../DOMAIN.md#track
  - ../../contracts/path-identity-storage.md#stored-path-representation
  - ../../STORAGE.md#sqlite-responsibility
---

# Track

A Track is OMYM2's current managed state for one music file. It records the last known Library-relative paths, hashes, metadata, and status, but it does not prove that the filesystem still matches the database.

## Authoritative sources

- [Domain Track](../../DOMAIN.md#track)
- [Stored path representation](../../contracts/path-identity-storage.md#stored-path-representation)
- [SQLite responsibility](../../STORAGE.md#sqlite-responsibility)

## Relationships

- [Library](library.md) owns Track identity through `library_id`.
- [FileEvent](file-event.md) records Library music file mutations that can affect Track state.
- [Refresh safety](../playbooks/refresh-safety.md) depends on stable Track identity.

## Agent notes

- Do not derive `track_id` from path, canonical path, content hash, or metadata hash.
- Treat filesystem divergence as something `check` detects, not as proof that Track identity changed.
