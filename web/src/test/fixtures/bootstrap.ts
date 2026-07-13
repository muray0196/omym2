/**
 * Summary: Defines deterministic Bootstrap fixtures from generated API types.
 * Why: Makes normal and recovery tests drift when the backend contract changes.
 */
import type { ApiEnvelopeBootstrapData } from "../../api/generated";

const fixturePollingPolicy = {
  initial_ms: 17,
  backoff_factor: 3,
  max_ms: 91,
} as const;

export const normalBootstrap = {
  data: {
    active_library: {
      library_id: "018f0000-0000-7000-8000-000000000001",
      root_path: "/music/library",
      status: "registered",
      is_registered: true,
      registered_at: "2026-07-12T00:00:00Z",
      path_policy_fingerprint: "fixture-path-policy-fingerprint",
      is_path_policy_current: true,
    },
    active_operation_id: null,
    app_version: "0.1.0-test",
    config_validation: {
      config_revision: "fixture-config-revision",
      errors: [],
      valid: true,
    },
    csrf_token: "fixture-csrf-token",
    library_diagnostics: [],
    operation_polling: fixturePollingPolicy,
    runtime_capabilities: {
      can_change_settings: true,
      can_read_state: true,
      can_start_organize: true,
      can_start_operations: true,
      disabled_reasons: [],
    },
    status_catalog_version: 1,
  },
  errors: [],
} satisfies ApiEnvelopeBootstrapData;

const libraryUnregisteredError = {
  code: "library_unregistered",
  message: "No registered Library is available.",
  retryable: false,
  remediation: {
    label: "Create an Organize Plan",
    route: "/plans/new/organize",
  },
} as const;

export const missingConfigBootstrap = {
  data: {
    ...normalBootstrap.data,
    active_library: null,
    config_validation: {
      config_revision: "fixture-missing-config-revision",
      errors: [],
      valid: true,
    },
    library_diagnostics: [libraryUnregisteredError],
    runtime_capabilities: {
      ...normalBootstrap.data.runtime_capabilities,
      can_start_operations: false,
      disabled_reasons: [
        {
          ...libraryUnregisteredError,
          field: "runtime_capabilities.can_start_operations",
        },
      ],
    },
  },
  errors: [],
} satisfies ApiEnvelopeBootstrapData;

export const unregisteredBootstrap = missingConfigBootstrap;

const configInvalidError = {
  code: "config_invalid",
  field: "config",
  message: "Invalid TOML: Invalid value (at end of document)",
  retryable: false,
  remediation: {
    label: "Review Settings",
    route: "/settings",
  },
} as const;

const configInvalidCapabilityError = {
  code: "config_invalid",
  field: "runtime_capabilities.can_start_operations",
  message: "Configuration is invalid.",
  retryable: false,
  remediation: configInvalidError.remediation,
} as const;

const configInvalidOrganizeCapabilityError = {
  ...configInvalidCapabilityError,
  field: "runtime_capabilities.can_start_organize",
} as const;

const libraryUnregisteredCapabilityError = {
  ...libraryUnregisteredError,
  field: "runtime_capabilities.can_start_operations",
} as const;

export const degradedBootstrap = {
  data: {
    active_library: null,
    active_operation_id: null,
    app_version: "0.1.0-test",
    config_validation: {
      config_revision: "fixture-invalid-config-revision",
      errors: [configInvalidError],
      valid: false,
    },
    csrf_token: "fixture-recovery-csrf-token",
    library_diagnostics: [libraryUnregisteredError],
    operation_polling: fixturePollingPolicy,
    runtime_capabilities: {
      can_change_settings: true,
      can_read_state: true,
      can_start_organize: false,
      can_start_operations: false,
      disabled_reasons: [
        configInvalidCapabilityError,
        libraryUnregisteredCapabilityError,
        configInvalidOrganizeCapabilityError,
      ],
    },
    status_catalog_version: 1,
  },
  errors: [configInvalidError],
} satisfies ApiEnvelopeBootstrapData;
