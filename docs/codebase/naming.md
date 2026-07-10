---
type: Codebase Reference
title: Source Naming
description: Authoritative Python naming conventions for OMYM2 modules, classes, functions, and constants, including banned vague names and per-layer naming rules for domain, features, and adapters.
tags: [naming-conventions, python, code-style, architecture]
timestamp: 2026-07-10T02:07:51+09:00
---

# Source Naming

This document is authoritative for Python module naming, class/function/constant naming, banned vague names, domain naming, feature naming, adapter naming, and names not adopted.

Source placement is in [source-layout.md](source-layout.md).

## Common Rules

```text
Python module name   snake_case.py
Class name           PascalCase
Function / variable  snake_case
Constant             UPPER_SNAKE_CASE
```

Avoid ambiguous names. This is the authoritative list of banned ambiguous module names:

```text
Names to avoid:
  utils.py
  helpers.py
  manager.py
  service.py
  common.py
```

Even when placing shared processing as an exception, use a concrete concern name.

## Naming In domain/

`domain/` is noun-based. Do not place names that imply I/O or execution procedures.

Examples:

```text
domain/models/
  track.py
  track_metadata.py
  file_scan_entry.py
  file_snapshot.py
  plan.py
  plan_action.py
  run.py
  file_event.py
  check_issue.py

domain/services/
  path_policy.py
  collision_policy.py
  artist_id.py
  config_fingerprint.py
  metadata_fingerprint.py
  content_fingerprint.py
```

Even under `domain/services/`, do not append `_service.py` to file names. The directory already indicates that they are services.

## Naming In features/

`features/{feature}/` is divided by user goal.

```text
features/{feature}/
  usecases/
    {verb}_{object}.py
  ports.py
  dto.py
```

Examples:

```text
features/add/usecases/create_add_plan.py
features/apply/usecases/apply_plan.py
features/check/usecases/check_library.py
```

Feature-local `domain/` and `adapters/` directories are not created in principle; the authoritative placement rule is in [source-layout.md](source-layout.md).

## Naming In adapters/

Adapter names may include technical names or role names.

Examples:

```text
adapters/cli/commands/add.py
adapters/web/routes/api.py
adapters/db/sqlite/unit_of_work.py
adapters/fs/file_scanner.py
adapters/fs/file_snapshot_reader.py
adapters/metadata/mutagen_reader.py
```

Do not use the name DAO in the DB adapter.

## Names Not Adopted

The following are not adopted:

```text
platform/*_dao.py
*_service.py
```

Banned ambiguous module names are listed once in [Common Rules](#common-rules). Forbidden feature-local directories (`features/{feature}/domain/`, `features/{feature}/adapters/`) are authoritative in [source-layout.md](source-layout.md).
