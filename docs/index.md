# Core Documentation

* [Product](PRODUCT.md) - Describes OMYM2's product shape as a headless domain core with a CLI runner and a local Web settings, Plan creation/review, and status console, and defines its primary safe-import use case and technology stack.
* [Domain](DOMAIN.md) - Defines OMYM2's core domain entities, including Track stat baselines and snapshot trust boundaries, their invariants, and the UUIDv7-based identity policy.
* [Storage](STORAGE.md) - Defines the TOML-vs-SQLite boundary, repository, Track stat-baseline, and persisted check-diagnostic responsibilities, SQLite durability rules, reproducibility, and Library-relative path policy.
* [Development Harness](DEVELOPMENT.md) - Specifies dependency setup, developer quality gates, checks.sh, suppression rules, and Python runtime configuration policy.
* [Testing](TESTING.md) - Defines OMYM2's test policy across architecture, unit, and integration test categories, fixture policy, and which contract changes require which test focus.
* [Commands](COMMANDS.md) - Lists the OMYM2 CLI surface, including Plan workflows, diagnostics, settings, and the explicit organize/refresh/check trust-stat optimization flags.
* [Pipeline Performance Benchmark](BENCHMARKS.md) - Defines the reproducible end-to-end pipeline benchmark, its dataset, measurement boundaries, and trust-stat comparison procedure for performance changes.

# Directories

* [Codebase](codebase/) - Source layout, dependency, port, and naming rules.
* [Contracts](contracts/) - Config, DB schema, path identity, storage representation, and status values.
* [Execution](execution/) - Plan, apply, undo, refresh, organize, check, and failure semantics.
