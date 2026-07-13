---
name: update-docs
description: Edit anything under docs/ safely. Use for adding, changing, moving, or deleting docs, keeping docs frontmatter and index files consistent, and deciding where a rule's authoritative home is.
---

# Update Docs

`docs/` is generated and validated as a structured bundle. `AGENTS.md` owns the top-level routing rules.

## Rules

- Every non-index Markdown file under `docs/` has `type`, `title`, `description`, non-empty `tags`, and a current ISO 8601 `timestamp`; copy the structure of a neighboring doc.
- Never edit `docs/**/index.md` by hand. Regenerate all indexes with `uv run python scripts/generate_docs_indexes.py --write`.
- Keep one authoritative home for each rule; replace repetitions elsewhere with a short link.
- No progress notes, backlogs, TODO lists, or assignment state in `docs/`.
- Keep docs-only tasks docs-only.

## Procedure

1. Use the router in `AGENTS.md` to find the authoritative doc, then edit only the required docs.
2. Refresh each edited doc's `timestamp`; change its `description` only when its scope changes.
3. For moved, renamed, or deleted docs, use `rg -n "<old path or filename>" AGENTS.md ARCHITECTURE.md docs .agents/skills` to find affected routers and links.
4. Regenerate indexes with `uv run python scripts/generate_docs_indexes.py --write`.
5. Run the docs check selected by `validate`.

## Done means

- Generated indexes are current and the docs check selected by `validate` passes.

## Stop and report when

- Two docs claim authority over the same rule (name both; propose one home).
- A requested edit contradicts `ARCHITECTURE.md` or a contract doc.
