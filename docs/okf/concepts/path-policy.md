---
type: OMYM2 Domain Concept
title: PathPolicy
description: Pure canonical path generation for Library-root-relative destinations.
tags: [domain, path, config, execution]
authoritative: false
canonical_docs:
  - ../../DOMAIN.md#pathpolicy
  - ../../contracts/config.md#pathpolicyconfig
  - ../../contracts/path-identity-storage.md#pathresolver-boundary
  - ../../execution/apply.md#apply-behavior
---

# PathPolicy

PathPolicy is pure domain logic that generates Library-root-relative canonical paths from metadata, file extension, and path-policy config. It performs no I/O, does not check filesystem existence, and templates describe destination stems without file extensions.

## Authoritative sources

- [Domain PathPolicy](../../DOMAIN.md#pathpolicy)
- [PathPolicyConfig](../../contracts/config.md#pathpolicyconfig)
- [PathResolver boundary](../../contracts/path-identity-storage.md#pathresolver-boundary)
- [Apply behavior](../../execution/apply.md#apply-behavior)

## Relationships

- [PlanAction](plan-action.md) records target paths produced during plan creation.
- [Plan](plan.md) is the boundary between calculation and execution.
- [Path identity and storage](../references/path-identity-storage.md) covers path resolution boundaries.

## Agent notes

- Do not put filesystem existence checks in PathPolicy.
- Apply must use recorded PlanAction target paths instead of rerunning PathPolicy.
