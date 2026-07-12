/**
 * Summary: Exports deterministic OpenAPI JSON and regenerates the TypeScript client.
 * Why: Makes the schema-only Python app the sole frontend API type source.
 */
import { dirname, resolve } from "node:path";
import { fileURLToPath } from "node:url";
import { spawnSync } from "node:child_process";

const webRoot = resolve(dirname(fileURLToPath(import.meta.url)), "..");
const repositoryRoot = resolve(webRoot, "..");
run(
  "uv",
  [
    "run",
    "python",
    "scripts/export_web_openapi.py",
    "--output",
    "web-v2/openapi.json",
  ],
  repositoryRoot,
);
run("npm", ["exec", "--", "openapi-ts"], webRoot);

function run(command, args, cwd) {
  const result = spawnSync(command, args, {
    cwd,
    encoding: "utf8",
    stdio: "inherit",
  });
  if (result.error) {
    throw result.error;
  }
  if (result.status !== 0) {
    throw new Error(`${command} exited with status ${String(result.status)}`);
  }
}
