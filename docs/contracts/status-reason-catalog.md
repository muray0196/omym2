---
type: Contract
title: Status And Reason Catalog
description: Closed status/reason/type/error-code catalogs for all entities plus cross-surface presentation rules.
tags: [status, reason-codes, catalog, execution, companions, unprocessed, operations]
timestamp: 2026-07-18T12:00:00+09:00
---

# Status And Reason Catalog

Authoritative for allowed status, reason, action type, event type, check issue, and Operation kind/status/result values, the FileEvent error-code schema, and cross-surface status presentation. Domain concepts: [../DOMAIN.md](../DOMAIN.md); state transitions: [../execution/model.md](../execution/model.md), [../execution/apply.md](../execution/apply.md), [../execution/failure-policy.md](../execution/failure-policy.md).

## Library Status

`Library.status`: `registered` | `unregistered` | `stale` | `blocked`

## Track Status

`Track.status`: `active` | `removed`

`missing` is reported by `check`, not persisted as Track status.

## CompanionAsset Kind

`CompanionAsset.kind`: `lyrics` | `artwork`

## CompanionAsset Status

`CompanionAsset.status`: `active` | `removed`

`removed` retains the stable asset identity and its last managed Library-relative paths after an external Add Undo.

## Plan Status

`Plan.status`: `ready` | `applying` | `applied` | `partial_failed` | `failed` | `cancelled` | `expired`

## PlanAction Action Type

`PlanAction.action_type`: `move` | `move_lyrics` | `move_artwork` | `move_unprocessed` | `skip` | `refresh_metadata`

`conflict` and `error` are not action types. `move_lyrics`/`move_artwork` are metadata-free companion mutations. `move_unprocessed` is a trackless, dependency-free, content-only mutation between two absolute paths below a retained Add source root. `refresh_metadata` reingests Track metadata and hashes for an unchanged path without a file mutation.

## PlanAction Status

`PlanAction.status`: `planned` | `blocked` | `applied` | `failed`

`skip` is an action type, not a status.

## PlanAction Reason

`PlanAction.reason`: `target_exists` | `missing_required_metadata` | `invalid_path` | `source_missing` | `source_changed` | `duplicate_hash` | `companion_owner_blocked` | `companion_association_ambiguous` | `companion_dependency_failed` | `operation_interrupted`

Plan-creation problems are blocked; apply-time precondition failures are failed. `companion_owner_blocked`: no usable owning audio action/target at review time. `companion_association_ambiguous`: lyrics had multiple possible owners, or directory artwork's audio targets did not share one parent. `companion_dependency_failed`: apply-time failure recorded before observation or mutation when a durable dependency or semantic owner is not successfully applied. `operation_interrupted`: an eligible action whose completion could not be confirmed after worker dispatch failure or process restart; a related pending FileEvent remains the authority for an unknown mutation outcome.

## Run Status

`Run.status`: `running` | `succeeded` | `partial_failed` | `failed`

## FileEvent Event Type

`FileEvent.event_type`: `move_file` | `move_lyrics_file` | `move_artwork_file` | `move_unprocessed_file`

## FileEvent Status

`FileEvent.status`: `pending` | `succeeded` | `failed`

FileEvents are created only for attempted reviewed audio, companion, or unprocessed-file mutations. `move_unprocessed_file` carries no Track or CompanionAsset identity.

## FileEvent Error Code

`FileEvent.error_code` is a nullable open schema, not a closed enum. Apply writes `null` for pending and succeeded FileEvents and records a stable snake_case code when a pending move FileEvent fails. Adapter-specific raw exception names/messages are never persisted as codes; `error_message` carries human-readable detail.

Current core apply codes:

| Code | Meaning |
| --- | --- |
| `target_exists` | FileMover reported `FileExistsError` after the pending event, including a target that appeared after planning. |
| `source_missing` | FileMover reported `FileNotFoundError` after the pending event. A source missing during precondition verification creates no FileEvent. |
| `invalid_path` | Anchored FileMover rejected a symlink, path escape, or pathname replacement after the pending event. Invalid restore provenance found during precondition verification creates no FileEvent. |
| `move_failed` | FileMover raised another `OSError` with no more-specific stable code. |

New codes are permitted for a new observable mutation failure needing stable programmatic classification; document them in the emitting execution contract, cover with tests, and update this table when core apply emits one.

## CheckIssue Issue Type

