# Contracts

This folder contains concrete contracts for persisted state and externally
observable values.

* [Config Contract](config.md) - Complete TOML schema, defaults, validation, atomic-save protocol, path policy, and runtime control semantics.
* [DB Schema Contract](db-schema.md) - SQLite tables, constraints, indexes, migrations, JSON and timestamp policy for all persisted state.
* [Durable Operation Contract](operations.md) - Durable Operation identity, lifecycle, idempotent acceptance, polling, retention, restart reconciliation, and cancellation.
* [Path Identity And Storage Contract](path-identity-storage.md) - Library/Track/CompanionAsset identity, stored path representation, rooted observation/mutation, and escape prevention.
* [Status And Reason Catalog](status-reason-catalog.md) - Closed status/reason/type/error-code catalogs for all entities plus cross-surface presentation rules.
* [Web API Contract](web-api.md) - Authoritative local HTTP API contract - envelope, error catalog, CSRF, idempotency, browsing shapes, and every /api endpoint.
