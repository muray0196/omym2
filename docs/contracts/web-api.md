---
type: Contract
title: Web API Contract
description: Defines OMYM2's local Web API envelopes, browsing and Plan-creation requests, pagination/facets/groups, and exclusion of CLI-only trust-stat flags.
tags: [web-api, pagination, json, contract]
timestamp: 2026-07-12T15:18:04+09:00
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

* `page.total` is the count of rows matching the same filters as the request, ignoring the cursor, evaluated for this response. Pagination does not create a snapshot: the total may change between page requests as matching data changes.
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

`total` is the count of rows matching the request's filters, evaluated for this response (the same non-snapshot behavior as `page.total` on list endpoints). Check facets additionally carry a top-level `"checked_at": "<iso>" | null` field (see Check Endpoints below).

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

Group rows are ordered `count DESC, key ASC`. `page.total` is the number of group rows matching the request's filters, ignoring the cursor, evaluated for that response; it has no cross-page snapshot guarantee.

Plan action group rows extend the shared row with review-risk fields:

```jsonc
{
  "key": "Aimer/2024_Open α Door",
  "label": "Aimer / 2024_Open α Door",
  "count": 13,
  "blocked_count": 0,
  "top_reason": null
}
```

`blocked_count` counts group members whose recorded status is `blocked`.
`top_reason` is the most frequent non-null recorded reason among group members;
equal counts resolve to the lexicographically smaller reason, and a group with
no reasons returns `null`.

Check issue group rows extend the shared row with the path root that occurs
most often among the group's members:

```jsonc
{
  "key": "current_path_differs_from_canonical_path",
  "label": "current_path_differs_from_canonical_path",
  "count": 230,
  "common_path_root": "Aimer/"
}
```

`common_path_root` is the most frequent non-null derived Check `path_root`
among the group's members. Equal counts resolve to the lexicographically
smaller root key. It is `null` when every member is pathless.

## Endpoints

### Tracks

Ordering is `current_path ASC, track_id ASC` for the ordinary table list. A
group drill-down orders the selected Tracks by positive `track_number` first,
then title and `track_id`; tracks with a missing or non-positive number follow
the numbered tracks. This makes a disc readable as a release while keeping the
ordinary table focused on stored path inspection.

* `GET /api/tracks?query=&status=&track_id=&library_id=&group_by=&group_key=&limit=&cursor=` — list envelope of `TrackSummary` items. `track_id` is an exact identity filter. `query` matches `title`, `artist`, `album`, `current_path`, or `track_id`, case-insensitive substring. `group_by` and `group_key` are an optional drill-down pair: clients must provide both or neither, echoing a key obtained from the groups endpoint unchanged. The group filter combines with the other filters as AND.
* `GET /api/tracks/facets?library_id=` — facet envelope; facet field: `status`.
* `GET /api/tracks/groups?group_by=&parent_key=&library_id=&limit=&cursor=` — group envelope. Supported `group_by` values are `artist`, `album`, `disc`, and the retained aggregate `artist_album`.

Track hierarchy groups are derived only from persisted Track metadata; they do
not read the filesystem, parse a stored path, load the current PathPolicy, or
recalculate a canonical path. This is intentional: the browser must expose
path-policy effects and mismatches instead of treating a current path as
metadata.

* `artist` uses `album_artist`, then `artist`, when either remains non-blank
  after trimming ASCII space, tab, carriage return, line feed, vertical tab,
  and form feed; it otherwise uses `(unknown)`. It has no `parent_key`.
* `album` is identified by that artist value, `album` after the same
  ASCII-whitespace check (or `(unknown)`), and its recorded `year`; its label
  appends the year when known. It requires the opaque artist `parent_key`
  returned by the `artist` groups response.
* `disc` is identified by its parent album identity and its positive recorded
  `disc_number`. A missing, zero, or negative number is an `Unnumbered disc`
  group so malformed metadata remains visible. It requires the opaque album
  `parent_key` returned by the `album` groups response.
