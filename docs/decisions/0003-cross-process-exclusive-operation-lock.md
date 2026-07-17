---
type: Architecture Decision Record
title: "ADR 0003: Serialize Mutations With a Cross-Process Exclusive Lock"
description: The native cross-platform file-lock mechanism that serializes all Web and CLI mutations and protects atomic Apply acceptance.
tags: [adr, locking, concurrency, apply]
timestamp: 2026-07-18T12:00:00+09:00
---

# ADR 0003: Serialize Mutations With a Cross-Process Exclusive Lock

## Status

Accepted.

## Context

Web workers and CLI commands run in separate processes against the same application root; a SQLite write lock is too narrow and short-lived to protect work spanning filesystem access and multiple transactions. One exclusion mechanism must be shared by every inbound adapter, with crash release supplied by the operating system rather than inferred from process metadata.

## Decision

* Every state-changing Web or CLI operation acquires one nonblocking exclusive lock rooted at the application root before starting and holds the open lock handle for the operation's full lifetime. Read-only GETs stay available. Acquisition failure is immediate: Web returns `409 Conflict`; neither surface queues the mutation.
* Lock path: `.data/exclusive-operation.lock`, defined once as `EXCLUSIVE_OPERATION_LOCK_FILE_NAME` in `src/omym2/config.py` and exposed by `ApplicationPaths`. Supported only on a native local filesystem with OS file-lock semantics; no network-filesystem lease or third-party fallback.
* Unix: hold the file open, `fcntl.flock(fd, LOCK_EX | LOCK_NB)`. Windows: ensure a sentinel byte, seek to it, hold the file open, `msvcrt.locking(fd, LK_NBLCK, 1)`. Locking a sentinel byte avoids empty-file ambiguity; the mechanism uses no PID, wall clock, or lease expiry. (Alternatives rejected in the M0 spike: create-and-delete lock files go stale after a crash; timestamp/PID leases can steal from a live owner. M3 validated contention, owner-handle release, crash release, and harmless lock-file persistence with real independent-process tests on Windows and Unix.)
* Owner metadata in the file is diagnostic only. File presence, metadata, PID, or elapsed time never proves ownership; there is no lease, liveness check, stale-file deletion, or takeover. Closing the handle or process death releases the OS lock; the file may remain.
* The adapter also tracks its held lease in process, so a second same-process acquisition reports busy even where the OS record-lock API would treat same-process ownership as compatible; cross-process authority still comes from the OS lock.
* Apply acceptance runs while the lock is held: verify the Library root against `library_root_at_plan`; in one transaction compare-and-set the Plan `ready` → `applying`, create the running Run, reserve the durable Operation; commit before dispatch. The lock stays owned across dispatch and execution. The claim does not make later DB and filesystem work atomic — [Apply execution](../execution/apply.md) and the [durable FileEvent log](../execution/model.md#durable-file-mutation-log) remain authoritative. The state-changing mutation set is owned by the [execution model](../execution/model.md#shared-exclusive-operation), the HTTP conflict envelope by the [Web API contract](../contracts/web-api.md), and Operation lifecycle by the [Operations contract](../contracts/operations.md).

## Consequences

* Web and CLI mutations cannot race through different process-local mutexes; state-changing work is deliberately serialized for a simple safety boundary while GET snapshots stay responsive.
* A lock file left on disk is normal and must never be removed as stale.
* Process crashes release exclusion automatically; durable Operation, Run, and FileEvent records preserve reconciliation evidence.
* The Apply claim is single-use and durable before dispatch, but FileEvents are still required because DB and filesystem mutation cannot be one transaction.
