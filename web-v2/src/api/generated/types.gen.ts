/**
 * Summary: Auto-generates typed API client code from the committed OpenAPI contract.
 * Why: Keeps frontend transport types synchronized with backend Pydantic schemas.
 */

export type ClientOptions = {
    baseUrl: `${string}://${string}` | (string & {});
};

/**
 * ActionStatus
 *
 * Supported planned action statuses.
 */
export type ActionStatus = 'planned' | 'blocked' | 'applied' | 'failed';

/**
 * ActionType
 *
 * Supported planned action types.
 */
export type ActionType = 'move' | 'skip' | 'refresh_metadata';

/**
 * ApiEnvelope[BootstrapData]
 */
export type ApiEnvelopeBootstrapData = {
    data: BootstrapData | null;
    /**
     * Errors
     */
    errors: Array<ApiError>;
};

/**
 * ApiEnvelope[CheckIssueFacetsData]
 */
export type ApiEnvelopeCheckIssueFacetsData = {
    data: CheckIssueFacetsData | null;
    /**
     * Errors
     */
    errors: Array<ApiError>;
};

/**
 * ApiEnvelope[CheckIssueGroupsData]
 */
export type ApiEnvelopeCheckIssueGroupsData = {
    data: CheckIssueGroupsData | null;
    /**
     * Errors
     */
    errors: Array<ApiError>;
};

/**
 * ApiEnvelope[CheckIssuesData]
 */
export type ApiEnvelopeCheckIssuesData = {
    data: CheckIssuesData | null;
    /**
     * Errors
     */
    errors: Array<ApiError>;
};

/**
 * ApiEnvelope[FileEventFacetsData]
 */
export type ApiEnvelopeFileEventFacetsData = {
    data: FileEventFacetsData | null;
    /**
     * Errors
     */
    errors: Array<ApiError>;
};

/**
 * ApiEnvelope[FileEventGroupsData]
 */
export type ApiEnvelopeFileEventGroupsData = {
    data: FileEventGroupsData | null;
    /**
     * Errors
     */
    errors: Array<ApiError>;
};

/**
 * ApiEnvelope[LibrariesData]
 */
export type ApiEnvelopeLibrariesData = {
    data: LibrariesData | null;
    /**
     * Errors
     */
    errors: Array<ApiError>;
};

/**
 * ApiEnvelope[LibraryResource]
 */
export type ApiEnvelopeLibraryResource = {
    data: LibraryResource | null;
    /**
     * Errors
     */
    errors: Array<ApiError>;
};

/**
 * ApiEnvelope[PaginatedData[FileEventResource]]
 */
export type ApiEnvelopePaginatedDataFileEventResource = {
    data: PaginatedDataFileEventResource | null;
    /**
     * Errors
     */
    errors: Array<ApiError>;
};

/**
 * ApiEnvelope[PaginatedData[PlanActionResource]]
 */
export type ApiEnvelopePaginatedDataPlanActionResource = {
    data: PaginatedDataPlanActionResource | null;
    /**
     * Errors
     */
    errors: Array<ApiError>;
};

/**
 * ApiEnvelope[PaginatedData[PlanSummary]]
 */
export type ApiEnvelopePaginatedDataPlanSummary = {
    data: PaginatedDataPlanSummary | null;
    /**
     * Errors
     */
    errors: Array<ApiError>;
};

/**
 * ApiEnvelope[PaginatedData[RunHeader]]
 */
export type ApiEnvelopePaginatedDataRunHeader = {
    data: PaginatedDataRunHeader | null;
    /**
     * Errors
     */
    errors: Array<ApiError>;
};

/**
 * ApiEnvelope[PaginatedData[TrackResource]]
 */
export type ApiEnvelopePaginatedDataTrackResource = {
    data: PaginatedDataTrackResource | null;
    /**
     * Errors
     */
    errors: Array<ApiError>;
};

/**
 * ApiEnvelope[PlanActionFacetsData]
 */
export type ApiEnvelopePlanActionFacetsData = {
    data: PlanActionFacetsData | null;
    /**
     * Errors
     */
    errors: Array<ApiError>;
};

/**
 * ApiEnvelope[PlanActionGroupsData]
 */
export type ApiEnvelopePlanActionGroupsData = {
    data: PlanActionGroupsData | null;
    /**
     * Errors
     */
    errors: Array<ApiError>;
};

/**
 * ApiEnvelope[PlanDetailData]
 */
export type ApiEnvelopePlanDetailData = {
    data: PlanDetailData | null;
    /**
     * Errors
     */
    errors: Array<ApiError>;
};

/**
 * ApiEnvelope[RunDetailData]
 */
export type ApiEnvelopeRunDetailData = {
    data: RunDetailData | null;
    /**
     * Errors
     */
    errors: Array<ApiError>;
};

/**
 * ApiEnvelope[RunFacetsData]
 */
export type ApiEnvelopeRunFacetsData = {
    data: RunFacetsData | null;
    /**
     * Errors
     */
    errors: Array<ApiError>;
};

/**
 * ApiEnvelope[TrackFacetsData]
 */
export type ApiEnvelopeTrackFacetsData = {
    data: TrackFacetsData | null;
    /**
     * Errors
     */
    errors: Array<ApiError>;
};

/**
 * ApiEnvelope[TrackGroupsData]
 */
export type ApiEnvelopeTrackGroupsData = {
    data: TrackGroupsData | null;
    /**
     * Errors
     */
    errors: Array<ApiError>;
};

/**
 * ApiEnvelope[TrackResource]
 */
export type ApiEnvelopeTrackResource = {
    data: TrackResource | null;
    /**
     * Errors
     */
    errors: Array<ApiError>;
};

/**
 * ApiError
 *
 * One stable Web API error or disabled reason.
 */
export type ApiError = {
    code: ApiErrorCode;
    /**
     * Field
     */
    field?: string;
    /**
     * Message
     */
    message: string;
    /**
     * Remediation
     */
    remediation?: ApiRemediation;
    /**
     * Retryable
     */
    retryable: boolean;
};

