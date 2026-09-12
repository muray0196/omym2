---
name: architecture-boundaries
description: Check production module placement and imports between OMYM2 layers. Use for structural changes and architecture reviews; skip standalone scripts, docs, and test-only file additions.
---

# Architecture Boundaries

Authoritative sources: [docs/codebase/dependency-boundaries.md](../../../docs/codebase/dependency-boundaries.md), [docs/codebase/source-layout.md](../../../docs/codebase/source-layout.md), [docs/codebase/naming.md](../../../docs/codebase/naming.md). This skill is the fast decision path.

## Import decision table

Row = the file you are editing; column = what it wants to import.

| From \ imports | shared | domain | features | adapters | platform |
| --- | --- | --- | --- | --- | --- |
| `shared/` | yes | NO | NO | NO | NO |
| `domain/` | yes | yes | NO | NO | NO |
| `features/` | yes | yes | own feature + `common_ports` only | NO | NO |
| `adapters/` | yes | yes | ports, dto, usecases | own subpackage | NO |
| `platform/` | yes | yes | yes | yes | yes |

Domain no-I/O, cross-feature import, and CLI/Web direct-filesystem rules are
the Non-Negotiable Rules in `ARCHITECTURE.md`, detailed in
[docs/codebase/dependency-boundaries.md](../../../docs/codebase/dependency-boundaries.md).

Additional hard rules not on the table above:

- Outbound adapters (`db`, `fs`, `metadata`, `config`) implement ports from `src/omym2/features/*/ports.py` or `src/omym2/features/common_ports.py`.
- Inbound adapters (`adapters/cli/`, `adapters/web/`) must not import concrete
  outbound adapter subpackages (`adapters.db`, `adapters.fs`,
  `adapters.metadata`, `adapters.config`, `adapters.artist_ids`), and
  `adapters/cli/` must not import `adapters.web`. The architecture test's
  exact-pair allowlist contains only the pure, I/O-free CLI TOML helper import
  (`adapters/cli/commands/config.py` →
  `omym2.adapters.config.toml_config_store`). Web schemas have no outbound-
  adapter exception; do not add a pair without updating that allowlist and
  this rule.
- Durable Operation worker dispatch and feature chaining belong in `platform/`.
  `domain/` owns the pure Operation model, the DB adapter persists it, and the
  application-root lock adapter belongs with filesystem adapters. Web/CLI must
  not import either concrete adapter.

## Business rule placement

Adapters must not decide business rules (conflicts/duplicates, canonical
paths, metadata validity, PlanAction/Run/FileEvent status); authoritative in
`ARCHITECTURE.md`'s Non-Negotiable Rules and the Business Rule Placement
section of [docs/codebase/dependency-boundaries.md](../../../docs/codebase/dependency-boundaries.md).

## New file checklist

- [ ] Placement matches [docs/codebase/source-layout.md](../../../docs/codebase/source-layout.md).
- [ ] `domain/` names are nouns; usecase names are `{verb}_{object}.py`.

## Procedure

1. Consult the import decision table above for the layer you are editing and the layer you want to import.
2. For adapter code, check against Business rule placement above; move any domain-meaning decision into a domain service or usecase.
3. Work through the New file checklist before adding a production module.
4. Use `validate` to select checks. Run `arch` for a focused boundary check when
   needed; the Python completion gate already includes architecture tests.

## Done means

Architecture tests pass, either through the focused `arch` mode or the Python
completion gate. They enforce the highest-risk rules; review the tables above
as well, since tests do not prove every placement decision correct.

## Stop and report when

- The requested change only works by crossing a NO cell above.
- A new top-level package under `src/omym2/` would change the documented layers
  without authorization for that architectural change.
