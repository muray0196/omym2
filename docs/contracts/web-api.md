---
type: Contract
title: Web API Contract
description: Defines the bundled local Web API's typed envelopes, errors, bootstrap, settings concurrency, durable-operation routes, capabilities, and preserved browsing semantics.
tags: [web-api, openapi, operations, concurrency, pagination]
timestamp: 2026-07-13T19:17:09+09:00
---

# Web API Contract

This document is authoritative for OMYM2's local HTTP API: Pydantic request
and response models, JSON envelopes, structured errors, status codes, CSRF,
Bootstrap, Library and Settings resources, capability projections, durable
Operation routes, and browsing endpoint behavior.

The frontend/backend boundary is summarized in
[web-frontend.md](../codebase/web-frontend.md). Config storage and raw revision
behavior are authoritative in [config.md](config.md). Durable Operation
lifecycle, idempotency, polling, and retention are authoritative in
[operations.md](operations.md). Status and reason values are authoritative in
[status-reason-catalog.md](status-reason-catalog.md). The deliberate breaking
API decision is recorded in
[ADR 0001](../decisions/0001-breaking-bundled-web-api.md).

## Bundled Breaking Contract

The SPA and API ship from the same commit in one Python package. The API is not
an independently supported external-client surface.

* Routes remain under `/api`; there is no `/api/v1` prefix.
* The previous handwritten envelopes and synchronous long-running endpoints
  receive no compatibility adapter or transition period.
* The renewed SPA and API cut over together.
* Supporting independent external clients or a versioned compatibility
  surface requires a new architecture decision.

## Schema Source And Generated Client

Every route has Pydantic request and response models, including every declared
error response. Handwritten dictionaries are not an API schema source, and the
SPA must not duplicate Python response shapes manually.

A schema-only FastAPI app factory registers exactly the production API route
and model set without constructing or accessing a Config store, SQLite
database, filesystem adapter, metadata adapter, network client, or static Web
build. Generating OpenAPI must therefore perform no application I/O.

The generated TypeScript schema and client are committed. Contract changes
must update the Pydantic models, OpenAPI output, generated client, Python
contract tests, and SPA in one change. CI runs these steps in order:

1. Python API schema and contract tests.
2. OpenAPI export from the schema-only app.
3. TypeScript schema/client generation and drift check.
4. Frontend typecheck.

The drift check fails when regeneration changes a committed generated file.

## Generic Envelope

Every API response body uses this envelope:

```ts
type ApiEnvelope<T> = {
  data: T | null
  errors: ApiError[]
}

type ApiError = {
  code: ApiErrorCode
  message: string
  field?: string
  retryable: boolean
  remediation?: {
    label: string
    route?: string
    command?: string
  }
}
```

Envelope invariants are:

* Normal success: `data != null` and `errors = []`.
* Failure: `data = null` and `errors` is non-empty.
* A legitimate empty collection or empty result is a non-null typed value; it
  is never represented by `data = null`.
* Degraded Bootstrap is the sole exception: it may return recovery-oriented
  non-null data and non-empty errors together.
* A response never mixes a normal resource result with warnings in the
  top-level `errors`; resource-local validation diagnostics belong in that
  resource's typed data.

`ApiError.message` is displayable fallback text, not a branching contract.
Clients branch only on `code`. `field`, when present, uses a stable qualified
location such as `body.config.paths.library`, `query.cursor`, `path.plan_id`,
or `header.Idempotency-Key`.

`retryable` states whether the same logical request can be attempted again
after its stated condition changes. It does not authorize automatic mutation
retry. A remediation may contain a route, a command, both, or neither; the
client displays it but never executes a command automatically.

Every API response includes `X-OMYM2-Correlation-ID`. The same identifier is
written to server logs. Unexpected exception details and stack traces are
logged with that identifier but are never returned to the client.

## Error Catalog And Status Codes

`ApiError.code` is a closed catalog. The initial mapping for top-level failure
envelopes is:

| HTTP | Allowed codes |
| --- | --- |
| `400` | `invalid_json` |
| `403` | `csrf_invalid` |
| `404` | `api_not_found`, `library_not_found`, `track_not_found`, `plan_not_found`, `run_not_found`, `operation_not_found` |
| `405` | `method_not_allowed` |
| `409` | `config_invalid`, `config_changed`, `operation_in_progress`, `idempotency_key_reused`, `library_selection_ambiguous`, `library_unregistered`, `library_stale`, `library_blocked`, `plan_not_ready`, `library_root_changed`, `run_not_terminal`, `nothing_to_undo`, `undo_refresh_metadata_unsupported`, `already_undone_or_in_progress`, `pending_file_event_requires_review` |
| `410` | `operation_expired` |
| `422` | `validation_failed`, `path_not_found`, `path_not_directory`, `path_outside_library` |
| `500` | `storage_unavailable`, `config_io_failed`, `internal_error` |

Embedded `disabled_reasons`, validation diagnostics, and degraded Bootstrap
errors reuse the same codes inside a successful resource response; their
containing HTTP status remains 200 because they do not make that resource
envelope a top-level failure.

The following closed codes describe terminal Operation errors inside an
Operation resource rather than defining an additional HTTP status:

```text
operation_interrupted
metadata_read_failed
operation_failed
```

Invalid UUIDs, cursors, filter values, `group_by` values, headers, query
parameters, path parameters, and structurally valid JSON bodies return `422`.
Only JSON decoding failure returns `400 invalid_json`.

`FileEvent.error_code` is a separate open schema of stable snake_case values.
It is not narrowed to `ApiErrorCode`, and clients provide an unknown-value
fallback.

Successful responses use these status codes:

* `200` for reads, synchronous updates, and retained terminal Operation replay;
* `201` when a future route completes synchronous resource creation;
* `202` when a durable Operation is newly accepted or an active Operation is
  replayed idempotently.

The initial resource-creation workflows are durable Operations, so none of
them use `201` merely because their eventual result names a resource.

### Application Error Handlers

The FastAPI app installs handlers that preserve the envelope for:

* JSON decoding failures;
* `RequestValidationError`;
* application/domain errors translated by inbound routes;
* `HTTPException`;
* unknown API routes;
* method-not-allowed responses;
* unexpected exceptions.

Unknown `/api` routes always return JSON `404 api_not_found`; they never reach
the SPA fallback. Known routes called with an unsupported method return JSON
`405 method_not_allowed`.

Raw Python exceptions, exception class names, stack traces, arbitrary SQL
messages, and unredacted filesystem exception text must not appear in
responses. File and directory fields that are already part of an authorized
resource remain available through that resource's typed fields; errors do not
echo raw exception strings merely to expose a path.

## CSRF And Mutation Retry

`GET /api/bootstrap` issues the CSRF token without depending on valid Config or
database state. Every state-changing request sends it in
`X-OMYM2-CSRF-Token`. A missing or invalid token returns `403 csrf_invalid`
before validation side effects, lock acquisition, Operation acceptance, or
mutation.

After receiving exactly `403 csrf_invalid`, a client may refresh Bootstrap
once and retry once only for these explicitly safe cases:

* an Operation-start request with the identical `Idempotency-Key` and body;
* `PUT /api/settings` with the identical `expected_config_revision` and body;
* ready-Plan cancellation with the identical Plan ID.

The client does not automatically resend a mutation after a connectivity
failure, timeout, generic `403`, `409`, or `500`. It polls an accepted
Operation rather than resending its mutation.

## Shared Browsing Shapes

### List Data

Every keyset-paginated list endpoint returns:

```jsonc
{
  "data": {
    "items": [ /* typed rows */ ],
    "page": {
      "limit": 100,
      "next_cursor": "b64url...", // or null
      "total": 1234
    }
  },
  "errors": []
}
```

`page.total` counts rows matching the same filters while ignoring the cursor,
evaluated for that response. Pagination is not a snapshot; totals may change
between page requests. `page.next_cursor` is null when no further page exists,
and `page.limit` is the effective post-clamp limit.

### Cursor

