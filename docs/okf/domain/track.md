---
type: OMYM2 Knowledge Card
title: Track
description: Current managed state for one music file known to OMYM2.
resource: "../../domain.md#track"
tags: [domain, storage, identity, track]
authoritative: false
---

# Track

Authoritative source: [docs/domain.md#Track](../../domain.md#track).

## Relationships

* Belongs to exactly one Library through `library_id`.
* Can be moved or refreshed while preserving `track_id`.
* FileEvents and undo history stay meaningful because Track identity is not path-derived.

## Agent Notes

* Store Library-managed Track paths as Library-root-relative paths; verify the exact representation in [contracts/path-identity-storage.md#Stored Path Representation](../../contracts/path-identity-storage.md#stored-path-representation).
