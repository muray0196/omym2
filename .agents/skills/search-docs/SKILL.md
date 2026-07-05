---
name: search-docs
description: Search, navigate, and cite OMYM2 OKF docs efficiently. Use before broad docs reading, when looking for authoritative docs sections, or when an answer needs docs citations.
---

# Search Docs

Use this skill to find the smallest authoritative docs section before reading whole files.

## Fast Path

1. Search the docs:

   ```bash
   uv run python scripts/search_docs.py "<query>"
   ```

   The script parses `docs/` frontmatter, headings, and section bodies at query
   time; there is no index artifact and results are never stale. Use `--json`
   when another tool or prompt will consume the result.
2. Open the top matching section by `path:line`. Prefer hits whose `match=` includes `section`, `tags`, `title`, or `description` over body-only hits.
3. Follow only the local links that the opened section names as relevant.
4. Cite claims with `docs/path.md:line` or `docs/path.md#anchor`.

## Query Hints

- Search domain terms directly: `PlanAction`, `FileEvent`, `PathPolicy`, `library_root_at_plan`.
- Use `--type Contract`, `--type "Execution Spec"`, or `--type "Codebase Reference"` when the task already names the kind of rule.
- If the script is unavailable, fall back to `rg -n "<query>" docs`.

## Boundaries

- The Markdown docs are the only authority; the script output is navigation, not a source.
- Cite the Markdown section, never the script output itself.
- For docs edits, also use `update-docs`; this skill is for finding and citing docs, not changing them.
