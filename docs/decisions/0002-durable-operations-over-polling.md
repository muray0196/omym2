---
type: Architecture Decision Record
title: "ADR 0002: Persist Durable Operations and Poll Their Status"
description: Why long-running work uses persisted SQLite Operations, idempotent acceptance, bounded polling, and conservative restart recovery.
tags: [adr, operations, polling, idempotency]
timestamp: 2026-07-18T12:00:00+09:00
---

# ADR 0002: Persist Durable Operations and Poll Their Status

## Status

Accepted.

## Context

Plan scans, Check, and execution may outlive an HTTP request or be interrupted by process termination; synchronous requests would make a lost response indistinguishable from a rejected request and encourage unsafe retries. An Operation records orchestration lifecycle and typed result only — Plan, Run, and FileEvent records remain authoritative for music file execution and crash inspection ([execution model](../execution/model.md#durable-file-mutation-log)).

## Decision

* Operations persist in SQLite. Starting long-running work returns `202 Accepted` with the status URL in `Location`; each start request carries a client-generated UUID `Idempotency-Key` stored with the kind and a request fingerprint. Same key + fingerprint returns the existing operation; reuse with a different fingerprint conflicts.
* Clients poll only, with bounded backoff resetting on observable change. Terminal results have a finite full-result window, then an idempotency-preserving `410 Gone` tombstone window, then `404`. Exact timings and transitions: [Operations contract](../contracts/operations.md).
* No SSE, WebSocket, or user-triggered cancellation of in-flight operations. At startup, persisted `queued`/`running` operations become `interrupted`, never resumed automatically. A `pending` FileEvent stays pending (unknown filesystem outcome); recovery requires Check plus manual review, never inference or automatic repair ([failure policy](../execution/failure-policy.md#failure-cases)).

## Consequences

* Accepted work and idempotency survive lost responses and restarts.
* Polling adds bounded repeated reads in exchange for a simple same-origin transport and deterministic retries.
* Durable results have finite storage cost and need scheduled cleanup to tombstones, then deletion.
* Interrupted work stays visible; operators must deliberately inspect uncertain filesystem outcomes.
* Stage/count progress is intentionally absent; adding it, streaming, or in-flight cancellation requires a new architecture decision and safety contracts.