/**
 * ApiErrorCode
 *
 * Closed top-level Web API error catalog.
 */
export type ApiErrorCode = 'invalid_json' | 'csrf_invalid' | 'api_not_found' | 'library_not_found' | 'track_not_found' | 'plan_not_found' | 'run_not_found' | 'operation_not_found' | 'method_not_allowed' | 'config_invalid' | 'config_changed' | 'operation_in_progress' | 'idempotency_key_reused' | 'library_selection_ambiguous' | 'library_unregistered' | 'library_stale' | 'library_blocked' | 'plan_not_ready' | 'library_root_changed' | 'run_not_terminal' | 'nothing_to_undo' | 'undo_refresh_metadata_unsupported' | 'already_undone_or_in_progress' | 'pending_file_event_requires_review' | 'operation_expired' | 'validation_failed' | 'path_not_found' | 'path_not_directory' | 'path_outside_library' | 'storage_unavailable' | 'config_io_failed' | 'internal_error' | 'operation_interrupted' | 'metadata_read_failed' | 'operation_failed';

/**
 * ApiFailureEnvelope
 *
 * Failure-only envelope used for declared error responses.
 */
export type ApiFailureEnvelope = {
    /**
     * Data
     */
    data: null;
    /**
     * Errors
     */
    errors: Array<ApiError>;
};

/**
 * ApiRemediation
 *
 * Optional recovery action displayed but never executed automatically.
 */
export type ApiRemediation = {
    /**
     * Command
     */
    command?: string;
    /**
     * Label
     */
    label: string;
    /**
     * Route
     */
    route?: string;
};

/**
 * BootstrapData
 *
 * Initial application state returned even when recovery is required.
 */
export type BootstrapData = {
    active_library: LibraryResource | null;
    /**
     * Active Operation Id
     */
    active_operation_id: string | null;
    /**
     * App Version
     */
    app_version: string;
    config_validation: ConfigValidationResource;
    /**
     * Csrf Token
     */
    csrf_token: string;
    /**
     * Library Diagnostics
     */
    library_diagnostics: Array<ApiError>;
    operation_polling: OperationPollingPolicy;
    runtime_capabilities: RuntimeCapabilities;
    /**
     * Status Catalog Version
     */
    status_catalog_version: number;
};

/**
 * CheckIssueFacetSets
 *
 * CheckIssue type facets.
 */
export type CheckIssueFacetSets = {
    /**
     * Issue Type
     */
    issue_type: Array<FacetValueResourceCheckIssueType>;
};

/**
 * CheckIssueFacetsData
 *
 * CheckIssue facets, matching total, and freshness evidence.
 */
export type CheckIssueFacetsData = {
    /**
     * Checked At
     */
    checked_at: string | null;
    facets: CheckIssueFacetSets;
    total: NonNegativeCount;
};

/**
 * CheckIssueGroupResource
 *
 * One CheckIssue group with its most common non-null path root.
 */
export type CheckIssueGroupResource = {
    /**
     * Common Path Root
     */
    common_path_root: string | null;
    count: NonNegativeCount;
    /**
     * Key
     */
    key: string;
    /**
     * Label
     */
    label: string;
};

/**
 * CheckIssueGrouping
 *
 * Supported group-by keys for persisted CheckIssue browsing.
 */
export type CheckIssueGrouping = 'issue_type' | 'severity' | 'path_root' | 'artist_album' | 'suggested_command' | 'library_id';

/**
 * CheckIssueGroupsData
 *
 * One page of persisted CheckIssue groups.
 */
export type CheckIssueGroupsData = {
    group_by: CheckIssueGrouping;
    /**
     * Items
     */
    items: Array<CheckIssueGroupResource>;
    page: PageInfo;
};

/**
 * CheckIssueResource
 *
 * One persisted finding from the latest Check for its Library.
 */
export type CheckIssueResource = {
    /**
     * Detail
     */
    detail: string | null;
    issue_type: CheckIssueType;
    /**
     * Library Id
     */
    library_id: string;
    /**
     * Path
     */
    path: string | null;
    /**
     * Plan Id
     */
    plan_id: string | null;
    /**
     * Track Id
     */
    track_id: string | null;
};

/**
 * CheckIssueType
 *
 * Supported check issue types.
 */
export type CheckIssueType = 'db_file_missing' | 'unmanaged_file_exists' | 'content_hash_changed' | 'metadata_hash_changed' | 'current_path_differs_from_canonical_path' | 'duplicate_candidate' | 'plan_source_changed' | 'pending_file_event_exists' | 'library_unregistered' | 'library_stale' | 'library_blocked';

/**
 * CheckIssuesData
 *
 * One persisted CheckIssue page plus freshness evidence.
 */
export type CheckIssuesData = {
    /**
     * Checked At
     */
    checked_at: string | null;
    /**
     * Items
     */
    items: Array<CheckIssueResource>;
    page: PageInfo;
};

/**
 * ConfigValidationResource
 *
 * Current Config validity and opaque raw-storage revision.
 */
export type ConfigValidationResource = {
    /**
     * Config Revision
     */
    config_revision: string | null;
    /**
     * Errors
     */
    errors: Array<ApiError>;
    /**
     * Valid
     */
    valid: boolean;
};

/**
 * FacetValueResource[ActionStatus]
 */
export type FacetValueResourceActionStatus = {
    count: NonNegativeCount;
    value: ActionStatus;
};

/**
 * FacetValueResource[ActionType]
 */
export type FacetValueResourceActionType = {
    count: NonNegativeCount;
    value: ActionType;
};

/**
 * FacetValueResource[CheckIssueType]
 */
export type FacetValueResourceCheckIssueType = {
    count: NonNegativeCount;
    value: CheckIssueType;
};

/**
 * FacetValueResource[FileEventStatus]
 */
