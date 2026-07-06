---
name: react-best-practices
description: React and Next.js performance optimization guidance based on Vercel Engineering practices. Use when writing, reviewing, or refactoring React or Next.js components, pages, Server Components, API routes, data fetching, bundle loading, hydration, rendering performance, or JavaScript hot paths.
---

# React Best Practices

Use the local rule references to apply React and Next.js performance guidance without loading the whole corpus by default. The imported rules are Vercel Engineering material under MIT license metadata from the source package.

## Workflow

1. Classify the task by performance surface: async work, bundle size, server behavior, client data fetching, re-rendering, rendering, JavaScript hot paths, or advanced React patterns.
2. Read `references/rules/_sections.md` for category ordering when the relevant surface is unclear.
3. Search rule titles and filenames before opening detailed rules:

   ```bash
   rg -n "<keyword|component|API>" .agents/skills/react-best-practices/references/rules
   ```

4. Read only the rule files that match the current task. Prefer higher-impact categories when several rules apply.
5. Apply the smallest code change that satisfies the relevant rule and the local codebase conventions.
6. When reviewing, report concrete findings with file and line references; skip rules that do not apply.

## Rule Map

| Surface | First reference files |
| --- | --- |
| Waterfalls and async sequencing | `references/rules/async-*.md` |
| Bundle size and lazy loading | `references/rules/bundle-*.md` |
| Server Components, API routes, and SSR | `references/rules/server-*.md` |
| Client data fetching and browser listeners | `references/rules/client-*.md` |
| Re-render reduction | `references/rules/rerender-*.md` |
| Browser rendering and hydration | `references/rules/rendering-*.md` |
| JavaScript hot-path performance | `references/rules/js-*.md` |
| Specialized React patterns | `references/rules/advanced-*.md` |

## Reading Guidance

- Do not load all rule files for ordinary tasks.
- Use `rg --files .agents/skills/react-best-practices/references/rules` to list available rule files.
- Treat rule examples as patterns to adapt, not as required APIs when the local project already has stronger conventions.
