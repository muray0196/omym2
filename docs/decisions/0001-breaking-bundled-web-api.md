---
type: Architecture Decision Record
title: "ADR 0001: Replace the Bundled Web API Without a Version Prefix"
description: Records why the bundled SPA and Web API use one coordinated breaking contract without an external-client compatibility layer or version prefix.
tags: [adr, web-api, openapi, breaking-change]
timestamp: 2026-07-13T00:31:39+09:00
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

M1-M5 changes remain on an unreleased renewal integration line. Its CI pairs
`web-v2` only with the new API, while the last supported `main`/`stable`
release retains the old paired package. Only the completed M5 tree is
merged/released; intermediate artifacts are evaluation evidence, not a
supported compatibility period.

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
* Existing clients of the old local API may break without a compatibility
  period; this is deliberate because they are unsupported.
* Supporting independent external clients or introducing a version prefix
  requires a new architecture decision.
