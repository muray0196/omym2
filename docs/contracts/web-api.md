---
type: Contract
title: Web API Contract
description: Authoritative local HTTP API contract - envelope, error catalog, CSRF, idempotency, browsing shapes, and every /api endpoint.
tags: [web-api, openapi, artist-names, companions, unprocessed, operations, concurrency, pagination]
timestamp: 2026-07-18T12:00:00+09:00
---

# Web API Contract

Authoritative for OMYM2's local HTTP API: Pydantic models, JSON envelopes, structured errors, status codes, CSRF, Bootstrap, Library/Settings resources, capability projections, durable Operation routes, and browsing behavior.

Related: frontend boundary in [web-frontend.md](../codebase/web-frontend.md); Config storage and raw revision in [config.md](config.md); Operation lifecycle, idempotency, polling, and retention in [operations.md](operations.md); status and reason values in [status-reason-catalog.md](status-reason-catalog.md); breaking-API decision in [ADR 0001](../decisions/0001-breaking-bundled-web-api.md).

## Bundled Breaking Contract

The SPA and API ship from the same commit in one Python package. The API is not an independently supported external-client surface.

* Routes stay under `/api`; there is no `/api/v1` prefix.
* Old requests, response fields, browser URLs, and opaque keys receive no compatibility adapter or transition period; the SPA and API cut over together.
* Supporting independent external clients or a versioned compatibility surface requires a new architecture decision.

The 2026-07-16 pre-release clean-slate cutover removed the Track `group_by=artist_album` value, three unused path error codes, and Operation progress fields. Generated clients from older builds must be regenerated from the current OpenAPI document.

## Schema Source And Generated Client

Every route has Pydantic request and response models, including every declared error response. Handwritten dictionaries are not an API schema source, and the SPA must not duplicate Python response shapes manually.

A schema-only FastAPI app factory registers exactly the production route and model set without constructing a Config store, SQLite database, filesystem adapter, metadata adapter, network client, or static Web build; generating OpenAPI performs no application I/O.

The generated TypeScript schema and client are committed. A contract change updates the Pydantic models, OpenAPI output, generated client, Python contract tests, and SPA in one change. CI order:

1. Python API schema and contract tests.
2. OpenAPI export from the schema-only app.
3. TypeScript schema/client generation and drift check (fails when regeneration changes a committed file).
4. Frontend typecheck.

Generated closed enums use exhaustive presentation maps. An impossible value fails explicitly; the SPA does not present unknown raw enum values as a neutral forward-compatible state.

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

Invariants:

* Success: `data != null`, `errors = []`. Failure: `data = null`, non-empty `errors`.
* An empty collection or empty result is a non-null typed value, never `data = null`.
* Degraded Bootstrap is the sole exception: it may return recovery-oriented non-null data and non-empty errors together.
* A response never mixes a normal resource result with warnings in top-level `errors`; resource-local validation diagnostics belong in that resource's typed data.

`message` is displayable fallback text; clients branch only on `code`. `field`, when present, is a stable qualified location such as `body.config.paths.library`, `query.cursor`, `path.plan_id`, or `header.Idempotency-Key`. `retryable` states whether the same logical request can be attempted after its stated condition changes; it does not authorize automatic mutation retry. A remediation may contain a route, a command, both, or neither; the client displays it but never executes a command automatically.

Every API response includes `X-OMYM2-Correlation-ID`, also written to server logs. Unexpected exception details and stack traces are logged with that identifier, never returned to the client.

## Error Catalog And Status Codes

`ApiError.code` is a closed catalog. Top-level failure envelope mapping:

| HTTP | Allowed codes |
| --- | --- |
| `400` | `invalid_json` |
| `403` | `csrf_invalid` |
| `404` | `api_not_found`, `library_not_found`, `track_not_found`, `plan_not_found`, `run_not_found`, `operation_not_found` |
| `405` | `method_not_allowed` |
| `409` | `config_invalid`, `config_changed`, `artist_name_mappings_changed`, `operation_in_progress`, `idempotency_key_reused`, `library_selection_ambiguous`, `library_unregistered`, `library_stale`, `library_blocked`, `plan_not_ready`, `library_root_changed`, `run_not_terminal`, `nothing_to_undo`, `undo_refresh_metadata_unsupported`, `already_undone_or_in_progress`, `pending_file_event_requires_review` |
| `410` | `operation_expired` |
| `422` | `validation_failed` |
| `500` | `storage_unavailable`, `config_io_failed`, `internal_error` |

