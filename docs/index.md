# Core Documentation

* [Product](PRODUCT.md) - Defines OMYM2 as a Plan-centered local music operations core with peer CLI and desktop Web surfaces, including the Web execution boundary and non-goals.
* [Domain](DOMAIN.md) - Defines OMYM2's core entities, including durable Operations and Track stat baselines, their invariants, snapshot boundaries, and UUIDv7 identity policy.
* [Storage](STORAGE.md) - Defines TOML raw-revision and atomic-save ownership plus SQLite managed-state, durable Operation/FileEvent, consistency, reproducibility, and path responsibilities.
* [Development Harness](DEVELOPMENT.md) - Specifies dependency setup, current and renewal-transition quality gates, checks.sh, suppressions, and Python runtime configuration policy.
* [Testing](TESTING.md) - Defines OMYM2's Python, frontend, desktop-browser, architecture, integration, contract, fixture, and clean-room test policy.
* [Commands](COMMANDS.md) - Lists the OMYM2 CLI surface, including Plan workflows, diagnostics, settings, and the explicit organize/refresh/check trust-stat optimization flags.
* [Pipeline Performance Benchmark](BENCHMARKS.md) - Defines the reproducible end-to-end pipeline benchmark, its dataset, measurement boundaries, and trust-stat comparison procedure for performance changes.

# Directories

* [Codebase](codebase/) - Source layout, dependency, ports, naming, and Web frontend rules.
* [Contracts](contracts/) - Config, DB, Operation, path identity, status, and Web API contracts.
* [Architecture Decisions](decisions/) - Accepted architecture decisions, rationale, and consequences.
* [Execution](execution/) - Plan, apply, undo, refresh, organize, check, and failure semantics.
