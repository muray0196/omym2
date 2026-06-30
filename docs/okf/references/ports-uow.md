---
type: OMYM2 Architecture Reference
title: Ports and UnitOfWork
description: Port usage, transaction boundaries, and durable operation-log exception.
tags: [architecture, ports, unit-of-work, execution]
authoritative: false
canonical_docs:
  - ../../codebase/ports-uow.md
---

# Ports and UnitOfWork

External I/O is expressed through ports, and usecases coordinate persistence through UnitOfWork. Apply and undo are special because filesystem mutations and DB transactions cannot be fully atomic, so they rely on FileEvents as a durable operation log.

## Authoritative sources

- [Ports and UnitOfWork](../../codebase/ports-uow.md)

## Relationships

- [FileEvent](../concepts/file-event.md) is the operation-log concept used by apply and undo.
- [Plan-centered apply](../playbooks/plan-centered-apply.md) shows the execution flow that uses ports.
- [Dependency boundaries](dependency-boundaries.md) explains where adapter and usecase responsibilities split.

## Agent notes

- Do not solve apply or undo safety by inventing one large transaction around filesystem mutation.
- Keep concrete DB, filesystem, metadata, and config details behind ports.