Embedded `disabled_reasons`, validation diagnostics, and degraded Bootstrap errors reuse the same codes inside a successful (HTTP 200) resource response.

Terminal Operation errors inside an Operation resource (no additional HTTP status): `operation_interrupted`, `metadata_read_failed`, `operation_failed`.

Invalid UUIDs, cursors, filter values, `group_by` values, headers, query/path parameters, and structurally valid JSON bodies return `422`. Only JSON decoding failure returns `400 invalid_json`.

`FileEvent.error_code` is a separate open schema of stable snake_case values, not narrowed to `ApiErrorCode`; clients provide an unknown-value fallback.

Success codes: `200` for reads, synchronous updates, and retained terminal Operation replay; `201` reserved for a future synchronous-creation route; `202` when a durable Operation is newly accepted or an active Operation is replayed idempotently. Initial resource-creation workflows are durable Operations, so none use `201`.

The FastAPI app installs envelope-preserving handlers for JSON decoding failures, `RequestValidationError`, translated application/domain errors, `HTTPException`, unknown API routes, method-not-allowed, and unexpected exceptions. Unknown `/api` routes always return JSON `404 api_not_found` (never the SPA fallback); known routes with an unsupported method return JSON `405 method_not_allowed`. Raw Python exceptions, class names, stack traces, SQL messages, and unredacted filesystem exception text must not appear in responses; authorized path fields stay available through typed resource fields, never echoed exception strings.

## CSRF And Mutation Retry

`GET /api/bootstrap` issues the CSRF token without depending on valid Config or database state. Every state-changing request sends it in `X-OMYM2-CSRF-Token`. A missing or invalid token returns `403 csrf_invalid` before validation side effects, lock acquisition, Operation acceptance, or mutation.

After receiving exactly `403 csrf_invalid`, a client may refresh Bootstrap once and retry once only for:

* an Operation-start request with the identical `Idempotency-Key` and body;
* `PUT /api/settings` with the identical `expected_config_revision` and body;
* ready-Plan cancellation with the identical Plan ID.

The client never automatically resends a mutation after a connectivity failure, timeout, generic `403`, `409`, or `500`. It polls an accepted Operation rather than resending its mutation.

## Shared Browsing Shapes

### List Data

Every keyset-paginated list endpoint returns:

```jsonc
{
  "data": {
    "items": [ /* typed rows */ ],
    "page": { "limit": 100, "next_cursor": "b64url... or null", "total": 1234 }
  },
  "errors": []
}
```

`page.total` counts rows matching the same filters while ignoring the cursor, evaluated per response; pagination is not a snapshot. `next_cursor` is null when no further page exists; `limit` is the effective post-clamp limit.

### Cursor

Cursors are opaque. The current server representation is `base64url(JSON array of strings)` over endpoint-specific keyset columns, but clients only echo `next_cursor` as the next `cursor`; they never construct, decode, or interpret it. A cursor failing decoding, JSON parsing, value-shape validation, or the endpoint's key-length/value validation returns `422 validation_failed` with `field = "query.cursor"`.

### Limit

`limit` defaults to 100, minimum 1, maximum 500; values above 500 clamp to 500. Non-integer or below-1 values return `422 validation_failed`. Routes use the shared pagination primitives; no second limit policy.

### Facet Data

Facet endpoints ignore pagination and return `data = { facets: { "<field>": [ { value, count } ] }, total }`. `total` counts rows matching the request's filters. Check facets additionally carry `checked_at` inside `data`.

### Group Data

Group endpoints return `data = { group_by, items: [ { key, label, count } ], page }`. Groups order by `count DESC, key ASC`. `page.total` counts group rows matching the filters while ignoring the cursor; no cross-page snapshot guarantee.

PlanAction group rows add `blocked_count` (members with recorded status `blocked`) and `top_reason` (most frequent non-null recorded reason; ties choose the lexicographically smaller reason; null when no member has a reason).