export type FacetValueResourceFileEventStatus = {
    count: NonNegativeCount;
    value: FileEventStatus;
};

/**
 * FacetValueResource[PlanActionReason]
 */
export type FacetValueResourcePlanActionReason = {
    count: NonNegativeCount;
    value: PlanActionReason;
};

/**
 * FacetValueResource[RunStatus]
 */
export type FacetValueResourceRunStatus = {
    count: NonNegativeCount;
    value: RunStatus;
};

/**
 * FacetValueResource[TrackStatus]
 */
export type FacetValueResourceTrackStatus = {
    count: NonNegativeCount;
    value: TrackStatus;
};

/**
 * FileEventFacetSets
 *
 * FileEvent status facets.
 */
export type FileEventFacetSets = {
    /**
     * Status
     */
    status: Array<FacetValueResourceFileEventStatus>;
};

/**
 * FileEventFacetsData
 *
 * FileEvent status facets plus total events for one Run.
 */
export type FileEventFacetsData = {
    facets: FileEventFacetSets;
    total: NonNegativeCount;
};

export type FileEventGrouping = 'target_directory';

/**
 * FileEventGroupsData
 *
 * One page of FileEvent target-directory groups.
 */
export type FileEventGroupsData = {
    group_by: FileEventGrouping;
    /**
     * Items
     */
    items: Array<GroupResource>;
    page: PageInfo;
};

/**
 * FileEventResource
 *
 * One durable Library music-file mutation record.
 */
export type FileEventResource = {
    /**
     * Completed At
     */
    completed_at: string | null;
    /**
     * Error Code
     */
    error_code: string | null;
    /**
     * Error Message
     */
    error_message: string | null;
    /**
     * Event Id
     */
    event_id: string;
    event_type: FileEventType;
    /**
     * Library Id
     */
    library_id: string;
    /**
     * Plan Action Id
     */
    plan_action_id: string;
    /**
     * Run Id
     */
    run_id: string;
    /**
     * Sequence No
     */
    sequence_no: number;
    /**
     * Source Path
     */
    source_path: string;
    /**
     * Started At
     */
    started_at: string;
    status: FileEventStatus;
    /**
     * Target Path
     */
    target_path: string;
};

/**
 * FileEventStatus
 *
 * Supported durable operation event statuses.
 */
export type FileEventStatus = 'pending' | 'succeeded' | 'failed';

/**
 * FileEventType
 *
 * Supported durable operation event types.
 */
export type FileEventType = 'move_file';

/**
 * GroupResource
 *
 * One stable group key, display label, and matching row count.
 */
export type GroupResource = {
    count: NonNegativeCount;
    /**
     * Key
     */
    key: string;
    /**
     * Label
     */
    label: string;
};

/**
 * LibrariesData
 *
 * Every persisted Library in stable repository order.
 */
export type LibrariesData = {
    /**
     * Items
     */
    items: Array<LibraryResource>;
};

/**
 * LibraryResource
 *
 * One effective Library readiness resource.
 */
export type LibraryResource = {
    /**
     * Is Path Policy Current
     */
    is_path_policy_current: boolean;
    /**
     * Is Registered
     */
    is_registered: boolean;
    /**
     * Library Id
     */
    library_id: string;
    /**
     * Path Policy Fingerprint
     */
    path_policy_fingerprint: string;
    /**
     * Registered At
     */
    registered_at: string | null;
    /**
     * Root Path
     */
    root_path: string;
    status: LibraryStatus;
};

/**
 * LibraryStatus
 *
 * Known Library registration states.
 */
export type LibraryStatus = 'registered' | 'unregistered' | 'stale' | 'blocked';

export type NonNegativeCount = number;

/**
 * OperationPollingPolicy
 *
 * Polling policy serialized from backend-owned tunables.
 */
export type OperationPollingPolicy = {
    /**
     * Backoff Factor
     */
    backoff_factor: number;
    /**
     * Initial Ms
     */
    initial_ms: number;
    /**
     * Max Ms
     */
    max_ms: number;
};

/**
 * PageInfo
 *
 * One effective keyset page with an opaque next cursor.
 */
export type PageInfo = {
    /**
     * Limit
     */
    limit: number;
    /**
     * Next Cursor
     */
    next_cursor: string | null;
    total: NonNegativeCount;
};

/**
 * PaginatedData[FileEventResource]
 */
export type PaginatedDataFileEventResource = {
    /**
     * Items
     */
    items: Array<FileEventResource>;
    page: PageInfo;
};

/**
 * PaginatedData[PlanActionResource]
 */
export type PaginatedDataPlanActionResource = {
    /**
     * Items
     */
    items: Array<PlanActionResource>;
    page: PageInfo;
};

/**
 * PaginatedData[PlanSummary]
 */
export type PaginatedDataPlanSummary = {
    /**
     * Items
     */
    items: Array<PlanSummary>;
    page: PageInfo;
};

/**
 * PaginatedData[RunHeader]
 */
export type PaginatedDataRunHeader = {
    /**
     * Items
     */
    items: Array<RunHeader>;
    page: PageInfo;
};

/**
 * PaginatedData[TrackResource]
 */
export type PaginatedDataTrackResource = {
    /**
     * Items
     */
    items: Array<TrackResource>;
    page: PageInfo;
};

/**
 * PlanActionFacetSets
 *
 * The filter-aware status, action type, and non-null reason facets.
 */
export type PlanActionFacetSets = {
    /**
     * Action Type
     */
    action_type: Array<FacetValueResourceActionType>;
    /**
     * Reason
     */
    reason: Array<FacetValueResourcePlanActionReason>;
    /**
     * Status
     */
    status: Array<FacetValueResourceActionStatus>;
};

/**
 * PlanActionFacetsData
 *
 * PlanAction facets plus the Plan-wide target-collision risk count.
 */
export type PlanActionFacetsData = {
    facets: PlanActionFacetSets;
    target_collisions: NonNegativeCount;
    total: NonNegativeCount;
};

