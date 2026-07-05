// Domain types for the OMYM2 local console.

export type LibraryStatus = "registered" | "unregistered" | "stale" | "blocked"
export type TrackStatus = "active" | "removed"
export type PlanStatus =
  "ready" | "applying" | "applied" | "partial_failed" | "failed" | "cancelled" | "expired"
export type PlanActionStatus = "planned" | "blocked" | "applied" | "failed"
export type RunStatus = "running" | "succeeded" | "partial_failed" | "failed"
export type FileEventStatus = "pending" | "succeeded" | "failed"

export type CheckIssueType =
  | "db_file_missing"
  | "unmanaged_file_exists"
  | "content_hash_changed"
  | "metadata_hash_changed"
  | "current_path_differs_from_canonical_path"
  | "duplicate_candidate"
  | "plan_source_changed"
  | "pending_file_event_exists"
  | "library_unregistered"
  | "library_stale"
  | "library_blocked"

export type IssueSeverity = "info" | "warning" | "error"

export interface AppConfig {
  version: number
  paths: {
    library: string | null
    incoming: string | null
  }
  add: {
    default_mode: string
    auto_apply: boolean
  }
  organize: {
    default_mode: string
    auto_apply: boolean
    only_misplaced: boolean
  }
  refresh: {
    default_mode: string
    auto_apply: boolean
  }
  path_policy: {
    template: string
    unknown_artist: string
    unknown_album: string
    sanitize: boolean
    max_filename_length: number
    disc_number_style: string
    disc_number_condition: string
  }
  artist_ids: {
    max_length: number
    fallback_id: string
    entries: Record<string, string>
  }
  metadata: {
    prefer_album_artist: boolean
    require_title: boolean
    require_artist: boolean
    require_album: boolean
  }
  collision: {
    on_target_exists: string
    on_duplicate_hash: string
    on_missing_metadata: string
  }
  ui: {
    theme: string
    show_advanced_settings: boolean
  }
}

export interface SettingsChoices {
  command_modes: string[]
  duplicate_hash_policies: string[]
  missing_metadata_policies: string[]
  target_exists_policies: string[]
  disc_number_styles: string[]
  disc_number_conditions: string[]
  ui_themes: string[]
}

export interface ValidationResult {
  valid: boolean
  errors: string[]
  config_hash: string | null
}

export interface PathPreview {
  path: string | null
  errors: string[]
}

export interface SettingsChange {
  label: string
  before: string
  after: string
}

export interface SettingsState {
  config: AppConfig
  choices: SettingsChoices
  validation: ValidationResult
  preview: PathPreview
  errors: string[]
  csrf_token: string
}

export interface SettingsValidateResult {
  valid: boolean
  errors: string[]
  changes: SettingsChange[]
  preview: PathPreview
}

export type SettingsPreviewResult = PathPreview

export interface SettingsSaveResult {
  saved: boolean
  errors: string[]
  changes: SettingsChange[]
  config?: AppConfig
  validation?: ValidationResult
  preview?: PathPreview
}

export interface ArtistIdGenerationEntry {
  source_artist: string
  generation_artist: string
  artist_id: string
  saved: boolean
  overwritten: boolean
}

export interface ArtistIdGenerationResult {
  generated: boolean
  errors: string[]
  entries: ArtistIdGenerationEntry[]
}

export interface RunSummary {
  run_id: string
  plan_id: string
  library_id: string
  status: RunStatus
  started_at: string
  completed_at: string | null
  error_summary: string | null
}

export interface HistoryResponse {
  runs: RunSummary[]
  errors: string[]
}

export interface FileEvent {
  event_id: string
  library_id: string
  run_id: string
  plan_action_id: string
  event_type: string
  source_path: string
  target_path: string
  status: FileEventStatus
  started_at: string
  completed_at: string | null
  error_code: string | null
  error_message: string | null
  sequence_no: number
}

export interface RunDetail {
  run: RunSummary
  file_events: FileEvent[]
}

export interface RunDetailResponse {
  detail: RunDetail | null
  errors: string[]
}

export interface CheckIssue {
  issue_type: CheckIssueType
  issue_id?: string
  severity?: IssueSeverity
  library_id: string
  path: string | null
  track_id: string | null
  plan_id: string | null
  detail: string | null
}

export interface CheckResponse {
  issues: CheckIssue[]
  errors: string[]
}

export interface TrackMetadata {
  title: string | null
  artist: string | null
  album: string | null
  album_artist: string | null
  genre: string | null
  year: number | null
  track_number: number | null
  track_total: number | null
  disc_number: number | null
  disc_total: number | null
}

export interface TrackSummary {
  track_id: string
  library_id: string
  current_path: string
  canonical_path: string
  content_hash: string
  metadata_hash: string
  metadata: TrackMetadata
  status: TrackStatus
  first_seen_at: string
  last_seen_at: string
  updated_at: string
}

export interface TracksResponse {
  tracks: TrackSummary[]
  errors: string[]
}

export interface SampleMetadata {
  title: string
  artist: string
  album: string
  album_artist: string
  year: string
  disc_number: string
  disc_total: string
  track_number: string
  extension: string
}
