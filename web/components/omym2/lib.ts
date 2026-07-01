import type { AppConfig, CheckIssueType, IssueSeverity, SampleMetadata } from "./types"

/** Truncate a long string in the middle, keeping head and tail visible. */
export function truncateMiddle(value: string, max = 42): string {
  if (value.length <= max) return value
  const keep = Math.floor((max - 1) / 2)
  return `${value.slice(0, keep)}…${value.slice(value.length - keep)}`
}

/** Format an ISO timestamp into a compact, locale-stable display string. */
export function formatTimestamp(iso: string | null): string {
  if (!iso) return "—"
  const d = new Date(iso)
  if (Number.isNaN(d.getTime())) return iso
  const pad = (n: number) => String(n).padStart(2, "0")
  // Use UTC getters so server and client render identical text (avoids
  // hydration mismatches caused by differing local timezones).
  return `${d.getUTCFullYear()}-${pad(d.getUTCMonth() + 1)}-${pad(d.getUTCDate())} ${pad(
    d.getUTCHours(),
  )}:${pad(d.getUTCMinutes())}`
}

/** Compute a short duration label between two timestamps. */
export function formatDuration(start: string, end: string | null): string {
  if (!end) return "running"
  const ms = new Date(end).getTime() - new Date(start).getTime()
  if (Number.isNaN(ms) || ms < 0) return "—"
  const s = Math.round(ms / 1000)
  if (s < 60) return `${s}s`
  const m = Math.floor(s / 60)
  const rem = s % 60
  return `${m}m ${rem}s`
}

export const TEMPLATE_TOKENS = [
  "{album_artist}",
  "{album}",
  "{disc}",
  "{track}",
  "{title}",
  "{artist}",
  "{year}",
] as const

const SANITIZER_REPLACEMENT = "-"
const UNSAFE_PATH_TEXT = /[^\p{Letter}\p{Number}_-]/gu
const HYPHEN_RUN = /-+/g
const ALLOWED_EXTENSION = /^[A-Za-z0-9]+$/

function utf8Length(value: string): number {
  return new TextEncoder().encode(value).length
}

function limitUtf8(value: string, maxLength: number | null): string {
  if (maxLength === null) return value
  if (maxLength <= 0) return ""

  let output = ""
  for (const char of Array.from(value)) {
    const next = output + char
    if (utf8Length(next) > maxLength) break
    output = next
  }
  return output
}

function stripReplacement(value: string): string {
  return value.replace(/^-+|-+$/g, "")
}

function sanitizeBaseText(value: string): string {
  return value
    .normalize("NFKC")
    .replaceAll("'", "")
    .replace(UNSAFE_PATH_TEXT, SANITIZER_REPLACEMENT)
    .replace(HYPHEN_RUN, SANITIZER_REPLACEMENT)
    .replace(/^-+|-+$/g, "")
}

function splitPreservedExtension(value: string, preserveExtension: boolean): [string, string] {
  if (!preserveExtension) return [value, ""]

  const dotIndex = value.lastIndexOf(".")
  if (dotIndex <= 0 || dotIndex === value.length - 1) return [value, ""]

  const extension = value.slice(dotIndex + 1)
  if (!ALLOWED_EXTENSION.test(extension)) return [value, ""]
  return [value.slice(0, dotIndex), `.${extension}`]
}

function sanitizeString(
  value: string | number | null | undefined,
  maxLength: number | null = null,
  preserveExtension = false,
): string {
  if (!value) return ""

  const [baseText, extensionSuffix] = splitPreservedExtension(String(value), preserveExtension)
  const sanitizedBase = sanitizeBaseText(baseText)
  if (extensionSuffix) {
    const limitedBase = stripReplacement(limitUtf8(sanitizedBase, maxLength))
    return `${limitedBase || "_"}${extensionSuffix}`
  }
  return stripReplacement(limitUtf8(sanitizedBase, maxLength))
}

function sanitizePathComponent(
  value: string | number | null | undefined,
  maxLength: number | null = null,
  preserveExtension = false,
): string {
  if (!value) return ""
  return sanitizeString(value, maxLength, preserveExtension) || "_"
}

