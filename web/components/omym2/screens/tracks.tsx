"use client"

import { Music, Search, TriangleAlert } from "lucide-react"
import { useMemo, useState } from "react"
import { useApp } from "../app-context"
import { truncateMiddle } from "../lib"
import type { TrackSummary } from "../types"
import {
  CopyButton,
  DataTable,
  EmptyState,
  Mono,
  Notice,
  Panel,
  StatusBadge,
  type Column,
} from "../primitives"
import { Field, Select, TextInput, Toggle } from "../forms"
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

function DetailRow({ label, children }: { label: string; children: React.ReactNode }) {
  return (
    <div className="flex flex-col gap-0.5 border-b border-border py-2 last:border-0 sm:flex-row sm:items-center sm:justify-between sm:gap-3">
      <dt className="text-xs uppercase tracking-wide text-muted-foreground">{label}</dt>
      <dd className="min-w-0 text-sm">{children}</dd>
    </div>
  )
}

function TrackDetail({ track }: { track: TrackSummary }) {
  const mismatch = track.current_path !== track.canonical_path
  const m = track.metadata
  const title = metadataText(m.title)
  const artist = metadataText(m.artist)
  const album = metadataText(m.album)
  return (
    <div className="flex flex-col gap-4">
      <div>
        <h3 className="text-sm font-semibold">{title}</h3>
        <p className="text-xs text-muted-foreground">
          {artist} · {album}
        </p>
      </div>

      {mismatch ? (
        <div className="rounded-md border border-warning/40 bg-warning-muted p-2.5">
          <p className="flex items-center gap-1.5 text-xs font-medium text-warning">
            <TriangleAlert className="size-3.5" aria-hidden="true" />
            Current path differs from canonical path
          </p>
        </div>
      ) : null}

      <dl className="rounded-md border border-border px-3">
        <DetailRow label="Current path">
          <span className="flex items-center gap-1">
            <Mono
              className={mismatch ? "text-warning" : "text-foreground"}
              title={track.current_path}
            >
              {truncateMiddle(track.current_path, 30)}
            </Mono>
            <CopyButton value={track.current_path} label="Copy current path" />
          </span>
        </DetailRow>
        <DetailRow label="Canonical path">
          <span className="flex items-center gap-1">
            <Mono className="text-foreground" title={track.canonical_path}>
              {truncateMiddle(track.canonical_path, 30)}
            </Mono>
            <CopyButton value={track.canonical_path} label="Copy canonical path" />
          </span>
        </DetailRow>
        <DetailRow label="track_id">
          <span className="flex items-center gap-1">
            <Mono title={track.track_id}>{truncateMiddle(track.track_id, 20)}</Mono>
            <CopyButton value={track.track_id} label="Copy track id" />
          </span>
        </DetailRow>
        <DetailRow label="content_hash">
          <span className="flex items-center gap-1">
            <Mono title={track.content_hash}>{truncateMiddle(track.content_hash, 24)}</Mono>
            <CopyButton value={track.content_hash} label="Copy content hash" />
          </span>
        </DetailRow>
        <DetailRow label="metadata_hash">
          <span className="flex items-center gap-1">
            <Mono title={track.metadata_hash}>{truncateMiddle(track.metadata_hash, 24)}</Mono>
            <CopyButton value={track.metadata_hash} label="Copy metadata hash" />
          </span>
        </DetailRow>
        <DetailRow label="first_seen_at">
          <Mono className="text-muted-foreground">{track.first_seen_at}</Mono>
        </DetailRow>
        <DetailRow label="last_seen_at">
          <Mono className="text-muted-foreground">{track.last_seen_at}</Mono>
        </DetailRow>
      </dl>

      <div>
        <p className="mb-2 text-xs font-semibold uppercase tracking-wide text-muted-foreground">
          Metadata
        </p>
        <dl className="rounded-md border border-border px-3">
          <DetailRow label="Album artist">{metadataText(m.album_artist)}</DetailRow>
          <DetailRow label="Genre">{metadataText(m.genre)}</DetailRow>
          <DetailRow label="Year">{m.year ?? "—"}</DetailRow>
          <DetailRow label="Track">
            {m.track_number ?? "—"} / {m.track_total ?? "—"}
          </DetailRow>
          <DetailRow label="Disc">
            {m.disc_number ?? "—"} / {m.disc_total ?? "—"}
          </DetailRow>
        </dl>
      </div>
    </div>
  )
}

export function TracksScreen() {
  const { trackErrors, tracks, tracksLoaded } = useApp()
  const [query, setQuery] = useState("")
  const [status, setStatus] = useState("all")
  const [mismatchOnly, setMismatchOnly] = useState(false)
  const [missingOnly, setMissingOnly] = useState(false)
  const [selectedId, setSelectedId] = useState<string | null>(null)

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
  const libraryOptions = useMemo(
    () =>
      Array.from(new Set(tracks.map((track) => track.library_id))).map((libraryId) => ({
        value: libraryId,
        label: truncateMiddle(libraryId, 20),
      })),
    [tracks],
  )
  const libraryValue = libraryOptions[0]?.value ?? "all"

  const columns: Column<TrackSummary>[] = [
    {
      key: "title",
      header: "Title",
      cell: (t) => <span className="font-medium">{metadataText(t.metadata.title)}</span>,
    },
    {
      key: "artist",
      header: "Artist",
      cell: (t) => <span className="text-muted-foreground">{metadataText(t.metadata.artist)}</span>,
    },
    {
      key: "album",
      header: "Album",
      cell: (t) => <span className="text-muted-foreground">{metadataText(t.metadata.album)}</span>,
    },
    { key: "status", header: "Status", cell: (t) => <StatusBadge status={t.status} /> },
    {
      key: "current_path",
      header: "Current path",
      cell: (t) => {
        const mismatch = t.current_path !== t.canonical_path
        return (
          <span className="flex items-center gap-1.5">
            <Mono className={mismatch ? "text-warning" : "text-foreground"} title={t.current_path}>
              {truncateMiddle(t.current_path, 28)}
            </Mono>
            {mismatch ? (
              <TriangleAlert className="size-3.5 text-warning" aria-label="Path mismatch" />
            ) : null}
          </span>
        )
      },
      className: "min-w-[16rem]",
    },
    {
      key: "canonical_path",
      header: "Canonical path",
      cell: (t) => (
        <Mono className="text-muted-foreground" title={t.canonical_path}>
          {truncateMiddle(t.canonical_path, 28)}
        </Mono>
      ),
      className: "min-w-[16rem]",
    },
    {
      key: "updated_at",
      header: "Updated",
      cell: (t) => (
        <span className="whitespace-nowrap text-muted-foreground">{t.updated_at.slice(0, 10)}</span>
      ),
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
                      className="pointer-events-none absolute left-2.5 top-1/2 size-4 -translate-y-1/2 text-muted-foreground"
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
              <div className="grid grid-cols-2 gap-3">
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
                <Field label="Library">
                  {(id) => (
                    <Select
                      id={id}
                      options={
                        libraryOptions.length > 0
                          ? libraryOptions
                          : [{ value: "all", label: "All libraries" }]
                      }
                      value={libraryValue}
                      disabled
                    />
                  )}
                </Field>
              </div>
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
              onRowClick={(t) => setSelectedId(t.track_id)}
              rowIsActive={(t) => t.track_id === selectedId}
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
