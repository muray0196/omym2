/*
Summary: Copies the Next static export into the Python package.
Why: Lets `omym2 settings` serve the current web app without a Node server.
*/

import { cp, mkdir, rm } from "node:fs/promises"
import path from "node:path"
import { fileURLToPath } from "node:url"

const scriptPath = fileURLToPath(import.meta.url)
const webRoot = path.resolve(path.dirname(scriptPath), "..")
const repoRoot = path.resolve(webRoot, "..")
const exportDir = path.join(webRoot, "out")
const packageStaticDir = path.join(repoRoot, "src", "omym2", "adapters", "web", "static_dist")

await rm(packageStaticDir, { force: true, recursive: true })
await mkdir(path.dirname(packageStaticDir), { recursive: true })
await cp(exportDir, packageStaticDir, { recursive: true })