* `artist_album` retains the pre-hierarchy aggregate behavior: artist and
  album only, with no `parent_key`.

All Track group keys are opaque. Clients must never construct, parse, or infer
membership from a label; they pass keys returned by the server to the next
hierarchy request or the list drill-down. Group rows remain ordered `count DESC,
key ASC`, and their count covers every Track in scope, including removed
records. Hierarchy grouping never derives artist, album, or disc from path
segments because path templates are configurable and stored current paths may
differ from canonical paths.

### Plans

Plan ordering: `created_at DESC, plan_id DESC`. Action ordering: `sort_order ASC, action_id ASC`.

* `GET /api/plans?status=&type=&limit=&cursor=` — list envelope of `PlanSummary` items.
* `GET /api/plans/{plan_id}` → `{ "detail": { "plan": {...} }, "errors": [] }`. Header only: the previous embedded `actions` array and `total_action_count` field are REMOVED. Actions are fetched separately (below).
* `GET /api/plans/{plan_id}/actions?status=&group_by=&group_key=&limit=&cursor=` — list envelope of `PlanAction` items. `group_by` and `group_key` are an optional drill-down pair: clients must provide both or neither. The group filter combines with `status` as AND and uses the same membership rules as the groups endpoint.
* `GET /api/plans/{plan_id}/facets` — facet envelope; facet fields: `status`, `action_type`, and non-null `reason`. The response additionally carries top-level `target_collisions`, counting distinct non-null target paths recorded by two or more actions.
* `GET /api/plans/{plan_id}/groups?group_by=&limit=&cursor=` — enriched Plan action group envelope. Supported `group_by` values are `target_directory`, `source_directory`, `artist_album`, `action_type`, `status`, `block_reason`, and `extension`.
* `POST /api/plans/add` — creates an add Plan; the body may carry `source_path` as a string or `null`.
* `POST /api/plans/organize` — registers or organizes a Library; the body may carry `library_root` as a string or `null`.
* `POST /api/plans/refresh` — creates a refresh Plan; the body may carry `target_path` as a string or `null` and `include_all` as a boolean.

Plan action group keys are derived only from values recorded on each
`PlanAction`; review never recalculates target paths from current config:

* `target_directory` and `source_directory` use the stored path's POSIX parent directory. A root-level file uses `(root)`; a null path has no group.
* `artist_album` uses the first two directory segments of the stored target path, reflecting the default album-artist/album directory layout. Its label joins those segments with ` / `. A null target uses key `(unknown)` and label `Unknown Artist / Unknown Album`; a root-level target uses `(root)`.
* `action_type` and `status` use their recorded catalog values.
* `block_reason` uses the recorded non-null reason; actions without a reason have no group.
* `extension` uses the lowercased suffix (without `.`) of the stored source path, falling back to the target path. A suffix-less filename uses `(none)`; an action without either path has no group.

All Plan-creation POSTs require the `X-OMYM2-CSRF-Token` header. Their shared response envelope is `{ "created": <boolean>, "detail": { "plan": {...} } | null, "registration": {...} | null, "errors": [...] }`. `detail` is header-only: it never embeds `actions` or `total_action_count`; clients fetch actions through `GET /api/plans/{plan_id}/actions`. `registration` is populated only by organize, including when clean registration needs no Plan and therefore returns `created: false` with `detail: null`.

Plan-creation JSON does not accept `trust_stat`. Web organize and refresh always use complete snapshot capture; the optimization is an explicit CLI command flag only.

### Check

Check findings are persisted, not recomputed per request. Each Library retains
only its own latest completed check run and its issues. Ordering is
`issue_seq ASC`: it preserves insertion order within a check run, while an
aggregate response orders the current runs by their persisted sequence values.

The optional `library_id` selects the scope for every `GET /api/check*`
endpoint:

* With `library_id`, the endpoint reads only that Library's latest persisted
  check run and its issues.