`CheckIssue.issue_type`: `db_file_missing` | `unmanaged_file_exists` | `content_hash_changed` | `metadata_hash_changed` | `current_path_differs_from_canonical_path` | `companion_file_missing` | `companion_content_hash_changed` | `companion_current_path_differs_from_canonical_path` | `companion_owner_missing` | `unmanaged_companion_exists` | `failed_companion_source_exists` | `unprocessed_file_missing` | `unprocessed_content_hash_changed` | `duplicate_candidate` | `plan_source_changed` | `pending_file_event_exists` | `library_unregistered` | `library_stale` | `library_blocked`

`failed_companion_source_exists` is a recovery finding, not proof of an unrecorded success. It requires definitive non-pending failure evidence for a terminal companion action, succeeded owner-audio provenance, an active same-Library owner Track, and a safely rooted source that still exists. It permits creation of a new reviewed Plan, never automatic repair. Its `detail` is `add` (exact-root external recovery) or `organize` (Library-relative recovery); this stable scope drives suggested-command grouping on both POSIX and Windows — clients must not infer it from path spelling.

`unprocessed_file_missing` and `unprocessed_content_hash_changed` describe the target of an unreversed succeeded `move_unprocessed_file` event. Both have `error` severity and map to the `history` command family with label `omym2 history`; they intentionally do not suggest Refresh, Add, or automatic repair because the Plan/FileEvent pair, not a managed Track row, is the durable evidence.

## Unprocessed Presentation Labels

| Value | Label | Tone |
| --- | --- | --- |
| `move_unprocessed` | Move unprocessed file | info |
| `move_unprocessed_file` | Move unprocessed file | info |
| `unprocessed_file_missing` | Unprocessed file is missing | danger |
| `unprocessed_content_hash_changed` | Unprocessed file content changed | danger |

The two findings present an explicit History-review remediation, never an automatic repair control.

## Operation Kind

`Operation.kind`: `add_plan` | `organize_plan` | `refresh_plan` | `check` | `apply_plan` | `undo_plan`

## Operation Status

`Operation.status`: `queued` | `running` | `succeeded` | `failed` | `interrupted`

`interrupted` applies only to durable Operations. Restart reconciliation makes an associated Run and Plan terminal using their existing `failed` or `partial_failed` statuses; there is no `interrupted` Run or Plan status.

## Operation Result Kind

`Operation.result.kind` when status is `succeeded`: `plan_created` | `registered_without_plan` | `check_completed` | `run_completed`

Lifecycle, result fields, and retention: [operations.md](operations.md).

## Status Presentation Contract

Every closed value has an explicit product-default-language label, meaning, tone, and icon mapping in the bundled frontend. The SPA and API ship from the same commit; a missing closed-value mapping is a programming or data-integrity error and fails explicitly instead of presenting a neutral fallback. Only an explicitly open field such as `FileEvent.error_code` may display an unknown raw stable code.

* Status is never communicated by color alone; text or an accessible name is mandatory.
* A Plan with blocked actions may still be applied when its backend capability permits; executable and unresolved blocked counts stay separate.
* `partial_failed` means confirmed work and failure coexist; never describe it as rollback.
* A `pending` FileEvent means the mutation outcome is unknown and requires manual review; no automatic repair action is presented.
* A terminal Plan is never presented with Retry; the recovery action is "Create a new Plan from the current state".
* A succeeded Run with zero FileEvents is valid for blocked-only, skip-only, or `refresh_metadata` actions and displays its linked PlanAction summary.
* A Run whose Plan contains `refresh_metadata` is presented as Undo-ineligible before Apply and in History.
* Disabled controls remain visible with backend-provided reasons and remediation; the frontend never infers permission from these statuses.

## Cross-Cutting Rules

* Skip actions become applied without FileEvent.
* `refresh_metadata` actions become applied without FileEvent; the Track is updated in place.
* Companion actions require every recorded dependency before filesystem observation and create a typed pending FileEvent before mutation.
* Unprocessed actions require exact retained-root path shape and content hash, create a typed pending FileEvent, and never create managed Track or CompanionAsset state.
* A successful companion move creates or advances its CompanionAsset; failed and pending mutations do not.
* Blocked actions remain blocked during apply.
* Precondition failures before mutation do not create FileEvents.
* Terminal Plans are single-use.
* FileEvent error codes are an open stable snake_case schema and retain an explicit unknown-value presentation.
* Status catalog changes require state transition and failure behavior tests.
