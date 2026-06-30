---
type: OMYM2 Domain Concept
title: Run
description: Execution attempt for applying a Plan.
tags: [domain, execution, history]
authoritative: false
canonical_docs:
  - ../../domain.md#run
  - ../../execution/model.md#run-behavior
  - ../../execution/apply.md#run-status
---

# Run

A Run records an attempt to apply a Plan. It is the parent unit for FileEvents and gives history, diagnosis, and undo planning a stable execution context.

## Authoritative sources

- [Domain Run](../../domain.md#run)
- [Run behavior](../../execution/model.md#run-behavior)
- [Run status](../../execution/apply.md#run-status)

## Relationships

- [Plan](plan.md) is the reviewed work a Run applies.
- [FileEvent](file-event.md) belongs to a Run.
- [Undo safety](../playbooks/undo-safety.md) traces successful FileEvents from a Run.

## Agent notes

- Create a Run before processing PlanActions when an apply attempt starts.
- Do not create a Run for an apply request rejected before the attempt begins.
