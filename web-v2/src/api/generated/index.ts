/**
 * Summary: Auto-generates typed API client code from the committed OpenAPI contract.
 * Why: Keeps frontend transport types synchronized with backend Pydantic schemas.
 */

export { getBootstrap, type Options } from './sdk.gen';
export type { ApiEnvelopeBootstrapData, ApiError, ApiErrorCode, ApiFailureEnvelope, ApiRemediation, BootstrapData, ClientOptions, ConfigValidationResource, GetBootstrapData, GetBootstrapError, GetBootstrapErrors, GetBootstrapResponse, GetBootstrapResponses, LibraryResource, LibraryStatus, OperationPollingPolicy, RuntimeCapabilities } from './types.gen';
