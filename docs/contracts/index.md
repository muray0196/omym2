# Contracts

This folder contains concrete contracts for persisted state and externally
observable values.

* [Config Contract](config.md) - Defines the authoritative contract for OMYM2's TOML-based application config, including its file location, AppConfig shape, path-policy templates, artist ID rules, and metadata/collision policy.
* [DB Schema Contract](db-schema.md) - Defines the authoritative SQLite schema contract for OMYM2, covering table responsibilities (libraries, tracks, plans, plan_actions, runs, file_events, check_runs, check_issues), migrations, indexes, stored JSON fields, and timestamp policy.
* [Path Identity And Storage Contract](path-identity-storage.md) - Defines the authoritative rules for Library and Track identity stability, stored path representation, PathResolver boundaries, absolute-path exceptions, and path escape prevention.
* [Status And Reason Catalog](status-reason-catalog.md) - Defines the authoritative catalog of allowed status, reason, action type, event type, error code, and check issue values used across Library, Track, Plan, PlanAction, Run, and FileEvent entities.
* [Web API Contract](web-api.md) - Defines the authoritative JSON envelope, pagination/cursor, facet, and group-by contract for OMYM2's local Web API browsing endpoints (tracks, plans, check, history).