CheckIssue group rows add `common_path_root`: the most frequent non-null derived path root; ties choose the lexicographically smaller root; null when every member is pathless.

## Bootstrap

### `GET /api/bootstrap`

Returns `200 ApiEnvelope<BootstrapData>`:

```ts
type BootstrapData = {
  csrf_token: string
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
  operation_polling: { initial_ms: number; backoff_factor: number; max_ms: number }
  active_operation_id: string | null
}
```

* Bootstrap selects a Library only when selection is unambiguous; otherwise `active_library` is null and `library_diagnostics` explains why. It never silently selects the first Library.
* Bootstrap is the sole degraded-envelope exception: invalid Config or unavailable persistence may produce non-null recovery data plus top-level errors, and CSRF issuance stays available for Settings recovery.
* Polling values are serialized from the constants in `src/omym2/config.py`; the SPA and its tests do not repeat policy literals.
* `can_start_organize` is the explicit capability for `POST /api/plans/organize`. It stays true when Library selection is missing, unregistered, stale, blocked, or ambiguous (an explicit root is the registration/reconciliation input); it is false when Config cannot load validly or state storage cannot be read. Its disabled reasons use `field = "runtime_capabilities.can_start_organize"`. The Organize endpoint still revalidates the submitted root and all mutation-time guards.

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

* `GET /api/libraries` returns `200` with `data = { "items": LibraryResource[] }`.
* `GET /api/libraries/{library_id}` returns `200` with one `LibraryResource`. Unknown ID: `404 library_not_found`; invalid UUID: `422 validation_failed`.

Library IDs remain in every route and resource even though the initial SPA presents one unambiguous active Library. `path_policy_fingerprint` is the API name for stored `libraries.path_policy_hash`, opaque to clients. `is_path_policy_current` derives from the stored fingerprint versus current valid Config; Settings save does not attempt a cross-store atomic write to persist it. `LibraryResource.status` is the effective projection: persisted `registered` with a false fingerprint comparison returns `status = "stale"`, emits a `library_stale` diagnostic/capability reason, and disables Add. The API never returns `registered` with `is_path_policy_current = false`.

## Settings

Config schema and revision algorithm are authoritative in [config.md](config.md). The Web API never reads or writes TOML directly; it calls Settings usecases through ports.

`AppConfigResource` does not contain artist display-name preferences; the editable romanized-name mapping is SQLite feature data returned alongside Config as `artist_name_mappings`. Per-artist compact IDs are not part of the Settings API. It exposes `companions.enabled` and the typed `unprocessed` object (`enabled`, `directory`, `result_preview_limit`). The companion toggle gates only new unmanaged actions and unmanaged Check discovery. The preview limit controls result presentation only; no API list, Plan summary, or generated client may treat it as a persisted-action cap.

### `GET /api/settings`

Returns `200` with:

```ts
type SettingsData = {
  config: AppConfigResource
  config_revision: string
  choices: SettingsChoices
  validation: { valid: boolean; errors: ApiError[] }
  preview: PathPreview
  artist_name_mappings: {
    entries: Array<{
      source_name: string
      english_name: string
      source: string // currently "musicbrainz" or "user"
      selected_name_kind: "alias" | "alias_sort_name" | "name" | "sort_name" | null
      selected_locale: string | null
    }>
    revision: string
  }
}
```

For MusicBrainz rows, `selected_name_kind` identifies the exact selected field (alias `name`, alias `sort-name`, artist `name`, artist `sort-name`); alias-derived rows also expose their locale (e.g. `ja-Latn`). User rows have null selection fields.

Invalid persisted TOML is represented by `validation.valid = false` with resource-local errors while the top-level envelope stays a normal success; `config` contains the backend-provided recovery draft. The raw invalid text is never returned.

### `POST /api/settings/validate`

Request: `config` and `expected_config_revision`. Revision mismatch: `409 config_changed`. Otherwise `200` with `valid`, typed validation errors, a before/after change list, and a PathPolicy preview. Candidate-domain validation failure is a typed validation result, not a server error.

### `POST /api/settings/preview`

