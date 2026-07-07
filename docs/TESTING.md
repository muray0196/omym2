---
type: Testing Guide
title: Testing
description: Defines OMYM2's test policy across architecture, unit, and integration test categories, fixture policy, and which contract changes require which test focus.
tags: [testing, pytest, architecture-tests, fixtures]
timestamp: 2026-07-07T14:00:00+09:00
---

# Testing

This document is authoritative for test policy, test categories, fixture policy, and when contract changes require tests.

Domain rules are in [DOMAIN.md](DOMAIN.md), execution semantics are in [execution/](execution/), storage rules are in [STORAGE.md](STORAGE.md), contract docs are in [contracts/](contracts/), and developer validation commands are in [DEVELOPMENT.md](DEVELOPMENT.md).

This document is not a test backlog.

Required test authoring uses `pytest` and `pytest-mock` only.

`pytest-cov` may exist in the development environment for optional local coverage inspection, but coverage reporting is not a separate required test category unless this document defines a threshold.

Browser E2E testing is deferred. Do not add Playwright requirements to the initial test plan unless this document is updated.

## Architecture Tests

Architecture tests should make later implementation hard to place in the wrong layer.

Required architecture test coverage:

* source files follow naming conventions
* usecases do not import concrete SQLite or filesystem adapters
* domain does not import adapters or platform
* shared does not import upper layers
* forbidden dependencies remain forbidden
* adapters do not import platform
* CLI and Web adapters do not import concrete outbound adapters (`db`, `fs`, `metadata`, `config`, `artist_ids`), except the documented two-pair allowlist

## Unit Tests

Unit tests should cover pure domain behavior and usecases through ports and fakes.

Use unit tests for:

* domain services and invariants
* typed ID behavior through IdGenerator
* path normalization and PathPolicy behavior
* usecase decisions expressed through repositories, ports, and fakes
* state transitions that do not require concrete adapters

## Integration Tests

Integration tests should cover adapters and vertical slices once their dependencies exist.

Use integration tests for:

* TOML config load / save / validation
* SQLite migrations and repositories
* internal storage creation under the application root
* filesystem scanning and snapshot capture
* metadata adapter behavior
* vertical flows that combine usecases with real adapters

## Contract Change Test Requirements

Contract changes require tests for the changed behavior.

| Contract change | Required test focus |
| --- | --- |
| Config contract | config load, save, validation, defaults, and migration behavior |
| DB schema contract | migrations, repositories, constraints, stored JSON, timestamps, and path representation |
| Path identity contract | path normalization, relink, Library identity, Track identity, and Library-root-relative persistence |
| Status catalog | state transitions, failure behavior, and persistence of allowed values |
| Execution contract | Plan, PlanAction, Run, FileEvent, apply order, failure cases, and undo/refresh/check behavior |
| Architecture contract | dependency-boundary tests and source naming tests |

## Fixture Policy

Use in-memory repositories for usecase tests.

Use fixed Clock and IdGenerator ports in tests so time and IDs are deterministic.

Filesystem fixtures should be minimal and task-focused. Read-only filesystem fixtures are appropriate for FileScanner, metadata, hashing, and FileSnapshotReader tests. File-moving fixtures should wait until apply behavior is under test because apply is the workflow that mutates Library music files.

## Test Commands

Use [DEVELOPMENT.md](DEVELOPMENT.md#test-commands) for quick global checks, focused failure inspection, and deep debug commands. This document defines what to test; `docs/DEVELOPMENT.md` defines how to run validation commands.
