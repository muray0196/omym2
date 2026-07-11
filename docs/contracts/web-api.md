---
type: Contract
title: Web API Contract
description: Defines OMYM2's local Web API envelopes, browsing and Plan-creation requests, pagination/facets/groups, and exclusion of CLI-only trust-stat flags.
tags: [web-api, pagination, json, contract]
timestamp: 2026-07-11T10:21:41+09:00
---

# Web API Contract

This document is authoritative for the JSON response shapes, keyset pagination, cursor encoding, facet endpoints, group-by endpoints, and Plan-creation endpoints of OMYM2's local Web API.

The frontend/backend boundary is summarized in [../codebase/web-frontend.md](../codebase/web-frontend.md). Row/item field shapes (`TrackSummary`, `PlanSummary`, `PlanAction`, `CheckIssue`, `RunSummary`, `FileEvent`) are owned by the serializers in `src/omym2/adapters/web/routes/api_serializers.py`; this document does not restate their fields. Status, action type, event type, and issue type values are owned by [status-reason-catalog.md](status-reason-catalog.md). DB field responsibilities are owned by [db-schema.md](db-schema.md). The pure pagination primitives (`PageRequest`, `Page`, `GroupCount`, `FacetValue`, cursor encode/decode, limit clamping) are implemented in `src/omym2/shared/pagination.py`.

This is a coordinated breaking change: the previous domain-named array responses (top-level `tracks`, `plans`, `issues`, `runs` keys, and embedded `actions` / `file_events` arrays inside detail responses) are replaced by the envelopes in this document. The SPA and the API ship together in one package, so there is no compatibility window between them.

## Envelope (All List Endpoints)

Every list endpoint returns:

```jsonc
{
  "items": [ /* ... */ ],
  "page": { "limit": 100, "next_cursor": "b64url..." /* or null */, "total": 1234 },
  "errors": []
}
```

* `page.total` is the count of rows matching the same filters as the request, ignoring the cursor. It does not change as the client pages forward.
* `page.next_cursor` is `null` when there is no further page.
* `page.limit` echoes the effective (post-clamp) limit that was applied to this response.

### Cursor

The cursor is opaque to clients: `base64url(JSON array of strings)`, keyset-based on the endpoint's documented ordering columns. Clients must only echo a `next_cursor` value back as the next request's `cursor` parameter and must not construct or parse cursor values themselves. Encoding/decoding is implemented once in `src/omym2/shared/pagination.py` (`encode_cursor` / `decode_cursor`).

A malformed cursor (fails base64url decoding, fails JSON parsing, or decodes to a JSON value that is not a list of strings) returns HTTP 400 with:

```jsonc
{ "items": [], "page": null, "errors": ["Invalid cursor."] }
```

An unknown filter value or unknown `group_by` value also returns HTTP 400, in the same envelope style: the endpoint's normal list/data field(s) are emptied (`items: []` for list and group endpoints; `facets: {}` for facet endpoints), `page` (or the endpoint's equivalent) is `null`, and `errors` carries a human-readable message.

### Limit

`limit` defaults to 100, minimum 1, maximum 500. Values above 500 are clamped down to 500 (not an error). A non-integer value or a value below 1 is an HTTP 400 request error. This matches `clamp_limit` in `src/omym2/shared/pagination.py`: `None` resolves to the default, `1..500` pass through unchanged, `>500` clamps to 500, and `<1` raises (routes translate that raise into HTTP 400).

## Facet Envelope

Facet endpoints return value/count breakdowns for one or more fields, ignoring pagination entirely:

```jsonc
{
  "facets": {
    "<field>": [ { "value": "...", "count": 17 }, /* ... */ ]
  },
  "total": 1234,
  "errors": []
}
```

`total` is the count of rows matching the request's filters (the same definition as `page.total` on list endpoints). Check facets additionally carry a top-level `"checked_at": "<iso>" | null` field (see Check Endpoints below).

## Group Envelope

Group-by endpoints return paginated group rows:

```jsonc
{
  "group_by": "<key>",
  "items": [ { "key": "...", "label": "...", "count": 42 }, /* ... */ ],
  "page": { "limit": 100, "next_cursor": "b64url..." /* or null */, "total": 1234 },
  "errors": []
}
```

Group rows are ordered `count DESC, key ASC`. `page.total` is the total number of group rows matching the request's filters, ignoring the cursor.

## Endpoints

### Tracks

Ordering: `current_path ASC, track_id ASC`.