A cursor is opaque to clients. Its current server representation is
`base64url(JSON array of strings)` over endpoint-specific keyset columns, but
clients only echo `next_cursor` as the next request's `cursor`; they never
construct, decode, or interpret it.

A cursor that fails decoding, JSON parsing, value-shape validation, or the
endpoint's key-length/value validation returns `422 validation_failed` with
`field = "query.cursor"`.

### Limit

`limit` defaults to 100, has a minimum of 1, and has a maximum of 500. Values
above 500 clamp to 500. A non-integer value or value below 1 returns
`422 validation_failed`. These behaviors match the shared pagination
primitives; routes do not implement a second limit policy.

### Facet Data

Facet endpoints ignore pagination and return:

```jsonc
{
  "data": {
    "facets": {
      "<field>": [
        { "value": "...", "count": 17 }
      ]
    },
    "total": 1234
  },
  "errors": []
}
```

`total` counts rows matching the request's filters. Check facets additionally
carry `checked_at` inside `data`.

### Group Data

Group endpoints return:

```jsonc
{
  "data": {
    "group_by": "<key>",
    "items": [
      { "key": "...", "label": "...", "count": 42 }
    ],
    "page": {
      "limit": 100,
      "next_cursor": null,
      "total": 1
    }
  },
  "errors": []
}
```

Groups order by `count DESC, key ASC`. `page.total` counts group rows matching
the filters while ignoring the cursor and has no cross-page snapshot
guarantee.

PlanAction group rows add `blocked_count` and `top_reason`.
`blocked_count` counts members whose recorded status is `blocked`.
`top_reason` is the most frequent non-null recorded reason, breaking ties by
lexicographically smaller reason, and is null when no member has a reason.

CheckIssue group rows add `common_path_root`, the most frequent non-null
derived path root. Equal counts choose the lexicographically smaller root, and
the value is null when every member is pathless.

## Bootstrap

### `GET /api/bootstrap`

Returns `200 ApiEnvelope<BootstrapData>`:

```ts
type BootstrapData = {
  app_version: string
  csrf_token: string
  status_catalog_version: number
  active_library: LibraryResource | null
  library_diagnostics: ApiError[]
  config_validation: {
    valid: boolean
    config_revision: string | null
    errors: ApiError[]
  }
  runtime_capabilities: {
    can_read_state: boolean
    can_change_settings: boolean
    can_start_operations: boolean
    can_start_organize: boolean
    disabled_reasons: ApiError[]
  }
  operation_polling: {
    initial_ms: number
    backoff_factor: number
    max_ms: number
  }
  active_operation_id: string | null
}
```

Bootstrap selects a Library only when selection is unambiguous. When no
Library can be selected, or multiple Libraries make selection ambiguous,
`active_library` is null and `library_diagnostics` explains the condition.
It never silently selects the first Library.

Bootstrap is the sole degraded-envelope exception. Invalid Config or
unavailable persistence may produce non-null recovery data and top-level
errors simultaneously. CSRF issuance, app version, and catalog version remain
available so the client can open Settings and display recovery guidance.
`status_catalog_version` is exactly `1` for this frozen contract.
The polling values are serialized from the constants centralized in
`src/omym2/config.py`; the SPA and its tests do not repeat policy literals.

`can_start_organize` is the explicit capability for
`POST /api/plans/organize`. It remains true when Library selection is missing,
unregistered, stale, blocked, or ambiguous because an explicit Library root is
the registration and reconciliation input. It is false when Config cannot be
loaded validly or state storage cannot be read. Its disabled reasons use
`field = "runtime_capabilities.can_start_organize"`. The Organize endpoint
still revalidates the submitted root and all mutation-time guards; this
advisory capability does not authorize an unmatched root when another Library
exists.

## Libraries

```ts
type LibraryResource = {
  library_id: string
  root_path: string
  status: "registered" | "unregistered" | "stale" | "blocked"
  is_registered: boolean
  registered_at: string | null
  path_policy_fingerprint: string
  is_path_policy_current: boolean
}
```

* `GET /api/libraries` returns `200` with
  `data = { "items": LibraryResource[] }`.
