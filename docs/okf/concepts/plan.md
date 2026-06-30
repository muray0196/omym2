---
type: OMYM2 Domain Concept
title: Plan
description: Reviewed scheduled set of PlanActions before execution.
tags: [domain, execution, safety, plan]
authoritative: false
canonical_docs:
  - ../../DOMAIN.md#plan
  - ../../execution/model.md#plan-centered-execution
  - ../../execution/apply.md#apply-behavior
---

# Plan

A Plan is the reviewed schedule of work created before execution. It contains PlanActions and preserves enough reviewed data for apply to execute the chosen operations without recalculating destinations from the latest AppConfig.

## Authoritative sources

- [Domain Plan](../../DOMAIN.md#plan)
- [Plan-centered execution](../../execution/model.md#plan-centered-execution)
- [Apply behavior](../../execution/apply.md#apply-behavior)

## Relationships

- [PlanAction](plan-action.md) is the reviewed action unit inside a Plan.
- [Run](run.md) records an execution attempt for applying a Plan.
- [Plan-centered apply](../playbooks/plan-centered-apply.md) summarizes the apply flow.

## Agent notes

- Treat plan creation as the calculation-to-execution boundary.
- Apply must use recorded PlanActions, not target paths recalculated from current config.
