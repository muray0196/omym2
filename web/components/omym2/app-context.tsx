/*
Summary: Provides shell state and navigation for the OMYM2 console.
Why: Shares settings, CSRF, and detail fallbacks across client screens.
*/

"use client"

import {
  createContext,
  useCallback,
  useContext,
  useEffect,
  useMemo,
  useState,
  type ReactNode,
} from "react"
import {
  createAddPlan as createAddPlanRequest,
  createOrganizePlan as createOrganizePlanRequest,
  createRefreshPlan as createRefreshPlanRequest,
  getHistoryPage,
  getPlanDetail,
  getRunDetail,
  getSettings,
  generateArtistIds as generateArtistIdsRequest,
  saveSettings as saveSettingsRequest,
  validateSettings,
} from "./api-client"
import { savedArtistIdEntries } from "./lib"
import { defaultConfig, mockSettingsState } from "./mock-data"
import type {
  AppConfig,
  CheckGroupBy,
  CheckIssueType,
  CheckViewMode,
  PathPreview,
  PlanActionStatus,
  PlanCreateResult,
  PlanDetail,
  PlanSummary,
  RunDetail,
  RunSummary,
  SettingsChange,
  SettingsChoices,
  ValidationResult,
} from "./types"

const INITIAL_RUN_LIMIT = 30
const RUN_POLL_INTERVAL_MS = 5000

export type Route =
  | { name: "dashboard" }
  | { name: "settings" }
  | { name: "path-policy"; trackId?: string }
  | { name: "plans" }
  | { name: "plan-detail"; planId: string; actionId?: string; actionStatus?: PlanActionStatus }
  | { name: "runs" }
  | { name: "run-detail"; runId: string }
  | {
      name: "check"
      query?: string
      issueType?: CheckIssueType
      view?: CheckViewMode
      groupBy?: CheckGroupBy
    }
  | { name: "tracks"; query?: string; trackId?: string }

export type NavKey =
  "dashboard" | "settings" | "path-policy" | "plans" | "runs" | "check" | "tracks"

interface AppContextValue {
  route: Route
  /**
   * Move to a route. `replace: true` swaps the current history entry
   * instead of pushing a new one — use it for in-screen selection changes
   * (e.g. picking a track row) so browsing N items doesn't require N
   * back-presses to leave the screen. Navigation between screens pushes.
   */
  navigate: (route: Route, options?: { replace?: boolean }) => void
  /** The currently persisted (saved) configuration. */
  savedConfig: AppConfig
  /** The in-progress draft being edited. */
  draftConfig: AppConfig
  setDraftConfig: (updater: (prev: AppConfig) => AppConfig) => void
  saveConfig: () => Promise<boolean>
  resetDraft: () => void
  generateArtistIds: (artistNames: string[], overwrite: boolean) => Promise<boolean>
  historyErrors: string[]
  historyLoaded: boolean
  loadHistory: () => Promise<void>
  createAddPlan: (sourcePath: string | null) => Promise<PlanCreateResult>
  createOrganizePlan: (libraryRoot: string | null) => Promise<PlanCreateResult>
  createRefreshPlan: (targetPath: string | null, includeAll: boolean) => Promise<PlanCreateResult>
  loadPlanDetail: (planId: string) => Promise<void>
  planDetailErrors: Record<string, string[]>
  planDetailLoading: Record<string, boolean>
  planDetails: Record<string, PlanDetail | null>
  /** Local Plan snapshot used only as an immediate detail fallback after creation. */
  plans: PlanSummary[]
  loadRunDetail: (runId: string) => Promise<void>
  runDetailErrors: Record<string, string[]>
  runDetailLoading: Record<string, boolean>
  runDetails: Record<string, RunDetail | null>
  /** First Run page used for command palette entries and optimistic detail fallback. */
  runs: RunSummary[]
  settingsChoices: SettingsChoices
  settingsChanges: SettingsChange[]
  settingsErrors: string[]
  settingsLoaded: boolean
  settingsLoadError: string | null
  settingsPreview: PathPreview
  settingsValidation: ValidationResult
  validateDraft: () => Promise<boolean>
}

const AppContext = createContext<AppContextValue | null>(null)

export function useApp(): AppContextValue {
  const ctx = useContext(AppContext)
  if (!ctx) throw new Error("useApp must be used within AppProvider")
  return ctx
}

