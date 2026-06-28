# Refresh Execution

This document is authoritative for refresh after external tag correction, file / directory / all targets, metadata reload, canonical path recalculation, relocation plan creation, and stable `track_id` preservation.

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
create move plan if needed
  ↓
apply
  ↓
update DB
```

`refresh` does not move files directly. As a rule, it creates a Plan.

Stable `track_id` allows refresh to treat tag changes and canonical path changes as changes to the same managed Track, not as removal of one Track and creation of another.

Only when `--apply` is specified is the created plan applied within the same command.
