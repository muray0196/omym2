---
type: Codebase Reference
title: Dependency Boundaries
description: Dependency direction, forbidden dependency list, feature-import rules, adapter rules, and business-rule placement.
tags: [architecture, dependency-boundaries, desktop, hexagonal-architecture, business-rules]
timestamp: 2026-07-18T12:00:00+09:00
---

# Dependency Boundaries

Authoritative for dependency direction, forbidden dependencies, direct feature-to-feature import rules, adapter rules, and business-rule placement. Source placement: [source-layout.md](source-layout.md).

## Dependency Direction

```text
adapters/cli, adapters/web
  ↓
features/*/usecases/*.py
  ↓
domain/
  ↓
shared/
```

`adapters/desktop` is an inbound presentation/runtime adapter invoked by the platform composition root: it receives the already-composed ASGI application through its server boundary and does not import features or `adapters/web`.

Outbound adapters implement ports owned by features or common feature ports:

```text
adapters/db, adapters/fs, adapters/metadata, adapters/config, adapters/artist_ids
  ↓
features/*/ports.py or features/common_ports.py
  ↓
domain/
```

`platform/` is the composition root wiring features and adapters together; inbound adapters never construct outbound adapters themselves. Composition-module inventory: [source-layout.md](source-layout.md).

## Forbidden Dependencies

```text
domain -> adapters | platform | db | fs | web | cli
features -> concrete adapter implementations
features -> internal implementations of other features
adapters -> platform
adapters/cli, adapters/web, adapters/desktop -> adapters/db, adapters/fs, adapters/metadata, adapters/config, adapters/artist_ids
adapters/cli -> adapters/web
adapters/desktop -> adapters/web
adapters/web/routes -> direct filesystem operations
adapters/cli/commands -> direct filesystem operations
```

Inbound adapters must not import concrete outbound adapter subpackages. The exact-pair allowlist permits only the pure, I/O-free TOML-representation helper import from `adapters/cli/commands/config.py` to `omym2.adapters.config.toml_config_store`; it does not permit adapter construction or I/O from the CLI. No file under `adapters/web/` or `adapters/desktop/`, and no other file under `adapters/cli/`, may import a concrete outbound adapter subpackage; typed Web schemas translate feature DTOs without importing TOML validators or serializers. The desktop adapter does not import the Web adapter — the platform layer injects the composed FastAPI application.

Direct imports between features are prohibited in principle; chained usecases are orchestrated in CLI, Web, or platform. Example: `omym2 add --apply` does not have `features/add` call `features/apply`; the CLI or platform calls `ApplyPlanUseCase` after `CreateAddPlanUseCase`.

## Business Rule Placement

Domain services and usecases decide business rules. Adapters persist, restore, read, write, scan, move, render, parse, and call external tools — they must not decide conflicts, duplicates, canonical paths, metadata validity, or PlanAction status. A repository that sets a PlanAction to conflict because a target path exists is a violation; a repository that merely restores a `Track` from persisted row data is correct.

## Inbound Adapter Rule

CLI and Web route user intent to usecases. The desktop adapter supplies native window and server mechanics around the composed Web application; it never calls feature usecases or exposes a native bridge. Inbound adapters may orchestrate multiple usecases when the command contract requires it but must not perform filesystem mutations directly. Route and command handlers stay thin: translate input, call usecases, format output.

## Outbound Adapter Rule

DB, filesystem, metadata, and config adapters implement ports. FileScanner must not read tags or calculate hashes. FileSnapshotReader may compose filesystem stat, MetadataReader, hash calculation, and Clock, but must not decide conflicts, duplicates, canonical paths, or PlanAction status.

## Tests

Architecture tests enforce the highest-risk rules: source naming conventions; usecases not importing concrete adapters; domain not importing adapters or platform; shared staying below upper layers; adapters not importing platform; CLI/Web/desktop adapters not importing concrete outbound adapters (except the one CLI-only pair above); the desktop adapter not importing the Web adapter or exposing feature access.
