/*
Summary: Renders a lazily expanded artist-to-track library browser.
Why: Lets users inspect managed library hierarchy without loading every track.
*/

"use client"

import { ChevronDown, ChevronRight, ListTree, Music, TriangleAlert } from "lucide-react"
import { useCallback, useId, useState, type ReactNode } from "react"
import { getTrackGroups, getTracksPage } from "./api-client"
import { cn } from "./lib"
import type { GroupCount, TrackGroupBy, TrackStatus, TrackSummary } from "./types"
import { usePagedList } from "./use-paged-list"
import { Button, EmptyState, Mono, Notice, StatusBadge } from "./primitives"

const TRACK_BROWSER_GROUP_LIMIT = 50
const TRACK_BROWSER_TRACK_LIMIT = 100

type BrowserGroupBy = Exclude<TrackGroupBy, "artist_album">

function LoadMoreFooter({
  shown,
  total,
  hasMore,
  loading,
  onLoadMore,
  noun,
}: {
  shown: number
  total: number | null
  hasMore: boolean
  loading: boolean
  onLoadMore: () => void
  noun: string
}) {
  const cappedShown = total === null ? shown : Math.min(shown, total)
  return (
    <div className="flex flex-wrap items-center justify-between gap-3 border-t border-hairline bg-surface-elevated px-3 py-2.5">
      <span className="text-xs tabular-nums text-mute">
        {total === null
          ? `${cappedShown} ${noun}${cappedShown === 1 ? "" : "s"} loaded`
          : `${cappedShown} of ${total} ${noun}${total === 1 ? "" : "s"} loaded`}
      </span>
      <Button
        type="button"
        variant="outline"
        size="sm"
        disabled={!hasMore || loading}
        onClick={onLoadMore}
      >
        <ChevronDown className="size-4" aria-hidden="true" />
        {loading ? "Loading..." : hasMore ? "Load more" : `All ${noun}s loaded`}
      </Button>
    </div>
  )
}

function GroupRow({
  group,
  expanded,
  onToggle,
  children,
}: {
  group: GroupCount
  expanded: boolean
  onToggle: () => void
  children: ReactNode
}) {
  const contentId = useId()
  return (
    <li className="border-b border-hairline last:border-0">
      <button
        type="button"
        aria-expanded={expanded}
        aria-controls={contentId}
        onClick={onToggle}
        className="flex w-full items-center gap-2.5 px-3 py-2.5 text-left text-sm transition-colors hover:bg-surface-card/60 focus-visible:outline-2 focus-visible:-outline-offset-2 focus-visible:outline-ring"
      >
        <ChevronRight
          className={cn("size-4 shrink-0 text-mute transition-transform", expanded && "rotate-90")}
          aria-hidden="true"
        />
        <span className="min-w-0 flex-1 truncate font-medium text-ink" title={group.label}>
          {group.label}
        </span>
        <span className="shrink-0 tabular-nums text-xs text-mute">
          {group.count} track{group.count === 1 ? "" : "s"}
        </span>
      </button>
      {expanded ? (
        <div
          id={contentId}
          className="border-t border-hairline bg-surface-canvas/60 py-1 pl-7 pr-3"
        >
          {children}
        </div>
      ) : null}
    </li>
  )
}

function TrackRow({
  track,
  selected,
  onSelect,
}: {
  track: TrackSummary
  selected: boolean
  onSelect: (trackId: string) => void
}) {
  const title = track.metadata.title?.trim() || "Untitled track"
  const mismatch = track.current_path !== track.canonical_path
  return (
    <li className="border-b border-hairline-soft last:border-0">
      <button
        type="button"
        aria-current={selected ? "true" : undefined}
        onClick={() => onSelect(track.track_id)}
        className={cn(
          "flex w-full items-start gap-2.5 px-3 py-2 text-left text-sm transition-colors hover:bg-surface-card/60 focus-visible:outline-2 focus-visible:-outline-offset-2 focus-visible:outline-ring",
          selected && "bg-surface-active",
        )}
      >
        <Mono className="mt-0.5 w-6 shrink-0 text-right text-xs text-mute">
          {track.metadata.track_number ?? "—"}
        </Mono>
        <span className="min-w-0 flex-1">
          <span className="flex min-w-0 items-center gap-1.5">
            <span className="truncate font-medium text-ink" title={title}>
              {title}
            </span>
            {mismatch ? (
              <TriangleAlert
                className="size-3.5 shrink-0 text-warning"
                aria-label="Current path differs from canonical path"
              />
            ) : null}
          </span>
          <Mono className="block truncate text-xs text-mute" title={track.current_path}>
            {track.current_path}
          </Mono>
        </span>
        <StatusBadge status={track.status} iconOnly />
      </button>
    </li>
  )
}

