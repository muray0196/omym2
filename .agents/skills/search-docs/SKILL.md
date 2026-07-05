---
name: search-docs
description: Search, navigate, and cite OMYM2 OKF docs efficiently. Use before broad docs reading, when looking for authoritative docs sections, or when an answer needs docs citations.
---

# Search Docs

Use this skill to find the smallest authoritative docs section before reading whole files.

## Fast Path

1. Route the task to docs when you need a reading list:

   ```bash
   uv run python scripts/route_docs.py route "<task or docs question>"
   ```

   The router builds its catalog from `docs/**/*.md` OKF frontmatter and content at
   query time. It always includes `ARCHITECTURE.md` as required context and returns
   repo-relative paths.
2. Search specific terms when you need citation targets inside docs:

   ```bash
   uv run python scripts/search_docs.py "<query>"
   ```

   The script parses `docs/` frontmatter, headings, and section bodies at query
   time; there is no index artifact and results are never stale. Use `--json`
   when another tool or prompt will consume the result.
3. Open the top matching section by `path:line`. Prefer hits whose `match=` includes `section`, `tags`, `title`, or `description` over body-only hits.
4. Follow only the local links that the opened section names as relevant.
5. Cite claims with `docs/path.md:line` or `docs/path.md#anchor`.

## Query Hints

- Search domain terms directly: `PlanAction`, `FileEvent`, `PathPolicy`, `library_root_at_plan`.
- Use `--type Contract`, `--type "Execution Spec"`, or `--type "Codebase Reference"` when the task already names the kind of rule.
- If the script is unavailable, fall back to `rg -n "<query>" docs`.

## Vague Requests

When you cannot name the domain terms yet (vague or Japanese information need), delegate section
selection to the local LLM:

```bash
uv run python scripts/ask_local_llm.py docs-search --ask "<what you need, any language>"
```

It returns an advisory reading list (`readings` with `path`, `line`, `anchor`, `section`, `why`),
pre-validated against the parsed docs — hallucinated paths and anchors are dropped by the script.
Open each hit and cite the Markdown itself. If `readings` is empty, run the Fast Path with the
returned `suggested_queries`. If the local LLM endpoint is unreachable, fall back to the Fast Path
or `rg` — never block on the concierge.

## Boundaries

- The Markdown docs are the only authority; the script output is navigation, not a source.
- Cite the Markdown section, never the script output itself.
- Do not hand-maintain docs router tables; `route_docs.py` discovers concept docs from OKF frontmatter.
- For docs edits, also use `update-docs`; this skill is for finding and citing docs, not changing them.
