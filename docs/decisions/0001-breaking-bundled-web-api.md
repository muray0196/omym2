---
type: Architecture Decision Record
title: "ADR 0001: Replace the Bundled Web API Without a Version Prefix"
description: Records why the bundled SPA and Web API use one coordinated breaking contract without an external-client compatibility layer or version prefix.
tags: [adr, web-api, openapi, breaking-change]
timestamp: 2026-07-16T22:15:00+09:00
---

# ADR 0001: Replace the Bundled Web API Without a Version Prefix

## Status

Accepted.

## Context

OMYM2 distributes its React SPA and Python Web API in the same package and
releases them from the same commit. The API exists to support that bundled SPA;
external Web API clients are not a supported product surface.

Maintaining the previous response shapes, parallel versioned routes, or a
translation layer would create a compatibility window between two components
that are always upgraded together. It would also allow handwritten frontend
types to drift from the Python schemas.

## Decision

The renewed SPA and Web API make one coordinated breaking replacement under
`/api`. OMYM2 does not add an `/api/v1` prefix, preserve legacy endpoints or
envelopes, or provide a compatibility adapter. External clients receive no
stability or migration guarantee for this local API.

OMYM2 is pre-release. Development databases, Config files, browser URLs,
opaque group keys, generated clients, and internal Python imports are not
supported upgrade surfaces. A coordinated contract change updates or removes
all owning code and artifacts in one change. Old local state is rejected with
an explicit reset instruction instead of being translated.

The 2026-07-16 clean-slate cutover rebased SQLite to one baseline migration,
advanced the Config schema version, removed the retired Track
`group_by=artist_album` wire key, and removed dormant Operation progress
fields. No adapters or aliases preserve those pre-release contracts.

Pydantic request and response models are the schema source. A schema-only app
exports OpenAPI, and the SPA consumes the generated TypeScript client rather
than duplicating response shapes. The authoritative envelopes, status codes,
routes, errors, and generation requirements live in the
[Web API contract](../contracts/web-api.md).

## Consequences

* The SPA and API must cut over atomically in one package.
* Every API contract change must update its Pydantic models, OpenAPI artifact,
  generated client, contract tests, and bundled SPA together.
* Generated-client drift is a build failure.
* Old local API requests, browser URLs, Config files, and SQLite databases may
  break without a compatibility period; this is deliberate because they are
  unsupported pre-release state.
* Supporting independent external clients or introducing a version prefix
  requires a new architecture decision.
