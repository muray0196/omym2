---
type: OMYM2 Domain Concept
title: AppConfig
description: In-memory settings used by usecases after TOML loading.
tags: [domain, config, settings]
authoritative: false
canonical_docs:
  - ../../domain.md#appconfig
  - ../../contracts/config.md
  - ../../storage.md#toml-responsibility
---

# AppConfig

AppConfig is the in-memory settings object that usecases receive after config adapters load and validate TOML. It is not the TOML file itself, and pure domain logic should receive narrower config objects when possible.

## Authoritative sources

- [Domain AppConfig](../../domain.md#appconfig)
- [Config contract](../../contracts/config.md)
- [TOML responsibility](../../storage.md#toml-responsibility)

## Relationships

- [PathPolicy](path-policy.md) uses narrower path-policy config instead of the whole AppConfig where possible.
- [TOML and SQLite boundary](../references/toml-sqlite-boundary.md) explains why settings remain in TOML.

## Agent notes

- Keep TOML reading and writing in config adapters.
- Do not move editable settings into SQLite.
