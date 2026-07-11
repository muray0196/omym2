/*
Summary: Calls the local OMYM2 Web API from the Next console.
Why: Connects settings UI state to persisted TOML while preserving static previews.
*/

import {
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
  mockGetRunEventFacets,
  mockGetRunEventGroups,
  mockGetTrackFacets,
  mockGetTrackGroups,
  mockGetTracksPage,
  mockGenerateArtistIds,
  mockPlanDetailResponse,
  mockRunCheck,
  mockRunDetailResponse,
  mockSaveSettings,
  mockSettingsState,
  mockValidateSettings,
  mockPreviewSettings,
} from "./mock-data"
import type {
  AppConfig,
  ArtistIdGenerationResult,
  CheckFacetsResponse,
  CheckIssueType,
  CheckPageResponse,
  CheckRunResponse,
  FacetsResponse,
  FileEvent,
  FileEventStatus,
  GroupsResponse,
  PagedResponse,
  PlanAction,
  PlanActionStatus,
  PlanCreateResult,
  PlanDetailResponse,
  PlanFacetsResponse,
  PlanGroupBy,
  PlanGroupsResponse,
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

export async function getRunDetail(runId: string): Promise<RunDetailResponse> {
  if (isMockApiMode()) {
    return clonePayload(mockRunDetailResponse(runId))
  }
  return requestJson<RunDetailResponse>(`/api/history/${encodeURIComponent(runId)}`)
}

export async function getPlanDetail(planId: string): Promise<PlanDetailResponse> {
  if (isMockApiMode()) {
    return clonePayload(mockPlanDetailResponse(planId))
  }
  return requestJson<PlanDetailResponse>(`/api/plans/${encodeURIComponent(planId)}`)
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
// Screens use these cursor-paginated/faceted/grouped endpoints directly; the
// previous top-level array responses were removed with the browsing contract.

export async function getTracksPage(
  options: {
    query?: string
    status?: TrackStatus | "all"
    libraryId?: string
    trackId?: string
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
  if (options.trackId) {
    params.set("track_id", options.trackId)
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
  options: {
    status?: PlanActionStatus | "all"
    /** Drill-down pair: pass `groupBy` and `groupKey` together or not at all. */
    groupBy?: PlanGroupBy
    groupKey?: string
    limit?: number
    cursor?: string
  } = {},
): Promise<PagedResponse<PlanAction>> {
  if (isMockApiMode()) {
    return clonePayload(mockGetPlanActionsPage(planId, options))
  }
  const params = new URLSearchParams()
  if (options.status && options.status !== "all") {
    params.set("status", options.status)
  }
  if (options.groupBy && options.groupKey !== undefined) {
    params.set("group_by", options.groupBy)
    params.set("group_key", options.groupKey)
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

export async function getPlanFacets(planId: string): Promise<PlanFacetsResponse> {
  if (isMockApiMode()) {
    return clonePayload(mockGetPlanFacets(planId))
  }
  return requestJson<PlanFacetsResponse>(`/api/plans/${encodeURIComponent(planId)}/facets`)
}

export async function getPlanGroups(
  planId: string,
  options: { groupBy: PlanGroupBy; limit?: number; cursor?: string },
): Promise<PlanGroupsResponse> {
  if (isMockApiMode()) {
    return clonePayload(mockGetPlanGroups(planId, options))
  }
  const params = new URLSearchParams({ group_by: options.groupBy })
  if (options.limit) {
    params.set("limit", String(options.limit))
  }
  if (options.cursor) {
    params.set("cursor", options.cursor)
  }
  return requestJson<PlanGroupsResponse>(
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
    planId?: string
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
  if (options.planId) {
    params.set("plan_id", options.planId)
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

export async function getRunEventFacets(runId: string): Promise<FacetsResponse> {
  if (isMockApiMode()) {
    return clonePayload(mockGetRunEventFacets(runId))
  }
  return requestJson<FacetsResponse>(`/api/history/${encodeURIComponent(runId)}/events/facets`)
}

export async function getRunEventGroups(
  runId: string,
  options: { limit?: number; cursor?: string } = {},
): Promise<GroupsResponse> {
  if (isMockApiMode()) {
    return clonePayload(mockGetRunEventGroups(runId, options))
  }
  const params = new URLSearchParams({ group_by: "target_directory" })
  if (options.limit) {
    params.set("limit", String(options.limit))
  }
  if (options.cursor) {
    params.set("cursor", options.cursor)
  }
  return requestJson<GroupsResponse>(
    `/api/history/${encodeURIComponent(runId)}/events/groups?${params.toString()}`,
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

function clonePayload<T>(payload: T): T {
  return structuredClone(payload)
}