* Without `library_id`, the endpoint aggregates the latest persisted issues of
  every Library. Libraries can have different check times; this is not one
  global latest run.

For list and facet responses, `checked_at` is the selected Library's check time
when `library_id` is supplied. In the aggregate scope it is the earliest check
time among Libraries that have completed a check, intentionally reporting the
least-fresh component; it is `null` only when the selected scope has no
completed check run. The `issue_type` filter does not change this freshness
timestamp. The groups response uses the same data scope but carries no
`checked_at` field.

`group_by` and `group_key` are an optional Check drill-down pair on the list
endpoint: clients must provide both or neither. A supplied pair selects the
same members as its corresponding groups response, combines with an optional
`issue_type` filter as AND, and is applied before pagination. Clients obtain a
group key from `GET /api/check/groups` and echo it unchanged; they do not
construct group keys themselves.

* `GET /api/check?issue_type=&group_by=&group_key=&library_id=&limit=&cursor=` — list envelope of `CheckIssue` items, plus a top-level `"checked_at": "<iso>" | null` field. The optional `group_by` / `group_key` pair loads a group’s first examples and, through pagination, its full member list.
* `GET /api/check/facets?library_id=` — facet envelope; facet field: `issue_type`; carries `checked_at` per the Facet Envelope section above.
* `GET /api/check/groups?group_by=&library_id=&limit=&cursor=` — enriched Check issue group envelope. Supported `group_by` values are `issue_type`, `severity`, `path_root`, `artist_album`, `suggested_command`, and `library_id`. Group members are not embedded in this response; clients load examples and expanded members through the list endpoint's drill-down pair.
* `POST /api/check/run` — CSRF-protected via the `X-OMYM2-CSRF-Token` header; body may carry an optional `library_id`. With it, the request recomputes one Library; without it, the request recomputes every known Library. Returns `{ "checked_at": "<iso>", "total": N, "errors": [] }` for that invocation.

Check group values are derived from each persisted `CheckIssue`; no endpoint
recomputes diagnostics or reads the filesystem:

* `issue_type` uses the recorded CheckIssue catalog value as its key and label.
* `severity` uses `error` for `db_file_missing` and
  `content_hash_changed`, `info` for `library_stale`, and `warning` for every
  other CheckIssue type. Its key and label are the resulting severity value.
* `path_root` uses the first directory segment of a relative path, including a
  trailing `/`. For example, `Aimer/Album/01.flac` has path root `Aimer/`. A root-level relative path uses
  `(root)`, an absolute path uses `(external)`, and a null path uses
  `(unknown)`; each is both the key and label.
* `artist_album` uses the first two directory segments of a relative path and
  labels them as `Artist / Album`. A one-directory path uses
  `Artist / (root)`, a root-level path uses `(root)`, an absolute path uses
  `(external)`, and a null path uses key `(unknown)` with label
  `Unknown Artist / Unknown Album`.
* `suggested_command` normalizes issue types into command-family keys and
  labels: `refresh` (`db_file_missing`, `content_hash_changed`, and
  `metadata_hash_changed`) uses `omym2 refresh <file>`;
  `add` (`unmanaged_file_exists`) uses `omym2 add <path>`;
  `organize` (`current_path_differs_from_canonical_path`,
  `duplicate_candidate`, and `plan_source_changed`) uses `omym2 organize`;
  `history` (`pending_file_event_exists`) uses `omym2 history`; and `check`
  (`library_unregistered`, `library_stale`, and `library_blocked`) uses
  `omym2 check`.
* `library_id` uses the recorded Library UUID string as its key and label.

Every Check grouping is ordered `count DESC, key ASC`, including equal-count
ties. `common_path_root` uses the non-null `path_root` derivation above,
independent of which grouping was requested.

The check-run body does not accept `trust_stat`; Web recomputation always uses complete managed-file snapshots.

`GET /api/check*` never recomputes findings. The `omym2 check` CLI command and `POST /api/check/run` persist them, and browsing endpoints read the stored latest findings in their selected scope.

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
