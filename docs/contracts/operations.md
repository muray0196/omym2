---
type: Contract
title: Durable Operation Contract
description: Defines durable background Operation identity, lifecycle, idempotency, progress, polling, retention, Operation-level restart recovery, and cancellation policy.
tags: [operations, idempotency, polling, progress, recovery, desktop]
timestamp: 2026-07-15T00:13:25+09:00
---

# Durable Operation Contract

This document is authoritative for durable background Operation identity,
lifecycle, idempotency, progress, polling, retention, Operation-level restart
recovery, and cancellation policy. Each execution specification owns recovery
of the domain records for its operation kind.

The persisted table shape is owned by [db-schema.md](db-schema.md#operations).
HTTP representations and errors are owned by [web-api.md](web-api.md). The
choice of polling is recorded in
[../decisions/0002-durable-operations-over-polling.md](../decisions/0002-durable-operations-over-polling.md).
Library music file mutation ordering remains authoritative in
[../execution/apply.md](../execution/apply.md).

## Operation Versus FileEvent

An `Operation` is the durable record of one accepted background request. It
exists so a client can recover after a lost response, poll progress, and inspect
an interruption after a process restart.

A `FileEvent` is the durable evidence for one attempted Library music file
mutation. It must be committed as `pending` immediately before that mutation.
An Operation never replaces, batches, or weakens FileEvent ordering.

## Identity And Kinds

`operation_id` is a backend-generated UUIDv7. It is stable for the lifetime of
the retained Operation and is never derived from an HTTP idempotency key.

The closed Operation-kind values are authoritative in
[status-reason-catalog.md](status-reason-catalog.md#operation-kind). This
contract defines what those kinds do; it does not maintain a second catalog.

Settings save and ready-Plan cancellation are short synchronous mutations and
do not create Operations. They still use the exclusive-operation protocol.

## Lifecycle

The closed Operation-status values are authoritative in
[status-reason-catalog.md](status-reason-catalog.md#operation-status).

Allowed transitions are:

| From | Condition | To |
| --- | --- | --- |
| none | request is durably accepted | `queued` |
| `queued` | the committed reservation is handed to a worker | `running` |
| `running` | the typed result and its managed-state writes commit | `succeeded` |
| `running` | the worker observes a terminal error and commits a redacted error | `failed` |
| `queued` or `running` | startup or dispatch-failure reconciliation finds unfinished work | `interrupted` |

Terminal statuses never transition. Expiration is a retrieval condition, not
an Operation status.

While the full resource is retained, status controls nullable fields:

| Status | `started_at` | `completed_at` | `result` | `error` |
| --- | --- | --- | --- | --- |
| `queued` | null | null | null | null |
| `running` | non-null | null | null | null |
| `succeeded` | non-null | non-null | exactly one typed result | null |
| `failed` | non-null | non-null | null | exactly one typed error |
| `interrupted` | nullable only when dispatch never started | non-null | null | exactly one `operation_interrupted` error |

`requested_at <= started_at <= completed_at` for timestamps that exist, and
`requested_at <= completed_at` always holds for a terminal Operation. Terminal
expiry timestamps are non-null and derived from `completed_at`. Repository,
domain, Pydantic, and generated-client tests reject any other combination.
After full-result expiry the API returns the separate 410 tombstone projection;
cleared payload columns are never serialized as a malformed terminal resource.

## Typed Results

An Operation has no result until its terminal write commits. Result-kind values
are authoritative in
[status-reason-catalog.md](status-reason-catalog.md#operation-result-kind); the
required payload for each is:

| Result kind | Required fields | Used by |
| --- | --- | --- |
| `plan_created` | `plan_id` | Add, Organize with actions, Refresh, Undo |
| `registered_without_plan` | `library_id`, `track_count` | clean Organize registration |
| `check_completed` | non-empty `check_run_ids`, `issue_count` | Check |
| `run_completed` | `run_id` | Apply, including Apply of an Undo Plan |

Plan generation never embeds PlanActions in an Operation result. A client opens
the Plan and retrieves actions through cursor pagination. A result and the
newly created managed resource it names must commit in the same transaction so
restart reconciliation cannot expose an orphaned success. Undo deduplication is
the explicit exception: a `plan_created` result may link an already committed
ready Undo Plan, and the Operation's terminal transaction does not rewrite that
resource.

## Idempotent Acceptance

Every HTTP request that creates an Operation requires one client-generated UUID
in the `Idempotency-Key` header. The backend stores the key before dispatch,
together with the Operation kind and a fingerprint of the validated,
canonical request, including its selected Library when applicable.

For a CLI-started durable Operation, platform orchestration generates one fresh
UUID idempotency key before reservation, uses it for every internal acceptance
retry in that invocation. The CLI does not expose a separate idempotency flag,
change its user-facing command result merely to print the internal key,
automatically repeat a crashed operation, or reuse the generated key in a later
invocation. Thus every persisted Operation has a non-null globally unique key
without pretending that an HTTP header exists on the CLI surface.

The idempotency key is globally unique within the application database:

* the same key, kind, and fingerprint returns the existing Operation reference
  and does not repeat validation side effects or dispatch;
* the same key with a different kind or fingerprint fails with
  `409 idempotency_key_reused`;
* retention of the key follows the Operation tombstone lifetime, so expiration
  cannot make a recent request executable again.

The raw request body is not retained merely to implement idempotency. Paths and
other request values are represented only by the canonical fingerprint and by
the domain records that the accepted operation legitimately creates.

## Progress

Progress contains:

* a stable snake_case `stage_code` or `null`;
* `completed_units` and `total_units`, either both non-null or both null;
* an optional redacted message that is safe to display locally.

Counts are monotonic within one stage and satisfy
`0 <= completed_units <= total_units`. A worker that cannot report real counts
uses null counts; neither backend nor frontend fabricates a percentage.
Unknown stage codes use a generic presentation and remain pollable.

## Polling

Polling is the only initial progress transport. An accepted response supplies
the status URL in `Location` and an Operation reference with
`poll_after_ms = 500`.

The client waits 0.5 seconds before the first poll. An unchanged Operation
snapshot doubles the interval up to 5 seconds. A status, stage, count, result,
or error change resets the interval to 0.5 seconds. A connectivity failure uses
the same capped backoff while the UI reports disconnection; it never causes an
automatic mutation retry.

The backend owns these tunables in `src/omym2/config.py`; Python production
code and tests import the named values rather than repeat literals. Bootstrap
serializes the polling subset for the SPA, so frontend code and tests consume
the contract instead of defining a second policy:

```text
OPERATION_POLL_INITIAL_SECONDS = 0.5
OPERATION_POLL_BACKOFF_FACTOR = 2.0
OPERATION_POLL_MAX_SECONDS = 5.0
OPERATION_RECONCILE_INTERVAL_SECONDS = 5.0
OPERATION_RESULT_RETENTION_HOURS = 24
OPERATION_TOMBSTONE_RETENTION_DAYS = 30
```

## Retention And Lookup

The full terminal Operation, typed result or error, progress, and idempotency
record remain available for 24 hours after `completed_at`.

After 24 hours, the result/error payload may be removed, but a minimal
Operation and idempotency tombstone remains through 30 days after
`completed_at`. Lookup during that tombstone period returns
`410 operation_expired`. Lookup for an ID that was never known, or whose
30-day tombstone has elapsed, returns `404 operation_not_found`.

Cleanup must not remove an active Operation. Retention cleanup is a DB-only
state change performed under the same exclusive-operation protocol.

## Restart And Dispatch Reconciliation

Startup or pre-mutation reconciliation first acquires the shared exclusive
lock. If acquisition fails, another process or worker is active and no
Operation is reclassified. After acquiring it, reconciliation runs before
accepting another exclusive operation.

Reconciliation considers retained `queued`/`running` Operations and any
`interrupted` Operation still linked to nonterminal managed state. It invokes
the owning execution specification for each candidate. In particular,
[Apply's dispatch and restart rules](../execution/apply.md#dispatch-failure-and-restart)
are authoritative for PlanAction, Plan, Run, and FileEvent recovery; this
contract does not redefine those transitions.

All managed-state recovery and the Operation transition commit in one
transaction. A candidate without kind-specific nonterminal state preserves any
atomically committed domain resource, does not infer a missing success result,
and becomes `interrupted` with a redacted error. The client creates a new
request with a new idempotency key after inspecting current state. An Apply
candidate becomes `interrupted` in the same transaction as its execution-spec
recovery, even when durable action evidence permits a normal terminal Plan/Run
result.

If reconciliation crashes, the transaction rolls back the Operation and all
kind-specific managed-state changes so the candidate remains discoverable on
the next pass. Re-visiting an already interrupted Operation with nonterminal
managed state makes recovery idempotent even for state created by an older or
incomplete pass.

The first `queued`/`running` to `interrupted` transition sets `completed_at`,
`result_expires_at`, and `tombstone_expires_at` once. A repair pass for an
already interrupted Operation preserves those terminal timestamps and never
extends retention; it updates only the nonterminal associations or missing
redacted reconciliation evidence.

While the Web server is running, a platform reconciliation supervisor wakes
every 5 seconds and attempts the same nonblocking exclusive lock. A busy lock
means a compliant worker/process is active, so the supervisor changes nothing.
If it acquires the lock, it atomically reconciles stale candidates and releases
the lock. Startup and every later mutation also run this check. Lock metadata
and file presence are never liveness evidence.

Operation GET and idempotent replay remain read-only snapshots and never run
reconciliation themselves. They may report a recently orphaned row as active
until the bounded supervisor pass commits; polling then observes the terminal
state. Without a Web server, the next CLI/Web process startup or state-changing
command performs reconciliation before mutation.

A failure to dispatch after the atomic Apply reservation follows the same
reconciliation rules immediately. It is not safe to roll the Plan back to
`ready` because the reservation may already have escaped the request thread.

## Cancellation

The initial Operation contract has no user-triggered cancellation for queued or
running Operations. Closing a browser or the packaged desktop window, losing a
polling connection, or sending another request does not cancel work. Desktop
shutdown waits for accepted work to finish and release the shared operation
lock before process exit.

Ready-Plan cancellation is a separate synchronous Plan transition. It is
permitted only before Apply claims the Plan and is serialized by the shared
exclusive-operation lock. A later in-flight cancellation protocol requires a
new contract and explicit recovery semantics.
