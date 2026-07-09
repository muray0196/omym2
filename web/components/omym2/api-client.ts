/*
Summary: Calls the local OMYM2 Web API from the Next console.
Why: Connects settings UI state to persisted TOML while preserving static previews.
*/

import {
  mockCheckResponse,
  mockCreatePlan,
  mockGetCheckFacets,
  mockGetCheckGroups,
  mockGetCheckPage,
  mockGetHistoryFacets,
  mockGetHistoryPage,
  mockGetPlanActionsPage,
  mockGetPlanFacets,
  mockGetPlanGroups,
  mockGetPlansPage,
  mockGetRunEventsPage,
  mockGetTrackFacets,
  mockGetTrackGroups,
  mockGetTracksPage,
  mockHistoryResponse,
  mockGenerateArtistIds,
  mockPlanDetailResponse,
  mockPlansResponse,
  mockRunCheck,
  mockRunDetailResponse,
  mockSaveSettings,
  mockSettingsState,
  mockTracksResponse,
  mockValidateSettings,
  mockPreviewSettings,
} from "./mock-data"
import type {
  AppConfig,
  ArtistIdGenerationResult,
  CheckFacetsResponse,
  CheckIssueType,
  CheckPageResponse,
  CheckResponse,
  CheckRunResponse,
  FacetsResponse,
  FileEvent,
  FileEventStatus,
  GroupsResponse,
  HistoryResponse,
  PagedResponse,
  PlanAction,
  PlanActionStatus,
  PlanCreateResult,
  PlanDetailResponse,
  PlansResponse,
  PlanStatus,
  PlanSummary,
  PlanType,
  RunDetailResponse,
  RunStatus,
  RunSummary,
  SampleMetadata,
  SettingsPreviewResult,
  SettingsSaveResult,
  SettingsState,
  SettingsValidateResult,
  TracksResponse,
  TrackStatus,
  TrackSummary,
} from "./types"

const CSRF_HEADER = "X-OMYM2-CSRF-Token"
const MOCK_API_MODE = "mock"
const LOCAL_API_HOSTNAMES = new Set(["localhost", "127.0.0.1", "::1"])

export async function getSettings(): Promise<SettingsState> {
  if (isMockApiMode()) {
    return clonePayload(mockSettingsState)
  }
  return requestJson<SettingsState>("/api/settings")
}

export async function getHistory(): Promise<HistoryResponse> {
  if (isMockApiMode()) {
    return clonePayload(mockHistoryResponse)
  }
  return requestJson<HistoryResponse>("/api/history")
}

export async function getPlans(
  filters: {
    status?: PlanStatus | "all"
    type?: PlanType | "all"
    limit?: number
  } = {},
): Promise<PlansResponse> {
  if (isMockApiMode()) {
    const response = clonePayload(mockPlansResponse)
    return { ...response, plans: filterPlanRows(response.plans, filters) }
  }
  const params = new URLSearchParams()
  if (filters.status && filters.status !== "all") {
    params.set("status", filters.status)
  }
  if (filters.type && filters.type !== "all") {
    params.set("type", filters.type)
  }
  if (filters.limit) {
    params.set("limit", String(filters.limit))
  }
  const query = params.toString()
  return requestJson<PlansResponse>(query ? `/api/plans?${query}` : "/api/plans")
}

export async function getRunDetail(runId: string): Promise<RunDetailResponse> {
  if (isMockApiMode()) {
    return clonePayload(mockRunDetailResponse(runId))
  }
  return requestJson<RunDetailResponse>(`/api/history/${encodeURIComponent(runId)}`)
}

export async function getPlanDetail(
  planId: string,
  actionStatus?: PlanActionStatus | "all",
): Promise<PlanDetailResponse> {
  if (isMockApiMode()) {
    return clonePayload(mockPlanDetailResponse(planId, actionStatus))
  }
  const params = new URLSearchParams()
  if (actionStatus && actionStatus !== "all") {
    params.set("actions", actionStatus)
  }
  const query = params.toString()
  return requestJson<PlanDetailResponse>(
    `/api/plans/${encodeURIComponent(planId)}${query ? `?${query}` : ""}`,
  )
}

export async function getCheck(): Promise<CheckResponse> {
  if (isMockApiMode()) {
    return clonePayload(mockCheckResponse)
  }
  return requestJson<CheckResponse>("/api/check")
}

export async function getTracks(): Promise<TracksResponse> {
  if (isMockApiMode()) {
    return clonePayload(mockTracksResponse)
  }
  return requestJson<TracksResponse>("/api/tracks")
}