/**
 * PlanActionGroupResource
 *
 * One enriched PlanAction group row for drill-down browsing.
 */
export type PlanActionGroupResource = {
    blocked_count: NonNegativeCount;
    count: NonNegativeCount;
    /**
     * Key
     */
    key: string;
    /**
     * Label
     */
    label: string;
    top_reason: PlanActionReason | null;
};

/**
 * PlanActionGrouping
 *
 * Supported group_by keys for browsing one Plan's actions.
 */
export type PlanActionGrouping = 'target_directory' | 'source_directory' | 'artist_album' | 'action_type' | 'status' | 'block_reason' | 'extension';

/**
 * PlanActionGroupsData
 *
 * One filter-aware page of enriched PlanAction groups.
 */
export type PlanActionGroupsData = {
    group_by: PlanActionGrouping;
    /**
     * Items
     */
    items: Array<PlanActionGroupResource>;
    page: PageInfo;
};

/**
 * PlanActionReason
 *
 * Documented reasons for blocked, skipped, or failed actions.
 */
export type PlanActionReason = 'target_exists' | 'missing_required_metadata' | 'invalid_path' | 'source_missing' | 'source_changed' | 'duplicate_hash' | 'operation_interrupted';

/**
 * PlanActionResource
 *
 * One recorded PlanAction in immutable review order.
 */
export type PlanActionResource = {
    /**
     * Action Id
     */
    action_id: string;
    action_type: ActionType;
    /**
     * Content Hash At Plan
     */
    content_hash_at_plan: string | null;
    /**
     * Library Id
     */
    library_id: string;
    /**
     * Metadata Hash At Plan
     */
    metadata_hash_at_plan: string | null;
    /**
     * Plan Id
     */
    plan_id: string;
    reason: PlanActionReason | null;
    /**
     * Sort Order
     */
    sort_order: number;
    /**
     * Source Path
     */
    source_path: string | null;
    status: ActionStatus;
    /**
     * Target Path
     */
    target_path: string | null;
    /**
     * Track Id
     */
    track_id: string | null;
};

/**
 * PlanActionSummary
 *
 * Typed current action count summary that replaces opaque Plan storage data.
 */
export type PlanActionSummary = {
    counts: PlanActionSummaryCounts;
    total: NonNegativeCount;
};

/**
 * PlanActionSummaryCounts
 *
 * The complete status matrix for one Plan's current recorded actions.
 */
export type PlanActionSummaryCounts = {
    applied: PlanActionTypeCounts;
    blocked: PlanActionTypeCounts;
    failed: PlanActionTypeCounts;
    planned: PlanActionTypeCounts;
};

/**
 * PlanActionTypeCounts
 *
 * Counts for the three recorded PlanAction types within one status.
 */
export type PlanActionTypeCounts = {
    move: NonNegativeCount;
    refresh_metadata: NonNegativeCount;
    skip: NonNegativeCount;
};

/**
 * PlanCapabilities
 *
 * Backend-authoritative operation availability for one Plan.
 */
export type PlanCapabilities = {
    /**
     * Can Apply
     */
    can_apply: boolean;
    /**
     * Can Cancel
     */
    can_cancel: boolean;
    /**
     * Can Recreate
     */
    can_recreate: boolean;
    /**
     * Disabled Reasons
     */
    disabled_reasons: Array<ApiError>;
};

/**
 * PlanDetailData
 *
 * Plan header, current action summary, and advisory capabilities.
 */
export type PlanDetailData = {
    /**
     * Active Operation Id
     */
    active_operation_id: string | null;
    capabilities: PlanCapabilities;
    plan: PlanHeader;
    summary: PlanActionSummary;
};

/**
 * PlanHeader
 *
 * One Plan header without actions or an opaque persisted summary.
 */
export type PlanHeader = {
    /**
     * Config Hash
     */
    config_hash: string;
    /**
     * Created At
     */
    created_at: string;
    /**
     * Library Id
     */
    library_id: string;
    /**
     * Library Root At Plan
     */
    library_root_at_plan: string;
    /**
     * Plan Id
     */
    plan_id: string;
    plan_type: PlanType;
    status: PlanStatus;
};

/**
 * PlanStatus
 *
 * Supported Plan statuses.
 */
export type PlanStatus = 'ready' | 'applying' | 'applied' | 'partial_failed' | 'failed' | 'cancelled' | 'expired';

/**
 * PlanSummary
 *
 * One Plan list row without execution capabilities or opaque persistence fields.
 */
export type PlanSummary = {
    /**
     * Created At
     */
    created_at: string;
    /**
     * Library Id
     */
    library_id: string;
    /**
     * Plan Id
     */
    plan_id: string;
    plan_type: PlanType;
    status: PlanStatus;
    summary: PlanActionSummary;
};

/**
 * PlanType
 *
 * Supported Plan types.
 */
export type PlanType = 'add' | 'organize' | 'refresh' | 'undo';

/**
 * RunCapabilities
 *
 * Backend-authoritative Undo Plan availability for one Run.
 */
export type RunCapabilities = {
    /**
     * Can Create Undo
     */
    can_create_undo: boolean;
    /**
     * Disabled Reasons
     */
    disabled_reasons: Array<ApiError>;
};

/**
 * RunDetailData
 *
 * One Run header with capability and active-operation projections.
 */
export type RunDetailData = {
    /**
     * Active Operation Id
     */
    active_operation_id: string | null;
    capabilities: RunCapabilities;
    run: RunHeader;
};

/**
 * RunFacetSets
 *
 * Run status facets.
 */
export type RunFacetSets = {
    /**
     * Status
     */
    status: Array<FacetValueResourceRunStatus>;
};

/**
 * RunFacetsData
 *
 * Run status facets plus total Runs in scope.
 */
export type RunFacetsData = {
    facets: RunFacetSets;
    total: NonNegativeCount;
};

/**
 * RunHeader
 *
 * One apply Run header without embedded FileEvents.
 */
