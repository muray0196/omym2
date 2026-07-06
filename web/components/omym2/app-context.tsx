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
  getCheck,
  getHistory,
  getPlanDetail,
  getPlans,
  getRunDetail,
  getSettings,
  getTracks,
  generateArtistIds as generateArtistIdsRequest,
  saveSettings as saveSettingsRequest,
  validateSettings,
} from "./api-client"
import { savedArtistIdEntries } from "./lib"
import { defaultConfig, mockSettingsState } from "./mock-data"
import type {
  AppConfig,
  CheckIssue,
  PathPreview,
  PlanActionStatus,
  PlanCreateResult,
  PlanDetail,
  PlanStatus,
  PlanSummary,
  PlanType,
  RunDetail,
  RunSummary,
  SettingsChange,
  SettingsChoices,
  TrackSummary,
  ValidationResult,
} from "./types"

export type Route =
  | { name: "dashboard" }
  | { name: "settings" }
  | { name: "path-policy" }
  | { name: "plans" }
  | { name: "plan-detail"; planId: string }
  | { name: "runs" }
  | { name: "run-detail"; runId: string }
  | { name: "check" }
  | { name: "tracks" }

export type NavKey =
  "dashboard" | "settings" | "path-policy" | "plans" | "runs" | "check" | "tracks"

export interface PlanFilters {
  status?: PlanStatus | "all"
  type?: PlanType | "all"
  limit?: number
}

interface AppContextValue {
  route: Route
  navigate: (route: Route) => void
  /** The currently persisted (saved) configuration. */
  savedConfig: AppConfig
  /** The in-progress draft being edited. */
  draftConfig: AppConfig
  setDraftConfig: (updater: (prev: AppConfig) => AppConfig) => void
  saveConfig: () => Promise<boolean>
  resetDraft: () => void
  generateArtistIds: (artistNames: string[], overwrite: boolean) => Promise<boolean>
  checkErrors: string[]
  checkIssues: CheckIssue[]
  checkLoaded: boolean
  historyErrors: string[]
  historyLoaded: boolean
  createAddPlan: (sourcePath: string | null) => Promise<PlanCreateResult>
  createOrganizePlan: (libraryRoot: string | null) => Promise<PlanCreateResult>
  createRefreshPlan: (targetPath: string | null, includeAll: boolean) => Promise<PlanCreateResult>
  loadPlanDetail: (planId: string, actionStatus?: PlanActionStatus | "all") => Promise<void>
  loadPlans: (filters?: PlanFilters) => Promise<void>
  planDetailErrors: Record<string, string[]>
  planDetailLoading: Record<string, boolean>
  planDetails: Record<string, PlanDetail | null>
  planErrors: string[]
  plans: PlanSummary[]
  plansLoaded: boolean
  loadRunDetail: (runId: string) => Promise<void>
  runDetailErrors: Record<string, string[]>
  runDetailLoading: Record<string, boolean>
  runDetails: Record<string, RunDetail | null>
  runs: RunSummary[]
  settingsChoices: SettingsChoices
  settingsChanges: SettingsChange[]
  settingsErrors: string[]
  settingsLoadError: string | null
  settingsPreview: PathPreview
  settingsValidation: ValidationResult
  trackErrors: string[]
  tracks: TrackSummary[]
  tracksLoaded: boolean
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
  const [planErrors, setPlanErrors] = useState<string[]>([])
  const [plansLoaded, setPlansLoaded] = useState(false)
  const [planDetails, setPlanDetails] = useState<Record<string, PlanDetail | null>>({})
  const [planDetailErrors, setPlanDetailErrors] = useState<Record<string, string[]>>({})
  const [planDetailLoading, setPlanDetailLoading] = useState<Record<string, boolean>>({})
  const [runDetails, setRunDetails] = useState<Record<string, RunDetail | null>>({})
  const [runDetailErrors, setRunDetailErrors] = useState<Record<string, string[]>>({})
  const [runDetailLoading, setRunDetailLoading] = useState<Record<string, boolean>>({})
  const [checkIssues, setCheckIssues] = useState<CheckIssue[]>([])
  const [checkErrors, setCheckErrors] = useState<string[]>([])
  const [checkLoaded, setCheckLoaded] = useState(false)
  const [tracks, setTracks] = useState<TrackSummary[]>([])
  const [trackErrors, setTrackErrors] = useState<string[]>([])
  const [tracksLoaded, setTracksLoaded] = useState(false)