* `GET /api/libraries/{library_id}` returns `200` with one
  `LibraryResource`.

Library IDs remain in every route and resource even though the initial SPA
presents only one unambiguous active Library. An unknown ID returns
`404 library_not_found`; an invalid UUID returns `422 validation_failed`.

`is_path_policy_current` is derived from the Library's stored fingerprint and
the current valid Config. Settings save does not attempt a cross-store atomic
write merely to persist this derived readiness value.

`path_policy_fingerprint` is the API name for the stored
`libraries.path_policy_hash`; it is opaque to the client. `LibraryResource.status`
is the effective projection: when the persisted status is `registered` but the
fingerprint comparison is false, the API returns `status = "stale"`, emits a
`library_stale` diagnostic/capability reason, and disables Add. It never returns
an apparently ready `registered` resource with `is_path_policy_current = false`.

## Settings

The Config schema and revision algorithm are authoritative in
[config.md](config.md). The Web API never reads or writes TOML directly; it
calls Settings usecases through ports.

### `GET /api/settings`

Returns `200` with:

```ts
type SettingsData = {
  config: AppConfigResource
  config_revision: string
  choices: SettingsChoices
  validation: {
    valid: boolean
    errors: ApiError[]
  }
  preview: PathPreview
}
```

Invalid persisted TOML is represented by `validation.valid = false` and
resource-local validation errors while the top-level envelope remains a normal
success. `config` contains the backend-provided recovery draft. The raw invalid
text is never returned.

### `POST /api/settings/validate`

The Pydantic request contains `config` and `expected_config_revision`.
Revision mismatch returns `409 config_changed`. Otherwise the `200` response
contains `valid`, typed validation errors, a before/after change list, and a
PathPolicy preview. Candidate-domain validation failure is a typed validation
result, not an unexpected server error.

### `POST /api/settings/preview`

Accepts a self-contained PathPolicy/Artist-ID draft, sample Track metadata,
and file extension. It returns `200` with `PathPreview`. It performs no Config
or DB write and requires no revision because every input affecting the preview
is in the request.

### `PUT /api/settings`

The Pydantic request contains `config` and `expected_config_revision`. The
usecase acquires the shared exclusive-operation lock, re-reads the raw
revision, and atomically replaces the Config only when the revision matches.

Success returns `200` with the saved Config, new `config_revision`, change
list, validation result, and preview. A mismatch returns
`409 config_changed` and performs no write. Invalid candidate Config returns
`422 validation_failed`. A client may intentionally replace invalid persisted
TOML when it supplies the revision it read; invalid current Config does not by
itself block this recovery save. Config I/O failure returns
`500 config_io_failed`.

### `POST /api/settings/artist-ids/generate`

Accepts artist names, overwrite intent, and the Artist-ID settings from the
current form draft. It returns generated draft entries and performs no Config
write. The client merges the result into its local Settings draft; only
`PUT /api/settings` persists it. This draft-only endpoint is not a mutation and
does not require CSRF or an idempotency key.

## Capabilities

Capabilities are computed by feature usecases, not route adapters. They are
advisory display snapshots and are revalidated at mutation time.

```ts
type PlanCapabilities = {
  can_apply: boolean
  can_cancel: boolean
  can_recreate: boolean
  disabled_reasons: ApiError[]
}

type RunCapabilities = {
  can_create_undo: boolean
  disabled_reasons: ApiError[]
}

type PlanDetailData = {
  plan: PlanHeader
  summary: PlanActionSummary
  capabilities: PlanCapabilities
  active_operation_id: string | null
}

type RunDetailData = {
  run: RunHeader
  capabilities: RunCapabilities
  active_operation_id: string | null
}
```

Every disabled capability has at least one reason with remediation when a
known next action exists. The frontend does not infer permission from Plan or
Run status. Unknown reason codes use generic disabled presentation.

Capability reasons set `field` to the affected capability, for example
`capabilities.can_apply`, so one detail response cannot ambiguously attach a
reason to the wrong control. A ready Plan may have `can_apply = true` even when
some or all actions are blocked; the typed summary keeps blocked and executable
counts separate.

