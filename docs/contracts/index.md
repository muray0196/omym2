# Contracts

This folder contains concrete contracts for persisted state and externally
observable values.

* [Config Contract](config.md) - Defines OMYM2's TOML config schema, atomic-save protocol, naming and path policy, runtime controls, companion processing, and unprocessed-file collection.
* [DB Schema Contract](db-schema.md) - Defines OMYM2's SQLite tables, provider cadence, CompanionAsset identity, trackless unprocessed action/event provenance, migrations, downgrade safety, indexes, JSON, and timestamps.
* [Durable Operation Contract](operations.md) - Defines durable background Operation identity, lifecycle, idempotency, progress, polling, retention, and restart recovery including unprocessed-file mutation evidence.
* [Path Identity And Storage Contract](path-identity-storage.md) - Defines Library, Track, and CompanionAsset identity, retained-root layouts and stored paths, protected inventory, cross-platform retained-object observation and mutation, and escape prevention.
* [Status And Reason Catalog](status-reason-catalog.md) - Defines the versioned Track and CompanionAsset statuses, Plan action/reason, unprocessed FileEvent and CheckIssue values, durable-operation catalogs, triage, and presentation behavior.
* [Web API Contract](web-api.md) - Defines the bundled local Web API's typed envelopes, companion and unprocessed Plan/FileEvent/Check resources, settings, Bootstrap catalog v3, operations, and browsing semantics.
