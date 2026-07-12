/**
 * Summary: Auto-generates typed API client code from the committed OpenAPI contract.
 * Why: Keeps frontend transport types synchronized with backend Pydantic schemas.
 */

export type ClientOptions = {
    baseUrl: `${string}://${string}` | (string & {});
};

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
