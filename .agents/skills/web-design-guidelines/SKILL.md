---
name: web-design-guidelines
description: Review UI code for Web Interface Guidelines compliance. Use when asked to "review my UI", "check accessibility", "audit design", "review UX", or "check my site against best practices".
---

# Web Interface Guidelines

Review UI files against the current Vercel Web Interface Guidelines.

## Workflow

1. Identify the files or glob the user wants reviewed. Ask for the target only when no file or pattern is available.
2. Fetch the current guidelines from:

   ```text
   https://raw.githubusercontent.com/vercel-labs/web-interface-guidelines/main/command.md
   ```

3. If network access is unavailable, state that the live guideline source could not be fetched before reviewing.
4. Read the target files and check every fetched rule that applies.
5. Group findings by file. Use `file:line` format and keep findings terse.
6. Mark a file as passing only when no guideline issue is found.

## Review Focus

- Prioritize accessibility, focus states, forms, animation, content handling, images, performance, navigation state, touch behavior, layout safety, theme behavior, locale handling, hydration safety, hover states, and actionable copy.
- Flag concrete anti-patterns such as missing labels, icon buttons without `aria-label`, `transition: all`, disabled zoom, blocked paste, missing image dimensions, hardcoded date or number formats, and click handlers on non-interactive elements.
- Do not rewrite the UI unless the user asks for fixes after the review.

Source: https://github.com/vercel-labs/web-interface-guidelines/blob/main/command.md
