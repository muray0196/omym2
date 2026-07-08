"use client"

import { Music, Search, TriangleAlert } from "lucide-react"
import { useMemo, useState } from "react"
import { useApp } from "../app-context"
import { cn, truncateMiddle, truncatePathTail } from "../lib"
import type { TrackSummary } from "../types"
import {
  CopyButton,
  DataTable,
  EmptyState,
  MetaRow,
  Mono,
  Notice,
  Panel,
  StatusBadge,
  type Column,
} from "../primitives"
import { Field, Select, TextInput, Toggle } from "../forms"
import { AppIconTile } from "../command-kit"
import { PageHeading } from "./page-heading"

const STATUS_OPTIONS = [
  { value: "all", label: "All statuses" },
  { value: "active", label: "Active" },
  { value: "removed", label: "Removed" },
]

function hasMissingMetadata(t: TrackSummary): boolean {
  const m = t.metadata
  return !m.title?.trim() || !m.artist?.trim() || !m.album?.trim()
}

function metadataText(value: string | null): string {
  return value?.trim() || "—"
}

function TrackDetail({ track }: { track: TrackSummary }) {
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
  const { navigate, route, trackErrors, tracks, tracksLoaded } = useApp()
  const [query, setQuery] = useState("")
  const [status, setStatus] = useState("all")
  const [mismatchOnly, setMismatchOnly] = useState(false)
  const [missingOnly, setMissingOnly] = useState(false)
  // Selection lives in the URL (?track=<id>) rather than local state so it
  // survives a refresh, matching Plans/Runs which use real routes for their
  // master-detail selection. Selecting is not navigating, though: replace
  // the history entry so back leaves the screen in one press no matter how
  // many rows were inspected.
  const selectedId = route.name === "tracks" ? (route.trackId ?? null) : null
  const selectTrack = (trackId: string) => navigate({ name: "tracks", trackId }, { replace: true })

  const filtered = useMemo(() => {
    return tracks
      .filter((t) => (status === "all" ? true : t.status === status))
      .filter((t) => (mismatchOnly ? t.current_path !== t.canonical_path : true))
      .filter((t) => (missingOnly ? hasMissingMetadata(t) : true))
      .filter((t) => {
        if (!query.trim()) return true
        const q = query.toLowerCase()
        return (
          (t.metadata.title ?? "").toLowerCase().includes(q) ||
          (t.metadata.artist ?? "").toLowerCase().includes(q) ||
          (t.metadata.album ?? "").toLowerCase().includes(q) ||
          t.current_path.toLowerCase().includes(q) ||
          t.track_id.toLowerCase().includes(q)
        )
      })
  }, [missingOnly, mismatchOnly, query, status, tracks])

  const selected = filtered.find((t) => t.track_id === selectedId) ?? null

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
        description="Inspect managed track records and compare current paths against canonical paths. This is not a music player."
      />

      <div className="grid gap-6 lg:grid-cols-3">
        <div className="lg:col-span-2">
          <Panel title="Managed tracks" icon={Music} bodyClassName="flex flex-col gap-4">
            <div className="grid gap-3 sm:grid-cols-2">
              <Field label="Search" help="Match title, artist, album, path, or track_id.">
                {(id) => (
                  <div className="relative">
                    <Search
                      className="pointer-events-none absolute left-2.5 top-1/2 size-4 -translate-y-1/2 text-mute"
                      aria-hidden="true"
                    />
                    <TextInput
                      id={id}
                      className="pl-8"
                      placeholder="Search tracks…"
                      value={query}
                      onChange={(e) => setQuery(e.target.value)}
                    />
                  </div>
                )}
              </Field>
              <Field label="Status">
                {(id) => (
                  <Select
                    id={id}
                    options={STATUS_OPTIONS}
                    value={status}
                    onChange={(e) => setStatus(e.target.value)}
                  />
                )}
              </Field>
            </div>
            <div className="grid gap-2 sm:grid-cols-2">
              <Toggle
                checked={mismatchOnly}
                onChange={setMismatchOnly}
                label="Path mismatch only"
                help="Show tracks where current differs from canonical."
              />
              <Toggle
                checked={missingOnly}
                onChange={setMissingOnly}
                label="Missing metadata only"
                help="Show tracks missing a required field."
              />
            </div>

            {trackErrors.length > 0 ? (
              <Notice tone="warning" title="Track data is incomplete">
                {trackErrors.join(" ")}
              </Notice>
            ) : null}

            <DataTable
              columns={columns}
              rows={filtered}
              getRowKey={(t) => t.track_id}
              onRowClick={(t) => selectTrack(t.track_id)}
              rowIsActive={(t) => t.track_id === selectedId}
              rowActiveClassName="bg-surface-active"
              caption="Managed tracks"
              empty={
                <EmptyState
                  icon={Music}
                  title={tracksLoaded ? "No tracks match your filters." : "Loading tracks..."}
                  description={
                    tracksLoaded
                      ? "Clear filters or adjust your search to see managed track records."
                      : "Managed track records will appear here once they are loaded."
                  }
                />
              }
            />
          </Panel>
        </div>

        <div className="lg:sticky lg:top-6 lg:self-start">
          <Panel title="Track detail" icon={Music}>
            {selected ? (
              <TrackDetail track={selected} />
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
