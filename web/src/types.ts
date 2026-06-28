export type AppConfig = {
  version: number;
  paths: {
    library: string | null;
    incoming: string | null;
  };
  add: CommandConfig;
  organize: OrganizeConfig;
  refresh: CommandConfig;
  path_policy: {
    template: string;
    unknown_artist: string;
    unknown_album: string;
    sanitize: boolean;
    max_filename_length: number;
  };
  metadata: {
    prefer_album_artist: boolean;
    require_title: boolean;
    require_artist: boolean;
    require_album: boolean;
  };
  collision: {
    on_target_exists: string;
    on_duplicate_hash: string;
    on_missing_metadata: string;
  };
  ui: {
    theme: string;
    show_advanced_settings: boolean;
  };
};

export type CommandConfig = {
  default_mode: string;
  auto_apply: boolean;
};

export type OrganizeConfig = CommandConfig & {
  only_misplaced: boolean;
};

export type SettingsChoices = {
  command_modes: string[];
  duplicate_hash_policies: string[];
  missing_metadata_policies: string[];
  target_exists_policies: string[];
  ui_themes: string[];
};

export type ValidationResult = {
  valid: boolean;
  errors: string[];
  config_hash: string | null;
};

export type PathPreview = {
  path: string | null;
  errors: string[];
};

export type SettingsChange = {
  label: string;
  before: string;
  after: string;
};

export type SettingsState = {
  config: AppConfig;
  choices: SettingsChoices;
  validation: ValidationResult;
  preview: PathPreview;
  errors: string[];
  csrf_token: string;
};

export type SettingsValidateResult = {
  valid: boolean;
  errors: string[];
  changes: SettingsChange[];
  preview: PathPreview;
};

export type SettingsSaveResult = {
  saved: boolean;
  errors: string[];
  changes: SettingsChange[];
  config?: AppConfig;
  validation?: ValidationResult;
  preview?: PathPreview;
};

export type RunSummary = {
  run_id: string;
  plan_id: string;
  library_id: string;
  status: string;
  started_at: string;
  completed_at: string | null;
  error_summary: string | null;
};

export type FileEvent = {
  event_id: string;
  library_id: string;
  run_id: string;
  plan_action_id: string;
  event_type: string;
  source_path: string;
  target_path: string;
  status: string;
  started_at: string;
  completed_at: string | null;
  error_code: string | null;
  error_message: string | null;
  sequence_no: number;
};

export type RunDetail = {
  run: RunSummary;
  file_events: FileEvent[];
};

export type HistoryResponse = {
  runs: RunSummary[];
  errors: string[];
};

export type RunDetailResponse = {
  detail: RunDetail | null;
  errors: string[];
};

export type CheckIssue = {
  issue_type: string;
  library_id: string;
  path: string | null;
  track_id: string | null;
  plan_id: string | null;
  detail: string | null;
};

export type CheckResponse = {
  issues: CheckIssue[];
  errors: string[];
};

export type TrackMetadata = {
  title: string | null;
  artist: string | null;
  album: string | null;
  album_artist: string | null;
  genre: string | null;
  year: number | null;
  track_number: number | null;
  track_total: number | null;
  disc_number: number | null;
  disc_total: number | null;
};

export type TrackSummary = {
  track_id: string;
  library_id: string;
  current_path: string;
  canonical_path: string;
  content_hash: string;
  metadata_hash: string;
  metadata: TrackMetadata;
  status: string;
  first_seen_at: string;
  last_seen_at: string;
  updated_at: string;
};

export type TracksResponse = {
  tracks: TrackSummary[];
  errors: string[];
};