export function AppProvider({ children }: { children: ReactNode }) {
  const [route, setRoute] = useState<Route>({ name: "dashboard" })
  const [savedConfig, setSavedConfig] = useState<AppConfig>(defaultConfig)
  const [draftConfig, setDraftConfigState] = useState<AppConfig>(defaultConfig)
  const [settingsChoices, setSettingsChoices] = useState<SettingsChoices>(mockSettingsState.choices)
  const [settingsChanges, setSettingsChanges] = useState<SettingsChange[]>([])
  const [settingsErrors, setSettingsErrors] = useState<string[]>([])
  const [settingsLoaded, setSettingsLoaded] = useState(false)
  const [settingsLoadError, setSettingsLoadError] = useState<string | null>(null)
  const [settingsPreview, setSettingsPreview] = useState<PathPreview>(mockSettingsState.preview)
  const [settingsValidation, setSettingsValidation] = useState<ValidationResult>(
    mockSettingsState.validation,
  )
  const [csrfToken, setCsrfToken] = useState(mockSettingsState.csrf_token)
  const [runs, setRuns] = useState<RunSummary[]>([])
  const [historyErrors, setHistoryErrors] = useState<string[]>([])
  const [historyLoaded, setHistoryLoaded] = useState(false)
  const [plans, setPlans] = useState<PlanSummary[]>([])
  const [planDetails, setPlanDetails] = useState<Record<string, PlanDetail | null>>({})
  const [planDetailErrors, setPlanDetailErrors] = useState<Record<string, string[]>>({})
  const [planDetailLoading, setPlanDetailLoading] = useState<Record<string, boolean>>({})
  const [runDetails, setRunDetails] = useState<Record<string, RunDetail | null>>({})
  const [runDetailErrors, setRunDetailErrors] = useState<Record<string, string[]>>({})
  const [runDetailLoading, setRunDetailLoading] = useState<Record<string, boolean>>({})

  useEffect(() => {
    function syncRouteFromLocation() {
      setRoute(routeFromPath(window.location.pathname, window.location.search))
    }

    syncRouteFromLocation()
    window.addEventListener("popstate", syncRouteFromLocation)
    return () => window.removeEventListener("popstate", syncRouteFromLocation)
  }, [])

  useEffect(() => {
    let cancelled = false

    getSettings()
      .then((state) => {
        if (cancelled) return
        setSavedConfig(state.config)
        setDraftConfigState(state.config)
        setSettingsChoices(state.choices)
        setSettingsErrors(state.errors)
        setSettingsLoadError(null)
        setSettingsPreview(state.preview)
        setSettingsValidation(state.validation)
        setCsrfToken(state.csrf_token)
        setSettingsLoaded(true)
      })
      .catch((error: unknown) => {
        if (cancelled) return
        setSettingsLoadError(error instanceof Error ? error.message : "Settings failed to load.")
        // Loading is finished either way; consumers must treat
        // (settingsLoaded && settingsLoadError) as "unavailable" rather
        // than falling back to the fabricated default config values.
        setSettingsLoaded(true)
      })

    return () => {
      cancelled = true
    }
  }, [])

  useEffect(() => {
    let cancelled = false

    async function loadInspectionState() {
      const historyResult = await getHistoryPage({ limit: INITIAL_RUN_LIMIT })
      if (cancelled) return

      setRuns(historyResult.items)
      setHistoryErrors(historyResult.errors)
      setHistoryLoaded(true)
    }

    loadInspectionState().catch((error: unknown) => {
      if (cancelled) return
      setHistoryErrors([errorMessage(error, "Run history failed to load.")])
      setHistoryLoaded(true)
    })
    return () => {
      cancelled = true
    }
  }, [])

  const loadRunDetail = useCallback(async (runId: string) => {
    setRunDetailLoading((current) => ({ ...current, [runId]: true }))
    try {
      const result = await getRunDetail(runId)
      setRunDetails((current) => ({ ...current, [runId]: result.detail }))
      setRunDetailErrors((current) => ({ ...current, [runId]: result.errors }))
    } catch (error: unknown) {
      setRunDetails((current) => ({ ...current, [runId]: null }))
      setRunDetailErrors((current) => ({
        ...current,
        [runId]: [errorMessage(error, "Run detail failed to load.")],
      }))
    } finally {
      setRunDetailLoading((current) => ({ ...current, [runId]: false }))
    }
  }, [])

  const loadHistory = useCallback(async () => {
    try {
      const result = await getHistoryPage({ limit: INITIAL_RUN_LIMIT })
      setRuns(result.items)
      setHistoryErrors(result.errors)
    } catch (error: unknown) {
      setHistoryErrors([errorMessage(error, "Run history failed to load.")])
    } finally {
      setHistoryLoaded(true)
    }
  }, [])

  // Runs list has no polling by default. While any run is "running" (the
  // only non-terminal RunStatus), refetch history on a short cadence so
  // in-progress apply attempts eventually show up as succeeded/failed
  // without a manual refresh. Stops as soon as no run is running.
  const hasRunningRun = runs.some((run) => run.status === "running")
  useEffect(() => {
    if (!hasRunningRun) return
    const interval = setInterval(() => {
      void loadHistory()
    }, RUN_POLL_INTERVAL_MS)
    return () => clearInterval(interval)
  }, [hasRunningRun, loadHistory])

  const loadPlanDetail = useCallback(async (planId: string) => {
    setPlanDetailLoading((current) => ({ ...current, [planId]: true }))
    try {
      const result = await getPlanDetail(planId)
      setPlanDetails((current) => ({ ...current, [planId]: result.detail }))
      setPlanDetailErrors((current) => ({ ...current, [planId]: result.errors }))
    } catch (error: unknown) {
      setPlanDetails((current) => ({ ...current, [planId]: null }))
      setPlanDetailErrors((current) => ({
        ...current,
        [planId]: [errorMessage(error, "Plan detail failed to load.")],
      }))
    } finally {
      setPlanDetailLoading((current) => ({ ...current, [planId]: false }))
    }
  }, [])

  const recordCreatedPlan = useCallback((result: PlanCreateResult) => {
    const detail = result.detail
    if (!detail) return
    setPlans((current) => upsertPlan(current, detail.plan))
    setPlanDetails((current) => ({ ...current, [detail.plan.plan_id]: detail }))
    setPlanDetailErrors((current) => ({ ...current, [detail.plan.plan_id]: result.errors }))
  }, [])

  const createAddPlan = useCallback(
    async (sourcePath: string | null) => {
      try {
        const result = await createAddPlanRequest(sourcePath, csrfToken)
        recordCreatedPlan(result)
        return result
      } catch (error: unknown) {
        const result: PlanCreateResult = {
          created: false,
          detail: null,
          registration: null,
          errors: [errorMessage(error, "Add Plan creation failed.")],
        }
        return result
      }
    },
    [csrfToken, recordCreatedPlan],
  )

  const createOrganizePlan = useCallback(
    async (libraryRoot: string | null) => {
      try {
        const result = await createOrganizePlanRequest(libraryRoot, csrfToken)
        recordCreatedPlan(result)
        return result
      } catch (error: unknown) {
        const result: PlanCreateResult = {
          created: false,
          detail: null,
          registration: null,
          errors: [errorMessage(error, "Organize Plan creation failed.")],
        }
        return result
      }
    },
    [csrfToken, recordCreatedPlan],
  )

  const createRefreshPlan = useCallback(
    async (targetPath: string | null, includeAll: boolean) => {
      try {
        const result = await createRefreshPlanRequest(targetPath, includeAll, csrfToken)
        recordCreatedPlan(result)
        return result
      } catch (error: unknown) {
        const result: PlanCreateResult = {
          created: false,
          detail: null,
          registration: null,
          errors: [errorMessage(error, "Refresh Plan creation failed.")],
        }
        return result
      }
    },
    [csrfToken, recordCreatedPlan],
  )

  // Apply theme to <html>. This console is dark-only: `:root` is always the
  // Raycast dark palette, so "light" and "system" both render as dark. The
  // only real variant is "oled", which layers pure-black surfaces on top.
  useEffect(() => {
    document.documentElement.classList.toggle("oled", draftConfig.ui.theme === "oled")
  }, [draftConfig.ui.theme])

  const value = useMemo<AppContextValue>(
    () => ({
      route,
      navigate: (next, options) => {
        setRoute(next)
        const path = routeToPath(next)
        if (options?.replace) {
          // Selection, not navigation: keep the history entry (and scroll
          // position) so one back-press still leaves the screen.
          window.history.replaceState({}, "", path)
          return
        }
        window.history.pushState({}, "", path)
        window.scrollTo({ top: 0 })
      },
      savedConfig,
      draftConfig,
      setDraftConfig: (updater) => {
        setDraftConfigState((prev) => updater(prev))
        setSettingsChanges([])
        setSettingsErrors([])
      },
      saveConfig: async () => {
        try {
          const result = await saveSettingsRequest(draftConfig, csrfToken)
          setSettingsChanges(result.changes)
          setSettingsErrors(result.errors)
          if (result.preview) {
            setSettingsPreview(result.preview)
          }
          if (result.validation) {
            setSettingsValidation(result.validation)
          }
          if (result.saved && result.config) {
            setSavedConfig(result.config)
            setDraftConfigState(result.config)
          }
          return result.saved
        } catch (error: unknown) {
          setSettingsErrors([error instanceof Error ? error.message : "Settings save failed."])
          return false
        }
      },
      resetDraft: () => {
        setDraftConfigState(savedConfig)
        setSettingsChanges([])
        setSettingsErrors([])
      },
      generateArtistIds: async (artistNames, overwrite) => {
        try {
          const result = await generateArtistIdsRequest(artistNames, overwrite, csrfToken)
          setSettingsErrors(result.errors)
          if (!result.generated) return false
          const generatedEntries = savedArtistIdEntries(result.entries)
          setSavedConfig((prev) => ({
            ...prev,
            artist_ids: {
              ...prev.artist_ids,
              entries: { ...prev.artist_ids.entries, ...generatedEntries },
            },
          }))
          setDraftConfigState((prev) => ({
            ...prev,
            artist_ids: {
              ...prev.artist_ids,
              entries: { ...prev.artist_ids.entries, ...generatedEntries },
            },
          }))
          setSettingsChanges([])
          return true
        } catch (error: unknown) {
          setSettingsErrors([
            error instanceof Error ? error.message : "Artist ID generation failed.",
          ])
          return false
        }
      },
      createAddPlan,
      createOrganizePlan,
      createRefreshPlan,
      historyErrors,
      historyLoaded,
      loadHistory,
      loadPlanDetail,
      planDetailErrors,
      planDetailLoading,
      planDetails,
      plans,
      loadRunDetail,
      runDetailErrors,
      runDetailLoading,
      runDetails,
      runs,
      settingsChoices,
      settingsChanges,
      settingsErrors,
      settingsLoaded,
      settingsLoadError,
      settingsPreview,
      settingsValidation,
      validateDraft: async () => {
        try {
          const result = await validateSettings(draftConfig)
          setSettingsChanges(result.changes)
          setSettingsErrors(result.errors)
          setSettingsPreview(result.preview)
          setSettingsValidation((current) => ({
            config_hash: current.config_hash,
            errors: result.errors,
            valid: result.valid,
          }))
          return result.valid
        } catch (error: unknown) {
          setSettingsErrors([
            error instanceof Error ? error.message : "Settings validation failed.",
          ])
          return false
        }
      },
    }),
    [
      createAddPlan,
      createOrganizePlan,
      createRefreshPlan,
      csrfToken,
      draftConfig,
      historyErrors,
      historyLoaded,
      loadHistory,
      loadPlanDetail,
      loadRunDetail,
      planDetailErrors,
      planDetailLoading,
      planDetails,
      plans,
      route,
      runDetailErrors,
      runDetailLoading,
      runDetails,
      runs,
      savedConfig,
      settingsChanges,
      settingsChoices,
      settingsErrors,
      settingsLoaded,
      settingsLoadError,
      settingsPreview,
      settingsValidation,
    ],
  )

  return <AppContext.Provider value={value}>{children}</AppContext.Provider>
}

