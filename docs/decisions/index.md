# Architecture Decisions

This folder records accepted architecture decisions and their consequences.

* [ADR 0001: Replace the Bundled Web API Without a Version Prefix](0001-breaking-bundled-web-api.md) - Why the bundled SPA and Web API share one coordinated breaking contract with no version prefix or compatibility layer.
* [ADR 0002: Persist Durable Operations and Poll Their Status](0002-durable-operations-over-polling.md) - Why long-running work uses persisted SQLite Operations, idempotent acceptance, bounded polling, and conservative restart recovery.
* [ADR 0003: Serialize Mutations With a Cross-Process Exclusive Lock](0003-cross-process-exclusive-operation-lock.md) - The native cross-platform file-lock mechanism that serializes all Web and CLI mutations and protects atomic Apply acceptance.
* [ADR 0004: Package a Thin Windows Desktop Application](0004-windows-desktop-application.md) - The Windows-only pywebview desktop shell, loopback server, stable data root, shutdown semantics, and audited onedir packaging.
