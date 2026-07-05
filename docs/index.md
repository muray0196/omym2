---
okf_version: "0.1"
---

# Core Documentation

* [Product](PRODUCT.md) - Describes OMYM2's product shape as a headless domain core with a CLI runner and a local Web settings console, and defines its primary safe-import use case and technology stack.
* [Domain](DOMAIN.md) - Defines OMYM2's core domain entities (AppConfig, FileScanEntry, FileSnapshot, TrackMetadata, PathPolicy, Library, Track, Plan, PlanAction, Run, FileEvent, CheckIssue), their invariants, and the UUIDv7-based ID design policy.
* [Storage](STORAGE.md) - Defines the TOML-vs-SQLite storage boundary, repository responsibilities, DB consistency and reproducibility principles, and the high-level Library-root-relative stored path policy.
* [Development Harness](DEVELOPMENT.md) - Specifies developer quality commands, the checks.sh wrapper, docs search scripts, local LLM helpers, suppression rules, and Python runtime configuration policy.
* [Testing](TESTING.md) - Defines OMYM2's test policy across architecture, unit, and integration test categories, fixture policy, and which contract changes require which test focus.
* [Commands](COMMANDS.md) - Lists and summarizes the OMYM2 CLI command surface, including add, plans, apply, refresh, organize, history, undo, check, inspect, config, artist-ids, and settings.

# Directories

* [Codebase](codebase/) - Source layout, dependency, port, and naming rules.
* [Contracts](contracts/) - Config, DB schema, path identity, storage representation, and status values.
* [Execution](execution/) - Plan, apply, undo, refresh, organize, check, and failure semantics.
