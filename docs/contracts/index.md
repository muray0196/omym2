# Contracts

This folder contains concrete contracts for persisted state and externally
observable values.

* [Config Contract](config.md) - Defines the authoritative contract for OMYM2's TOML-based application config, including its file location, AppConfig shape, path-policy templates, artist ID rules, and metadata/collision policy.
* [DB Schema Contract](db-schema.md) - Defines OMYM2's SQLite tables, nullable Track stat baselines, forward-only migrations, performance indexes, stored JSON boundaries, and timestamp policy.
* [Path Identity And Storage Contract](path-identity-storage.md) - Defines the authoritative rules for Library and Track identity stability, stored path representation, PathResolver boundaries, absolute-path exceptions, and path escape prevention.
* [Status And Reason Catalog](status-reason-catalog.md) - Defines the authoritative catalog of allowed status, reason, action type, event type, and check issue values, plus the FileEvent error-code schema used across Library, Track, Plan, PlanAction, Run, and FileEvent entities.
* [Web API Contract](web-api.md) - Defines OMYM2's local Web API envelopes, browsing and Plan-creation requests, pagination/facets/groups, and exclusion of CLI-only trust-stat flags.
