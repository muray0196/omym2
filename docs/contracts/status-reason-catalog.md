# Status And Reason Catalog

This document is authoritative for allowed status, reason, action type, event type, error code, and check issue values.

Domain concepts are in [../domain.md](../domain.md). Execution state transitions are in [../execution/model.md](../execution/model.md), [../execution/apply.md](../execution/apply.md), and [../execution/failure-policy.md](../execution/failure-policy.md).

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
```

`conflict` and `error` are not action types.

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
```

Plan creation problems are blocked. Apply-time precondition failures are failed.

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

No closed catalog exists yet.

Values must be stable snake_case strings. Adapter-specific raw exception names must not be persisted directly.

Any newly introduced `error_code` must be added to this catalog and covered by tests.

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

## Cross-Cutting Rules

* Skip actions become applied without FileEvent.
* Blocked actions remain blocked during apply.
* Precondition failures before mutation do not create FileEvents.
* Terminal Plans are single-use.
* Status catalog changes require state transition and failure behavior tests.
