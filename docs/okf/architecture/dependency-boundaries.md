---
type: OMYM2 Knowledge Card
title: Dependency Boundaries
description: Layer direction and business-rule placement for OMYM2 architecture.
resource: "../../architecture/dependency-boundaries.md#dependency-direction"
tags: [architecture, dependencies, adapters, features]
authoritative: false
---

# Dependency Boundaries

Authoritative source: [docs/architecture/dependency-boundaries.md#Dependency Direction](../../architecture/dependency-boundaries.md#dependency-direction).

## Relationships

* Inbound adapters call features; features use domain; domain may use shared primitives.
* Outbound adapters implement ports owned by features or common feature ports.
* Business rules belong in domain services or usecases, not adapters.

## Agent Notes

* Before moving logic across layers, read [docs/architecture/dependency-boundaries.md#Business Rule Placement](../../architecture/dependency-boundaries.md#business-rule-placement).
