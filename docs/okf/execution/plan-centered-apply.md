---
type: OMYM2 Knowledge Card
title: Plan-centered Apply
description: Apply safety model built around reviewed PlanActions and durable FileEvents.
resource: "../../execution/apply.md#apply-behavior"
tags: [execution, safety, plan, apply]
authoritative: false
---

# Plan-centered Apply

Authoritative source: [docs/execution/apply.md#Apply Behavior](../../execution/apply.md#apply-behavior).

## Relationships

* Starts from a reviewed Plan and processes recorded PlanActions in order.
* Creates Runs for apply attempts and FileEvents for attempted Library music file mutations.
* Uses `library_root_at_plan` to reject stale-root Plans before unsafe mutation.

## Agent Notes

* Never recalculate apply targets from the latest AppConfig; follow recorded PlanActions and the precondition rules in [execution/apply.md#Apply-Time Precondition Failures](../../execution/apply.md#apply-time-precondition-failures).
