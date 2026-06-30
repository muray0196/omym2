---
type: OMYM2 Knowledge Card
title: Library
description: Stable Library identity and root-path context for managed music files.
resource: "../../domain.md#library"
tags: [domain, storage, identity, library]
authoritative: false
---

# Library

Authoritative source: [docs/domain.md#Library](../../domain.md#library).

## Relationships

* Owns Tracks, Plans, PlanActions, Runs, and FileEvents through `library_id`.
* Runtime filesystem access resolves Library-root-relative paths against the current `libraries.root_path`.

## Agent Notes

* Do not treat `root_path` as identity; confirm path identity rules in [contracts/path-identity-storage.md#Identity Rules](../../contracts/path-identity-storage.md#identity-rules).
