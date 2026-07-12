/*
Summary: Renders hierarchy and table views for managed Track browsing.
Why: Lets users explore library records without fetching every track.
*/

"use client"

import {
  ListTree,
  Music,
  Route as RouteIcon,
  ShieldCheck,
  Table2,
  TriangleAlert,
} from "lucide-react"
import { useCallback, useEffect, useState } from "react"
import { getTrackFacets, getTracksPage } from "../api-client"
import { useApp } from "../app-context"
import { BrowseFilters, countedFacetOptions, SEARCH_DEBOUNCE_MS } from "../browse-filters"
import { useDebouncedValue } from "../use-debounced-value"
import { TracksBrowser } from "../tracks-browser"
import { cn, truncateMiddle, truncatePathTail } from "../lib"
import type { FacetValue, TrackStatus, TrackSummary } from "../types"
import { usePagedList } from "../use-paged-list"
import {
  CopyButton,
  DataTable,
  EmptyState,
  MetaRow,
  Mono,
  Notice,
  Panel,
  SegmentedControl,
  StatusBadge,
  Button,
  type Column,
  type SegmentedOption,
} from "../primitives"
import { AppIconTile } from "../command-kit"
import { PageHeading } from "./page-heading"

const STATUS_OPTIONS = [
  { value: "all", label: "All statuses" },
  { value: "active", label: "Active" },
  { value: "removed", label: "Removed" },
]

const TRACK_PAGE_LIMIT = 100

type TracksViewMode = "browser" | "table"

const VIEW_MODE_OPTIONS: SegmentedOption<TracksViewMode>[] = [
  { value: "browser", label: "Browser", icon: ListTree },
  { value: "table", label: "Table", icon: Table2 },
]

function metadataText(value: string | null): string {
  return value?.trim() || "—"
}

function errorMessage(error: unknown, fallback: string): string {
  return error instanceof Error ? error.message : fallback
}

function TrackDetail({
  track,
  onViewCheckIssues,
  onPreviewPath,
}: {
  track: TrackSummary
  onViewCheckIssues: (trackId: string) => void
  onPreviewPath: (trackId: string) => void
}) {
  const mismatch = track.current_path !== track.canonical_path
  const m = track.metadata
  const title = metadataText(m.title)
  const artist = metadataText(m.artist)
  const album = metadataText(m.album)
  return (
    <div className="flex flex-col gap-4">
      <div className="flex items-center gap-3">
        <AppIconTile icon={Music} size={40} />
        <div className="min-w-0">
          <h3 className="truncate text-sm font-medium text-ink" title={title}>
            {title}
          </h3>
          <p className="truncate text-xs text-mute" title={`${artist} · ${album}`}>
            {artist} · {album}
          </p>
        </div>
      </div>

      {mismatch ? (
        <div className="rounded-md bg-warning-muted px-3 py-2.5">
          <p className="flex items-center gap-1.5 text-xs font-medium text-warning">
            <TriangleAlert className="size-3.5" aria-hidden="true" />
            Current path differs from canonical path
          </p>
        </div>
      ) : null}

      <div className="flex flex-wrap gap-2">
        <Button variant="outline" size="sm" onClick={() => onViewCheckIssues(track.track_id)}>
          <ShieldCheck className="size-3.5" aria-hidden="true" /> Check issues
        </Button>
        <Button variant="outline" size="sm" onClick={() => onPreviewPath(track.track_id)}>
          <RouteIcon className="size-3.5" aria-hidden="true" /> Path Preview
        </Button>
      </div>

      <dl className="rounded-md border border-hairline px-3">
        <MetaRow label="Current path" responsive>
          <span className="flex items-start gap-1">
            <Mono className={cn("break-all", mismatch ? "text-warning" : "text-ink")}>
              {track.current_path}
            </Mono>
            <CopyButton value={track.current_path} label="Copy current path" />
          </span>
        </MetaRow>
        <MetaRow label="Canonical path" responsive>
          <span className="flex items-start gap-1">
            <Mono className="break-all text-ink">{track.canonical_path}</Mono>
            <CopyButton value={track.canonical_path} label="Copy canonical path" />
          </span>
        </MetaRow>
        <MetaRow label="track_id" responsive>
          <span className="flex items-center gap-1">
            <Mono title={track.track_id}>{truncateMiddle(track.track_id, 20)}</Mono>
            <CopyButton value={track.track_id} label="Copy track id" />
          </span>
        </MetaRow>
        <MetaRow label="content_hash" responsive>
          <span className="flex items-center gap-1">
            <Mono title={track.content_hash}>{truncateMiddle(track.content_hash, 24)}</Mono>
            <CopyButton value={track.content_hash} label="Copy content hash" />
          </span>
        </MetaRow>
        <MetaRow label="metadata_hash" responsive>
          <span className="flex items-center gap-1">
            <Mono title={track.metadata_hash}>{truncateMiddle(track.metadata_hash, 24)}</Mono>
            <CopyButton value={track.metadata_hash} label="Copy metadata hash" />
          </span>
        </MetaRow>
        <MetaRow label="first_seen_at" responsive>
          <Mono className="text-mute">{track.first_seen_at}</Mono>
        </MetaRow>
        <MetaRow label="last_seen_at" responsive>
          <Mono className="text-mute">{track.last_seen_at}</Mono>
        </MetaRow>
      </dl>

      <div>
        <p className="mb-2 text-xs font-medium uppercase tracking-wide text-mute">Metadata</p>
        <dl className="rounded-md border border-hairline px-3">
          <MetaRow label="Album artist" responsive>
            {metadataText(m.album_artist)}
          </MetaRow>
          <MetaRow label="Genre" responsive>
            {metadataText(m.genre)}
          </MetaRow>
          <MetaRow label="Year" responsive>
            {m.year ?? "—"}
          </MetaRow>
          <MetaRow label="Track" responsive>
            {m.track_number ?? "—"} / {m.track_total ?? "—"}
          </MetaRow>
          <MetaRow label="Disc" responsive>
            {m.disc_number ?? "—"} / {m.disc_total ?? "—"}
          </MetaRow>
        </dl>
      </div>
    </div>
  )
}

