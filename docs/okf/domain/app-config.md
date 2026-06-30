---
type: OMYM2 Knowledge Card
title: AppConfig
description: In-memory application settings used by usecases.
resource: "../../domain.md#appconfig"
tags: [domain, config, toml, app-config]
authoritative: false
---

# AppConfig

Authoritative source: [docs/domain.md#AppConfig](../../domain.md#appconfig).

## Relationships

* Is loaded and saved through config adapters, not by domain or usecases reading TOML directly.
* Provides settings to usecases; pure domain services should receive narrower config where possible.
* Owns PathPolicyConfig and other settings defined by the config contract.

## Agent Notes

* Do not store editable settings in SQLite; read [contracts/config.md#Responsibilities](../../contracts/config.md#responsibilities) and [storage.md#TOML Responsibility](../../storage.md#toml-responsibility).