* `GET /api/tracks?query=&status=&track_id=&library_id=&limit=&cursor=` — list envelope of `TrackSummary` items. `track_id` is an exact identity filter. `query` matches `title`, `artist`, `album`, `current_path`, or `track_id`, case-insensitive substring.
* `GET /api/tracks/facets?library_id=` — facet envelope; facet field: `status`.
* `GET /api/tracks/groups?group_by=artist_album&library_id=&limit=&cursor=` — group envelope.

### Plans

Plan ordering: `created_at DESC, plan_id DESC`. Action ordering: `sort_order ASC, action_id ASC`.

* `GET /api/plans?status=&type=&limit=&cursor=` — list envelope of `PlanSummary` items.
* `GET /api/plans/{plan_id}` → `{ "detail": { "plan": {...} }, "errors": [] }`. Header only: the previous embedded `actions` array and `total_action_count` field are REMOVED. Actions are fetched separately (below).
* `GET /api/plans/{plan_id}/actions?status=&limit=&cursor=` — list envelope of `PlanAction` items.
* `GET /api/plans/{plan_id}/facets` — facet envelope; facet fields: `status`, `action_type`.
* `GET /api/plans/{plan_id}/groups?group_by=target_directory&limit=&cursor=` — group envelope.
* `POST /api/plans/add` — creates an add Plan; the body may carry `source_path` as a string or `null`.
* `POST /api/plans/organize` — registers or organizes a Library; the body may carry `library_root` as a string or `null`.
* `POST /api/plans/refresh` — creates a refresh Plan; the body may carry `target_path` as a string or `null` and `include_all` as a boolean.

All Plan-creation POSTs require the `X-OMYM2-CSRF-Token` header. Their shared response envelope is `{ "created": <boolean>, "detail": { "plan": {...} } | null, "registration": {...} | null, "errors": [...] }`. `detail` is header-only: it never embeds `actions` or `total_action_count`; clients fetch actions through `GET /api/plans/{plan_id}/actions`. `registration` is populated only by organize, including when clean registration needs no Plan and therefore returns `created: false` with `detail: null`.

Plan-creation JSON does not accept `trust_stat`. Web organize and refresh always use complete snapshot capture; the optimization is an explicit CLI command flag only.

### Check

Check findings are persisted, not recomputed per request. Ordering: `issue_seq ASC` (insertion order of the latest check run).

* `GET /api/check?issue_type=&library_id=&limit=&cursor=` — list envelope of `CheckIssue` items, plus a top-level `"checked_at": "<iso>" | null` field. `checked_at` is `null` when no check run has ever completed; in that case `items` is empty.
* `GET /api/check/facets?library_id=` — facet envelope; facet field: `issue_type`; carries `checked_at` per the Facet Envelope section above.
* `GET /api/check/groups?group_by=issue_type&library_id=&limit=&cursor=` — group envelope.
* `POST /api/check/run` — CSRF-protected via the `X-OMYM2-CSRF-Token` header; body may carry an optional `library_id`. Returns `{ "checked_at": "<iso>", "total": N, "errors": [] }`.

The check-run body does not accept `trust_stat`; Web recomputation always uses complete managed-file snapshots.

Behavior change: `GET /api/check` no longer recomputes findings on every request. Findings are persisted by either the `omym2 check` CLI command or `POST /api/check/run`, and all `GET /api/check*` endpoints read the stored findings of the most recent check run.

### History

Run ordering: `started_at DESC, run_id DESC`. Event ordering: `sequence_no ASC, event_id ASC`.

* `GET /api/history?status=&plan_id=&library_id=&limit=&cursor=` — list envelope of `RunSummary` items. `plan_id` is an exact Plan identity filter.
* `GET /api/history/facets?library_id=` — facet envelope; facet field: `status`.
* `GET /api/history/{run_id}` → `{ "detail": { "run": {...} }, "errors": [] }`. Header only: the previous embedded `file_events` array is REMOVED. Events are fetched separately (below).
* `GET /api/history/{run_id}/events?status=&limit=&cursor=` — list envelope of `FileEvent` items.
* `GET /api/history/{run_id}/events/facets` — facet envelope; facet field: `status`.
* `GET /api/history/{run_id}/events/groups?group_by=target_directory&limit=&cursor=` — group envelope.

## Search Implementation

Search (`query` filters and substring matching) is implemented with SQL `LIKE` and `json_extract`, not a full-text index. FTS5 is explicitly deferred; it is the escalation path if a Library's track count reaches the hundreds of thousands and `LIKE`-based search is no longer fast enough.
