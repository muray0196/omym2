/*
Summary: Defines Web UI data contracts for the OMYM2 console.
Why: Keeps frontend state aligned with the packaged local JSON API.
*/

export type LibraryStatus = "registered" | "unregistered" | "stale" | "blocked"
export type TrackStatus = "active" | "removed"
export type PlanType = "add" | "organize" | "refresh" | "undo"
export type PlanStatus =
  "ready" | "applying" | "applied" | "partial_failed" | "failed" | "cancelled" | "expired"
export type PlanActionType = "move" | "skip" | "refresh_metadata"
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
    album_year_resolution: string
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
  album_year_resolution_methods: string[]
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

export interface PlanSummary {
  plan_id: string
  library_id: string
  plan_type: PlanType
  status: PlanStatus
  created_at: string
  summary: Record<string, string>
}

export interface PlanHeader extends PlanSummary {
  config_hash: string
  library_root_at_plan: string
}

export interface PlanAction {
  action_id: string
  plan_id: string
  library_id: string
  track_id: string | null
  action_type: PlanActionType
  source_path: string | null
  target_path: string | null
  content_hash_at_plan: string | null
  metadata_hash_at_plan: string | null
  status: PlanActionStatus
  reason: string | null
  sort_order: number
}

export interface PlanDetail {
  plan: PlanHeader
}

export interface PlanDetailResponse {
  detail: PlanDetail | null
  errors: string[]
}

export interface OrganizeRegistration {
  library: {
    library_id: string
    root_path: string
    path_policy_hash: string
    registered_at: string | null
    status: LibraryStatus
    created_at: string
    updated_at: string
  }
  track_count: number
}

export interface PlanCreateResult {
  created: boolean
  detail: PlanDetail | null
  registration: OrganizeRegistration | null
  errors: string[]
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

// --- Paginated Web API contracts (D6) --------------------------------------
// Envelope types shared by the paginated list/facet/group endpoints under
// /api/tracks, /api/plans/*, /api/check, and /api/history/*. Row payloads
// reuse the existing TrackSummary/PlanSummary/PlanAction/CheckIssue/
// RunSummary/FileEvent types above; these types are additive only.

export interface PageInfo {
  limit: number
  next_cursor: string | null
  total: number
}

export interface PagedResponse<T> {
  items: T[]
  page: PageInfo | null
  errors: string[]
}

export interface FacetValue {
  value: string
  count: number
}

export interface FacetsResponse {
  facets: Record<string, FacetValue[]>
  total: number | null
  errors: string[]
}

export interface GroupCount {
  key: string
  label: string
  count: number
}

export interface GroupsResponse {
  group_by: string
  items: GroupCount[]
  page: PageInfo | null
  errors: string[]
}

/** Group-by keys accepted by GET /api/plans/{plan_id}/groups. */
export type PlanGroupBy =
  | "target_directory"
  | "source_directory"
  | "artist_album"
  | "action_type"
  | "status"
  | "block_reason"
  | "extension"

/**
 * Plan group items are richer than the shared GroupCount: they carry the
 * blocked-action count and the most frequent non-null block reason so the
 * grouped review view can surface risk without drilling into every group.
 */
export interface PlanGroupCount extends GroupCount {
  blocked_count: number
  top_reason: string | null
}

export interface PlanGroupsResponse {
  group_by: string
  items: PlanGroupCount[]
  page: PageInfo | null
  errors: string[]
}

/**
 * Plan facets extend the shared envelope with `target_collisions`: the number
 * of distinct non-null target paths used by two or more actions. The `facets`
 * record additionally includes `reason` (non-null block reasons) alongside
 * `status` and `action_type`.
 */
export interface PlanFacetsResponse extends FacetsResponse {
  target_collisions: number
}

export interface CheckPageResponse extends PagedResponse<CheckIssue> {
  checked_at: string | null
}

export interface CheckFacetsResponse extends FacetsResponse {
  checked_at: string | null
}

export interface CheckRunResponse {
  checked_at: string
  total: number
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
