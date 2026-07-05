---
name: update-docs
description: Edit anything under docs/ safely. Use for adding, changing, moving, or deleting docs, keeping OKF frontmatter and index files consistent, and deciding where a rule's authoritative home is.
---

# Update Docs

`docs/` is an OKF v0.1 knowledge bundle. Conformance is enforced by `tests/docs/test_okf_bundle.py`; a wrong edit fails CI.

## Hard format rules

1. Every `docs/**/*.md` except `index.md` must start with this frontmatter:

   ```markdown
   ---
   type: <doc category, e.g. Codebase Reference>
   title: <Title>
   description: <one-line summary of what the doc specifies>
   tags: [kebab-topic, another-topic]
   timestamp: 2026-07-04T12:00:00+09:00
   ---
   ```

   All five fields required; `tags` non-empty; `timestamp` ISO 8601.
2. `index.md` files carry no frontmatter (only the root `docs/index.md` may have `okf_version`).
3. Every directory's `index.md` lists each sibling doc as:
   `* [Title](file.md) - description`
   where the description **exactly matches** that file's frontmatter `description`.
4. Every relative link must resolve to an existing file/directory, and anchors must exist in the target.

## Procedure for any docs edit

1. Identify the authoritative home of the rule you are changing. One rule lives in exactly one doc; other docs may only summarize briefly and link. `AGENTS.md` and `ARCHITECTURE.md` name the authoritative homes.
2. Make the edit in the authoritative home. If another doc repeats the rule, replace the repeat with a pointer.
3. In every edited doc: refresh `timestamp` to now; update `description` if the doc's scope changed.
4. If `description` changed, update the matching line in that directory's `index.md`.
5. If you added, deleted, moved, or renamed a doc: ensure it has complete OKF frontmatter. Do not hand-edit per-doc router tables; `scripts/route_docs.py` discovers concept docs from frontmatter and content. Update `AGENTS.md`, `ARCHITECTURE.md`, other docs, or `.agents/skills/*/SKILL.md` only when their top-level routing policy or explicit links change.
6. Regenerate directory indexes after docs changes:
   `uv run python scripts/generate_docs_indexes.py --write`
7. Verify: `scripts/checks.sh docs` — must pass before you finish.

Draft `description` and `tags` directly from the edited doc content. Do not use a local-LLM helper for docs metadata; `scripts/ask_local_llm.py` has been removed.

## Content rules

- Docs are for agents: state rules as testable statements, not narrative.
- No progress notes, backlogs, TODO lists, or assignment state in `docs/`.
- Keep docs-only tasks docs-only; do not drift into code changes.
- When code behavior changes, the doc describing it must change in the same task — check `docs/execution/`, `docs/contracts/`, and `docs/codebase/` for affected files.

## Stop and report when

- Two docs claim authority over the same rule (name both; propose one home).
- A requested edit contradicts `ARCHITECTURE.md` or a contract doc.
