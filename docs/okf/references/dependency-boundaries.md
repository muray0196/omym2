---
type: OMYM2 Architecture Reference
title: Dependency boundaries
description: Architecture direction and business-rule placement.
tags: [architecture, dependencies, adapters, domain]
authoritative: false
canonical_docs:
  - ../../codebase/dependency-boundaries.md
---

# Dependency Boundaries

OMYM2 keeps domain and feature behavior independent from concrete adapters. Inbound adapters route user intent to usecases, outbound adapters implement ports, and business rules stay in domain services or usecases.

## Authoritative sources

- [Dependency boundaries](../../codebase/dependency-boundaries.md)

## Relationships

- [Ports and UnitOfWork](ports-uow.md) describes port and transaction boundaries.
- [PathPolicy](../concepts/path-policy.md) is an example of pure domain logic.
- [Plan-centered apply](../playbooks/plan-centered-apply.md) depends on feature orchestration through ports.

## Agent notes

- Do not put business decisions in adapters.
- Do not add direct feature-to-feature imports; compose workflows in CLI, Web, or platform.
