---
type: Execution Spec
title: Refresh Execution
description: Defines the refresh command for re-evaluating file/directory/all targets after external tag correction, including metadata reload, canonical path recalculation, move vs refresh_metadata plan action selection, and stable track_id preservation.
tags: [refresh, metadata, plan-creation, track-id]
timestamp: 2026-07-04T12:54:48+09:00
---

# Refresh Execution

This document is authoritative for refresh after external tag correction, file / directory / all targets, metadata reload, canonical path recalculation, relocation plan creation, metadata-only refresh action selection, and stable `track_id` preservation.

Common execution rules are in [model.md](model.md). Apply rules are in [apply.md](apply.md).

## Refresh Behavior

`refresh` is an operation for re-evaluation and relocation after tag correction.

Targets can be file / directory / all.

```bash
omym2 refresh <file>
omym2 refresh <dir>
omym2 refresh --all
```

Expected flow:

```text
Correct tags with an external tag editor
  ↓
omym2 refresh <file>
  ↓
reload metadata
  ↓
recalculate canonical path
  ↓
create plan if needed
  ↓
apply
  ↓
update DB
```

For each selected Track without a review-time issue, plan creation chooses one outcome:

* If the recalculated canonical path differs from the Track's current path, refresh plans a `move` action.
* If the canonical path is unchanged but the content hash or metadata hash differs from the managed Track, refresh plans a `refresh_metadata` action that reingests Track metadata and hashes without moving the file. Applying it updates the Track in place without creating a FileEvent, as described in [apply.md](apply.md).
* If neither the path nor the hashes changed, refresh plans no action for that Track.

`refresh` does not move files directly. As a rule, it creates a Plan.

Stable `track_id` allows refresh to treat tag changes and canonical path changes as changes to the same managed Track, not as removal of one Track and creation of another.

Only when `--apply` is specified is the created plan applied within the same command.