export function TracksScreen() {
  const { navigate, route } = useApp()
  const [viewMode, setViewMode] = useState<TracksViewMode>("browser")
  const [query, setQuery] = useState(route.name === "tracks" ? (route.query ?? "") : "")
  const debouncedQuery = useDebouncedValue(query, SEARCH_DEBOUNCE_MS)

  useEffect(() => {
    if (route.name === "tracks" && route.query !== undefined) {
      setQuery(route.query)
    }
  }, [route])
  const [status, setStatus] = useState<TrackStatus | "all">("all")
  const [statusFacets, setStatusFacets] = useState<FacetValue[]>([])
  const [facetTotal, setFacetTotal] = useState<number | null>(null)
  const [facetErrors, setFacetErrors] = useState<string[]>([])
  const [selectedTrack, setSelectedTrack] = useState<TrackSummary | null>(null)
  const [selectedTrackErrors, setSelectedTrackErrors] = useState<string[]>([])
  const [selectedTrackLoading, setSelectedTrackLoading] = useState(false)
  // Selection lives in the URL (?track=<id>) rather than local state so it
  // survives a refresh, matching Plans/Runs which use real routes for their
  // master-detail selection. Selecting is not navigating, though: replace
  // the history entry so back leaves the screen in one press no matter how
  // many rows were inspected.
  const selectedId = route.name === "tracks" ? (route.trackId ?? null) : null
  const selectTrack = (trackId: string) => navigate({ name: "tracks", trackId }, { replace: true })

  const loadTracksPage = useCallback(
    (cursor?: string) => {
      if (viewMode !== "table") {
        return Promise.resolve({ errors: [], items: [], page: null })
      }
      return getTracksPage({
        cursor,
        limit: TRACK_PAGE_LIMIT,
        query: debouncedQuery.trim() || undefined,
        status,
      })
    },
    [debouncedQuery, status, viewMode],
  )
  const tracksPage = usePagedList({
    errorMessage: "Tracks failed to load.",
    loadPage: loadTracksPage,
  })
  const browseTotal =
    status === "all"
      ? facetTotal
      : (statusFacets.find((facet) => facet.value === status)?.count ?? 0)

  useEffect(() => {
    let cancelled = false
    getTrackFacets({ query: debouncedQuery.trim() || undefined })
      .then((response) => {
        if (cancelled) return
        setStatusFacets(response.facets.status ?? [])
        setFacetTotal(response.total)
        setFacetErrors(response.errors)
      })
      .catch((error: unknown) => {
        if (cancelled) return
        setStatusFacets([])
        setFacetTotal(null)
        setFacetErrors([errorMessage(error, "Track facets failed to load.")])
      })
    return () => {
      cancelled = true
    }
  }, [debouncedQuery])

  useEffect(() => {
    if (!selectedId) {
      setSelectedTrack(null)
      setSelectedTrackErrors([])
      setSelectedTrackLoading(false)
      return
    }

    const loadedTrack = tracksPage.items.find((track) => track.track_id === selectedId)
    if (loadedTrack) {
      setSelectedTrack(loadedTrack)
      setSelectedTrackErrors([])
      setSelectedTrackLoading(false)
      return
    }

    let cancelled = false
    setSelectedTrackLoading(true)
    setSelectedTrackErrors([])
    getTracksPage({ trackId: selectedId, limit: 1 })
      .then((response) => {
        if (cancelled) return
        setSelectedTrack(response.items[0] ?? null)
        setSelectedTrackErrors(
          response.items.length === 0 ? ["Selected track was not found."] : response.errors,
        )
      })
      .catch((error: unknown) => {
        if (cancelled) return
        setSelectedTrack(null)
        setSelectedTrackErrors([errorMessage(error, "Selected track failed to load.")])
      })
      .finally(() => {
        if (!cancelled) {
          setSelectedTrackLoading(false)
        }
      })

    return () => {
      cancelled = true
    }
  }, [selectedId, tracksPage.items])

  const columns: Column<TrackSummary>[] = [
    {
      key: "title",
      header: "Title",
      cell: (t) => <span className="font-medium text-ink">{metadataText(t.metadata.title)}</span>,
    },
    {
      key: "artist",
      header: "Artist",
      cell: (t) => <span className="text-mute">{metadataText(t.metadata.artist)}</span>,
    },
    {
      key: "album",
      header: "Album",
      cell: (t) => <span className="text-mute">{metadataText(t.metadata.album)}</span>,
    },
    {
      key: "status",
      header: "Status",
      cell: (t) => <StatusBadge status={t.status} iconOnly />,
      className: "w-16 text-center",
    },
    {
      key: "path",
      header: "Path",
      cell: (t) => {
        const mismatch = t.current_path !== t.canonical_path
        return (
          <span className="flex flex-col gap-0.5">
            <span className="flex items-center gap-1.5">
              <Mono className={mismatch ? "text-warning" : "text-ink"} title={t.current_path}>
                {truncatePathTail(t.current_path, 56)}
              </Mono>
              {mismatch ? (
                <TriangleAlert
                  className="size-3.5 shrink-0 text-warning"
                  aria-label="Path mismatch"
                />
              ) : null}
            </span>
            {mismatch ? (
              <Mono className="text-xs text-mute" title={t.canonical_path}>
                → {truncatePathTail(t.canonical_path, 54)}
              </Mono>
            ) : null}
          </span>
        )
      },
      className: "min-w-[20rem]",
    },
    {
      key: "updated_at",
      header: "Updated",
      cell: (t) => <span className="whitespace-nowrap text-mute">{t.updated_at.slice(0, 10)}</span>,
    },
  ]

  return (
    <>
      <PageHeading
        title="Tracks"
        description="Explore managed library metadata and compare current paths against canonical paths. This is not a music player."
      />

      <div className="grid gap-6 lg:grid-cols-3">
        <div className="lg:col-span-2">
          <Panel
            title={viewMode === "browser" ? "Library browser" : "Managed tracks"}
            icon={Music}
            bodyClassName="flex flex-col gap-4"
            actions={
              <SegmentedControl
                ariaLabel="Tracks view mode"
                size="sm"
                options={VIEW_MODE_OPTIONS}
                value={viewMode}
                onChange={setViewMode}
              />
            }
          >
            <BrowseFilters
              query={query}
              onQueryChange={setQuery}
              searchHelp="Match title, artist, album, path, or track ID."
              searchPlaceholder="Search tracks…"
              total={browseTotal}
              facets={[
                {
                  key: "status",
                  label: "Status",
                  value: status,
                  options: countedFacetOptions(STATUS_OPTIONS, statusFacets),
                  onChange: (value) => setStatus(value as TrackStatus | "all"),
                },
              ]}
            />
            {facetErrors.length > 0 ? (
              <Notice tone="warning" title="Track facets are incomplete">
                {facetErrors.join(" ")}
              </Notice>
            ) : null}
            {viewMode === "browser" ? (
              <TracksBrowser
                query={debouncedQuery.trim() || undefined}
                status={status}
                selectedTrackId={selectedId}
                onSelectTrack={selectTrack}
              />
            ) : (
              <>
                {tracksPage.errors.length > 0 ? (
                  <Notice tone="warning" title="Track data is incomplete">
                    {tracksPage.errors.join(" ")}
                  </Notice>
                ) : null}

                <DataTable
                  columns={columns}
                  rows={tracksPage.items}
                  getRowKey={(t) => t.track_id}
                  onRowClick={(t) => selectTrack(t.track_id)}
                  rowIsActive={(t) => t.track_id === selectedId}
                  rowActiveClassName="bg-surface-active"
                  caption="Managed tracks"
                  empty={
                    <EmptyState
                      icon={Music}
                      title={
                        tracksPage.loaded ? "No tracks match your filters." : "Loading tracks..."
                      }
                      description={
                        tracksPage.loaded
                          ? "Clear filters or adjust your search to see managed track records."
                          : "Managed track records will appear here once they are loaded."
                      }
                    />
                  }
                  loadMore={{
                    hasMore: tracksPage.hasMore,
                    loading: tracksPage.loadingMore,
                    onLoadMore: tracksPage.loadMore,
                    total: tracksPage.page?.total ?? tracksPage.items.length,
                  }}
                />
              </>
            )}
          </Panel>
        </div>

        <div className="lg:sticky lg:top-6 lg:self-start">
          <Panel title="Track detail" icon={Music}>
            {selectedTrackErrors.length > 0 ? (
              <Notice tone="warning" title="Track detail is incomplete">
                {selectedTrackErrors.join(" ")}
              </Notice>
            ) : selectedTrack ? (
              <TrackDetail
                track={selectedTrack}
                onViewCheckIssues={(trackId) => navigate({ name: "check", query: trackId })}
                onPreviewPath={(trackId) => navigate({ name: "path-policy", trackId })}
              />
            ) : selectedTrackLoading ? (
              <EmptyState icon={Music} title="Loading selected track..." />
            ) : (
              <EmptyState
                icon={Music}
                title="No track selected"
                description="Select a row to inspect metadata, hashes, and path consistency."
              />
            )}
          </Panel>
        </div>
      </div>
    </>
  )
}
