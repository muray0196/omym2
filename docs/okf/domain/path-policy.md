---
type: OMYM2 Knowledge Card
title: PathPolicy
description: Pure domain service for Library-root-relative canonical paths.
resource: "../../domain.md#pathpolicy"
tags: [domain, config, path, path-policy]
authoritative: false
---

# PathPolicy

Authoritative source: [docs/domain.md#PathPolicy](../../domain.md#pathpolicy).

## Relationships

* Receives TrackMetadata, file extension, and PathPolicyConfig.
* Generates canonical paths for PlanActions, but does not check filesystem existence.
* Uses config rules owned by the AppConfig contract.

## Agent Notes

* Apply uses recorded PlanAction paths and does not rerun PathPolicy; read [execution/apply.md#Apply Behavior](../../execution/apply.md#apply-behavior).
