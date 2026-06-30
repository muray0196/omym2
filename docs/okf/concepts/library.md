---
type: OMYM2 Domain Concept
title: Library
description: Stable music Library identity with a mutable runtime root.
tags: [domain, storage, identity]
authoritative: false
canonical_docs:
  - ../../DOMAIN.md#library
  - ../../contracts/path-identity-storage.md#identity-rules
  - ../../execution/organize.md
---

# Library

A Library is a music collection managed by OMYM2. Its identity is stable through `library_id`, while its current root path is a runtime location used to resolve Library-root-relative paths.

## Authoritative sources

- [Domain Library](../../DOMAIN.md#library)
- [Identity rules](../../contracts/path-identity-storage.md#identity-rules)
- [Organize execution](../../execution/organize.md)

## Relationships

- [Track](track.md) belongs to exactly one Library.
- [Plan](plan.md) stores the Library root used when the Plan was created.
- [Path identity and storage](../references/path-identity-storage.md) explains stored path representation.

## Agent notes

- Do not treat `root_path` as Library identity.
- Relink preserves Library-managed records instead of duplicating them.