function routeFromPath(pathname: string, search = ""): Route {
  if (pathname === "/settings") return { name: "settings" }
  if (pathname === "/path-policy") {
    const trackId = new URLSearchParams(search).get("track")
    return { name: "path-policy", trackId: trackId ?? undefined }
  }
  if (pathname === "/plans") return { name: "plans" }
  if (pathname.startsWith("/plans/")) {
    const params = new URLSearchParams(search)
    const actionId = params.get("action")
    const actionStatus = planActionStatusFromValue(params.get("status"))
    return {
      name: "plan-detail",
      planId: decodeURIComponent(pathname.replace("/plans/", "")),
      actionId: actionId ?? undefined,
      actionStatus,
    }
  }
  if (pathname === "/history") return { name: "runs" }
  if (pathname.startsWith("/history/")) {
    return { name: "run-detail", runId: decodeURIComponent(pathname.replace("/history/", "")) }
  }
  if (pathname === "/check") {
    const params = new URLSearchParams(search)
    return {
      name: "check",
      query: params.get("query") ?? undefined,
      issueType: checkIssueTypeFromValue(params.get("issue_type")),
      view: checkViewModeFromValue(params.get("view")),
      groupBy: checkGroupByFromValue(params.get("group_by")),
    }
  }
  if (pathname === "/tracks") {
    const params = new URLSearchParams(search)
    return {
      name: "tracks",
      query: params.get("query") ?? undefined,
      trackId: params.get("track") ?? undefined,
    }
  }
  return { name: "dashboard" }
}

