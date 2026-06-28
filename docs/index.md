# OMYM2 Documentation Index

This directory contains focused developer and coding-agent documents.

Future agents should read selectively. Rules should not be duplicated across documents unless the duplication is explicitly marked as a summary. When a rule has an authoritative home, update that home and link to it from summaries.

## Task Routing

Use this table to choose the smallest document set for the current task.

| Task | Read |
| --- | --- |
| Understanding the top-level architecture constraints | [../ARCHITECTURE.md](../ARCHITECTURE.md) |
| Adding packages, moving modules, or changing import boundaries | [architecture/source-layout.md](architecture/source-layout.md), [architecture/dependency-boundaries.md](architecture/dependency-boundaries.md), [architecture/naming.md](architecture/naming.md) |
| Changing ports, UnitOfWork, transactions, or durable operation logs | [architecture/ports-uow.md](architecture/ports-uow.md) |
| Changing product scope, non-goals, or UI role | [product.md](product.md) |
| Changing domain concepts, invariants, or ID behavior | [domain.md](domain.md) |
| Changing plan execution, apply, undo, refresh, or file-event behavior | [execution/index.md](execution/index.md) |
| Changing CLI commands or command behavior | [commands.md](commands.md) |
| Changing storage responsibilities or persisted state boundaries | [storage.md](storage.md) |
| Changing config file behavior | [contracts/config.md](contracts/config.md) |
| Changing SQLite schema or repository persistence | [contracts/db-schema.md](contracts/db-schema.md) |
| Changing stored paths, path identity, Library identity, or relink behavior | [contracts/path-identity-storage.md](contracts/path-identity-storage.md) |
| Adding or changing status and reason values | [contracts/status-reason-catalog.md](contracts/status-reason-catalog.md) |
| Running development checks or changing quality-gate policy | [development.md](development.md) |
| Writing or updating tests | [testing.md](testing.md) |
| Planning or tracking active work | [process/work-tracking.md](process/work-tracking.md) |
| Configuring or using Codex subagents | [agent/subagents.md](agent/subagents.md) |
| Checking accepted rationale for durable architecture decisions | [decisions/](decisions/) |

## Authoritative Homes

Use this table to find the canonical owner for a rule family before editing or deduplicating rules.

| Rule family | Authoritative home |
| --- | --- |
| Architecture overview and non-negotiable rules | [../ARCHITECTURE.md](../ARCHITECTURE.md) |
| Source layout | [architecture/source-layout.md](architecture/source-layout.md) |
| Dependency boundaries | [architecture/dependency-boundaries.md](architecture/dependency-boundaries.md) |
| Ports and UnitOfWork | [architecture/ports-uow.md](architecture/ports-uow.md) |
| Naming | [architecture/naming.md](architecture/naming.md) |
| Domain concepts and invariants | [domain.md](domain.md) |
| Execution model and behavior | [execution/](execution/) |
| Command surface | [commands.md](commands.md) |
| Storage responsibility | [storage.md](storage.md) |
| Config contract | [contracts/config.md](contracts/config.md) |
| DB schema contract | [contracts/db-schema.md](contracts/db-schema.md) |
| Path identity and storage | [contracts/path-identity-storage.md](contracts/path-identity-storage.md) |
| Status and reason values | [contracts/status-reason-catalog.md](contracts/status-reason-catalog.md) |
| Development workflow and quality gates | [development.md](development.md) |
| Test policy | [testing.md](testing.md) |
| Work-tracking process schema | [process/work-tracking.md](process/work-tracking.md) |
| Codex subagent routing and model policy | [agent/subagents.md](agent/subagents.md) |
| Accepted architecture decisions | [decisions/](decisions/) |

## Documentation Boundaries

Repository docs store durable specifications, process schemas, and decision records.

Active implementation status, backlog, blockers, work assignment, issue dependencies, milestone progress, and partial completion state belong in GitHub Issues, Projects, and Milestones.
