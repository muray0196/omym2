---
type: OMYM2 Knowledge Card
title: Refresh
description: Re-evaluation workflow after external tag correction.
resource: "../../execution/refresh.md#refresh-behavior"
tags: [execution, refresh, track, path-policy]
authoritative: false
---

# Refresh

Authoritative source: [docs/execution/refresh.md#Refresh Behavior](../../execution/refresh.md#refresh-behavior).

## Relationships

* Reloads metadata, recalculates canonical path, and creates a relocation Plan when needed.
* Preserves stable `track_id` across metadata and canonical path changes.
* Uses apply only when the user requests the created Plan to be applied.

## Agent Notes

* Treat refresh as re-evaluation and planning; do not make it a direct file mover.