function DiscTracks({
  groupKey,
  query,
  status,
  selectedTrackId,
  onSelectTrack,
}: {
  groupKey: string
  query?: string
  status: TrackStatus | "all"
  selectedTrackId: string | null
  onSelectTrack: (trackId: string) => void
}) {
  const loadTracksPage = useCallback(
    (cursor?: string) =>
      getTracksPage({
        cursor,
        groupBy: "disc",
        groupKey,
        query,
        status,
        limit: TRACK_BROWSER_TRACK_LIMIT,
      }),
    [groupKey, query, status],
  )
  const tracksPage = usePagedList<TrackSummary>({
    errorMessage: "Disc tracks failed to load.",
    loadPage: loadTracksPage,
  })

  return (
    <div className="flex flex-col">
      {tracksPage.errors.length > 0 ? (
        <Notice tone="warning" title="Disc tracks are incomplete" className="my-2">
          {tracksPage.errors.join(" ")}
        </Notice>
      ) : null}
      {tracksPage.items.length === 0 ? (
        <p className="py-2 text-sm text-mute">
          {tracksPage.loaded ? "No managed tracks in this disc." : "Loading tracks..."}
        </p>
      ) : (
        <ul className="flex flex-col">
          {tracksPage.items.map((track) => (
            <TrackRow
              key={track.track_id}
              track={track}
              selected={track.track_id === selectedTrackId}
              onSelect={onSelectTrack}
            />
          ))}
        </ul>
      )}
      {tracksPage.items.length > 0 ? (
        <LoadMoreFooter
          shown={tracksPage.items.length}
          total={tracksPage.page?.total ?? null}
          hasMore={tracksPage.hasMore}
          loading={tracksPage.loadingMore}
          onLoadMore={tracksPage.loadMore}
          noun="track"
        />
      ) : null}
    </div>
  )
}

function BrowserGroups({
  groupBy,
  parentKey,
  query,
  status,
  selectedTrackId,
  onSelectTrack,
}: {
  groupBy: BrowserGroupBy
  parentKey?: string
  query?: string
  status: TrackStatus | "all"
  selectedTrackId: string | null
  onSelectTrack: (trackId: string) => void
}) {
  const [expandedKey, setExpandedKey] = useState<string | null>(null)
  const loadGroupsPage = useCallback(
    (cursor?: string) =>
      getTrackGroups({
        cursor,
        groupBy,
        limit: TRACK_BROWSER_GROUP_LIMIT,
        parentKey,
        query,
        status,
      }),
    [groupBy, parentKey, query, status],
  )
  const groupsPage = usePagedList<GroupCount>({
    errorMessage: "Library groups failed to load.",
    loadPage: loadGroupsPage,
  })
  const noun = groupBy === "artist" ? "artist" : groupBy === "album" ? "album" : "disc"

  return (
    <div className="flex flex-col">
      {groupsPage.errors.length > 0 ? (
        <Notice tone="warning" title="Library browser is incomplete" className="my-2">
          {groupsPage.errors.join(" ")}
        </Notice>
      ) : null}
      {groupsPage.items.length === 0 ? (
        <EmptyState
          icon={groupBy === "artist" ? ListTree : Music}
          title={groupsPage.loaded ? `No ${noun}s to show.` : `Loading ${noun}s...`}
          description={
            groupsPage.loaded && groupBy === "artist"
              ? query || status !== "all"
                ? "Clear filters or adjust your search to see managed tracks."
                : "Managed tracks will appear here once a library is registered."
              : undefined
          }
        />
      ) : (
        <div className="overflow-hidden rounded-md border border-hairline">
          <ul className="flex flex-col">
            {groupsPage.items.map((group) => (
              <GroupRow
                key={group.key}
                group={group}
                expanded={expandedKey === group.key}
                onToggle={() =>
                  setExpandedKey((current) => (current === group.key ? null : group.key))
                }
              >
                {groupBy === "artist" ? (
                  <BrowserGroups
                    groupBy="album"
                    parentKey={group.key}
                    query={query}
                    status={status}
                    selectedTrackId={selectedTrackId}
                    onSelectTrack={onSelectTrack}
                  />
                ) : groupBy === "album" ? (
                  <BrowserGroups
                    groupBy="disc"
                    parentKey={group.key}
                    query={query}
                    status={status}
                    selectedTrackId={selectedTrackId}
                    onSelectTrack={onSelectTrack}
                  />
                ) : (
                  <DiscTracks
                    groupKey={group.key}
                    query={query}
                    status={status}
                    selectedTrackId={selectedTrackId}
                    onSelectTrack={onSelectTrack}
                  />
                )}
              </GroupRow>
            ))}
          </ul>
          <LoadMoreFooter
            shown={groupsPage.items.length}
            total={groupsPage.page?.total ?? null}
            hasMore={groupsPage.hasMore}
            loading={groupsPage.loadingMore}
            onLoadMore={groupsPage.loadMore}
            noun={noun}
          />
        </div>
      )}
    </div>
  )
}

export function TracksBrowser({
  query,
  status,
  selectedTrackId,
  onSelectTrack,
}: {
  query?: string
  status: TrackStatus | "all"
  selectedTrackId: string | null
  onSelectTrack: (trackId: string) => void
}) {
  return (
    <BrowserGroups
      groupBy="artist"
      query={query}
      status={status}
      selectedTrackId={selectedTrackId}
      onSelectTrack={onSelectTrack}
    />
  )
}
