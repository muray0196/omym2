/*
Summary: Configures lint checks for the Next Web UI.
Why: Keeps npm-based frontend validation runnable after adopting the current web app.
*/

import js from "@eslint/js"
import eslintConfigPrettier from "eslint-config-prettier"
import tseslint from "typescript-eslint"

export default tseslint.config(
  {
    ignores: [".next/**", "node_modules/**", "out/**", "tsconfig.tsbuildinfo"],
  },
  js.configs.recommended,
  ...tseslint.configs.recommended,
  {
    files: ["**/*.{ts,tsx}"],
    rules: {
      // Filesystem sanitizer regexes need explicit control-character ranges.
      "no-control-regex": "off",
      "no-undef": "off",
    },
  },
  eslintConfigPrettier,
)
