---
type: OMYM2 Execution Playbook
title: Refresh safety
description: Navigation guide for tag correction and relocation planning.
tags: [execution, refresh, metadata, path-policy]
authoritative: false
canonical_docs:
  - ../../execution/refresh.md
  - ../../DOMAIN.md#track
  - ../../DOMAIN.md#pathpolicy
  - ../../execution/apply.md#apply-behavior
---

# Refresh Safety

Refresh re-evaluates managed Tracks after external tag correction. It reloads metadata, recalculates canonical paths during planning, creates a relocation Plan when needed, and then relies on apply to execute recorded PlanActions.

## Authoritative sources

- [Refresh execution](../../execution/refresh.md)
- [Domain Track](../../DOMAIN.md#track)
- [Domain PathPolicy](../../DOMAIN.md#pathpolicy)
- [Apply behavior](../../execution/apply.md#apply-behavior)

## Relationships

- [Track](../concepts/track.md) identity survives metadata and canonical path changes.
- [PathPolicy](../concepts/path-policy.md) is used during planning.
- [Plan](../concepts/plan.md) records the reviewed relocation work.

## Agent notes

- Refresh may recalculate canonical paths while creating a Plan.
- Apply still uses the recorded PlanAction target paths.
