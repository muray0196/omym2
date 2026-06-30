---
type: OMYM2 Knowledge Card
title: Plan
description: Reviewed scheduled set of PlanActions before execution.
resource: "../../domain.md#plan"
tags: [domain, execution, safety, plan]
authoritative: false
---

# Plan

Authoritative source: [docs/domain.md#Plan](../../domain.md#plan).

## Relationships

* Contains reviewed PlanActions and records `library_root_at_plan` for apply safety.
* Is applied through a Run and produces FileEvents only for attempted Library music file mutations.
* Stores enough reviewed data for apply to avoid recalculating target paths from current AppConfig.

## Agent Notes

* Treat Plans as single-use; read [execution/apply.md#Apply Behavior](../../execution/apply.md#apply-behavior) before changing apply behavior.