Accepts a self-contained PathPolicy/Artist-ID draft, sample Track metadata, and file extension. Reads the current saved artist-name mapping, returns `200` with `PathPreview`, performs no Config or DB write.

### `PUT /api/settings`

Request: `config` and `expected_config_revision`. The usecase acquires the shared exclusive-operation lock, re-reads the raw revision, and atomically replaces the Config only on revision match. Success: `200` with saved Config, new `config_revision`, change list, validation result, and preview. Mismatch: `409 config_changed`, no write. Invalid candidate Config: `422 validation_failed`. A client may intentionally replace invalid persisted TOML when it supplies the revision it read. Config I/O failure: `500 config_io_failed`.

### `PUT /api/settings/artist-names`

Accepts the complete `original name -> English name` mapping and the `expected_revision` from `GET /api/settings`. Under the shared exclusive lock it compares the mapping revision, then applies additions, corrections, and deletions in one SQLite transaction. New or changed rows become user-supplied; unchanged MusicBrainz rows retain provider provenance. Success returns the saved mapping and new revision. Stale input: `409 artist_name_mappings_changed`; lock contention: `409 operation_in_progress`; invalid or non-Latin English names: `422 validation_failed`. Requires CSRF.

## Capabilities

Capabilities are computed by feature usecases, not route adapters. They are advisory display snapshots, revalidated at mutation time.

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

* Every disabled capability has at least one reason, with remediation when a known next action exists. The frontend does not infer permission from Plan or Run status. Unknown reason codes use generic disabled presentation.
* Capability reasons set `field` to the affected capability (e.g. `capabilities.can_apply`). A ready Plan may have `can_apply = true` even when some or all actions are blocked; the typed summary keeps blocked and executable counts separate.
* `can_recreate` means the backend permits opening the corresponding Add, Organize, or Refresh creation flow to calculate a new Plan from current state. It never clones recorded PlanActions or bypasses that creation endpoint. Undo Plan recreation follows the Run capability and Undo deduplication contract instead.
* Plan detail and Run detail each expose `active_operation_id: string | null`, the related queued/running Operation. A `409 operation_in_progress` response includes remediation to the active Operation route when an ID is available.

## Durable Operation HTTP Resource

Operation lifecycle and result kinds are authoritative in [operations.md](operations.md). HTTP projections:

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

`poll_after_ms` is 500 initially; clients apply the Operation contract's polling/backoff policy. Progress fields (stage, count, message, percentage) are not part of the resource because the runtime has no producer. The nullable Library/Plan/Run associations are durable navigation evidence, not a success result; they remain on failed or interrupted Operations so polling can open the affected Plan, Run History, or Check review.

### `GET /api/operations/{operation_id}`

Returns `200 ApiEnvelope<OperationResource>` while the full active or retained terminal resource exists. Retained tombstone: `410 operation_expired`. Unknown or fully purged ID: `404 operation_not_found`.

GET is a read-only snapshot and never reconciles state. The platform supervisor performs the bounded lock-based liveness check, so a recently orphaned queued/running row may remain visible until the next supervisor pass, then becomes terminal on a later poll.

## Operation Acceptance And Idempotency

Each Operation-start endpoint requires a client-generated UUID in `Idempotency-Key` and a valid CSRF token. Missing or invalid header syntax: `422 validation_failed`.

Acceptance classifies any retained idempotency key before lock acquisition: a matching kind/fingerprint returns its active, terminal, or tombstone outcome; a mismatched kind/fingerprint returns `409 idempotency_key_reused`; only an absent key proceeds to the exclusive lock. The reservation transaction rechecks the key before touching a Plan or inserting anything.

New acceptance returns `202 ApiEnvelope<OperationRef>` with a relative status URL in `Location`. Replaying the same key, kind, and canonical request returns the existing reference without redispatch:

* queued/running replay: `202` and `Location` (read-only; stale-row reconciliation belongs to the supervisor/startup/pre-mutation pass, after which replay returns the terminal resource with `200`);
* retained terminal replay: `200` and `Location`;
* tombstone-period match: `410 operation_expired`, never executes again;
* different kind or fingerprint: `409 idempotency_key_reused`.

