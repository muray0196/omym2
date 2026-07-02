import type { AppConfig, CheckIssueType, IssueSeverity } from "./types"

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
  "{artist_id}",
] as const

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
  if (config.artist_ids.max_length < 1) {
    errors.push("artist_ids.max_length must be positive.")
  }
  if (!config.artist_ids.fallback_id.trim()) {
    errors.push("artist_ids.fallback_id must not be empty.")
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
