---
type: Architecture Decision Record
title: "ADR 0001: Replace the Bundled Web API Without a Version Prefix"
description: Why the bundled SPA and Web API share one coordinated breaking contract with no version prefix or compatibility layer.
tags: [adr, web-api, openapi, breaking-change]
timestamp: 2026-07-18T12:00:00+09:00
---

# ADR 0001: Replace the Bundled Web API Without a Version Prefix

## Status

Accepted.

## Context

The React SPA and Python Web API ship in one package from one commit; the API exists only for that bundled SPA. Versioned routes or a translation layer would create a compatibility window between components always upgraded together and let handwritten frontend types drift from the Python schemas.

## Decision

* The SPA and Web API make coordinated breaking replacements under `/api`: no `/api/v1` prefix, no legacy endpoints or envelopes, no compatibility adapter, no stability guarantee for external clients.
* OMYM2 is pre-release: development databases, Config files, browser URLs, opaque group keys, generated clients, and internal Python imports are not supported upgrade surfaces. A contract change updates or removes all owning code and artifacts in one change; old local state is rejected with an explicit reset instruction, never translated. (The 2026-07-16 clean-slate cutover applied this: one baseline migration, advanced Config version, removed retired wire keys and dormant progress fields.)
* Pydantic request/response models are the schema source; a schema-only app exports OpenAPI, and the SPA consumes the generated TypeScript client. Authoritative envelopes, routes, errors, and generation requirements: [Web API contract](../contracts/web-api.md).

## Consequences

* SPA and API cut over atomically in one package; every API change updates Pydantic models, OpenAPI artifact, generated client, contract tests, and bundled SPA together.
* Generated-client drift is a build failure.
* Old local API requests, URLs, Config files, and databases may break without a compatibility period — deliberate, as unsupported pre-release state.
* Supporting external clients or adding a version prefix requires a new architecture decision.