`can_recreate` means the backend permits opening the corresponding Add,
Organize, or Refresh creation flow to calculate a new Plan from current state.
It never clones recorded PlanActions or bypasses that creation endpoint. Undo
Plan recreation follows the Run capability and Undo deduplication contract
instead.

Plan detail and Run detail each expose `active_operation_id: string | null`.
It identifies the related queued/running Operation and is null when no related
Operation is active. A `409 operation_in_progress` response includes
remediation to the active Operation route when an Operation ID is available.

## Durable Operation HTTP Resource

Operation lifecycle and result kinds are authoritative in
[operations.md](operations.md). The HTTP projections are:

```ts
type OperationRef = {
  operation_id: string
  kind: "add_plan" | "organize_plan" | "refresh_plan" | "check" |
    "apply_plan" | "undo_plan"
  status: "queued" | "running" | "succeeded" | "failed" | "interrupted"
  status_url: string
  poll_after_ms: number
}

type OperationResource = {
  operation_id: string
  kind: OperationRef["kind"]
  status: OperationRef["status"]
  library_id: string | null
  plan_id: string | null
  run_id: string | null
  progress: {
    stage_code: string | null
    completed_units: number | null
    total_units: number | null
    message: string | null
  }
  result:
    | { kind: "plan_created"; plan_id: string }
    | { kind: "registered_without_plan"; library_id: string; track_count: number }
    | { kind: "check_completed"; check_run_ids: string[]; issue_count: number }
    | { kind: "run_completed"; run_id: string }
    | null
  error: ApiError | null
  requested_at: string
  started_at: string | null
  completed_at: string | null
}
```

`poll_after_ms` is 500 initially. Clients apply the polling/backoff policy from
the Operation contract. Progress counts are both null or both non-null; the
client never fabricates a percentage.

The nullable Library/Plan/Run associations are durable navigation evidence,
not a success result. They remain available on failed or interrupted
Operations so polling can open the affected Plan, Run History, or Check/manual
review even when no `run_completed` result exists.

### `GET /api/operations/{operation_id}`

Returns `200 ApiEnvelope<OperationResource>` while the full active or retained
terminal resource exists. A retained tombstone returns
`410 operation_expired`. An unknown or fully purged ID returns
`404 operation_not_found`.

GET is a read-only snapshot and never reconciles state. The platform supervisor
performs the bounded lock-based liveness check from the Operation contract, so
a recently orphaned queued/running row may remain visible until the next
supervisor pass and then becomes terminal on a later poll.

## Operation Acceptance And Idempotency

Each endpoint that starts an Operation requires a client-generated UUID in
`Idempotency-Key` and a valid CSRF token. Missing or invalid header syntax
returns `422 validation_failed`.

Acceptance classifies any retained idempotency key before lock acquisition: a
matching kind/fingerprint returns its active, terminal, or tombstone outcome;
a mismatched kind/fingerprint returns `409 idempotency_key_reused`; only an
absent key proceeds to the exclusive lock. The reservation transaction then
rechecks the key before touching a Plan or inserting anything.

An exact queued/running replay remains read-only and returns `202`; the bounded
platform supervisor, startup, or pre-mutation pass owns stale-row
reconciliation. After that pass commits, replay returns the terminal resource
with `200`.

New acceptance returns `202 ApiEnvelope<OperationRef>` and a relative status
URL in `Location`. Replaying the same key, Operation kind, and canonical
request returns the existing reference without redispatch:

* queued/running replay returns `202` and `Location`;
* a retained terminal replay returns `200` and `Location`;
* a matching request whose Operation is in its tombstone period returns
  `410 operation_expired` and never executes again;
* reuse with a different kind or request fingerprint returns
  `409 idempotency_key_reused`.

An Operation result containing `plan_created` stores only `plan_id`. The
client refetches Plan detail and retrieves actions through cursor pagination;
Operation results never embed PlanActions or a stale capability snapshot.

The Operation-start routes are:

* `POST /api/plans/add` — accepts an optional `source_path` and selected
  `library_id`; starts `add_plan`.
* `POST /api/plans/organize` — accepts the explicitly confirmed
  `library_root`; starts `organize_plan`.
* `POST /api/plans/refresh` — accepts exactly one file, directory, or all
  target plus selected `library_id`; starts `refresh_plan`.
* `POST /api/check/run` — accepts optional `library_id`; starts `check`.
* `POST /api/plans/{plan_id}/apply` — starts `apply_plan` after the atomic
  Apply claim.
* `POST /api/history/{run_id}/undo-plan` — starts `undo_plan`.

Web Plan creation and Check requests never accept `trust_stat`; that
optimization remains CLI-only.

## Apply, Cancel, And Undo

### `POST /api/plans/{plan_id}/apply`

Apply uses only recorded PlanActions. Before returning `202`, the backend holds
the shared exclusive lock, verifies `library_root_at_plan`, and atomically
commits the Plan `ready -> applying` compare-and-set, running Run, and queued
Operation reservation.

Root mismatch before Run creation expires the Plan and returns
`409 library_root_changed`. A non-ready or terminal Plan returns
`409 plan_not_ready`. Capabilities do not replace this mutation-time claim.

### `POST /api/plans/{plan_id}/cancel`

Ready-Plan cancellation is synchronous and does not create an Operation. It
acquires the shared lock and performs a `ready -> cancelled` compare-and-set.
Success returns `200` with the updated Plan header and capabilities. Losing a
race to Apply or another Cancel returns `409 plan_not_ready`. In-flight
Operation cancellation is not supported.

### `POST /api/history/{run_id}/undo-plan`

Undo Plan generation is a durable Operation. Only terminal Runs with at least
one succeeded FileEvent and no `refresh_metadata` action are eligible. A
pending FileEvent in the source Run or any prior Undo Run for the same
`source_run_id` requires manual review and returns
`409 pending_file_event_requires_review` rather than guessing an original or
reversal outcome.

The endpoint returns an existing ready Undo Plan through the Operation result
instead of creating a duplicate. An applying or applied Undo Plan for the same
source Run returns `409 already_undone_or_in_progress`. No reversible events
returns `409 nothing_to_undo`; a running source Run returns
`409 run_not_terminal`; refresh metadata history returns
`409 undo_refresh_metadata_unsupported`.

After a failed or partially failed prior Undo Plan, regeneration is allowed
only from current durable state, only when no FileEvent in that source/prior-
Undo scope is pending, and must
exclude each source event linked by `reverses_event_id` to a succeeded reversal
FileEvent from the earlier Undo execution.

Undo never mutates the filesystem directly. Its `plan_created` result opens
normal Plan Review, and applying that Undo Plan uses the same Apply endpoint.

## Plan Endpoints

Plan ordering remains `created_at DESC, plan_id DESC`. Action ordering remains
`sort_order ASC, action_id ASC`.

* `GET /api/plans?query=&status=&type=&blocked=&limit=&cursor=` returns list
  data of `PlanSummary` rows. `query` matches `plan_id`, `library_id`,
  `plan_type`, or `status` as an ASCII-case-insensitive substring.
  `blocked=true` selects Plans whose current recorded PlanActions include at
  least one blocked action; omitted or false does not filter by blocked count.
  Filters combine before pagination. Every response `PlanSummary.summary` uses
  the typed action summary below rather than exposing the persisted opaque map.
* `GET /api/plans/{plan_id}` returns a Plan header, typed action summary,
  `PlanCapabilities`, and `active_operation_id`. It never embeds actions.
* `GET /api/plans/{plan_id}/actions?query=&status=&action_type=&reason=&group_by=&group_key=&limit=&cursor=`
  returns PlanAction list data. `query` matches `action_id`, `track_id`,
  `source_path`, `target_path`, `content_hash_at_plan`, or
  `metadata_hash_at_plan`. `group_by` and `group_key` are provided together or
  omitted together and combine with all other filters as AND.