export type RunHeader = {
    /**
     * Completed At
     */
    completed_at: string | null;
    /**
     * Error Summary
     */
    error_summary: string | null;
    /**
     * Library Id
     */
    library_id: string;
    /**
     * Plan Id
     */
    plan_id: string;
    /**
     * Run Id
     */
    run_id: string;
    /**
     * Started At
     */
    started_at: string;
    status: RunStatus;
};

/**
 * RunStatus
 *
 * Supported Run statuses.
 */
export type RunStatus = 'running' | 'succeeded' | 'partial_failed' | 'failed';

/**
 * RuntimeCapabilities
 *
 * Backend-authoritative application runtime availability.
 */
export type RuntimeCapabilities = {
    /**
     * Can Change Settings
     */
    can_change_settings: boolean;
    /**
     * Can Read State
     */
    can_read_state: boolean;
    /**
     * Can Start Operations
     */
    can_start_operations: boolean;
    /**
     * Disabled Reasons
     */
    disabled_reasons: Array<ApiError>;
};

/**
 * TrackFacetSets
 *
 * Filter-aware Track status facets.
 */
export type TrackFacetSets = {
    /**
     * Status
     */
    status: Array<FacetValueResourceTrackStatus>;
};

/**
 * TrackFacetsData
 *
 * Track facets and total count for the current search scope.
 */
export type TrackFacetsData = {
    facets: TrackFacetSets;
    total: NonNegativeCount;
};

/**
 * TrackGrouping
 *
 * Known Track group-by query groupings.
 */
export type TrackGrouping = 'artist' | 'album' | 'disc' | 'artist_album';

/**
 * TrackGroupsData
 *
 * One filter-aware page of opaque Track hierarchy groups.
 */
export type TrackGroupsData = {
    group_by: TrackGrouping;
    /**
     * Items
     */
    items: Array<GroupResource>;
    page: PageInfo;
};

/**
 * TrackMetadataResource
 *
 * Persisted tag metadata for one managed Track.
 */
export type TrackMetadataResource = {
    /**
     * Album
     */
    album: string | null;
    /**
     * Album Artist
     */
    album_artist: string | null;
    /**
     * Artist
     */
    artist: string | null;
    /**
     * Disc Number
     */
    disc_number: number | null;
    /**
     * Disc Total
     */
    disc_total: number | null;
    /**
     * Genre
     */
    genre: string | null;
    /**
     * Title
     */
    title: string | null;
    /**
     * Track Number
     */
    track_number: number | null;
    /**
     * Track Total
     */
    track_total: number | null;
    /**
     * Year
     */
    year: number | null;
};

/**
 * TrackResource
 *
 * One persisted Track inspection resource.
 */
export type TrackResource = {
    /**
     * Canonical Path
     */
    canonical_path: string;
    /**
     * Content Hash
     */
    content_hash: string;
    /**
     * Current Path
     */
    current_path: string;
    /**
     * First Seen At
     */
    first_seen_at: string;
    /**
     * Last Seen At
     */
    last_seen_at: string;
    /**
     * Library Id
     */
    library_id: string;
    metadata: TrackMetadataResource;
    /**
     * Metadata Hash
     */
    metadata_hash: string;
    /**
     * Mtime
     */
    mtime: string | null;
    size: NonNegativeCount | null;
    status: TrackStatus;
    /**
     * Track Id
     */
    track_id: string;
    /**
     * Updated At
     */
    updated_at: string;
};

/**
 * TrackStatus
 *
 * Known managed Track states.
 */
export type TrackStatus = 'active' | 'removed';

export type GetBootstrapData = {
    body?: never;
    path?: never;
    query?: never;
    url: '/api/bootstrap';
};

export type GetBootstrapErrors = {
    /**
     * Internal Server Error
     */
    500: ApiFailureEnvelope;
};

export type GetBootstrapError = GetBootstrapErrors[keyof GetBootstrapErrors];

export type GetBootstrapResponses = {
    /**
     * Successful Response
     */
    200: ApiEnvelopeBootstrapData;
};

export type GetBootstrapResponse = GetBootstrapResponses[keyof GetBootstrapResponses];

export type GetCheckIssuesData = {
    body?: never;
    path?: never;
    query?: {
        /**
         * Query
         */
        query?: string | null;
        /**
         * Issue Type
         */
        issue_type?: CheckIssueType | null;
        /**
         * Group By
         */
        group_by?: CheckIssueGrouping | null;
        /**
         * Group Key
         */
        group_key?: string | null;
        /**
         * Library Id
         */
        library_id?: string | null;
        /**
         * Limit
         */
        limit?: number | null;
        /**
         * Cursor
         */
        cursor?: string | null;
    };
    url: '/api/check';
};

export type GetCheckIssuesErrors = {
    /**
     * Unprocessable Content
     */
    422: ApiFailureEnvelope;
    /**
     * Internal Server Error
     */
    500: ApiFailureEnvelope;
};

export type GetCheckIssuesError = GetCheckIssuesErrors[keyof GetCheckIssuesErrors];

export type GetCheckIssuesResponses = {
    /**
     * Successful Response
     */
    200: ApiEnvelopeCheckIssuesData;
};

export type GetCheckIssuesResponse = GetCheckIssuesResponses[keyof GetCheckIssuesResponses];

export type GetCheckIssueFacetsData = {
    body?: never;
    path?: never;
    query?: {
        /**
         * Query
         */
        query?: string | null;
        /**
         * Library Id
         */
        library_id?: string | null;
    };
    url: '/api/check/facets';
};

export type GetCheckIssueFacetsErrors = {
    /**
     * Unprocessable Content
     */
    422: ApiFailureEnvelope;
    /**
     * Internal Server Error
     */
    500: ApiFailureEnvelope;
};

export type GetCheckIssueFacetsError = GetCheckIssueFacetsErrors[keyof GetCheckIssueFacetsErrors];

export type GetCheckIssueFacetsResponses = {
    /**
     * Successful Response
     */
    200: ApiEnvelopeCheckIssueFacetsData;
};

