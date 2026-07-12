/**
 * Summary: Configures deterministic generation of the committed typed API client.
 * Why: Keeps handwritten frontend code from duplicating Pydantic-owned schemas.
 */
import { defineConfig } from "@hey-api/openapi-ts";

export default defineConfig({
  input: "./openapi.json",
  output: {
    path: "./src/api/generated",
    header: [
      "/**",
      " * Summary: Auto-generates typed API client code from the committed OpenAPI contract.",
      " * Why: Keeps frontend transport types synchronized with backend Pydantic schemas.",
      " */",
    ],
  },
});