export async function validateSettings(config: AppConfig): Promise<SettingsValidateResult> {
  if (isMockApiMode()) {
    return clonePayload(mockValidateSettings(config))
  }
  return requestJson<SettingsValidateResult>("/api/settings/validate", {
    body: JSON.stringify({ config }),
    method: "POST",
  })
}

export async function previewSettings(
  config: AppConfig,
  metadata?: SampleMetadata,
): Promise<SettingsPreviewResult> {
  if (isMockApiMode()) {
    return clonePayload(mockPreviewSettings())
  }
  return requestJson<SettingsPreviewResult>("/api/settings/preview", {
    body: JSON.stringify(metadata ? { config, metadata } : { config }),
    method: "POST",
  })
}

export async function saveSettings(
  config: AppConfig,
  csrfToken: string,
): Promise<SettingsSaveResult> {
  if (isMockApiMode()) {
    return clonePayload(mockSaveSettings(config))
  }
  return requestJson<SettingsSaveResult>("/api/settings/save", {
    body: JSON.stringify({ config }),
    headers: { [CSRF_HEADER]: csrfToken },
    method: "POST",
  })
}

export async function generateArtistIds(
  artistNames: string[],
  overwrite: boolean,
  csrfToken: string,
): Promise<ArtistIdGenerationResult> {
  if (isMockApiMode()) {
    return clonePayload(mockGenerateArtistIds(artistNames))
  }
  return requestJson<ArtistIdGenerationResult>("/api/settings/artist-ids/generate", {
    body: JSON.stringify({ artist_names: artistNames, overwrite }),
    headers: { [CSRF_HEADER]: csrfToken },
    method: "POST",
  })
}

export async function createAddPlan(
  sourcePath: string | null,
  csrfToken: string,
): Promise<PlanCreateResult> {
  if (isMockApiMode()) {
    return clonePayload(mockCreatePlan("add"))
  }
  return requestJson<PlanCreateResult>("/api/plans/add", {
    body: JSON.stringify({ source_path: sourcePath }),
    headers: { [CSRF_HEADER]: csrfToken },
    method: "POST",
  })
}

export async function createOrganizePlan(
  libraryRoot: string | null,
  csrfToken: string,
): Promise<PlanCreateResult> {
  if (isMockApiMode()) {
    return clonePayload(mockCreatePlan("organize"))
  }
  return requestJson<PlanCreateResult>("/api/plans/organize", {
    body: JSON.stringify({ library_root: libraryRoot }),
    headers: { [CSRF_HEADER]: csrfToken },
    method: "POST",
  })
}

export async function createRefreshPlan(
  targetPath: string | null,
  includeAll: boolean,
  csrfToken: string,
): Promise<PlanCreateResult> {
  if (isMockApiMode()) {
    return clonePayload(mockCreatePlan("refresh"))
  }
  return requestJson<PlanCreateResult>("/api/plans/refresh", {
    body: JSON.stringify({ target_path: targetPath, include_all: includeAll }),
    headers: { [CSRF_HEADER]: csrfToken },
    method: "POST",
  })
}

// --- Paginated Web API (D6) --------------------------------------------------
// Additive alongside the legacy getTracks/getPlans/getCheck/getHistory
// methods above; those keep working unchanged. Screens are wired to these
// paged/faceted/grouped endpoints in a later dispatch.

export async function getTracksPage(
  options: {
    query?: string
    status?: TrackStatus | "all"
    libraryId?: string
    limit?: number
    cursor?: string
  } = {},
): Promise<PagedResponse<TrackSummary>> {
  if (isMockApiMode()) {
    return clonePayload(mockGetTracksPage(options))
  }
  const params = new URLSearchParams()
  if (options.query) {
    params.set("query", options.query)
  }
  if (options.status && options.status !== "all") {
    params.set("status", options.status)
  }
  if (options.libraryId) {
    params.set("library_id", options.libraryId)
  }
  if (options.limit) {
    params.set("limit", String(options.limit))
  }
  if (options.cursor) {
    params.set("cursor", options.cursor)
  }
  const query = params.toString()
  return requestJson<PagedResponse<TrackSummary>>(query ? `/api/tracks?${query}` : "/api/tracks")
}

export async function getTrackFacets(
  options: { libraryId?: string } = {},
): Promise<FacetsResponse> {
  if (isMockApiMode()) {
    return clonePayload(mockGetTrackFacets(options))
  }
  const params = new URLSearchParams()
  if (options.libraryId) {
    params.set("library_id", options.libraryId)
  }
  const query = params.toString()
  return requestJson<FacetsResponse>(query ? `/api/tracks/facets?${query}` : "/api/tracks/facets")
}

