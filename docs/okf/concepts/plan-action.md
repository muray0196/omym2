---
type: OMYM2 Domain Concept
title: PlanAction
description: One reviewed action inside a Plan.
tags: [domain, execution, status, plan]
authoritative: false
canonical_docs:
  - ../../domain.md#planaction
  - ../../execution/apply.md#planaction-status
  - ../../contracts/status-reason-catalog.md#planaction-action-type
---

# PlanAction

A PlanAction is the reviewed unit of work inside a Plan. Its source and target paths are recorded during plan creation, while its action type, status, and reason stay separate so review-time blocks and apply-time failures are not confused.

## Authoritative sources

- [Domain PlanAction](../../domain.md#planaction)
- [PlanAction status transitions](../../execution/apply.md#planaction-status)
- [PlanAction action type catalog](../../contracts/status-reason-catalog.md#planaction-action-type)

## Relationships

- [Plan](plan.md) owns PlanActions.
- [PathPolicy](path-policy.md) may generate target paths during plan creation.
- [FileEvent](file-event.md) records attempted Library music file mutations for eligible actions.

## Agent notes

- `conflict` and `error` are status or reason concepts, not action types.
- Blocked-at-plan-time and failed-at-apply-time are different states.