function normalizeExtensionSuffix(extension: string): string | null {
  const trimmed = extension.trim().toLowerCase().replace(/^\./, "")
  if (!trimmed) return null

  const sanitized = sanitizeString(trimmed, trimmed.length)
  return sanitized ? `.${sanitized}` : null
}

function limitComponent(value: string, maxLength: number): string {
  return limitUtf8(value, maxLength)
}

function limitComponentWithSuffix(
  value: string,
  extensionSuffix: string,
  maxLength: number,
): string {
  const extensionBytes = utf8Length(extensionSuffix)
  if (maxLength <= extensionBytes) {
    return extensionBytes > maxLength ? "" : extensionSuffix
  }
  return `${limitComponent(value, maxLength - extensionBytes)}${extensionSuffix}`
}

function normalizeGeneratedPath(
  renderedStem: string,
  extensionSuffix: string,
  policy: Pick<AppConfig["path_policy"], "sanitize" | "max_filename_length">,
): string {
  const parts = renderedStem.split("/")
  if (policy.sanitize) {
    const segments = parts
      .slice(0, -1)
      .map((part) => sanitizePathComponent(part, policy.max_filename_length))
    segments.push(
      sanitizePathComponent(
        `${parts[parts.length - 1]}${extensionSuffix}`,
        policy.max_filename_length,
        true,
      ),
    )
    return segments.join("/")
  }

  const segments = parts
    .slice(0, -1)
    .map((part) => limitComponent(part, policy.max_filename_length))
  segments.push(
    limitComponentWithSuffix(parts[parts.length - 1], extensionSuffix, policy.max_filename_length),
  )
  return segments.join("/")
}

function normalizeLibraryRelativePath(path: string): string | null {
  if (!path) return null

  const parts = path.replaceAll("\\", "/").split("/")
  const normalizedParts: string[] = []
  for (const part of parts) {
    if (!part || part === ".") continue
    if (part === "..") return null
    normalizedParts.push(part)
  }
  if (path.startsWith("/") || normalizedParts.length === 0) return null
  return normalizedParts.join("/")
}

export interface PathPreviewResult {
  path: string | null
  errors: string[]
}

/**
 * Render a canonical relative path from a template + sample metadata.
 * The file extension is appended AFTER rendering; templates must not
 * include an extension. The result is relative to the Library root.
 */
export function renderPath(
  template: string,
  meta: SampleMetadata,
  policy: Pick<
    AppConfig["path_policy"],
    "unknown_artist" | "unknown_album" | "sanitize" | "max_filename_length"
  >,
): PathPreviewResult {
  const errors: string[] = []

  if (!template.trim()) {
    errors.push("Template is empty.")
    return { path: null, errors }
  }

  if (/\.[a-z0-9]{1,5}\s*$/i.test(template.trim())) {
    errors.push(
      "Template must not include a file extension. The source extension is appended automatically.",
    )
  }

  const disc = meta.disc_number?.trim() || ""
  const track = meta.track_number?.trim() || ""

  const artist = meta.artist.trim() || meta.album_artist.trim() || policy.unknown_artist
  const albumArtist = meta.album_artist.trim() || meta.artist.trim() || policy.unknown_artist
  const album = meta.album.trim() || policy.unknown_album
  const title = meta.title.trim()
  const values: Record<string, string> = {
    "{album_artist}": policy.sanitize ? sanitizePathComponent(albumArtist, 50) : albumArtist,
    "{album}": policy.sanitize ? sanitizePathComponent(album, 90) : album,
    "{artist}": policy.sanitize ? sanitizePathComponent(artist, 50) : artist,
    "{title}": meta.title.trim(),
    "{year}": meta.year.trim(),
    "{disc}": disc ? String(Number(disc)) : "_",
    "{track}": track ? String(Number(track)).padStart(2, "0") : "_",
  }

  if (!title) {
    errors.push("Missing required metadata: title.")
  } else if (policy.sanitize) {
    values["{title}"] = sanitizeString(title) || "Unknown-Title"
  }

  const unknownTokens = template.match(/\{[a-z_]+\}/g)?.filter((t) => !(t in values))
  if (unknownTokens && unknownTokens.length > 0) {
    errors.push(`Unknown template token(s): ${Array.from(new Set(unknownTokens)).join(", ")}`)
  }

  let rendered = template
  for (const [token, value] of Object.entries(values)) {
    rendered = rendered.split(token).join(value)
  }

  const extensionSuffix = normalizeExtensionSuffix(meta.extension)
  if (!extensionSuffix) {
    errors.push("File extension must not be empty.")
    return { path: null, errors }
  }

  const path = normalizeLibraryRelativePath(
    normalizeGeneratedPath(rendered, extensionSuffix, policy),
  )
  if (!path) errors.push("Rendered path must be a non-empty Library-relative path.")

  return { path: errors.length > 0 ? null : path, errors }
}