export async function getTrackGroups(
  options: { libraryId?: string; limit?: number; cursor?: string } = {},
): Promise<GroupsResponse> {
  if (isMockApiMode()) {
    return clonePayload(mockGetTrackGroups(options))
  }
  const params = new URLSearchParams({ group_by: "artist_album" })
  if (options.libraryId) {
    params.set("library_id", options.libraryId)
  }
  if (options.limit) {
    params.set("limit", String(options.limit))
  }
  if (options.cursor) {
    params.set("cursor", options.cursor)
  }
  return requestJson<GroupsResponse>(`/api/tracks/groups?${params.toString()}`)
}

export async function getPlansPage(
  options: {
    status?: PlanStatus | "all"
    type?: PlanType | "all"
    limit?: number
    cursor?: string
  } = {},
): Promise<PagedResponse<PlanSummary>> {
  if (isMockApiMode()) {
    return clonePayload(mockGetPlansPage(options))
  }
  const params = new URLSearchParams()
  if (options.status && options.status !== "all") {
    params.set("status", options.status)
  }
  if (options.type && options.type !== "all") {
    params.set("type", options.type)
  }
  if (options.limit) {
    params.set("limit", String(options.limit))
  }
  if (options.cursor) {
    params.set("cursor", options.cursor)
  }
  const query = params.toString()
  return requestJson<PagedResponse<PlanSummary>>(query ? `/api/plans?${query}` : "/api/plans")
}

export async function getPlanActionsPage(
  planId: string,
  options: { status?: PlanActionStatus | "all"; limit?: number; cursor?: string } = {},
): Promise<PagedResponse<PlanAction>> {
  if (isMockApiMode()) {
    return clonePayload(mockGetPlanActionsPage(planId, options))
  }
  const params = new URLSearchParams()
  if (options.status && options.status !== "all") {
    params.set("status", options.status)
  }
  if (options.limit) {
    params.set("limit", String(options.limit))
  }
  if (options.cursor) {
    params.set("cursor", options.cursor)
  }
  const query = params.toString()
  return requestJson<PagedResponse<PlanAction>>(
    `/api/plans/${encodeURIComponent(planId)}/actions${query ? `?${query}` : ""}`,
  )
}

export async function getPlanFacets(planId: string): Promise<FacetsResponse> {
  if (isMockApiMode()) {
    return clonePayload(mockGetPlanFacets(planId))
  }
  return requestJson<FacetsResponse>(`/api/plans/${encodeURIComponent(planId)}/facets`)
}

export async function getPlanGroups(
  planId: string,
  options: { limit?: number; cursor?: string } = {},
): Promise<GroupsResponse> {
  if (isMockApiMode()) {
    return clonePayload(mockGetPlanGroups(planId, options))
  }
  const params = new URLSearchParams({ group_by: "target_directory" })
  if (options.limit) {
    params.set("limit", String(options.limit))
  }
  if (options.cursor) {
    params.set("cursor", options.cursor)
  }
  return requestJson<GroupsResponse>(
    `/api/plans/${encodeURIComponent(planId)}/groups?${params.toString()}`,
  )
}

export async function getCheckPage(
  options: {
    issueType?: CheckIssueType | "all"
    libraryId?: string
    limit?: number
    cursor?: string
  } = {},
): Promise<CheckPageResponse> {
  if (isMockApiMode()) {
    return clonePayload(mockGetCheckPage(options))
  }
  const params = new URLSearchParams()
  if (options.issueType && options.issueType !== "all") {
    params.set("issue_type", options.issueType)
  }
  if (options.libraryId) {
    params.set("library_id", options.libraryId)
  }
  if (options.limit) {
    params.set("limit", String(options.limit))
  }
  if (options.cursor) {
    params.set("cursor", options.cursor)
  }
  const query = params.toString()
  return requestJson<CheckPageResponse>(query ? `/api/check?${query}` : "/api/check")
}

export async function getCheckFacets(
  options: { libraryId?: string } = {},
): Promise<CheckFacetsResponse> {
  if (isMockApiMode()) {
    return clonePayload(mockGetCheckFacets(options))
  }
  const params = new URLSearchParams()
  if (options.libraryId) {
    params.set("library_id", options.libraryId)
  }
  const query = params.toString()
  return requestJson<CheckFacetsResponse>(
    query ? `/api/check/facets?${query}` : "/api/check/facets",
  )
}

export async function getCheckGroups(
  options: { libraryId?: string; limit?: number; cursor?: string } = {},
): Promise<GroupsResponse> {
  if (isMockApiMode()) {
    return clonePayload(mockGetCheckGroups(options))
  }
  const params = new URLSearchParams({ group_by: "issue_type" })
  if (options.libraryId) {
    params.set("library_id", options.libraryId)
  }
  if (options.limit) {
    params.set("limit", String(options.limit))
  }
  if (options.cursor) {
    params.set("cursor", options.cursor)
  }
  return requestJson<GroupsResponse>(`/api/check/groups?${params.toString()}`)
}

