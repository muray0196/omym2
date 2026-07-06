---
name: react-native-skills
description: React Native and Expo best practices for performant mobile apps. Use when building or reviewing React Native components, Expo apps, list and scroll performance, Reanimated animations, native navigation, native modules, images, safe areas, styling, or mobile UI state.
---

# React Native Skills

Use the local rule references to apply React Native and Expo performance and UI guidance without loading the whole corpus by default. The imported rules are Vercel Engineering material under MIT license metadata from the source package.

## Workflow

1. Classify the task by mobile surface: rendering, lists, animation, scroll, navigation, state, compiler compatibility, UI, design system, monorepo setup, imports, JavaScript hot paths, or fonts.
2. Read `references/rules/_sections.md` for category ordering when the relevant surface is unclear.
3. Search rule titles and filenames before opening detailed rules:

   ```bash
   rg -n "<keyword|component|API>" .agents/skills/react-native-skills/references/rules
   ```

4. Read only the rule files that match the current task. Prefer crash, list-performance, animation, and navigation rules before lower-impact cleanup.
5. Apply the smallest code change that satisfies the relevant rule and the local codebase conventions.
6. When reviewing, report concrete findings with file and line references; skip rules that do not apply.

## Rule Map

| Surface | First reference files |
| --- | --- |
| Runtime rendering safety | `references/rules/rendering-*.md` |
| List and scroll performance | `references/rules/list-performance-*.md`, `references/rules/scroll-*.md` |
| Reanimated and gestures | `references/rules/animation-*.md` |
| Native navigation | `references/rules/navigation-*.md` |
| State and React Compiler | `references/rules/react-state-*.md`, `references/rules/state-*.md`, `references/rules/react-compiler-*.md` |
| UI components, images, safe areas, styling | `references/rules/ui-*.md` |
| Design-system structure | `references/rules/design-system-*.md` |
| Monorepo and dependency boundaries | `references/rules/monorepo-*.md`, `references/rules/imports-*.md` |
| JavaScript and font setup | `references/rules/js-*.md`, `references/rules/fonts-*.md` |

## Reading Guidance

- Do not load all rule files for ordinary tasks.
- Use `rg --files .agents/skills/react-native-skills/references/rules` to list available rule files.
- Treat rule examples as patterns to adapt, not as required dependencies when the local project has different libraries or platform constraints.
