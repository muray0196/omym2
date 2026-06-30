---
type: OMYM2 Domain Concept
title: FileEvent
description: Durable operation log entry for Library music file mutations.
tags: [domain, execution, storage, undo]
authoritative: false
canonical_docs:
  - ../../domain.md#fileevent
  - ../../execution/model.md#fileevent-behavior
  - ../../execution/apply.md#fileevent-status
  - ../../storage.md#db-consistency
---

# FileEvent

A FileEvent is the durable operation log entry for one attempted Library music file mutation. A pending FileEvent must be persisted before the mutation starts so history, crash inspection, diagnosis, and undo planning can inspect what happened.

## Authoritative sources

- [Domain FileEvent](../../domain.md#fileevent)
- [FileEvent behavior](../../execution/model.md#fileevent-behavior)
- [FileEvent status](../../execution/apply.md#fileevent-status)
- [DB consistency](../../storage.md#db-consistency)

## Relationships

- [Run](run.md) is the parent execution attempt for FileEvents.
- [PlanAction](plan-action.md) is the reviewed action a FileEvent records an attempt for.
- [Undo safety](../playbooks/undo-safety.md) depends on FileEvent history.

## Agent notes

- DB-only state changes are not FileEvents.
- Do not create FileEvents for blocked actions, skip actions, or precondition failures before mutation.
