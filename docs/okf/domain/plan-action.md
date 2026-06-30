---
type: OMYM2 Knowledge Card
title: PlanAction
description: Planned operation for one file or managed track inside a Plan.
resource: "../../domain.md#planaction"
tags: [domain, execution, path, plan-action]
authoritative: false
---

# PlanAction

Authoritative source: [docs/domain.md#PlanAction](../../domain.md#planaction).

## Relationships

* Belongs to a Plan and may reference a Track through `track_id`.
* Carries recorded source and target path references used by apply.
* Has action type, status, and reason values cataloged outside this card.

## Agent Notes

* Do not model `conflict` or `error` as action types; route status/reason questions to [contracts/status-reason-catalog.md#PlanAction Action Type](../../contracts/status-reason-catalog.md#planaction-action-type).
