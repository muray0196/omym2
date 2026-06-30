---
type: OMYM2 Knowledge Card
title: Undo
description: Per-Run reversal workflow that creates an undo Plan from FileEvents.
resource: "../../execution/undo.md#undo-behavior"
tags: [execution, undo, run, file-event]
authoritative: false
---

# Undo

Authoritative source: [docs/execution/undo.md#Undo Behavior](../../execution/undo.md#undo-behavior).

## Relationships

* Traces succeeded FileEvents in reverse order for a selected Run.
* Produces an undo Plan, then uses normal apply semantics.
* May use absolute external restore targets only for documented external-path exceptions.

## Agent Notes

* Undo must not mutate files directly; route through Plan and apply.
