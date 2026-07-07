---
type: Codebase Reference
title: Dependency Boundaries
description: Defines OMYM2's dependency direction between adapters, features, domain, and shared layers, the forbidden dependencies, and where business rules must live.
tags: [architecture, dependency-boundaries, hexagonal-architecture, business-rules]
timestamp: 2026-07-07T14:00:00+09:00
---

# Dependency Boundaries

This document is authoritative for OMYM2 dependency direction, forbidden dependencies, direct feature-to-feature import rules, adapter rules, and business rule placement.

Source placement is in [source-layout.md](source-layout.md).

## Dependency Direction

Inbound adapters call features, features use domain, and domain may use shared primitives.

```text
adapters/cli, adapters/web
  ↓
features/*/usecases/*.py
  ↓
domain/
  ↓
shared/
```

Outbound adapters implement ports owned by features or common feature ports.

```text
adapters/db, adapters/fs, adapters/metadata, adapters/config
  ↓
features/*/ports.py or features/common_ports.py
  ↓
domain/
```

`platform/` is the composition root and wires features and adapters together. `platform/runtime_context.py` resolves shared application paths and stateful adapters once per invocation; `platform/feature_composition.py` and `platform/artist_ids_composition.py` build each feature's `*Ports` dataclass from concrete adapters; `platform/cli_composition.py` and `platform/cli_entry_point.py` assemble the CLI's `CommandDependencies` bundle and dispatch into `adapters/cli/main.py`; `platform/web_composition.py` builds the Web UI's `ApiRouteContext` and calls `adapters/web/app.py::create_web_app` with it. Inbound adapters no longer construct outbound adapters themselves.

## Forbidden Dependencies

```text
domain -> adapters
domain -> platform
domain -> db
domain -> fs
domain -> web
domain -> cli

features -> concrete db/fs/web/cli implementations
features -> internal implementations of other features

adapters -> platform
adapters/cli, adapters/web -> adapters/db, adapters/fs, adapters/metadata, adapters/config, adapters/artist_ids
adapters/cli -> adapters/web

adapters/web/routes -> direct filesystem operations
adapters/cli/commands -> direct filesystem operations
templates -> filesystem operations
```

The inbound-adapter-to-concrete-outbound-adapter rule has an exact-pair allowlist for two pure, I/O-free functions that are coupled only to the TOML config representation: `adapters/cli/commands/config.py` may import `omym2.adapters.config.toml_config_store`, and `adapters/web/schemas/settings_json.py` may import `omym2.adapters.config.config_validator`. No other file under `adapters/cli/` or `adapters/web/` may import a concrete outbound adapter subpackage.

Direct imports between features are prohibited in principle. When multiple usecases are chained, orchestration is done in CLI, Web, or platform.

For example, `omym2 add --apply` does not have `features/add` call `features/apply` directly. Instead, the CLI or platform calls `ApplyPlanUseCase` after executing `AddUseCase`.

## Business Rule Placement

Domain services and usecases decide business rules.

Adapters persist, restore, read, write, scan, move, render, parse, and call external tools. They must not decide conflicts, duplicates, canonical paths, metadata validity, or PlanAction status.

Bad example:

```python
# adapters/db/sqlite/repositories.py

if target_path_exists:
    action = PlanAction.conflict(...)
```

Conflict judgment is the responsibility of a domain service or usecase.

Good example:

```python
# adapters/db/sqlite/repositories.py

return Track(
    id=row["id"],
    current_path=row["current_path"],
    metadata_hash=row["metadata_hash"],
)
```

This only restores a domain model from persisted data, so it is allowed.

## Inbound Adapter Rule

CLI and Web route user intent to usecases. They may orchestrate multiple usecases when the command contract requires it, but they must not perform filesystem mutations directly.

Route handlers and command handlers should stay thin. They translate input, call usecases, and format output.

## Outbound Adapter Rule

DB, filesystem, metadata, and config adapters implement ports.

FileScanner must not read tags or calculate hashes. FileSnapshotReader may compose filesystem stat, MetadataReader, hash calculation, and Clock, but it must not decide conflicts, duplicates, canonical paths, or PlanAction status.

## Tests

Architecture tests enforce the highest-risk dependency rules:

* source files follow naming conventions
* usecases do not import concrete SQLite or filesystem adapters
* domain does not import adapters or platform
* shared stays below upper layers
* adapters do not import platform
* CLI and Web adapters do not import concrete outbound adapters (`db`, `fs`, `metadata`, `config`, `artist_ids`), except the two-pair allowlist above
