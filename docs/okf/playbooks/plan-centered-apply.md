---
type: OMYM2 Execution Playbook
title: Plan-centered apply
description: Navigation guide for safe Library music file mutations.
tags: [execution, apply, safety, plan]
authoritative: false
canonical_docs:
  - ../../execution/model.md#plan-centered-execution
  - ../../execution/apply.md#apply-behavior
  - ../../storage.md#db-consistency
---

# Plan-centered Apply

Library music file mutations go through Plan review and apply execution. Apply uses recorded PlanActions, persists FileEvents before attempted mutations, and fails closed when apply-time preconditions are not satisfied.

## Authoritative sources

- [Plan-centered execution](../../execution/model.md#plan-centered-execution)
- [Apply behavior](../../execution/apply.md#apply-behavior)
- [DB consistency](../../storage.md#db-consistency)

## Relationships

- [Plan](../concepts/plan.md) stores the reviewed work.
- [PlanAction](../concepts/plan-action.md) stores each reviewed action.
- [FileEvent](../concepts/file-event.md) is the durable operation log entry.
- [PathPolicy](../concepts/path-policy.md) is not rerun during apply.

## Agent notes

- Do not mutate Library music files directly from add, organize, refresh, or undo planning code.
- Do not recalculate target paths during apply.