* `GET /api/plans/{plan_id}/facets?query=&status=&action_type=&reason=` returns
  facets for `status`, `action_type`, and non-null `reason`. Each facet applies
  search and the other two filters while omitting its own. `data` additionally
  carries Plan-wide `target_collisions`, the count of distinct non-null target
  paths recorded by two or more actions; browse filters do not change it.
  `total` counts actions matching every supplied filter.
* `GET /api/plans/{plan_id}/groups?group_by=&query=&status=&action_type=&reason=&limit=&cursor=`
  returns enriched PlanAction groups. Supported groupings are
  `target_directory`, `source_directory`, `artist_album`, `action_type`,
  `status`, `block_reason`, and `extension`. Search and catalog filters apply
  before group counts and carry into group drill-downs.

The Plan detail action summary is computed from current recorded PlanActions,
not from an opaque string map:

```ts
type PlanActionTypeCounts = {
  move: number
  skip: number
  refresh_metadata: number
}

type PlanActionSummary = {
  total: number
  counts: {
    planned: PlanActionTypeCounts
    blocked: PlanActionTypeCounts
    applied: PlanActionTypeCounts
    failed: PlanActionTypeCounts
  }
}
```

Every count is a non-negative integer and `total` equals the sum of the full
status/action-type matrix.

PlanAction grouping derivations are unchanged:

* `target_directory` and `source_directory` use the stored path's POSIX parent;
  root-level files use `(root)`, and null paths have no group.
* `artist_album` uses the first two stored target-path directory segments. A
  label joins them with ` / `. A null target uses `(unknown)` /
  `Unknown Artist / Unknown Album`; a root-level target uses `(root)`.
* `action_type` and `status` use recorded catalog values.
* `block_reason` uses the recorded non-null reason; actions without a reason
  have no group.
* `extension` uses the lowercased source suffix without `.`, falling back to
  target; suffix-less paths use `(none)`, and actions without either path have
  no group.

Plan review never recalculates target paths from current Config.

## Track Endpoints

Ordinary Track ordering remains `current_path ASC, track_id ASC`. A group
drill-down orders Tracks by positive `track_number` first, then title and
`track_id`; missing or non-positive numbers follow numbered Tracks.

* `GET /api/tracks?query=&status=&track_id=&library_id=&group_by=&group_key=&limit=&cursor=`
  returns Track list data. `track_id` is exact. `query` matches title, artist,
  album, current path, or Track ID. `group_by` and `group_key` are supplied
  together or omitted together and combine with the other filters as AND.
* `GET /api/tracks/facets?query=&library_id=` returns the `status` facet.
  Counts apply search while omitting a selected list status.
* `GET /api/tracks/groups?group_by=&parent_key=&query=&status=&library_id=&limit=&cursor=`
  returns `artist`, `album`, `disc`, or `artist_album` groups. Search and status
  apply before grouping and carry into drill-down.

Track groups derive only from persisted metadata. They never read the
filesystem, parse a stored path, load current PathPolicy, or recalculate a
canonical path.

* `artist` uses non-blank `album_artist`, then non-blank `artist`, otherwise
  `(unknown)`. Blank detection trims ASCII space, tab, carriage return, line
  feed, vertical tab, and form feed. It has no `parent_key`.
* `album` is identified by artist, normalized album or `(unknown)`, and
  recorded year. Its label includes year when known and requires the opaque
  artist `parent_key` returned by the artist grouping.
* `disc` is identified by parent album and positive recorded disc number.
  Missing, zero, or negative numbers use `Unnumbered disc`. It requires the
  opaque album `parent_key`.
* `artist_album` retains the artist/album aggregate and has no parent key.

All Track group keys are opaque. Clients echo returned keys and never
construct, parse, or infer membership from labels. Counts include removed
Tracks.

## Check Endpoints

Check GET routes read persisted findings only and perform no filesystem I/O.
Each Library retains its latest completed CheckRun and issues. Issue ordering
remains `issue_seq ASC`, preserving insertion order.

The optional `library_id` scopes every `GET /api/check*` endpoint. With an ID,
the route reads that Library's latest result. Without one, it aggregates each
Library's latest result; this is not one global CheckRun.

