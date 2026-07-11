---
type: Execution Spec
title: Undo Execution
description: Defines per-Run undo, terminal Run requirements, refresh_metadata rejection, reverse FileEvent tracing, restore-destination conflict handling, and external restore Track removal.
tags: [undo, file-event, plan-creation, restore]
timestamp: 2026-07-11T21:38:14+09:00
---

# Undo Execution

This document is authoritative for undo per Run, terminal Run requirements, unsupported refresh_metadata history, reverse FileEvent tracing, undo Plan creation, external restore target path handling, conflict behavior at restore destination, and Track removal behavior for restored imported files.

Common execution rules are in [model.md](model.md). Apply rules are in [apply.md](apply.md). Path exceptions are in [../contracts/path-identity-storage.md](../contracts/path-identity-storage.md#absolute-external-path-exceptions).

## Undo Behavior

Undo is performed per Run.

Undo Plan creation requires the source Run to be terminal. A `running` Run must be rejected because its FileEvent history can still change.

Undo Plan creation must reject any source Run whose Plan contains a `refresh_metadata` action. `refresh_metadata` updates Track metadata and hashes without a FileEvent, and the initial history model does not persist before/after metadata state for reversal.

```text
run
  ↓
trace succeeded file_events in reverse order
  ↓
create undo plan
  ↓
apply
  ↓
restore to original paths
```

Undo does not modify the filesystem directly. It goes through a Plan.

```bash
omym2 undo <run-id>
omym2 apply <undo-plan-id>
```

Only when applying within the same command is `--apply` used.

```bash
omym2 undo <run-id> --apply
```

If the restore destination is already occupied during undo Plan creation, the
corresponding PlanAction is `blocked` with reason `target_exists`; it is not
overwritten automatically. A target that appears later is caught by apply's
exclusive-create move and fails closed, requiring manual review.

When undo restores a file that originally came from outside the Library, such as an add/import source, the undo Plan records the external restore destination as an absolute target path. Applying that undo moves the file out of the Library and marks the managed Track as `removed`; Track paths remain Library-root-relative and do not store the external destination.

Undo uses Run and FileEvent history. Stable `track_id` keeps the relationship between Track state and FileEvents even when paths, metadata, or hashes have changed.
