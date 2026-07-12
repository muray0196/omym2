/**
 * Summary: Generates API artifacts in isolation and byte-compares committed output.
 * Why: Detects drift without mutating or judging legitimate working-tree changes.
 */
import { spawnSync } from "node:child_process";
import { mkdtempSync, readFileSync, readdirSync, rmSync } from "node:fs";
import { tmpdir } from "node:os";
import { dirname, join, relative, resolve } from "node:path";
import { fileURLToPath } from "node:url";

import { createClient } from "@hey-api/openapi-ts";

import pendingOpenApiConfig from "../openapi-ts.config.ts";

const webRoot = resolve(dirname(fileURLToPath(import.meta.url)), "..");
const repositoryRoot = resolve(webRoot, "..");
const temporaryRoot = mkdtempSync(join(tmpdir(), "omym2-api-drift-"));
const temporarySpec = join(temporaryRoot, "openapi.json");
const temporaryClient = join(temporaryRoot, "generated");
const openApiConfig = await pendingOpenApiConfig;

try {
  run(
    "uv",
    [
      "run",
      "python",
      "scripts/export_web_openapi.py",
      "--output",
      temporarySpec,
    ],
    repositoryRoot,
  );
  await generateClient(temporarySpec, temporaryClient);

  compareFile(resolve(webRoot, "openapi.json"), temporarySpec, "openapi.json");
  compareDirectories(resolve(webRoot, "src/api/generated"), temporaryClient);
} finally {
  rmSync(temporaryRoot, { force: true, recursive: true });
}

function compareDirectories(committedRoot, generatedRoot) {
  const committedFiles = listFiles(committedRoot);
  const generatedFiles = listFiles(generatedRoot);
  if (JSON.stringify(committedFiles) !== JSON.stringify(generatedFiles)) {
    throw new Error(
      `Generated API file set drifted.\nCommitted: ${committedFiles.join(", ")}\nGenerated: ${generatedFiles.join(", ")}`,
    );
  }
  for (const path of committedFiles) {
    compareFile(
      join(committedRoot, path),
      join(generatedRoot, path),
      `src/api/generated/${path}`,
    );
  }
}

async function generateClient(input, outputPath) {
  if (typeof openApiConfig.output === "string") {
    throw new TypeError("OpenAPI output must retain its deterministic header.");
  }
  await createClient({
    ...openApiConfig,
    input,
    logs: {
      file: false,
      level: "silent",
    },
    output: {
      ...openApiConfig.output,
      path: outputPath,
    },
  });
}

function compareFile(committedPath, generatedPath, label) {
  if (!readFileSync(committedPath).equals(readFileSync(generatedPath))) {
    throw new Error(`${label} differs from freshly generated output.`);
  }
}

function listFiles(root) {
  const files = [];
  const pending = [root];
  while (pending.length > 0) {
    const directory = pending.pop();
    if (directory === undefined) {
      continue;
    }
    for (const entry of readdirSync(directory, { withFileTypes: true })) {
      const path = join(directory, entry.name);
      if (entry.isDirectory()) {
        pending.push(path);
      } else if (entry.isFile()) {
        files.push(relative(root, path));
      }
    }
  }
  return files.sort();
}

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
