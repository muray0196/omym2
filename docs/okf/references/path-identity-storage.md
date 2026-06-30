---
type: OMYM2 Storage Reference
title: Path identity and storage
description: Library identity, Track identity, and stored path representation.
tags: [storage, path, identity, library]
authoritative: false
canonical_docs:
  - ../../STORAGE.md#path-representation-summary
  - ../../contracts/path-identity-storage.md
  - ../../DOMAIN.md#library
  - ../../DOMAIN.md#track
---

# Path Identity and Storage

OMYM2 separates identity from filesystem location. Library-managed paths are stored relative to the Library root, while PathResolver creates absolute paths only at I/O boundaries.

## Authoritative sources

- [Path representation summary](../../STORAGE.md#path-representation-summary)
- [Path identity and storage contract](../../contracts/path-identity-storage.md)
- [Domain Library](../../DOMAIN.md#library)
- [Domain Track](../../DOMAIN.md#track)

## Relationships

- [Library](../concepts/library.md) identity is stable by `library_id`.
- [Track](../concepts/track.md) identity is stable by `track_id`.
- [PathPolicy](../concepts/path-policy.md) generates Library-root-relative canonical paths.

## Agent notes

- Store Library-managed Track paths as Library-root-relative paths.
- Resolve absolute filesystem paths only at I/O boundaries.
