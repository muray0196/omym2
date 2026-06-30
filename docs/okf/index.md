# OKF-lite Knowledge Index

This folder is an OKF-lite navigation aid for OMYM2 docs and agent investigation.
It is not an authoritative rule store, runtime state store, progress log, or
adoption of the Google OKF ecosystem.

Use these cards to find the authoritative docs for high-risk concepts, then read
the linked source before changing code, schemas, storage behavior, or execution
semantics. Existing docs remain the source of truth:

* [ARCHITECTURE.md](../../ARCHITECTURE.md) for top-level architecture rules.
* [AGENTS.md](../../AGENTS.md) for agent routing and required reading.
* [docs/domain.md](../domain.md) for domain concepts and invariants.
* [docs/execution/](../execution/) for Plan, apply, undo, refresh, and failure semantics.
* [docs/storage.md](../storage.md) and [docs/contracts/](../contracts/) for storage and contract rules.

Do not use this folder for active progress, blockers, queue state, handoff notes,
or Markdown representations of Plan, Run, FileEvent, Track, AppConfig, or other
runtime data.

## Domain

| Card | Use |
| --- | --- |
| [Library](domain/library.md) | Stable Library identity and root-path context. |
| [Track](domain/track.md) | Managed music file state and stable Track identity. |
| [Plan](domain/plan.md) | Reviewed scheduled work before execution. |
| [PlanAction](domain/plan-action.md) | Per-file action data inside a Plan. |
| [Run](domain/run.md) | Apply attempt history and FileEvent parent unit. |
| [FileEvent](domain/file-event.md) | Durable operation log entry for Library music file mutation. |
| [PathPolicy](domain/path-policy.md) | Pure canonical path generation. |
| [AppConfig](domain/app-config.md) | In-memory settings object loaded through config ports. |

## Execution

| Card | Use |
| --- | --- |
| [Plan-centered apply](execution/plan-centered-apply.md) | Apply safety, recorded PlanActions, and precondition handling. |
| [Undo](execution/undo.md) | Reverse FileEvent tracing and undo Plan creation. |
| [Refresh](execution/refresh.md) | Metadata reload, canonical path recalculation, and relocation planning. |

## Architecture

| Card | Use |
| --- | --- |
| [Dependency boundaries](architecture/dependency-boundaries.md) | Layer direction and business-rule placement. |
| [Ports and UnitOfWork](architecture/ports-uow.md) | I/O ports, transaction boundaries, and operation-log exceptions. |

## Storage

| Card | Use |
| --- | --- |
| [TOML and SQLite boundary](storage/toml-sqlite-boundary.md) | Editable settings vs managed state responsibilities. |
| [Path identity storage](storage/path-identity-storage.md) | Stable IDs, Library-root-relative paths, and PathResolver boundary. |
