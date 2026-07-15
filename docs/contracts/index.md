# Contracts

This folder contains concrete contracts for persisted state and externally
observable values.

* [Config Contract](config.md) - Defines OMYM2's TOML config schema, raw-storage revision and atomic-save protocol, path policy, artist display-name preferences, artist IDs, and metadata/collision policy.
* [DB Schema Contract](db-schema.md) - Defines OMYM2's SQLite tables, accepted artist-name provenance, durable Operation schema, atomic Apply reservation, undo provenance, forward-only migrations, indexes, JSON boundaries, and timestamp policy.
* [Durable Operation Contract](operations.md) - Defines durable background Operation identity, lifecycle, idempotency, progress, polling, retention, Operation-level restart recovery, and cancellation policy.
* [Path Identity And Storage Contract](path-identity-storage.md) - Defines Library and Track identity stability, stored path representation, PathResolver boundaries, descriptor-anchored mutation, absolute-path exceptions, and path escape prevention.
* [Status And Reason Catalog](status-reason-catalog.md) - Defines the versioned status, reason, action, event, check, and durable-operation catalogs plus required unknown-value and status presentation behavior.
* [Web API Contract](web-api.md) - Defines the bundled local Web API's typed envelopes, errors, artist-name settings, settings concurrency, bootstrap, durable-operation routes, capabilities, and preserved browsing semantics.