export type GetCheckIssueFacetsResponse = GetCheckIssueFacetsResponses[keyof GetCheckIssueFacetsResponses];

export type GetCheckIssueGroupsData = {
    body?: never;
    path?: never;
    query: {
        group_by: CheckIssueGrouping;
        /**
         * Query
         */
        query?: string | null;
        /**
         * Issue Type
         */
        issue_type?: CheckIssueType | null;
        /**
         * Library Id
         */
        library_id?: string | null;
        /**
         * Limit
         */
        limit?: number | null;
        /**
         * Cursor
         */
        cursor?: string | null;
    };
    url: '/api/check/groups';
};

export type GetCheckIssueGroupsErrors = {
    /**
     * Unprocessable Content
     */
    422: ApiFailureEnvelope;
    /**
     * Internal Server Error
     */
    500: ApiFailureEnvelope;
};

export type GetCheckIssueGroupsError = GetCheckIssueGroupsErrors[keyof GetCheckIssueGroupsErrors];

export type GetCheckIssueGroupsResponses = {
    /**
     * Successful Response
     */
    200: ApiEnvelopeCheckIssueGroupsData;
};

export type GetCheckIssueGroupsResponse = GetCheckIssueGroupsResponses[keyof GetCheckIssueGroupsResponses];

export type GetHistoryData = {
    body?: never;
    path?: never;
    query?: {
        /**
         * Query
         */
        query?: string | null;
        /**
         * Status
         */
        status?: RunStatus | null;
        /**
         * Plan Id
         */
        plan_id?: string | null;
        /**
         * Library Id
         */
        library_id?: string | null;
        /**
         * Limit
         */
        limit?: number | null;
        /**
         * Cursor
         */
        cursor?: string | null;
    };
    url: '/api/history';
};

export type GetHistoryErrors = {
    /**
     * Unprocessable Content
     */
    422: ApiFailureEnvelope;
    /**
     * Internal Server Error
     */
    500: ApiFailureEnvelope;
};

export type GetHistoryError = GetHistoryErrors[keyof GetHistoryErrors];

export type GetHistoryResponses = {
    /**
     * Successful Response
     */
    200: ApiEnvelopePaginatedDataRunHeader;
};

export type GetHistoryResponse = GetHistoryResponses[keyof GetHistoryResponses];

export type GetHistoryFacetsData = {
    body?: never;
    path?: never;
    query?: {
        /**
         * Library Id
         */
        library_id?: string | null;
    };
    url: '/api/history/facets';
};

export type GetHistoryFacetsErrors = {
    /**
     * Unprocessable Content
     */
    422: ApiFailureEnvelope;
    /**
     * Internal Server Error
     */
    500: ApiFailureEnvelope;
};

export type GetHistoryFacetsError = GetHistoryFacetsErrors[keyof GetHistoryFacetsErrors];

export type GetHistoryFacetsResponses = {
    /**
     * Successful Response
     */
    200: ApiEnvelopeRunFacetsData;
};

export type GetHistoryFacetsResponse = GetHistoryFacetsResponses[keyof GetHistoryFacetsResponses];

export type GetRunData = {
    body?: never;
    path: {
        /**
         * Run Id
         */
        run_id: string;
    };
    query?: never;
    url: '/api/history/{run_id}';
};

export type GetRunErrors = {
    /**
     * Not Found
     */
    404: ApiFailureEnvelope;
    /**
     * Unprocessable Content
     */
    422: ApiFailureEnvelope;
    /**
     * Internal Server Error
     */
    500: ApiFailureEnvelope;
};

export type GetRunError = GetRunErrors[keyof GetRunErrors];

export type GetRunResponses = {
    /**
     * Successful Response
     */
    200: ApiEnvelopeRunDetailData;
};

export type GetRunResponse = GetRunResponses[keyof GetRunResponses];

export type GetRunEventsData = {
    body?: never;
    path: {
        /**
         * Run Id
         */
        run_id: string;
    };
    query?: {
        /**
         * Status
         */
        status?: FileEventStatus | null;
        /**
         * Limit
         */
        limit?: number | null;
        /**
         * Cursor
         */
        cursor?: string | null;
    };
    url: '/api/history/{run_id}/events';
};

export type GetRunEventsErrors = {
    /**
     * Not Found
     */
    404: ApiFailureEnvelope;
    /**
     * Unprocessable Content
     */
    422: ApiFailureEnvelope;
    /**
     * Internal Server Error
     */
    500: ApiFailureEnvelope;
};

export type GetRunEventsError = GetRunEventsErrors[keyof GetRunEventsErrors];

export type GetRunEventsResponses = {
    /**
     * Successful Response
     */
    200: ApiEnvelopePaginatedDataFileEventResource;
};

export type GetRunEventsResponse = GetRunEventsResponses[keyof GetRunEventsResponses];

export type GetRunEventFacetsData = {
    body?: never;
    path: {
        /**
         * Run Id
         */
        run_id: string;
    };
    query?: never;
    url: '/api/history/{run_id}/events/facets';
};

export type GetRunEventFacetsErrors = {
    /**
     * Not Found
     */
    404: ApiFailureEnvelope;
    /**
     * Unprocessable Content
     */
    422: ApiFailureEnvelope;
    /**
     * Internal Server Error
     */
    500: ApiFailureEnvelope;
};

export type GetRunEventFacetsError = GetRunEventFacetsErrors[keyof GetRunEventFacetsErrors];

export type GetRunEventFacetsResponses = {
    /**
     * Successful Response
     */
    200: ApiEnvelopeFileEventFacetsData;
};

export type GetRunEventFacetsResponse = GetRunEventFacetsResponses[keyof GetRunEventFacetsResponses];

