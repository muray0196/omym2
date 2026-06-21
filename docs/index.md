# OMYM2 Documentation Index

This directory contains the focused project documents that future agents should read selectively.

Design rules should not be duplicated across documents unless the duplication is explicitly marked as a summary. When a rule has an authoritative home, update that home and link to it from summaries.

## Task Routing

* Start with [../ARCHITECTURE.md](../ARCHITECTURE.md) for architecture, layer boundaries, dependency direction, ports, UnitOfWork policy, transactions, durable operation logs, and source file naming.
* Read [product.md](product.md) for product intent, primary usage, non-goals, UI role, and product-facing technical policy.
* Read [domain.md](domain.md) for AppConfig, Library, Track, Plan, PlanAction, Run, FileEvent, CheckIssue, PathPolicy, domain invariants, and ID policy.
* Read [execution.md](execution.md) for Plan-centered execution, lazy bootstrap, Library identity/registration, add/apply/refresh/organize/undo/check behavior, Run and FileEvent semantics, blocked vs failed behavior, and durable operation log flow.
* Read [commands.md](commands.md) for CLI command surface and command-level behavior. Detailed execution rules live in [execution.md](execution.md).
* Read [storage.md](storage.md) for TOML config, SQLite responsibilities, Library identity and registration storage, table responsibilities, DB consistency, config reproducibility, and stored path representation.
* Read [development.md](development.md) for development workflow, quality gates, validation commands, suppressions, and Python runtime configuration policy.
* Read [testing.md](testing.md) for architecture tests, unit tests, integration tests, fixture policy, and tests to write first.
* Read [implementation_plan.md](implementation_plan.md) for dependency-first and vertical-slice-first implementation phases.
* Read [mvp.md](mvp.md) for the short MVP completion checklist.
* Read [decisions/](decisions/) for accepted architecture decision records when a task touches a previously decided trade-off.

## Authoritative Homes

* Architecture and naming rules: [../ARCHITECTURE.md](../ARCHITECTURE.md)
* Domain concepts and invariants: [domain.md](domain.md)
* Plan, apply, undo, Run, FileEvent, bootstrap, and Library identity/registration execution semantics: [execution.md](execution.md)
* Command surface: [commands.md](commands.md)
* Config, DB, Library identity/registration, and path storage: [storage.md](storage.md)
* Development workflow and quality gates: [development.md](development.md)
* Test requirements: [testing.md](testing.md)
* Implementation order: [implementation_plan.md](implementation_plan.md)
* MVP definition: [mvp.md](mvp.md)
* Accepted architecture decisions: [decisions/](decisions/)