/** A tiny stable "hash" of the config object for display only. */
export function configHash(config: AppConfig): string {
  const json = JSON.stringify(config)
  let h = 0x811c9dc5
  for (let i = 0; i < json.length; i++) {
    h ^= json.charCodeAt(i)
    h = Math.imul(h, 0x01000193)
  }
  const hex = (h >>> 0).toString(16).padStart(8, "0")
  return `sha256:${hex}${hex.slice(0, 8)}`
}

export interface ValidationResult {
  valid: boolean
  errors: string[]
}

/** Validate the configuration for safe CLI use. */
export function validateConfig(config: AppConfig): ValidationResult {
  const errors: string[] = []

  if (!config.paths.library) {
    errors.push("Library path is required.")
  } else if (!config.paths.library.startsWith("/")) {
    errors.push("Library path must be an absolute filesystem path.")
  }

  if (config.paths.incoming && !config.paths.incoming.startsWith("/")) {
    errors.push("Incoming path must be an absolute filesystem path.")
  }

  if (!config.path_policy.template.trim()) {
    errors.push("Path policy template must not be empty.")
  }
  if (/\.[a-z0-9]{1,5}\s*$/i.test(config.path_policy.template.trim())) {
    errors.push("Path policy template must not include a file extension.")
  }
  if (config.path_policy.max_filename_length < 16) {
    errors.push("max_filename_length must be at least 16.")
  }
  if (!config.path_policy.unknown_artist.trim()) {
    errors.push("unknown_artist fallback must not be empty.")
  }
  if (!config.path_policy.unknown_album.trim()) {
    errors.push("unknown_album fallback must not be empty.")
  }

  return { valid: errors.length === 0, errors }
}

export interface ConfigDiffRow {
  field: string
  before: string
  after: string
}

function flatten(obj: unknown, prefix = ""): Record<string, string> {
  const out: Record<string, string> = {}
  if (obj && typeof obj === "object") {
    for (const [k, v] of Object.entries(obj as Record<string, unknown>)) {
      const key = prefix ? `${prefix}.${k}` : k
      if (v && typeof v === "object") {
        Object.assign(out, flatten(v, key))
      } else {
        out[key] = v === null ? "null" : String(v)
      }
    }
  }
  return out
}

/** Compute a field-level diff between two configs. */
export function diffConfig(before: AppConfig, after: AppConfig): ConfigDiffRow[] {
  const a = flatten(before)
  const b = flatten(after)
  const keys = new Set([...Object.keys(a), ...Object.keys(b)])
  const rows: ConfigDiffRow[] = []
  for (const key of keys) {
    if (a[key] !== b[key]) {
      rows.push({ field: key, before: a[key] ?? "—", after: b[key] ?? "—" })
    }
  }
  return rows.sort((x, y) => x.field.localeCompare(y.field))
}

export function cn(...classes: Array<string | false | null | undefined>): string {
  return classes.filter(Boolean).join(" ")
}

/** Map backend check issue types to display-only severity badges. */
export function severityForIssue(issueType: CheckIssueType): IssueSeverity {
  if (issueType === "db_file_missing" || issueType === "content_hash_changed") {
    return "error"
  }
  if (issueType === "metadata_hash_changed" || issueType === "library_stale") {
    return "info"
  }
  return "warning"
}