A `plan_created` result stores only `plan_id`; the client refetches Plan detail and pages actions. Operation results never embed PlanActions or a stale capability snapshot.

Operation-start routes:

* `POST /api/plans/add` — optional `source_path` plus selected `library_id`; starts `add_plan`.
* `POST /api/plans/organize` — explicitly confirmed `library_root`; starts `organize_plan`.
* `POST /api/plans/refresh` — exactly one file, directory, or all target plus selected `library_id`; starts `refresh_plan`.
* `POST /api/check/run` — optional `library_id`; starts `check`.
* `POST /api/plans/{plan_id}/apply` — starts `apply_plan` after the atomic Apply claim.
* `POST /api/history/{run_id}/undo-plan` — starts `undo_plan`.

Web Plan creation and Check requests never accept `trust_stat`; that optimization is CLI-only.

## Apply, Cancel, And Undo

### `POST /api/plans/{plan_id}/apply`

Apply uses only recorded PlanActions. Before returning `202`, the backend holds the shared exclusive lock, verifies `library_root_at_plan`, and atomically commits the Plan `ready -> applying` compare-and-set, running Run, and queued Operation reservation. Root mismatch before Run creation expires the Plan and returns `409 library_root_changed`. Non-ready or terminal Plan: `409 plan_not_ready`. Capabilities do not replace this mutation-time claim.

### `POST /api/plans/{plan_id}/cancel`

Synchronous; creates no Operation. Acquires the shared lock and performs a `ready -> cancelled` compare-and-set. Success: `200` with updated Plan header and capabilities. Losing a race to Apply or another Cancel: `409 plan_not_ready`. In-flight Operation cancellation is not supported.

### `POST /api/history/{run_id}/undo-plan`

Undo Plan generation is a durable Operation. Only terminal Runs with at least one succeeded FileEvent and no `refresh_metadata` action are eligible. A pending FileEvent in the source Run or any prior Undo Run for the same `source_run_id` requires manual review: `409 pending_file_event_requires_review`. An existing ready Undo Plan is returned through the Operation result instead of duplicating. Applying or applied Undo Plan for the same source Run: `409 already_undone_or_in_progress`. No reversible events: `409 nothing_to_undo`; running source Run: `409 run_not_terminal`; refresh-metadata history: `409 undo_refresh_metadata_unsupported`.

After a failed or partially failed prior Undo Plan, regeneration is allowed only from current durable state, only when no FileEvent in that source/prior-Undo scope is pending, and must exclude each source event linked by `reverses_event_id` to a succeeded reversal FileEvent from the earlier Undo execution.

Undo never mutates the filesystem directly. Its `plan_created` result opens normal Plan Review; applying that Undo Plan uses the same Apply endpoint.

## Plan Endpoints

Plan ordering is `created_at DESC, plan_id DESC`. Action ordering is `sort_order ASC, action_id ASC`.

* `GET /api/plans?query=&status=&type=&blocked=&limit=&cursor=` returns `PlanSummary` list data. `query` matches `plan_id`, `library_id`, `plan_type`, or `status` as an ASCII-case-insensitive substring. `blocked=true` selects Plans with at least one currently blocked action; omitted or false does not filter. Filters combine before pagination. `PlanSummary.summary` uses the typed action summary below, not the persisted opaque map.
* `GET /api/plans/{plan_id}` returns a Plan header, typed action summary, `PlanCapabilities`, and `active_operation_id`. It never embeds actions.
* `GET /api/plans/{plan_id}/actions?query=&status=&action_type=&reason=&group_by=&group_key=&limit=&cursor=` returns PlanAction list data. `query` matches `action_id`, `track_id`, `companion_asset_id`, `owner_action_id`, `source_path`, `target_path`, `content_hash_at_plan`, or `metadata_hash_at_plan`. `group_by`/`group_key` are provided together or omitted together and AND with all other filters. Each action exposes nullable `artist_name_diagnostics` (recorded `artist`/`album_artist` source value, resolved value, provenance, nullable resolution issue from target calculation; never re-resolved), nullable `companion_asset_id`, nullable `owner_action_id`, and `depends_on_action_ids` in stable dependency-ID order.
* `GET /api/plans/{plan_id}/facets?query=&status=&action_type=&reason=` returns facets for `status`, `action_type`, and non-null `reason`. Each facet applies search and the other two filters while omitting its own. `data` also carries Plan-wide `target_collisions` (count of distinct non-null target paths recorded by two or more actions; unaffected by browse filters). `total` counts actions matching every supplied filter.
* `GET /api/plans/{plan_id}/groups?group_by=&query=&status=&action_type=&reason=&limit=&cursor=` returns enriched PlanAction groups. Supported: `target_directory`, `source_directory`, `artist_album`, `action_type`, `status`, `block_reason`, `extension`. Search and catalog filters apply before group counts and carry into drill-downs.

