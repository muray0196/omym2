# Contracts

This folder contains concrete contracts for persisted state and externally
observable values.

* [Config Contract](config.md) - Defines OMYM2's TOML config schema, atomic-save protocol, naming and path policy, runtime controls, companion processing, and unprocessed-file collection.
* [DB Schema Contract](db-schema.md) - Defines OMYM2's SQLite tables, migration history, reset policy, indexes, constraints, JSON, timestamps, and persisted companion and unprocessed evidence.
* [Durable Operation Contract](operations.md) - Defines durable background Operation identity, lifecycle, idempotency, status polling, retention, and restart recovery including unprocessed-file mutation evidence.
* [Path Identity And Storage Contract](path-identity-storage.md) - Defines Library, Track, and CompanionAsset identity, retained-root layouts and stored paths, protected inventory, cross-platform retained-object observation and mutation, and escape prevention.
* [Status And Reason Catalog](status-reason-catalog.md) - Defines the closed Track, CompanionAsset, Plan, FileEvent, CheckIssue, and Operation catalogs, triage semantics, and exhaustive bundled-client presentation behavior.
* [Web API Contract](web-api.md) - Defines the bundled local Web API's clean-slate typed envelopes, closed catalogs, generated client, operations, settings, and browsing semantics.
