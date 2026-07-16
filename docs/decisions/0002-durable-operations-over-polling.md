---
type: Architecture Decision Record
title: "ADR 0002: Persist Durable Operations and Poll Their Status"
description: Records why long-running work uses persisted SQLite operations, idempotent acceptance, bounded polling, and conservative restart recovery.
tags: [adr, operations, polling, idempotency]
timestamp: 2026-07-16T22:15:00+09:00
---

# ADR 0002: Persist Durable Operations and Poll Their Status

## Status

Accepted.

## Context

Plan scans, Check, and execution may outlive an HTTP request or be interrupted
by process termination. Tying that work to a synchronous request would make a
lost response indistinguishable from a rejected request and would encourage
unsafe retries.

An Operation records orchestration lifecycle status and its typed result. It does not
replace the Plan, Run, and FileEvent records that are authoritative for music
file execution and crash inspection. Those semantics remain in the
[execution model](../execution/model.md#durable-file-mutation-log).

## Decision

Operations are persisted in SQLite. Starting long-running work returns HTTP
`202 Accepted` with the operation status URL in `Location`. Each start
request carries a client-generated UUID in `Idempotency-Key`; the backend
stores that key with the operation kind and a request fingerprint. Repeating
the key with the same fingerprint returns the existing operation, while reuse
with a different fingerprint is a conflict.

Clients use polling only, with bounded backoff that resets when observable
status, result, or error state changes. Terminal results have a finite full-result window followed
by an idempotency-preserving `410 Gone` tombstone window and eventual
`404 Not Found`. The exact timings, central constants, and transition behavior
are owned by the Durable Operation contract rather than repeated in this ADR.

OMYM2 does not provide SSE, WebSocket transport, or user-triggered cancellation
of an in-flight operation. At process startup, persisted `queued` and
`running` operations become `interrupted`; they are not resumed
automatically. A `pending` FileEvent remains pending because its filesystem
outcome is unknown, and recovery requires Check plus manual review rather than
inference or automatic repair.

The authoritative operation resource, lifecycle, conflict, polling, retention,
and tombstone observables live in the
[Operations contract](../contracts/operations.md). FileEvent recovery remains
authoritative in the
[execution model](../execution/model.md#durable-file-mutation-log) and
[failure policy](../execution/failure-policy.md#failure-cases).

## Consequences

* Accepted work and idempotency survive a lost response and process restart.
* Local polling adds bounded repeated reads, accepted in exchange for a simpler
  same-origin transport and deterministic retry behavior.
* Durable results have a finite storage cost and require scheduled cleanup into
  tombstones and then deletion.
* Interrupted work remains visible, but operators must deliberately inspect
  uncertain filesystem outcomes.
* Stage/count progress is intentionally absent until a complete producer,
  persistence contract, and UI are designed together. Adding it, streaming,
  or in-flight cancellation requires a new architecture decision and
  corresponding safety contracts.
