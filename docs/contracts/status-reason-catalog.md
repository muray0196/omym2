---
type: Contract
title: Status And Reason Catalog
description: Defines the versioned status, reason, action, event, check, and durable-operation catalogs plus required unknown-value and status presentation behavior.
tags: [status, reason-codes, catalog, execution, operations]
timestamp: 2026-07-13T00:31:39+09:00
---

# Status And Reason Catalog

This document is authoritative for allowed status, reason, action type, event
type, check issue, Operation kind/status/result values, the FileEvent error-code
schema, and cross-surface status presentation behavior.

Domain concepts are in [../DOMAIN.md](../DOMAIN.md). Execution state transitions are in [../execution/model.md](../execution/model.md), [../execution/apply.md](../execution/apply.md), and [../execution/failure-policy.md](../execution/failure-policy.md).

## Catalog Version

The catalog version returned by Bootstrap is integer `1`. It versions the
closed catalogs in this document as one bundled client/server contract. Adding,
removing, or redefining a closed value increments the version in the same
coordinated change. It does not version the open FileEvent error-code or
Operation stage-code schemas.

## Library Status

Field: `Library.status`.

```text
registered
unregistered
stale
blocked
```

## Track Status

Field: `Track.status`.

```text
active
removed
```

`missing` is reported by `check` in the initial version rather than automatically persisted as Track status.

## Plan Status

Field: `Plan.status`.

```text
ready
applying
applied
partial_failed
failed
cancelled
expired
```

## PlanAction Action Type

Field: `PlanAction.action_type`.

```text
move
skip
refresh_metadata
```

`conflict` and `error` are not action types.

`refresh_metadata` reingests Track metadata and hashes for an unchanged path without a Library music file mutation.

## PlanAction Status

Field: `PlanAction.status`.

```text
planned
blocked
applied
failed
```

`skip` is an action type, not a status.

## PlanAction Reason

Field: `PlanAction.reason`.

```text
target_exists
missing_required_metadata
invalid_path
source_missing
source_changed
duplicate_hash
operation_interrupted
```

Plan creation problems are blocked. Apply-time precondition failures are failed.
`operation_interrupted` marks an eligible action whose completion could not be
confirmed after worker dispatch failure or process restart. A related pending
FileEvent remains the authority for an unknown mutation outcome.

## Run Status

Field: `Run.status`.

```text
running
succeeded
partial_failed
failed
```

## FileEvent Event Type

Field: `FileEvent.event_type`.

```text
move_file
```

## FileEvent Status

Field: `FileEvent.status`.

```text
pending
succeeded
failed
```

FileEvents are created only for attempted Library music file mutations.

## FileEvent Error Code

Field: `FileEvent.error_code`.

This nullable field is an open schema, not a closed enum. Apply writes `null`
for pending and succeeded FileEvents, and records a stable code when a pending
move FileEvent fails.

Values must be stable snake_case strings. Adapter-specific raw exception names
and raw exception messages must not be persisted as codes; `error_message`
carries the human-readable failure detail.

Current core apply codes are:

| Code | Meaning |
| --- | --- |
| `target_exists` | The FileMover reported `FileExistsError` after the pending event was recorded, including a target that appeared after planning. |
| `source_missing` | The FileMover reported `FileNotFoundError` after the pending event was recorded. A source missing during precondition verification creates no FileEvent. |
| `invalid_path` | The anchored FileMover rejected a symlink, path escape, or pathname replacement after the pending event was recorded. Invalid restore provenance found during precondition verification creates no FileEvent. |
| `move_failed` | The FileMover raised another `OSError` that has no more-specific stable code. |

New codes are permitted when a new observable mutation failure needs a stable
programmatic classification. They must be documented in the execution contract
that emits them and covered by tests; update the table when core apply begins
emitting a new code.

## CheckIssue Issue Type

Field: `CheckIssue.issue_type`.

```text
db_file_missing
unmanaged_file_exists
content_hash_changed
metadata_hash_changed
current_path_differs_from_canonical_path
duplicate_candidate
plan_source_changed
pending_file_event_exists
library_unregistered
library_stale
library_blocked
```

## Operation Kind

Field: `Operation.kind`.

```text
add_plan
organize_plan
refresh_plan
check
apply_plan
undo_plan
```

## Operation Status

Field: `Operation.status`.

```text
queued
running
succeeded
failed
interrupted
```

`interrupted` applies only to durable Operations. Restart reconciliation makes
an associated Run and Plan terminal using their existing `failed` or
`partial_failed` statuses; it does not add an `interrupted` Run or Plan status.

## Operation Result Kind

Field: `Operation.result.kind` when status is `succeeded`.

```text
plan_created
registered_without_plan
check_completed
run_completed
```

The lifecycle, result fields, and retention contract are in
[operations.md](operations.md).

## Status Presentation Contract

Every known closed value has an explicit product-default-language label,
meaning, tone, and icon mapping in the renewed frontend. Every open schema and
every server value newer than the bundled mapping has a neutral unknown-value
fallback that displays the raw stable code without crashing or enabling an
operation.

Presentation follows these rules:

* status is never communicated by color alone; text or an accessible name is
  mandatory;
* a Plan with blocked actions may still be applied when its backend capability
  permits it; executable and unresolved blocked counts remain separate;
* `partial_failed` means confirmed work and failure coexist and must never be
  described as rollback;
* a `pending` FileEvent means the mutation outcome is unknown and requires
  manual review; no automatic repair action is presented;
* a terminal Plan is never presented with Retry; the recovery action is
  “Create a new Plan from the current state”;
* a succeeded Run with zero FileEvents is valid for blocked-only, skip-only, or
  `refresh_metadata` actions and displays its linked PlanAction summary;
* a Run whose Plan contains `refresh_metadata` is presented as Undo-ineligible
  before Apply and in History;
* disabled controls remain visible with backend-provided reasons and
  remediation. The frontend never infers permission from these statuses.

## Cross-Cutting Rules

* Skip actions become applied without FileEvent.
* `refresh_metadata` actions become applied without FileEvent; the Track is updated in place.
* Blocked actions remain blocked during apply.
* Precondition failures before mutation do not create FileEvents.
* Terminal Plans are single-use.
* Operation stage codes and FileEvent error codes are open stable snake_case
  schemas and require unknown-value fallbacks.
* Status catalog changes require state transition and failure behavior tests.