Typed action summary (computed from current recorded PlanActions):

```ts
type PlanActionTypeCounts = {
  move: number
  move_lyrics: number
  move_artwork: number
  move_unprocessed: number
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

Every count is a non-negative integer; `total` equals the sum of the full status/action-type matrix.

PlanAction grouping derivations:

* `target_directory` / `source_directory`: the stored path's POSIX parent; root-level files use `(root)`; null paths have no group.
* `artist_album`: first two stored target-path directory segments; label joins with ` / `. Null target: `(unknown)` / `Unknown Artist / Unknown Album`; root-level target: `(root)`.
* `action_type` / `status`: recorded catalog values.
* `block_reason`: recorded non-null reason; actions without a reason have no group.
* `extension`: lowercased source suffix without `.`, falling back to target; suffix-less paths use `(none)`; actions without either path have no group.

Plan review never recalculates target paths from current Config.

## Track Endpoints

Ordinary Track ordering is `current_path ASC, track_id ASC`. A group drill-down orders by positive `track_number` first, then title and `track_id`; missing or non-positive numbers follow numbered Tracks.

* `GET /api/tracks?query=&status=&track_id=&library_id=&group_by=&group_key=&limit=&cursor=` returns Track list data. `track_id` is exact. `query` matches title, artist, album, current path, or Track ID. `group_by`/`group_key` are supplied together or omitted together and AND with the other filters.
* `GET /api/tracks/{track_id}` returns `200` with one `TrackResource`. Unknown ID: `404 track_not_found` with `field = "path.track_id"`.
* `GET /api/tracks/facets?query=&library_id=` returns the `status` facet. Counts apply search while omitting a selected list status.
* `GET /api/tracks/groups?group_by=&parent_key=&query=&status=&library_id=&limit=&cursor=` returns `artist`, `album`, or `disc` groups. Search and status apply before grouping and carry into drill-down.

Track groups derive only from persisted metadata. They never read the filesystem, parse a stored path, load current PathPolicy, or recalculate a canonical path.

* `artist`: non-blank `album_artist`, then non-blank `artist`, otherwise `(unknown)`. Blank detection trims ASCII space, tab, CR, LF, vertical tab, form feed. No `parent_key`.
* `album`: identified by artist, normalized album or `(unknown)`, and recorded year; label includes year when known; requires the opaque artist `parent_key`.
* `disc`: identified by parent album and positive recorded disc number; missing, zero, or negative numbers use `Unnumbered disc`; requires the opaque album `parent_key`.

Track group keys are opaque: clients echo returned keys and never construct, parse, or infer membership from labels. Keys and URLs from removed pre-release groupings are unsupported. Counts include removed Tracks.

## Check Endpoints

Check GET routes read persisted findings only and perform no filesystem I/O. Each Library retains its latest completed CheckRun and issues. Issue ordering is `issue_seq ASC` (insertion order).

Optional `library_id` scopes every `GET /api/check*` endpoint. With an ID, the route reads that Library's latest result. Without one, it aggregates each Library's latest result — not one global CheckRun.

For list and facet data, `checked_at` is the selected Library's time when an ID is supplied; in aggregate scope it is the earliest time among Libraries with a completed Check (least-fresh component). It is null only when the scope has no completed Check. Issue filters do not change it. Group data does not carry `checked_at`.

* `GET /api/check?query=&issue_type=&group_by=&group_key=&library_id=&limit=&cursor=` returns CheckIssue list data plus `checked_at`. `query` matches `library_id`, path, `track_id`, `plan_id`, `companion_asset_id`, or detail. Each row exposes nullable `companion_asset_id`. `group_by`/`group_key` form an optional pair and AND with issue type.
* `GET /api/check/facets?query=&library_id=` returns the `issue_type` facet plus `checked_at`. Counts omit a selected list issue type so alternatives stay visible.
* `GET /api/check/groups?group_by=&query=&issue_type=&library_id=&limit=&cursor=` supports `issue_type`, `severity`, `path_root`, `artist_album`, `suggested_command`, and `library_id`. Search and issue type apply before group counts.

Check grouping derivations:

* `issue_type`: the recorded catalog value.
* `severity`: `error` for `db_file_missing`, `content_hash_changed`, `companion_file_missing`, `companion_content_hash_changed`, `companion_owner_missing`, `failed_companion_source_exists`, `unprocessed_file_missing`, `unprocessed_content_hash_changed`; `info` for `library_stale`; `warning` otherwise.
* `path_root`: first relative directory segment with trailing `/`; root-level paths `(root)`, absolute paths `(external)`, null paths `(unknown)`.
* `artist_album`: first two relative path segments. One-directory paths `Artist / (root)`, root-level `(root)`, absolute `(external)`, null `(unknown)` / `Unknown Artist / Unknown Album`.
* `suggested_command` maps issue families to a command; the recorded detail, not platform path spelling, selects it:

| Command | Label | Issue types |
| --- | --- | --- |
| `refresh` | `omym2 refresh <file>` | `db_file_missing`, `content_hash_changed`, `metadata_hash_changed`, `companion_file_missing`, `companion_content_hash_changed` |
| `add` | `omym2 add <path>` | `unmanaged_file_exists`; `failed_companion_source_exists` with `detail = "add"` |
| `organize` | `omym2 organize` | `current_path_differs_from_canonical_path`, `companion_current_path_differs_from_canonical_path`, `companion_owner_missing`, `unmanaged_companion_exists`, `duplicate_candidate`, `plan_source_changed`; `failed_companion_source_exists` with `detail = "organize"` |
| `history` | `omym2 history` | `pending_file_event_exists`, `unprocessed_file_missing`, `unprocessed_content_hash_changed` |
| `check` | `omym2 check` | `library_unregistered`, `library_stale`, `library_blocked` |

* `library_id`: the recorded UUID string.

Every Check grouping orders by `count DESC, key ASC`. `common_path_root` uses the path-root derivation independently of the selected grouping.

## History Endpoints

Run ordering is `started_at DESC, run_id DESC`. FileEvent ordering is `sequence_no ASC, event_id ASC`.

* `GET /api/history?query=&status=&plan_id=&library_id=&limit=&cursor=` returns Run list data. `query` matches `run_id`, `plan_id`, `library_id`, status, or non-null redacted error summary. `plan_id` is an exact identity filter; all filters combine before pagination.
* `GET /api/history/facets?library_id=` returns the Run `status` facet.
* `GET /api/history/{run_id}` returns a Run header, `RunCapabilities`, and `active_operation_id`. It never embeds FileEvents.
* `GET /api/history/{run_id}/events?status=&limit=&cursor=` returns FileEvent list data. Each event exposes nullable `companion_asset_id`; lyrics and artwork mutations retain distinct event types, while a trackless unprocessed mutation uses `move_unprocessed_file` with null companion identity and its recorded absolute paths.
* `GET /api/history/{run_id}/events/facets` returns the FileEvent `status` facet.
* `GET /api/history/{run_id}/events/groups?group_by=target_directory&limit=&cursor=` returns FileEvent target-directory groups.

A Run with zero FileEvents is valid when it contains only blocked, skip, or `refresh_metadata` work; Run detail links to its PlanAction summary, and the API does not synthesize an event.

## Search Implementation

Search uses SQL `LIKE` and, for Track metadata, `json_extract`; FTS5 remains deferred. `%`, `_`, and the escape character in user input match literally. Case-insensitivity is ASCII-only: SQLite search paths use `LOWER()`, and in-process PlanAction group filters apply the same ASCII fold. Non-ASCII text matches case-sensitively across browse modes.
