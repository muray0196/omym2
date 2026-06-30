---
type: OMYM2 Knowledge Card
title: Path Identity Storage
description: Stable identity and stored path representation for Library-managed records.
resource: "../../contracts/path-identity-storage.md#identity-rules"
tags: [storage, identity, path, library]
authoritative: false
---

# Path Identity Storage

Authoritative source: [docs/contracts/path-identity-storage.md#Identity Rules](../../contracts/path-identity-storage.md#identity-rules).

## Relationships

* Library identity is `library_id`; Track identity is `track_id`.
* Library-managed paths are stored relative to the Library root.
* PathResolver combines current `libraries.root_path` with Library-root-relative paths at I/O boundaries.

## Agent Notes

* Absolute paths are exceptions only where the contract allows them; verify [contracts/path-identity-storage.md#Absolute External Path Exceptions](../../contracts/path-identity-storage.md#absolute-external-path-exceptions).
