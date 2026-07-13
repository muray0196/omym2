/**
 * Summary: Snapshots the isolated E2E Library tree for observable file assertions.
 * Why: Verifies passive routes and explicit execution effects against real files.
 */
import { readFile, readdir, stat } from "node:fs/promises";
import { join, relative } from "node:path";

export async function snapshotIsolatedLibrary() {
  const applicationRoot = process.env.OMYM2_E2E_APPLICATION_ROOT;
  if (applicationRoot === undefined || applicationRoot.length === 0) {
    throw new Error(
      "OMYM2_E2E_APPLICATION_ROOT must identify the isolated test application root.",
    );
  }
  const libraryRoot = join(applicationRoot, "library");
  const paths = await listTree(libraryRoot);
  return Promise.all(
    paths.map(async (path) => {
      const metadata = await stat(path, { bigint: true });
      const common = {
        modifiedNanoseconds: metadata.mtimeNs.toString(),
        path: relative(libraryRoot, path),
      };
      if (metadata.isDirectory()) {
        return { ...common, kind: "directory" as const };
      }
      return {
        ...common,
        bytes: (await readFile(path)).toString("base64"),
        kind: "file" as const,
      };
    }),
  );
}

async function listTree(root: string): Promise<string[]> {
  const paths: string[] = [];
  const pending = [root];
  while (pending.length > 0) {
    const directory = pending.pop();
    if (directory === undefined) continue;
    const entries = await readdir(directory, { withFileTypes: true });
    for (const entry of entries) {
      const path = join(directory, entry.name);
      paths.push(path);
      if (entry.isDirectory()) pending.push(path);
    }
  }
  return paths.toSorted();
}
