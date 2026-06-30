---
type: OMYM2 Knowledge Card
title: Ports and UnitOfWork
description: I/O port and transaction boundary model for OMYM2 usecases.
resource: "../../architecture/ports-uow.md#ports"
tags: [architecture, ports, unit-of-work, execution]
authoritative: false
---

# Ports and UnitOfWork

Authoritative source: [docs/architecture/ports-uow.md#Ports](../../architecture/ports-uow.md#ports).

## Relationships

* Features access external systems through ports such as UnitOfWork, FileScanner, MetadataReader, FileMover, ConfigStore, Clock, and IdGenerator.
* The baseline policy is one usecase per UnitOfWork.
* Apply and undo use FileEvents as the durable operation-log exception.

## Agent Notes

* Keep concrete DB, filesystem, metadata, and config mechanics behind adapters.
