---
type: Architecture Decision Record
title: "ADR 0003: Serialize Mutations With a Cross-Process Exclusive Lock"
description: Records the native cross-platform file-lock mechanism that serializes all Web and CLI mutations and protects atomic Apply acceptance.
tags: [adr, locking, concurrency, apply]
timestamp: 2026-07-13T00:31:39+09:00
---

# ADR 0003: Serialize Mutations With a Cross-Process Exclusive Lock

## Status

Accepted.

## Context

Web workers and CLI commands can run in separate processes against the same
application root. Concurrent Settings saves, scans, Checks, Plan state
transitions, or filesystem execution could observe or create an intermediate
state. A SQLite write lock is too narrow and too short-lived to protect work
that spans filesystem access and multiple transactions.

OMYM2 therefore needs one exclusion mechanism shared by every inbound adapter,
with crash release supplied by the operating system rather than inferred from
process metadata.

## Decision

Every state-changing Web or CLI operation acquires one nonblocking exclusive
lock rooted at the application root before it starts and holds the open lock
handle for the operation's full lifetime. Read-only GET requests remain
available while the lock is held. Acquisition failure is immediate: the Web
API returns `409 Conflict`, and neither Web nor CLI queues the requested
mutation.

The lock path is `.data/exclusive-operation.lock` beneath the application
root. OMYM2 supports this protocol only on a native local filesystem that
provides the operating system's file-lock semantics; it does not add a
network-filesystem lease or third-party lock fallback.

The filename is defined once as `EXCLUSIVE_OPERATION_LOCK_FILE_NAME` in
`src/omym2/config.py` and exposed by `ApplicationPaths`; adapters and tests do
not repeat the string literal.

On Unix, the adapter holds the file open and calls
`fcntl.flock(fd, LOCK_EX | LOCK_NB)`, following the official
[Python `fcntl.flock` documentation](https://docs.python.org/3/library/fcntl.html#fcntl.flock).
On Windows, the adapter ensures the file contains a sentinel byte, seeks to
that byte, holds the file open, and calls
`msvcrt.locking(fd, LK_NBLCK, 1)`, following the official
[Python `msvcrt.locking` documentation](https://docs.python.org/3/library/msvcrt.html#msvcrt.locking).

Owner metadata in the file is diagnostic only. File presence, metadata, a PID,
or elapsed time never proves lock ownership. The implementation has no lease,
PID liveness check, stale-file deletion, or stale-lock takeover. Closing the
handle or process termination releases the operating-system lock; the lock
file itself may remain.

The adapter also tracks its own held lease in process so a second acquisition
attempt from another thread in the same process reports busy even on an OS
whose record-lock API would otherwise treat same-process ownership as
compatible. Cross-process authority still comes from the OS lock, not this
process-local guard.

Apply acceptance occurs while this lock is held:

1. Verify the current Library root against the Plan's
   `library_root_at_plan`.
2. In one database transaction, compare-and-set the Plan from `ready` to
   `applying`, create the running Run, and reserve the durable Operation.
3. Commit that transaction before dispatching the worker.

The exclusive lock remains owned across dispatch and execution. This database
claim does not pretend that later database and filesystem work is atomic;
[Apply execution](../execution/apply.md) and the
[durable FileEvent log](../execution/model.md#durable-file-mutation-log) remain
authoritative after acceptance. The state-changing mutation set is owned by
the [execution model](../execution/model.md#shared-exclusive-operation), the
HTTP conflict envelope by the [Web API contract](../contracts/web-api.md), and
Operation lifecycle/association by the
[Operations contract](../contracts/operations.md).

## Windows Feasibility Spike

M0 evaluated the Python 3.14 Windows file-lock API against the required
properties before accepting this mechanism. The official `msvcrt.locking`
contract provides a nonblocking `LK_NBLCK` byte-range lock that raises
`OSError` on contention and is tied to the retained file descriptor. Locking a
sentinel byte avoids an empty-file ambiguity and uses no PID, wall clock, or
lease expiry. The alternatives were rejected: create-and-delete lock files
remain stale after a crash, and timestamp/PID leases can steal from a live
owner or misidentify a reused PID.

No production lock adapter exists during M0, so the documentation spike cannot
substitute for runtime proof. M3 must run real independent-process tests on
Windows and Unix that demonstrate contention, owner-handle release, crash
release, and harmless persistence of the unlocked file before any Web mutation
ships. A failure of those tests reopens this ADR; it must not be hidden behind
a lease or third-party fallback.

## Consequences

* Web and CLI mutations cannot race through different process-local mutexes.
* State-changing work is deliberately serialized, reducing concurrency in
  exchange for a simple safety boundary.
* GET snapshots remain responsive during long-running work.
* A lock file left on disk is normal and must never be removed as stale.
* Process crashes release exclusion automatically, while durable Operation,
  Run, and FileEvent records preserve the evidence needed for reconciliation.
* The Apply claim is single-use and durable before worker dispatch, but
  FileEvents are still required because database and filesystem mutation cannot
  be one transaction.
