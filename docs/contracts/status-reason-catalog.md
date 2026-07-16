---
type: Contract
title: Status And Reason Catalog
description: Defines the versioned Track and CompanionAsset statuses, Plan action/reason, unprocessed FileEvent and CheckIssue values, durable-operation catalogs, triage, and presentation behavior.
tags: [status, reason-codes, catalog, execution, companions, unprocessed, operations]
timestamp: 2026-07-16T04:51:16+09:00
---

# Status And Reason Catalog

This document is authoritative for allowed status, reason, action type, event
type, check issue, Operation kind/status/result values, the FileEvent error-code
schema, and cross-surface status presentation behavior.

Domain concepts are in [../DOMAIN.md](../DOMAIN.md). Execution state transitions are in [../execution/model.md](../execution/model.md), [../execution/apply.md](../execution/apply.md), and [../execution/failure-policy.md](../execution/failure-policy.md).

## Catalog Version

The catalog version returned by Bootstrap is integer `3`. It versions the
closed catalogs in this document as one bundled client/server contract. Adding,
removing, or redefining a closed value increments the version in the same
coordinated change. It does not version the open FileEvent error-code or
Operation stage-code schemas.

Version 2 adds companion closed values. Binaries bundled with version 1 must
not apply Plans containing them; the backup, ready-Plan cleanup, and
manual-review downgrade procedure is authoritative in
[Stage 4 And 5 Backup And Downgrade](db-schema.md#stage-4-and-5-backup-and-downgrade).

Version 3 adds `move_unprocessed`, `move_unprocessed_file`,
`unprocessed_file_missing`, and `unprocessed_content_hash_changed`. Version 1
or 2 binaries must not read current Stage 5 state or apply a Plan containing
these values; they must use the matched backup/downgrade procedure above.

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

## CompanionAsset Kind

Field: `CompanionAsset.kind`.

```text
lyrics
artwork
```

## CompanionAsset Status

Field: `CompanionAsset.status`.

```text
active
removed
```

`removed` retains the stable asset identity and its last managed
Library-relative paths after an external Add Undo.

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
move_lyrics
move_artwork
move_unprocessed
skip
refresh_metadata
```

`conflict` and `error` are not action types.

`move_lyrics` and `move_artwork` are metadata-free companion mutations.
`move_unprocessed` is a trackless, dependency-free, content-only mutation
between two absolute paths below a retained Add source root.
`refresh_metadata` reingests Track metadata and hashes for an unchanged path
without a file mutation.

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
companion_owner_blocked
companion_association_ambiguous
companion_dependency_failed
operation_interrupted
```

Plan creation problems are blocked. Apply-time precondition failures are failed.
`companion_owner_blocked` means a usable owning audio action/target was not
available at review time. `companion_association_ambiguous` means lyrics had
multiple possible owners or directory artwork's audio targets did not share
one parent. `companion_dependency_failed` is an Apply-time failure recorded
before observation or mutation when a durable dependency or semantic owner is
not successfully applied.
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
move_lyrics_file
move_artwork_file
move_unprocessed_file
```

## FileEvent Status

Field: `FileEvent.status`.

```text
pending
succeeded
failed
```

FileEvents are created only for attempted reviewed audio, companion, or
unprocessed-file mutations. `move_unprocessed_file` carries no Track or
CompanionAsset identity.

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
companion_file_missing
companion_content_hash_changed
companion_current_path_differs_from_canonical_path
companion_owner_missing
unmanaged_companion_exists
failed_companion_source_exists
unprocessed_file_missing
unprocessed_content_hash_changed
duplicate_candidate
plan_source_changed
pending_file_event_exists
library_unregistered
library_stale
library_blocked
```

`failed_companion_source_exists` is a recovery finding, not proof of an
unrecorded success. It requires definitive non-pending failure evidence for a
terminal companion action, succeeded owner-audio provenance, an active
same-Library owner Track, and a safely rooted source that still exists. It
permits creation of a new reviewed Plan; it never authorizes automatic repair.
Its `detail` is `add` for an exact-root external recovery and `organize` for a
Library-relative recovery. This stable scope drives suggested-command grouping
on both POSIX and Windows; clients must not infer it from path spelling.

`unprocessed_file_missing` and `unprocessed_content_hash_changed` describe the
target of an unreversed succeeded `move_unprocessed_file` event. Both have
`error` severity and map to the `history` command family with label
`omym2 history`. They intentionally do not suggest Refresh, Add, or automatic
repair because the Plan/FileEvent pair, not a managed Track row, is the durable
evidence.

## Stage 5 Presentation Labels

The product-default labels for the new closed values are:

| Value | Label | Tone |
| --- | --- | --- |
| `move_unprocessed` | Move unprocessed file | info |
| `move_unprocessed_file` | Move unprocessed file | info |
| `unprocessed_file_missing` | Unprocessed file is missing | danger |
| `unprocessed_content_hash_changed` | Unprocessed file content changed | danger |

The two findings present an explicit History-review remediation and never an
automatic repair control.

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
* Companion actions require every recorded dependency before filesystem
  observation and create a typed pending FileEvent before mutation.
* Unprocessed actions require exact retained-root path shape and content hash,
  create a typed pending FileEvent, and never create managed Track or
  CompanionAsset state.
* A successful companion move creates or advances its CompanionAsset; failed
  and pending mutations do not.
* Blocked actions remain blocked during apply.
* Precondition failures before mutation do not create FileEvents.
* Terminal Plans are single-use.
* Operation stage codes and FileEvent error codes are open stable snake_case
  schemas and require unknown-value fallbacks.
* Status catalog changes require state transition and failure behavior tests.