export type GetRunEventGroupsData = {
    body?: never;
    path: {
        /**
         * Run Id
         */
        run_id: string;
    };
    query: {
        /**
         * Group By
         */
        group_by: 'target_directory';
        /**
         * Limit
         */
        limit?: number | null;
        /**
         * Cursor
         */
        cursor?: string | null;
    };
    url: '/api/history/{run_id}/events/groups';
};

export type GetRunEventGroupsErrors = {
    /**
     * Not Found
     */
    404: ApiFailureEnvelope;
    /**
     * Unprocessable Content
     */
    422: ApiFailureEnvelope;
    /**
     * Internal Server Error
     */
    500: ApiFailureEnvelope;
};

export type GetRunEventGroupsError = GetRunEventGroupsErrors[keyof GetRunEventGroupsErrors];

export type GetRunEventGroupsResponses = {
    /**
     * Successful Response
     */
    200: ApiEnvelopeFileEventGroupsData;
};

export type GetRunEventGroupsResponse = GetRunEventGroupsResponses[keyof GetRunEventGroupsResponses];

export type GetLibrariesData = {
    body?: never;
    path?: never;
    query?: never;
    url: '/api/libraries';
};

export type GetLibrariesErrors = {
    /**
     * Internal Server Error
     */
    500: ApiFailureEnvelope;
};

export type GetLibrariesError = GetLibrariesErrors[keyof GetLibrariesErrors];

export type GetLibrariesResponses = {
    /**
     * Successful Response
     */
    200: ApiEnvelopeLibrariesData;
};

export type GetLibrariesResponse = GetLibrariesResponses[keyof GetLibrariesResponses];

export type GetLibraryData = {
    body?: never;
    path: {
        /**
         * Library Id
         */
        library_id: string;
    };
    query?: never;
    url: '/api/libraries/{library_id}';
};

export type GetLibraryErrors = {
    /**
     * Not Found
     */
    404: ApiFailureEnvelope;
    /**
     * Unprocessable Content
     */
    422: ApiFailureEnvelope;
    /**
     * Internal Server Error
     */
    500: ApiFailureEnvelope;
};

export type GetLibraryError = GetLibraryErrors[keyof GetLibraryErrors];

export type GetLibraryResponses = {
    /**
     * Successful Response
     */
    200: ApiEnvelopeLibraryResource;
};

export type GetLibraryResponse = GetLibraryResponses[keyof GetLibraryResponses];

export type ListPlansData = {
    body?: never;
    path?: never;
    query?: {
        /**
         * Query
         */
        query?: string | null;
        /**
         * Status
         */
        status?: PlanStatus | null;
        /**
         * Type
         */
        type?: PlanType | null;
        /**
         * Blocked
         */
        blocked?: boolean;
        /**
         * Limit
         */
        limit?: number;
        /**
         * Cursor
         */
        cursor?: string | null;
    };
    url: '/api/plans';
};

export type ListPlansErrors = {
    /**
     * Not Found
     */
    404: ApiFailureEnvelope;
    /**
     * Unprocessable Content
     */
    422: ApiFailureEnvelope;
    /**
     * Internal Server Error
     */
    500: ApiFailureEnvelope;
};

export type ListPlansError = ListPlansErrors[keyof ListPlansErrors];

export type ListPlansResponses = {
    /**
     * Successful Response
     */
    200: ApiEnvelopePaginatedDataPlanSummary;
};

export type ListPlansResponse = ListPlansResponses[keyof ListPlansResponses];

export type GetPlanData = {
    body?: never;
    path: {
        /**
         * Plan Id
         */
        plan_id: string;
    };
    query?: never;
    url: '/api/plans/{plan_id}';
};

export type GetPlanErrors = {
    /**
     * Not Found
     */
    404: ApiFailureEnvelope;
    /**
     * Unprocessable Content
     */
    422: ApiFailureEnvelope;
    /**
     * Internal Server Error
     */
    500: ApiFailureEnvelope;
};

export type GetPlanError = GetPlanErrors[keyof GetPlanErrors];

export type GetPlanResponses = {
    /**
     * Successful Response
     */
    200: ApiEnvelopePlanDetailData;
};

export type GetPlanResponse = GetPlanResponses[keyof GetPlanResponses];

export type ListPlanActionsData = {
    body?: never;
    path: {
        /**
         * Plan Id
         */
        plan_id: string;
    };
    query?: {
        /**
         * Query
         */
        query?: string | null;
        /**
         * Status
         */
        status?: ActionStatus | null;
        /**
         * Action Type
         */
        action_type?: ActionType | null;
        /**
         * Reason
         */
        reason?: PlanActionReason | null;
        /**
         * Group By
         */
        group_by?: PlanActionGrouping | null;
        /**
         * Group Key
         */
        group_key?: string | null;
        /**
         * Limit
         */
        limit?: number;
        /**
         * Cursor
         */
        cursor?: string | null;
    };
    url: '/api/plans/{plan_id}/actions';
};

export type ListPlanActionsErrors = {
    /**
     * Not Found
     */
    404: ApiFailureEnvelope;
    /**
     * Unprocessable Content
     */
    422: ApiFailureEnvelope;
    /**
     * Internal Server Error
     */
    500: ApiFailureEnvelope;
};

export type ListPlanActionsError = ListPlanActionsErrors[keyof ListPlanActionsErrors];

export type ListPlanActionsResponses = {
    /**
     * Successful Response
     */
    200: ApiEnvelopePaginatedDataPlanActionResource;
};

export type ListPlanActionsResponse = ListPlanActionsResponses[keyof ListPlanActionsResponses];

export type GetPlanActionFacetsData = {
    body?: never;
    path: {
        /**
         * Plan Id
         */
        plan_id: string;
    };
    query?: {
        /**
         * Query
         */
        query?: string | null;
        /**
         * Status
         */
        status?: ActionStatus | null;
        /**
         * Action Type
         */
        action_type?: ActionType | null;
        /**
         * Reason
         */
        reason?: PlanActionReason | null;
    };
    url: '/api/plans/{plan_id}/facets';
};