function routeToPath(route: Route): string {
  switch (route.name) {
    case "settings":
      return "/settings"
    case "path-policy":
      return route.trackId
        ? `/path-policy?track=${encodeURIComponent(route.trackId)}`
        : "/path-policy"
    case "plans":
      return "/plans"
    case "plan-detail": {
      const params = new URLSearchParams()
      if (route.actionId) params.set("action", route.actionId)
      if (route.actionStatus) params.set("status", route.actionStatus)
      const query = params.toString()
      return `/plans/${encodeURIComponent(route.planId)}${query ? `?${query}` : ""}`
    }
    case "runs":
      return "/history"
    case "run-detail":
      return `/history/${encodeURIComponent(route.runId)}`
    case "check": {
      const params = new URLSearchParams()
      if (route.query) params.set("query", route.query)
      if (route.issueType) params.set("issue_type", route.issueType)
      if (route.view) params.set("view", route.view)
      if (route.groupBy) params.set("group_by", route.groupBy)
      const query = params.toString()
      return `/check${query ? `?${query}` : ""}`
    }
    case "tracks": {
      const params = new URLSearchParams()
      if (route.query) params.set("query", route.query)
      if (route.trackId) params.set("track", route.trackId)
      const query = params.toString()
      return `/tracks${query ? `?${query}` : ""}`
    }
    case "dashboard":
    default:
      return "/"
  }
}

