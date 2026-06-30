---
type: OMYM2 Knowledge Card
title: FileEvent
description: Durable operation log entry for one Library music file mutation.
resource: "../../domain.md#fileevent"
tags: [domain, execution, storage, file-event]
authoritative: false
---

# FileEvent

Authoritative source: [docs/domain.md#FileEvent](../../domain.md#fileevent).

## Relationships

* Belongs to a Run and references the PlanAction being attempted.
* Records only Library music file mutations, not DB-only state changes.
* Supports run detail display, crash inspection, partial failure diagnosis, and undo planning.

## Agent Notes

* FileEvents must be created before the mutation they describe; read [execution/model.md#Durable Operation Log](../../execution/model.md#durable-operation-log).