export type GetPlanActionFacetsErrors = {
    /**
     * Not Found
     */
    404: ApiFailureEnvelope;
    /**
     * Unprocessable Content
     */
    422: ApiFailureEnvelope;
    /**
     * Internal Server Error
     */
    500: ApiFailureEnvelope;
};

export type GetPlanActionFacetsError = GetPlanActionFacetsErrors[keyof GetPlanActionFacetsErrors];

export type GetPlanActionFacetsResponses = {
    /**
     * Successful Response
     */
    200: ApiEnvelopePlanActionFacetsData;
};

export type GetPlanActionFacetsResponse = GetPlanActionFacetsResponses[keyof GetPlanActionFacetsResponses];

export type GroupPlanActionsData = {
    body?: never;
    path: {
        /**
         * Plan Id
         */
        plan_id: string;
    };
    query: {
        group_by: PlanActionGrouping;
        /**
         * Query
         */
        query?: string | null;
        /**
         * Status
         */
        status?: ActionStatus | null;
        /**
         * Action Type
         */
        action_type?: ActionType | null;
        /**
         * Reason
         */
        reason?: PlanActionReason | null;
        /**
         * Limit
         */
        limit?: number;
        /**
         * Cursor
         */
        cursor?: string | null;
    };
    url: '/api/plans/{plan_id}/groups';
};

export type GroupPlanActionsErrors = {
    /**
     * Not Found
     */
    404: ApiFailureEnvelope;
    /**
     * Unprocessable Content
     */
    422: ApiFailureEnvelope;
    /**
     * Internal Server Error
     */
    500: ApiFailureEnvelope;
};

export type GroupPlanActionsError = GroupPlanActionsErrors[keyof GroupPlanActionsErrors];

export type GroupPlanActionsResponses = {
    /**
     * Successful Response
     */
    200: ApiEnvelopePlanActionGroupsData;
};

export type GroupPlanActionsResponse = GroupPlanActionsResponses[keyof GroupPlanActionsResponses];

export type ListTracksData = {
    body?: never;
    path?: never;
    query?: {
        /**
         * Query
         */
        query?: string | null;
        /**
         * Status
         */
        status?: TrackStatus | null;
        /**
         * Track Id
         */
        track_id?: string | null;
        /**
         * Library Id
         */
        library_id?: string | null;
        /**
         * Group By
         */
        group_by?: TrackGrouping | null;
        /**
         * Group Key
         */
        group_key?: string | null;
        /**
         * Limit
         */
        limit?: number;
        /**
         * Cursor
         */
        cursor?: string | null;
    };
    url: '/api/tracks';
};

export type ListTracksErrors = {
    /**
     * Not Found
     */
    404: ApiFailureEnvelope;
    /**
     * Unprocessable Content
     */
    422: ApiFailureEnvelope;
    /**
     * Internal Server Error
     */
    500: ApiFailureEnvelope;
};

export type ListTracksError = ListTracksErrors[keyof ListTracksErrors];

export type ListTracksResponses = {
    /**
     * Successful Response
     */
    200: ApiEnvelopePaginatedDataTrackResource;
};

export type ListTracksResponse = ListTracksResponses[keyof ListTracksResponses];

export type GetTrackFacetsData = {
    body?: never;
    path?: never;
    query?: {
        /**
         * Query
         */
        query?: string | null;
        /**
         * Library Id
         */
        library_id?: string | null;
    };
    url: '/api/tracks/facets';
};

export type GetTrackFacetsErrors = {
    /**
     * Not Found
     */
    404: ApiFailureEnvelope;
    /**
     * Unprocessable Content
     */
    422: ApiFailureEnvelope;
    /**
     * Internal Server Error
     */
    500: ApiFailureEnvelope;
};

export type GetTrackFacetsError = GetTrackFacetsErrors[keyof GetTrackFacetsErrors];

export type GetTrackFacetsResponses = {
    /**
     * Successful Response
     */
    200: ApiEnvelopeTrackFacetsData;
};

export type GetTrackFacetsResponse = GetTrackFacetsResponses[keyof GetTrackFacetsResponses];

export type GetTrackGroupsData = {
    body?: never;
    path?: never;
    query: {
        group_by: TrackGrouping;
        /**
         * Parent Key
         */
        parent_key?: string | null;
        /**
         * Query
         */
        query?: string | null;
        /**
         * Status
         */
        status?: TrackStatus | null;
        /**
         * Library Id
         */
        library_id?: string | null;
        /**
         * Limit
         */
        limit?: number;
        /**
         * Cursor
         */
        cursor?: string | null;
    };
    url: '/api/tracks/groups';
};

export type GetTrackGroupsErrors = {
    /**
     * Not Found
     */
    404: ApiFailureEnvelope;
    /**
     * Unprocessable Content
     */
    422: ApiFailureEnvelope;
    /**
     * Internal Server Error
     */
    500: ApiFailureEnvelope;
};

export type GetTrackGroupsError = GetTrackGroupsErrors[keyof GetTrackGroupsErrors];

export type GetTrackGroupsResponses = {
    /**
     * Successful Response
     */
    200: ApiEnvelopeTrackGroupsData;
};

export type GetTrackGroupsResponse = GetTrackGroupsResponses[keyof GetTrackGroupsResponses];

export type GetTrackData = {
    body?: never;
    path: {
        /**
         * Track Id
         */
        track_id: string;
    };
    query?: never;
    url: '/api/tracks/{track_id}';
};

export type GetTrackErrors = {
    /**
     * Not Found
     */
    404: ApiFailureEnvelope;
    /**
     * Unprocessable Content
     */
    422: ApiFailureEnvelope;
    /**
     * Internal Server Error
     */
    500: ApiFailureEnvelope;
};

export type GetTrackError = GetTrackErrors[keyof GetTrackErrors];

export type GetTrackResponses = {
    /**
     * Successful Response
     */
    200: ApiEnvelopeTrackResource;
};

export type GetTrackResponse = GetTrackResponses[keyof GetTrackResponses];