function errorMessage(error: unknown, fallback: string): string {
  return error instanceof Error ? error.message : fallback
}

const PLAN_ACTION_STATUSES: PlanActionStatus[] = ["planned", "blocked", "applied", "failed"]
const CHECK_ISSUE_TYPES: CheckIssueType[] = [
  "db_file_missing",
  "unmanaged_file_exists",
  "content_hash_changed",
  "metadata_hash_changed",
  "current_path_differs_from_canonical_path",
  "duplicate_candidate",
  "plan_source_changed",
  "pending_file_event_exists",
  "library_unregistered",
  "library_stale",
  "library_blocked",
]
const CHECK_VIEW_MODES: CheckViewMode[] = ["triage", "grouped", "table"]
const CHECK_GROUP_BY_VALUES: CheckGroupBy[] = [
  "issue_type",
  "severity",
  "path_root",
  "artist_album",
  "suggested_command",
  "library_id",
]

function planActionStatusFromValue(value: string | null): PlanActionStatus | undefined {
  return value && PLAN_ACTION_STATUSES.includes(value as PlanActionStatus)
    ? (value as PlanActionStatus)
    : undefined
}

function checkIssueTypeFromValue(value: string | null): CheckIssueType | undefined {
  return value && CHECK_ISSUE_TYPES.includes(value as CheckIssueType)
    ? (value as CheckIssueType)
    : undefined
}

function checkViewModeFromValue(value: string | null): CheckViewMode | undefined {
  return value && CHECK_VIEW_MODES.includes(value as CheckViewMode)
    ? (value as CheckViewMode)
    : undefined
}

function checkGroupByFromValue(value: string | null): CheckGroupBy | undefined {
  return value && CHECK_GROUP_BY_VALUES.includes(value as CheckGroupBy)
    ? (value as CheckGroupBy)
    : undefined
}

function upsertPlan(plans: PlanSummary[], next: PlanSummary): PlanSummary[] {
  const withoutNext = plans.filter((plan) => plan.plan_id !== next.plan_id)
  return [next, ...withoutNext].sort((a, b) => b.created_at.localeCompare(a.created_at))
}
