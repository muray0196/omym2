---
type: Contract
title: Durable Operation Contract
description: Durable Operation identity, lifecycle, idempotent acceptance, polling, retention, restart reconciliation, and cancellation.
tags: [operations, idempotency, polling, recovery, unprocessed, desktop]
timestamp: 2026-07-18T12:00:00+09:00
---

# Durable Operation Contract

Authoritative for durable background Operation identity, lifecycle, idempotency, status polling, retention, Operation-level restart recovery, and cancellation. Each execution spec owns recovery of the domain records for its operation kind. Table shape: [db-schema.md](db-schema.md#operations); HTTP representation: [web-api.md](web-api.md); polling decision: [ADR 0002](../decisions/0002-durable-operations-over-polling.md); mutation ordering: [../execution/apply.md](../execution/apply.md).

## Operation Versus FileEvent

An `Operation` is the durable record of one accepted background request: it lets a client recover after a lost response, poll status, and inspect an interruption after restart. A `FileEvent` is the durable evidence for one attempted audio, companion, or unprocessed-file mutation and must be committed `pending` immediately before that mutation. An Operation never replaces, batches, or weakens FileEvent ordering.

## Identity And Kinds

`operation_id` is a backend-generated UUIDv7, stable for the retained Operation's lifetime, never derived from an HTTP idempotency key. Closed kind values: [status-reason-catalog.md](status-reason-catalog.md#operation-kind). Settings save and ready-Plan cancellation are short synchronous mutations and do not create Operations; they still use the exclusive-operation protocol.

## Lifecycle

Closed status values: [status-reason-catalog.md](status-reason-catalog.md#operation-status). Allowed transitions:

| From | Condition | To |
| --- | --- | --- |
| none | request is durably accepted | `queued` |
| `queued` | the committed reservation is handed to a worker | `running` |
| `running` | the typed result and its managed-state writes commit | `succeeded` |
| `running` | the worker observes a terminal error and commits a redacted error | `failed` |
| `queued` or `running` | startup or dispatch-failure reconciliation finds unfinished work | `interrupted` |

Terminal statuses never transition. Expiration is a retrieval condition, not a status. While the full resource is retained, status controls nullable fields:

| Status | `started_at` | `completed_at` | `result` | `error` |
| --- | --- | --- | --- | --- |
| `queued` | null | null | null | null |
| `running` | non-null | null | null | null |
| `succeeded` | non-null | non-null | exactly one typed result | null |
| `failed` | non-null | non-null | null | exactly one typed error |
| `interrupted` | nullable only when dispatch never started | non-null | null | exactly one `operation_interrupted` error |

`requested_at <= started_at <= completed_at` for timestamps that exist; `requested_at <= completed_at` always holds for a terminal Operation. Terminal expiry timestamps are non-null and derived from `completed_at`. Repository, domain, Pydantic, and generated-client tests reject any other combination. After full-result expiry the API returns the separate 410 tombstone projection; cleared payload columns are never serialized as a malformed terminal resource.

## Typed Results

An Operation has no result until its terminal write commits. Result-kind values: [status-reason-catalog.md](status-reason-catalog.md#operation-result-kind). Required payloads:

| Result kind | Required fields | Used by |
| --- | --- | --- |
| `plan_created` | `plan_id` | Add, Organize with actions, Refresh, Undo |
| `registered_without_plan` | `library_id`, `track_count` | clean Organize registration |
| `check_completed` | non-empty `check_run_ids`, `issue_count` | Check |
| `run_completed` | `run_id` | Apply, including Apply of an Undo Plan |

Plan generation never embeds PlanActions in a result; clients open the Plan and page its actions. A result and the newly created managed resource it names must commit in the same transaction so restart reconciliation cannot expose an orphaned success. Undo deduplication is the explicit exception: `plan_created` may link an already committed ready Undo Plan, and the terminal transaction does not rewrite that resource.

## Idempotent Acceptance

Every HTTP request creating an Operation requires one client-generated UUID in the `Idempotency-Key` header. The backend stores the key before dispatch with the Operation kind and a fingerprint of the validated canonical request, including the selected Library when applicable.

For a CLI-started durable Operation, platform orchestration generates one fresh UUID key before reservation and reuses it for every internal acceptance retry in that invocation. The CLI exposes no idempotency flag, does not print the internal key, never automatically repeats a crashed operation, and never reuses the key in a later invocation — so every persisted Operation has a non-null globally unique key without a fake HTTP header.

The key is globally unique within the application database:

* same key, kind, and fingerprint returns the existing Operation reference without repeating validation side effects or dispatch;
* same key with a different kind or fingerprint fails with `409 idempotency_key_reused`;
* key retention follows the Operation tombstone lifetime, so expiration cannot make a recent request executable again.

The raw request body is not retained for idempotency; request values live only in the canonical fingerprint and the domain records the accepted operation legitimately creates.

## Polling

Polling is the only Operation-status transport. An accepted response supplies the status URL in `Location` and an Operation reference with `poll_after_ms = 500`. The client waits 0.5 s before the first poll; an unchanged snapshot doubles the interval up to 5 s; any status/result/error change resets it to 0.5 s. Connectivity failures use the same capped backoff while the UI reports disconnection, never triggering an automatic mutation retry.

The pre-release stage/count/message progress scaffold was removed (no production producer). Current domain, SQLite, Web resource, and SPA represent only lifecycle status, typed result, and typed failure. Progress may return only as a complete feature with an authoritative producer and coordinated persistence and UI contracts.

The backend owns these tunables in `src/omym2/config.py`; production code and tests import the named values, and bootstrap serializes the polling subset for the SPA:

```text
OPERATION_POLL_INITIAL_SECONDS = 0.5
OPERATION_POLL_BACKOFF_FACTOR = 2.0
OPERATION_POLL_MAX_SECONDS = 5.0
OPERATION_RECONCILE_INTERVAL_SECONDS = 5.0
OPERATION_RESULT_RETENTION_HOURS = 24
OPERATION_TOMBSTONE_RETENTION_DAYS = 30
```

## Retention And Lookup

The full terminal Operation, typed result or error, and idempotency record remain available for 24 hours after `completed_at`. After that, the payload may be removed but a minimal Operation and idempotency tombstone remains through 30 days after `completed_at`; lookup during the tombstone period returns `410 operation_expired`. An ID never known, or past its 30-day tombstone, returns `404 operation_not_found`. Cleanup must not remove an active Operation and is a DB-only state change under the exclusive-operation protocol.

## Restart And Dispatch Reconciliation

Reconciliation first acquires the shared exclusive lock; if acquisition fails, another process or worker is active and nothing is reclassified. After acquiring it, reconciliation runs before accepting another exclusive operation.

It considers retained `queued`/`running` Operations and any `interrupted` Operation still linked to nonterminal managed state, invoking the owning execution specification per candidate. [Apply's dispatch and restart rules](../execution/apply.md#dispatch-failure-and-restart) are authoritative for PlanAction, Plan, Run, and FileEvent recovery. That recovery treats `move_unprocessed` like other mutation-bearing action types: a planned action not durably confirmed becomes failed with `operation_interrupted`, while any typed pending event remains pending and manual-review-only. Reconciliation never resumes the move, rereads current unprocessed Config, deletes directories, or infers an outcome from the filesystem.

All managed-state recovery and the Operation transition commit in one transaction. A candidate without kind-specific nonterminal state preserves any atomically committed domain resource, does not infer a missing success result, and becomes `interrupted` with a redacted error; the client creates a new request with a new idempotency key after inspecting current state. An Apply candidate becomes `interrupted` in the same transaction as its execution-spec recovery, even when durable action evidence permits a normal terminal Plan/Run result.

If reconciliation crashes, the transaction rolls back so the candidate stays discoverable on the next pass; re-visiting an already interrupted Operation with nonterminal managed state keeps recovery idempotent. The first `queued`/`running` → `interrupted` transition sets `completed_at`, `result_expires_at`, and `tombstone_expires_at` once; a repair pass preserves those terminal timestamps, never extends retention, and updates only nonterminal associations or missing redacted evidence.

While the Web server runs, a platform reconciliation supervisor wakes every 5 seconds and attempts the same nonblocking exclusive lock: busy means a compliant worker is active and nothing changes; acquired means it atomically reconciles stale candidates and releases. Startup and every later mutation also run this check. Lock metadata and file presence are never liveness evidence.

Operation GET and idempotent replay remain read-only snapshots and never run reconciliation; they may report a recently orphaned row as active until the bounded supervisor pass commits. Without a Web server, the next CLI/Web process startup or state-changing command reconciles before mutation.

A failure to dispatch after the atomic Apply reservation follows the same reconciliation rules immediately; rolling the Plan back to `ready` is unsafe because the reservation may already have escaped the request thread.

## Cancellation

There is no user-triggered cancellation for queued or running Operations. Closing a browser or the desktop window, losing a polling connection, or sending another request does not cancel work. Desktop shutdown waits for accepted work to finish and release the shared lock before process exit.

Ready-Plan cancellation is a separate synchronous Plan transition, permitted only before Apply claims the Plan, serialized by the shared exclusive-operation lock. An in-flight cancellation protocol would require a new contract with explicit recovery semantics.