For list and facet data, `checked_at` is the selected Library's time when an ID
is supplied. In aggregate scope it is the earliest time among Libraries with a
completed Check, representing the least-fresh component. It is null only when
the scope has no completed Check. Issue filters do not change it. Group data
does not carry `checked_at`.

* `GET /api/check?query=&issue_type=&group_by=&group_key=&library_id=&limit=&cursor=`
  returns CheckIssue list data plus `checked_at`. `query` matches `library_id`,
  path, `track_id`, `plan_id`, or detail. `group_by` and `group_key` form an
  optional pair and combine with issue type as AND.
* `GET /api/check/facets?query=&library_id=` returns the `issue_type` facet plus
  `checked_at`. Counts omit a selected list issue type so alternatives remain
  visible.
* `GET /api/check/groups?group_by=&query=&issue_type=&library_id=&limit=&cursor=`
  supports `issue_type`, `severity`, `path_root`, `artist_album`,
  `suggested_command`, and `library_id`. Search and issue type apply before
  group counts.

Check grouping derivations are unchanged:

* `issue_type` uses the recorded catalog value.
* `severity` is `error` for `db_file_missing` and `content_hash_changed`,
  `info` for `library_stale`, and `warning` otherwise.
* `path_root` uses the first relative directory segment with trailing `/`;
  root-level paths use `(root)`, absolute paths `(external)`, and null paths
  `(unknown)`.
* `artist_album` uses the first two relative path segments. One-directory
  paths use `Artist / (root)`, root-level paths `(root)`, absolute paths
  `(external)`, and null paths `(unknown)` / `Unknown Artist / Unknown Album`.
* `suggested_command` maps issue families to `refresh`, `add`, `organize`,
  `history`, or `check`: `db_file_missing`, `content_hash_changed`, and
  `metadata_hash_changed` map to `refresh` / `omym2 refresh <file>`;
  `unmanaged_file_exists` maps to `add` / `omym2 add <path>`;
  `current_path_differs_from_canonical_path`, `duplicate_candidate`, and
  `plan_source_changed` map to `organize` / `omym2 organize`;
  `pending_file_event_exists` maps to `history` / `omym2 history`; and
  `library_unregistered`, `library_stale`, and `library_blocked` map to
  `check` / `omym2 check`.
* `library_id` uses the recorded UUID string.

Every Check grouping orders by `count DESC, key ASC`. `common_path_root` uses
the path-root derivation independently of the selected grouping.

## History Endpoints

Run ordering remains `started_at DESC, run_id DESC`. FileEvent ordering remains
`sequence_no ASC, event_id ASC`.

* `GET /api/history?query=&status=&plan_id=&library_id=&limit=&cursor=` returns
  Run list data. `query` matches `run_id`, `plan_id`, `library_id`, status, or
  non-null redacted error summary. `plan_id` is an exact identity filter, and
  all filters combine before pagination.
* `GET /api/history/facets?library_id=` returns the Run `status` facet.
* `GET /api/history/{run_id}` returns a Run header, `RunCapabilities`, and
  `active_operation_id`. It never embeds FileEvents.
* `GET /api/history/{run_id}/events?status=&limit=&cursor=` returns FileEvent
  list data.
* `GET /api/history/{run_id}/events/facets` returns the FileEvent `status`
  facet.
* `GET /api/history/{run_id}/events/groups?group_by=target_directory&limit=&cursor=`
  returns FileEvent target-directory groups.

A Run with zero FileEvents is valid when it contains only blocked, skip, or
`refresh_metadata` work. The Run detail remains linked to its PlanAction summary;
the API does not synthesize an event.

## Search Implementation

Search retains SQL `LIKE` and, for Track metadata, `json_extract`; FTS5 remains
deferred. `%`, `_`, and the escape character in user input match literally.

Case-insensitivity remains ASCII-only. SQLite search paths use `LOWER()`, and
in-process PlanAction group filters apply the same ASCII fold. Non-ASCII text
therefore matches case-sensitively across browse modes.
