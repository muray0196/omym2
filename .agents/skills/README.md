# Skill Format Conventions

How every `SKILL.md` under `.agents/skills/` is written. Follow this when adding or editing a skill.

## Frontmatter

- Exactly two fields: `name` and `description`. No others.
- `description` is third-person and self-contained: it states what the skill does, plus every when-to-use and when-not-to-use trigger. The body never repeats these triggers.

## Body

- Under 100 lines.
- Section order:
  1. Skill-specific domain sections (invariant lists, decision tables, placement rules) — keep whatever headings fit the domain.
  2. `## Procedure` — numbered top-level steps.
  3. `## Done means` — mandatory, last-but-one section.
  4. `## Stop and report when` — mandatory, always the final section.
- Prefer tables for decision mappings (row/column lookups) and bullets over prose walls. Reserve prose for a sentence or two of framing.
- No code examples unless they are runnable commands or copy-paste templates (e.g. a shell command, a file template). Do not include illustrative snippets.

## Rule ownership

- One rule lives in exactly one skill. If another skill needs it, link to the owner (`` `owning-skill` ``) instead of repeating the rule.
- When two skills' procedures can both apply to the same change, state in each which one runs first and how the other's rules layer on top.

## Paths

- Every repo path is written repo-root-relative (e.g. `src/omym2/adapters/db/sqlite/migration_runner.py`, not `adapters/db/sqlite/migration_runner.py`).
- Verify a path exists before writing it into a skill.
