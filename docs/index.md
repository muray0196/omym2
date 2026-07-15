# Core Documentation

* [Product](PRODUCT.md) - Defines OMYM2 as a Plan-centered local music application with configurable artist display names across CLI, browser-hosted Web, and supported Windows desktop surfaces, including their execution boundary and non-goals.
* [Domain](DOMAIN.md) - Defines OMYM2's core entities, including raw track metadata, artist-name source keys, batch resolution and projections, durable Operations, Track stat baselines, snapshot boundaries, and UUIDv7 identity policy.
* [Storage](STORAGE.md) - Defines application-root selection, TOML raw-revision and atomic-save ownership, artist-name storage boundaries, SQLite managed state, durable Operation and FileEvent storage, consistency, reproducibility, and path responsibilities.
* [Commands](COMMANDS.md) - Lists the OMYM2 CLI surface, including Plan workflows, artist-name settings, diagnostics, and the explicit organize/refresh/check trust-stat optimization flags.

# Directories

* [Codebase](codebase/) - Source layout, dependency, ports, naming, and Web frontend rules.
* [Contracts](contracts/) - Config, DB, Operation, path identity, status, and Web API contracts.
* [Architecture Decisions](decisions/) - Accepted architecture decisions, rationale, and consequences.
* [Development](development/) - Development harness, quality gates, test policy, and benchmark procedure.
* [Execution](execution/) - Plan, apply, undo, refresh, organize, check, and failure semantics.
