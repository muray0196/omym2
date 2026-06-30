---
type: OMYM2 Knowledge Card
title: Run
description: Execution attempt for applying a Plan.
resource: "../../domain.md#run"
tags: [domain, execution, history, run]
authoritative: false
---

# Run

Authoritative source: [docs/domain.md#Run](../../domain.md#run).

## Relationships

* Starts before PlanActions are processed and before Library music file mutation.
* Owns FileEvents for the apply attempt.
* Feeds history and undo workflows.

## Agent Notes

* Partial filesystem success is represented as Run evidence, not hidden by retry logic; read [execution/model.md#Run Behavior](../../execution/model.md#run-behavior).
