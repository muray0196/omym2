---
name: update-docs
description: Edit anything under docs/ safely. Use for adding, changing, moving, or deleting docs, keeping docs frontmatter and index files consistent, and deciding where a rule's authoritative home is.
---

# Update Docs

`docs/` is a structured documentation bundle. Conformance is enforced by `tests/docs/test_docs_bundle.py`; a wrong edit fails CI.

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
2. `index.md` files carry no frontmatter (only the root `docs/index.md` may have `docs_bundle_version`).
3. Every directory's `index.md` lists each sibling doc as:
   `* [Title](file.md) - description`
   where the description **exactly matches** that file's frontmatter `description`.
4. Every relative link must resolve to an existing file/directory, and anchors must exist in the target.

## Procedure for any docs edit

1. Identify the authoritative home of the rule you are changing. One rule lives in exactly one doc; other docs may only summarize briefly and link. `AGENTS.md` and `ARCHITECTURE.md` name the authoritative homes.
2. Make the edit in the authoritative home. If another doc repeats the rule, replace the repeat with a pointer.
3. In every edited doc: refresh `timestamp` to now; update `description` if the doc's scope changed.
4. If `description` changed, update the matching line in that directory's `index.md`.
5. If you added, deleted, moved, or renamed a doc: update its directory `index.md`, plus every router that links to it (`AGENTS.md`, `ARCHITECTURE.md`, other docs, `.agents/skills/*/SKILL.md`).
6. Verify: `scripts/checks.sh docs` — must pass before you finish.

Optional: draft a `description` and `tags` with the local LLM:
`uv run python scripts/ask_local_llm.py doc-description --files docs/<file>.md` (see `delegate-local-llm`). Verify the draft yourself before using it.

## Content rules

- Docs are for agents: state rules as testable statements, not narrative.
- No progress notes, backlogs, TODO lists, or assignment state in `docs/`.
- Keep docs-only tasks docs-only; do not drift into code changes.
- When code behavior changes, the doc describing it must change in the same task — check `docs/execution/`, `docs/contracts/`, and `docs/codebase/` for affected files.

## Stop and report when

- Two docs claim authority over the same rule (name both; propose one home).
- A requested edit contradicts `ARCHITECTURE.md` or a contract doc.