  useEffect(() => {
    function syncRouteFromLocation() {
      setRoute(routeFromPath(window.location.pathname))
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
      })
      .catch((error: unknown) => {
        if (cancelled) return
        setSettingsLoadError(error instanceof Error ? error.message : "Settings failed to load.")
      })

    return () => {
      cancelled = true
    }
  }, [])

  useEffect(() => {
    let cancelled = false

    async function loadInspectionState() {
      const [historyResult, plansResult, checkResult, tracksResult] = await Promise.allSettled([
        getHistory(),
        getPlans(),
        getCheck(),
        getTracks(),
      ])
      if (cancelled) return

      if (historyResult.status === "fulfilled") {
        setRuns(historyResult.value.runs)
        setHistoryErrors(historyResult.value.errors)
      } else {
        setHistoryErrors([errorMessage(historyResult.reason, "Run history failed to load.")])
      }
      setHistoryLoaded(true)

      if (plansResult.status === "fulfilled") {
        setPlans(plansResult.value.plans)
        setPlanErrors(plansResult.value.errors)
      } else {
        setPlanErrors([errorMessage(plansResult.reason, "Plans failed to load.")])
      }
      setPlansLoaded(true)

      if (checkResult.status === "fulfilled") {
        setCheckIssues(checkResult.value.issues)
        setCheckErrors(checkResult.value.errors)
      } else {
        setCheckErrors([errorMessage(checkResult.reason, "Check issues failed to load.")])
      }
      setCheckLoaded(true)

      if (tracksResult.status === "fulfilled") {
        setTracks(tracksResult.value.tracks)
        setTrackErrors(tracksResult.value.errors)
      } else {
        setTrackErrors([errorMessage(tracksResult.reason, "Tracks failed to load.")])
      }
      setTracksLoaded(true)
    }

    void loadInspectionState()
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

  const loadPlans = useCallback(async (filters: PlanFilters = {}) => {
    try {
      const result = await getPlans(filters)
      setPlans(result.plans)
      setPlanErrors(result.errors)
    } catch (error: unknown) {
      setPlanErrors([errorMessage(error, "Plans failed to load.")])
    } finally {
      setPlansLoaded(true)
    }
  }, [])

  const loadPlanDetail = useCallback(
    async (planId: string, actionStatus: PlanActionStatus | "all" = "all") => {
      setPlanDetailLoading((current) => ({ ...current, [planId]: true }))
      try {
        const result = await getPlanDetail(planId, actionStatus)
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
    },
    [],
  )

  const recordCreatedPlan = useCallback((result: PlanCreateResult) => {
    setPlanErrors(result.errors)
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
        setPlanErrors(result.errors)
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
        setPlanErrors(result.errors)
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
        setPlanErrors(result.errors)
        return result
      }
    },
    [csrfToken, recordCreatedPlan],
  )

  // Apply theme to <html>.
  useEffect(() => {
    const root = document.documentElement
    const theme = draftConfig.ui.theme
    const apply = (dark: boolean) => {
      root.classList.toggle("dark", dark)
      root.classList.toggle("light", !dark)
      // OLED layers pure-black surfaces on top of the dark palette.
      root.classList.toggle("oled", theme === "oled")
    }
    if (theme === "system") {
      const mq = window.matchMedia("(prefers-color-scheme: dark)")
      apply(mq.matches)
      const onChange = (e: MediaQueryListEvent) => apply(e.matches)
      mq.addEventListener("change", onChange)
      return () => mq.removeEventListener("change", onChange)
    }
    apply(theme === "dark" || theme === "oled")
  }, [draftConfig.ui.theme])

  const value = useMemo<AppContextValue>(
    () => ({
      route,
      navigate: (next) => {
        setRoute(next)
        window.history.pushState({}, "", routeToPath(next))
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
      checkErrors,
      checkIssues,
      checkLoaded,
      createAddPlan,
      createOrganizePlan,
      createRefreshPlan,
      historyErrors,
      historyLoaded,
      loadPlanDetail,
      loadPlans,
      planDetailErrors,
      planDetailLoading,
      planDetails,
      planErrors,
      plans,
      plansLoaded,
      loadRunDetail,
      runDetailErrors,
      runDetailLoading,
      runDetails,
      runs,
      settingsChoices,
      settingsChanges,
      settingsErrors,
      settingsLoadError,
      settingsPreview,
      settingsValidation,
      trackErrors,
      tracks,
      tracksLoaded,
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
      checkErrors,
      checkIssues,
      checkLoaded,
      createAddPlan,
      createOrganizePlan,
      createRefreshPlan,
      csrfToken,
      draftConfig,
      historyErrors,
      historyLoaded,
      loadPlanDetail,
      loadPlans,
      loadRunDetail,
      planDetailErrors,
      planDetailLoading,
      planDetails,
      planErrors,
      plans,
      plansLoaded,
      route,
      runDetailErrors,
      runDetailLoading,
      runDetails,
      runs,
      savedConfig,
      settingsChanges,
      settingsChoices,
      settingsErrors,
      settingsLoadError,
      settingsPreview,
      settingsValidation,
      trackErrors,
      tracks,
      tracksLoaded,
    ],
  )

  return <AppContext.Provider value={value}>{children}</AppContext.Provider>
}

function routeFromPath(pathname: string): Route {
  if (pathname === "/settings") return { name: "settings" }
  if (pathname === "/path-policy") return { name: "path-policy" }
  if (pathname === "/plans") return { name: "plans" }
  if (pathname.startsWith("/plans/")) {
    return { name: "plan-detail", planId: decodeURIComponent(pathname.replace("/plans/", "")) }
  }
  if (pathname === "/history") return { name: "runs" }
  if (pathname.startsWith("/history/")) {
    return { name: "run-detail", runId: decodeURIComponent(pathname.replace("/history/", "")) }
  }
  if (pathname === "/check") return { name: "check" }
  if (pathname === "/tracks") return { name: "tracks" }
  return { name: "dashboard" }
}

function routeToPath(route: Route): string {
  switch (route.name) {
    case "settings":
      return "/settings"
    case "path-policy":
      return "/path-policy"
    case "plans":
      return "/plans"
    case "plan-detail":
      return `/plans/${encodeURIComponent(route.planId)}`
    case "runs":
      return "/history"
    case "run-detail":
      return `/history/${encodeURIComponent(route.runId)}`
    case "check":
      return "/check"
    case "tracks":
      return "/tracks"
    case "dashboard":
    default:
      return "/"
  }
}

function errorMessage(error: unknown, fallback: string): string {
  return error instanceof Error ? error.message : fallback
}

function upsertPlan(plans: PlanSummary[], next: PlanSummary): PlanSummary[] {
  const withoutNext = plans.filter((plan) => plan.plan_id !== next.plan_id)
  return [next, ...withoutNext].sort((a, b) => b.created_at.localeCompare(a.created_at))
}