export async function runCheck(csrfToken: string, libraryId?: string): Promise<CheckRunResponse> {
  if (isMockApiMode()) {
    return clonePayload(mockRunCheck(libraryId))
  }
  return requestJson<CheckRunResponse>("/api/check/run", {
    body: JSON.stringify(libraryId ? { library_id: libraryId } : {}),
    headers: { [CSRF_HEADER]: csrfToken },
    method: "POST",
  })
}

export async function getHistoryPage(
  options: {
    status?: RunStatus | "all"
    libraryId?: string
    limit?: number
    cursor?: string
  } = {},
): Promise<PagedResponse<RunSummary>> {
  if (isMockApiMode()) {
    return clonePayload(mockGetHistoryPage(options))
  }
  const params = new URLSearchParams()
  if (options.status && options.status !== "all") {
    params.set("status", options.status)
  }
  if (options.libraryId) {
    params.set("library_id", options.libraryId)
  }
  if (options.limit) {
    params.set("limit", String(options.limit))
  }
  if (options.cursor) {
    params.set("cursor", options.cursor)
  }
  const query = params.toString()
  return requestJson<PagedResponse<RunSummary>>(query ? `/api/history?${query}` : "/api/history")
}

export async function getHistoryFacets(
  options: { libraryId?: string } = {},
): Promise<FacetsResponse> {
  if (isMockApiMode()) {
    return clonePayload(mockGetHistoryFacets(options))
  }
  const params = new URLSearchParams()
  if (options.libraryId) {
    params.set("library_id", options.libraryId)
  }
  const query = params.toString()
  return requestJson<FacetsResponse>(query ? `/api/history/facets?${query}` : "/api/history/facets")
}

export async function getRunEventsPage(
  runId: string,
  options: { status?: FileEventStatus | "all"; limit?: number; cursor?: string } = {},
): Promise<PagedResponse<FileEvent>> {
  if (isMockApiMode()) {
    return clonePayload(mockGetRunEventsPage(runId, options))
  }
  const params = new URLSearchParams()
  if (options.status && options.status !== "all") {
    params.set("status", options.status)
  }
  if (options.limit) {
    params.set("limit", String(options.limit))
  }
  if (options.cursor) {
    params.set("cursor", options.cursor)
  }
  const query = params.toString()
  return requestJson<PagedResponse<FileEvent>>(
    `/api/history/${encodeURIComponent(runId)}/events${query ? `?${query}` : ""}`,
  )
}

async function requestJson<T>(url: string, init: RequestInit = {}): Promise<T> {
  const headers = new Headers(init.headers)
  if (!headers.has("Content-Type")) {
    headers.set("Content-Type", "application/json")
  }

  const response = await fetch(url, { ...init, headers })
  const body = await response.text()
  if (body.trim() === "") {
    throw new Error(
      `OMYM2 Web API returned an empty response for ${url} (HTTP ${response.status}).`,
    )
  }
  if (!isJsonContentType(response.headers.get("content-type") ?? "")) {
    throw new Error(
      `OMYM2 Web API returned a non-JSON response for ${url} (HTTP ${response.status}).`,
    )
  }

  try {
    return JSON.parse(body) as T
  } catch {
    throw new Error(`OMYM2 Web API returned invalid JSON for ${url} (HTTP ${response.status}).`)
  }
}

function isMockApiMode(): boolean {
  if (process.env.NEXT_PUBLIC_OMYM2_API_MODE === MOCK_API_MODE) {
    return true
  }
  if (typeof window === "undefined") {
    return false
  }
  return !LOCAL_API_HOSTNAMES.has(window.location.hostname)
}

function isJsonContentType(contentType: string): boolean {
  const mediaType = contentType.split(";")[0]?.trim().toLowerCase() ?? ""
  return mediaType === "application/json" || mediaType.endsWith("+json")
}

function filterPlanRows(
  plans: PlansResponse["plans"],
  filters: {
    status?: PlanStatus | "all"
    type?: PlanType | "all"
    limit?: number
  },
): PlansResponse["plans"] {
  let filtered = plans
  if (filters.status && filters.status !== "all") {
    filtered = filtered.filter((plan) => plan.status === filters.status)
  }
  if (filters.type && filters.type !== "all") {
    filtered = filtered.filter((plan) => plan.plan_type === filters.type)
  }
  if (filters.limit && filters.limit > 0) {
    filtered = filtered.slice(0, filters.limit)
  }
  return filtered
}

function clonePayload<T>(payload: T): T {
  return structuredClone(payload)
}
