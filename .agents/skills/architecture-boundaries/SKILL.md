---
name: architecture-boundaries
description: Decide whether a new module, package, or import between layers is allowed in OMYM2. Use before adding files or imports, and when reviewing structural changes for dependency direction and naming.
---

# Architecture Boundaries

Authoritative sources: `docs/codebase/dependency-boundaries.md`, `docs/codebase/source-layout.md`, `docs/codebase/naming.md`. This skill is the fast decision path.

## Import decision table

Row = the file you are editing; column = what it wants to import.

| From \ imports | shared | domain | features | adapters | platform |
| --- | --- | --- | --- | --- | --- |
| `shared/` | yes | NO | NO | NO | NO |
| `domain/` | yes | yes | NO | NO | NO |
| `features/` | yes | yes | own feature + `common_ports` only | NO | NO |
| `adapters/` | yes | yes | ports, dto, usecases | own subpackage | NO |
| `platform/` | yes | yes | yes | yes | yes |

Additional hard rules:

- `domain/` performs no I/O: no sqlite3, no file reads/writes, no HTTP, no TOML, no mutagen, no FastAPI/Typer imports.
- A feature never imports another feature's internals. Chaining usecases (e.g. `add --apply`) happens in CLI, Web, or platform.
- CLI commands and Web routes never touch the filesystem directly; they translate input, call usecases, format output.
- Outbound adapters (`db`, `fs`, `metadata`, `config`) implement ports from `src/omym2/features/*/ports.py` or `src/omym2/features/common_ports.py`.
- Inbound adapters (`adapters/cli/`, `adapters/web/`) must not import concrete outbound adapter subpackages (`adapters.db`, `adapters.fs`, `adapters.metadata`, `adapters.config`, `adapters.artist_ids`), and `adapters/cli/` must not import `adapters.web`. This is enforced by an architecture test with an exact-pair allowlist for exactly two pure, I/O-free functions coupled only to the TOML config representation (`adapters/cli/commands/config.py` → `omym2.adapters.config.toml_config_store`, `adapters/web/schemas/settings_json.py` → `omym2.adapters.config.config_validator`); do not add new pairs without updating that allowlist and this rule.
- `platform/` is the composition root: it builds concrete adapters, wires them into each feature's `*Ports` dataclass, and assembles the CLI/Web entry points. New wiring/chaining code belongs there, not inside `adapters/cli/` or `adapters/web/`.

## Business rule placement

Adapters persist, restore, read, write, scan, move, render, parse. Adapters must NOT decide:

- conflicts or duplicates
- canonical / target paths
- metadata validity
- PlanAction / Run / FileEvent status

If an adapter needs an `if` that encodes domain meaning, that decision belongs in a domain service or usecase; the adapter returns raw facts.

## New file checklist

- [ ] Placement matches the table in `implement-change` (or `docs/codebase/source-layout.md`).
- [ ] Module name is `snake_case.py` and concrete. Banned names: `utils.py`, `helpers.py`, `manager.py`, `service.py`, `common.py`; no `_service.py` or `_dao.py` suffixes.
- [ ] No `src/omym2/features/<feature>/domain/` or `src/omym2/features/<feature>/adapters/` directories.
- [ ] `domain/` names are nouns; usecase names are `{verb}_{object}.py`.

## Procedure

1. Consult the import decision table above for the layer you are editing and the layer you want to import.
2. Check business rule placement above: if an adapter would need an `if` that encodes domain meaning, move that decision into a domain service or usecase instead.
3. Work through the new file checklist above before adding any file.
4. Verify: run the check mode `validate` selects for architecture boundary / naming rules.

## Done means

The check mode `validate` selects for architecture boundary / naming rules passes. Architecture tests in `tests/architecture/` enforce the highest-risk rules; passing them is necessary but not sufficient — the tables above still apply.

## Stop and report when

- The requested change only works by crossing a NO cell above.
- You are about to add a new top-level package under `src/omym2/` (needs explicit human approval).
