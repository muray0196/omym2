/*
Summary: Audits generated static Web UI assets before packaging.
Why: Prevents secrets, source maps, and third-party analytics from entering the Python package.
*/

import { readdir, readFile, stat } from "node:fs/promises"
import path from "node:path"
import process from "node:process"
import { error as logError } from "node:console"
import { fileURLToPath, pathToFileURL } from "node:url"

const scriptPath = fileURLToPath(import.meta.url)
const webRoot = path.resolve(path.dirname(scriptPath), "..")
const defaultExportDirectory = path.join(webRoot, "out")

const textFileExtensions = new Set([
  ".css",
  ".html",
  ".js",
  ".json",
  ".svg",
  ".txt",
  ".webmanifest",
  ".xml",
])

const disallowedFileRules = [
  { pattern: /\.map$/iu, reason: "source maps expose source code" },
  { pattern: /(^|\/)\.env(?:\..*)?$/iu, reason: "environment files can contain local secrets" },
  {
    pattern: /\.(?:crt|db|key|log|p12|pem|sqlite|sqlite3)$/iu,
    reason: "runtime, credential, or log file",
  },
  { pattern: /(^|\/)required-server-files\.json$/iu, reason: "Next server manifest" },
  { pattern: /(^|\/)server-reference-manifest/iu, reason: "Next server manifest" },
  { pattern: /(^|\/)middleware-manifest/iu, reason: "Next server manifest" },
  { pattern: /(^|\/)trace(?:\.json)?$/iu, reason: "build trace output" },
]

const disallowedContentRules = [
  { pattern: /BEGIN [A-Z ]*PRIVATE KEY/iu, reason: "private key material" },
  { pattern: /\bAKIA[0-9A-Z]{16}\b/u, reason: "AWS access key id" },
  { pattern: /\bgh[pousr]_[A-Za-z0-9_]{36,}\b/u, reason: "GitHub token" },
  { pattern: /\bsk-[A-Za-z0-9]{20,}\b/u, reason: "API key token" },
  { pattern: /@vercel\/analytics/iu, reason: "third-party analytics package" },
  { pattern: /\/_vercel\/insights/iu, reason: "third-party analytics endpoint" },
  { pattern: /va\.vercel-scripts\.com/iu, reason: "third-party analytics script host" },
]

export async function auditStaticExport(exportDirectory = defaultExportDirectory) {
  const rootDirectory = path.resolve(exportDirectory)
  const rootStats = await stat(rootDirectory)
  if (!rootStats.isDirectory()) {
    throw new Error(`Static export audit expected a directory: ${rootDirectory}`)
  }

  const findings = []
  await collectFindings(rootDirectory, rootDirectory, findings)
  if (findings.length > 0) {
    throw new Error(
      ["Static export audit failed:", ...findings.map((finding) => `- ${finding}`)].join("\n"),
    )
  }
}

async function collectFindings(rootDirectory, currentDirectory, findings) {
  const entries = await readdir(currentDirectory, { withFileTypes: true })
  for (const entry of entries) {
    const absolutePath = path.join(currentDirectory, entry.name)
    const relativePath = normalizeRelativePath(rootDirectory, absolutePath)
    if (entry.isSymbolicLink()) {
      findings.push(`${relativePath}: symbolic links are not allowed in packaged static assets`)
      continue
    }
    if (entry.isDirectory()) {
      await collectFindings(rootDirectory, absolutePath, findings)
      continue
    }
    if (entry.isFile()) {
      await auditFile(absolutePath, relativePath, findings)
    }
  }
}

async function auditFile(absolutePath, relativePath, findings) {
  for (const rule of disallowedFileRules) {
    if (rule.pattern.test(relativePath)) {
      findings.push(`${relativePath}: ${rule.reason}`)
    }
  }

  if (!textFileExtensions.has(path.extname(relativePath).toLowerCase())) {
    return
  }

  const content = await readFile(absolutePath, "utf8")
  for (const rule of disallowedContentRules) {
    if (rule.pattern.test(content)) {
      findings.push(`${relativePath}: ${rule.reason}`)
    }
  }
}

function normalizeRelativePath(rootDirectory, absolutePath) {
  return path.relative(rootDirectory, absolutePath).split(path.sep).join("/")
}

const isRunningAsCli = process.argv[1]
  ? import.meta.url === pathToFileURL(process.argv[1]).href
  : false

if (isRunningAsCli) {
  const exportDirectory = process.argv[2] ?? defaultExportDirectory
  try {
    await auditStaticExport(exportDirectory)
  } catch (error) {
    logError(error instanceof Error ? error.message : String(error))
    process.exitCode = 1
  }
}
