---
type: Execution Spec
title: Organize Execution
description: Organize registration and reconciliation for audio and companions, clean DB-only registration, and trust-stat rules.
tags: [organize, library-registration, plan-creation, artist-names, companions, path-policy]
timestamp: 2026-07-18T12:00:00+09:00
---

# Organize Execution

Authoritative for `organize --library PATH`: first registration, existing-Library rescan, companion registration/planning, unregistered-path refusal, clean registration without a mutation Plan, and registration after successful Apply. Common rules: [model.md](model.md); path identity: [../contracts/path-identity-storage.md](../contracts/path-identity-storage.md).

## Library Registration Behavior

Library identity: [../DOMAIN.md](../DOMAIN.md#library). Registration is per Library, tied to `library_id` and `path_policy_hash` (or equivalent PathPolicy identity) — not defined by whether `tracks` has rows. Representative fields: `library_id`, `root_path`, `path_policy_hash`, `registered_at`, `status` ([allowed values](../contracts/status-reason-catalog.md#library-status)).

Changing PathPolicy invalidates prior registration; `add` then refuses to create a plan until the Library is re-registered via `omym2 organize --library PATH`. `organize` is the only supported path for an unregistered or unorganized Library to become usable by `add`, and `organize --library PATH` is the primary registration/reconciliation operation. Relink rules: [../contracts/path-identity-storage.md](../contracts/path-identity-storage.md#identity-rules).

## Organize Behavior

`organize --library PATH` scans the Library read-only and computes canonical paths under the current PathPolicy. For every otherwise valid snapshot, it batches raw artist and album-artist values through the shared `ArtistNameResolutionReader` before canonical path generation, letting it reconcile paths after a mapping change without rewriting stored Track metadata. Library selection and Track reads finish before resolver work; result persistence begins only after resolver work completes. When a resolved candidate becomes a PlanAction, Organize records its aligned resolution diagnostics on that action; already-correct files create no action or standalone diagnostic row, and candidates blocked before resolution record no pair.

The scan always covers the whole Library and only plans misplaced (current path differs from canonical target) or blocked files; correctly placed files never become actions.

MVP identity cases:

| Case | Policy |
| --- | --- |
| `PATH` matches an existing `libraries.root_path` | Rescan and organize the existing Library. |
| No Library exists yet | Create the first Library row and organize it. |
| `PATH` is unregistered while another Library exists | Stop with a clear message (moved Library vs. second Library is out of MVP scope). |

The MVP must not silently duplicate a Library when an unregistered path may represent an existing one. Plain `omym2 organize` is allowed only when exactly one known Library can be selected unambiguously; otherwise it fails and asks for `--library PATH`.

If files must move or blocking actions need review, `organize` creates an organize Plan; it never moves files directly except through `--apply` orchestration. If no moves and no blocking issues exist, it registers the Library without a mutation Plan (DB-only Library/Track/CompanionAsset updates are not file mutations). If the organize Plan applies successfully and no blocking Library-state issues remain, the Library becomes registered (DB-only, no FileEvent). If blocked actions remain, the Library must not become registered.

Blocking issues: missing required metadata; canonical path conflicts; companion association, ownership, observation, or target conflicts; invalid paths; missing source files; other problems preventing safe acceptance.

## Companion Reconciliation

When `companions.enabled` is true, Organize classifies the Library inventory with the shared [Companion Association](../DOMAIN.md#companion-association) policy after calculating audio targets. Companion files use rooted content-only snapshots and never enter music metadata or stat-trust processing.

An already canonical companion is persisted directly as an active CompanionAsset only after its owning Track has been established in the same transaction — DB-only registration, no PlanAction or FileEvent. A misplaced companion becomes one reviewed `move_lyrics`/`move_artwork` action after the relevant audio actions, with a stable asset ID, semantic owner, and every durable dependency. Existing matching CompanionAsset identity and `first_seen_at` are preserved. Active companion paths participate in collision judgment. A blocked companion keeps the Plan reviewable but leaves the Library `blocked`; registration requires no blocking audio or companion action remaining. With companion processing disabled, Organize creates no new companion state or actions and leaves existing managed assets unchanged.

### Failed Companion Recovery

Organize may create a companion-only recovery action when a definitive failed companion source is Library-relative, still exists safely below the current Library root, and retains valid succeeded owner-audio provenance plus an active same-Library owner Track. It reuses the recorded companion identity and owner Track without manufacturing an already-completed audio action or dependency. Pending or ambiguous outcomes remain manual-review-only and are not replanned.

## Trust-Stat Optimization

`omym2 organize --trust-stat` is an explicit CLI-only performance opt-in; the Web organize route always uses full snapshot capture.

A scanned source is eligible only when all hold: exactly one active Track in the Library has that `current_path`; the Track logical path and scanner observation path match the evaluated source; both persisted Track `size` and `mtime` are non-null; and current size and mtime exactly equal that baseline. Eligible sources may reconstruct the FileSnapshot from the scanner stat plus the Track's last verified hashes and metadata. Every null, ambiguous, path-mismatching, or changed baseline falls back to a complete snapshot (fresh stat, metadata read, content hash); full captures do not reuse the earlier scan observation when establishing the persisted baseline.

An accepted eligible source updates that same unique active Track identity; removed Tracks sharing the path stay removed. Accepted candidates persist snapshot size/mtime — backfilling null baselines only after full verification, while an eligible trusted candidate preserves its already verified baseline.

The opt-in can miss a content or metadata edit that preserves both size and mtime; omit the flag for full integrity verification. With `--apply`, apply still performs its mandatory full source-hash precondition before any Track update or mutation.
