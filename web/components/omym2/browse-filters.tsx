/*
Summary: Renders shared search and count-bearing facet controls for browse screens.
Why: Keeps Tracks, Plan actions, and Check issue filtering consistent.
*/

"use client"

import { Search, X } from "lucide-react"
import type { ChangeEvent } from "react"
import type { FacetValue } from "./types"
import { Button } from "./primitives"
import { Field, Select, TextInput } from "./forms"

/** Delay between the last search keystroke and the query-scoped refetches. */
export const SEARCH_DEBOUNCE_MS = 250

export interface BrowseFacet {
  key: string
  label: string
  value: string
  options: { value: string; label: string }[]
  onChange: (value: string) => void
}

export function countedFacetOptions(
  options: { value: string; label: string }[],
  counts: FacetValue[] | undefined,
): { value: string; label: string }[] {
  const countByValue = new Map(counts?.map((facet) => [facet.value, facet.count]) ?? [])
  return options.map((option) =>
    option.value === "all"
      ? option
      : { ...option, label: `${option.label} (${countByValue.get(option.value) ?? 0})` },
  )
}

export function BrowseFilters({
  query,
  onQueryChange,
  searchHelp,
  searchPlaceholder,
  facets,
  total,
}: {
  query: string
  onQueryChange: (value: string) => void
  searchHelp: string
  searchPlaceholder: string
  facets: BrowseFacet[]
  total: number | null
}) {
  const hasFilters = query.trim() !== "" || facets.some((facet) => facet.value !== "all")
  const clearFilters = () => {
    onQueryChange("")
    for (const facet of facets) facet.onChange("all")
  }

  return (
    <div className="flex flex-col gap-3 rounded-md border border-hairline bg-surface-canvas/40 p-3">
      <div className="grid gap-3 sm:grid-cols-2 xl:grid-cols-4">
        <Field label="Search" help={searchHelp}>
          {(id) => (
            <div className="relative">
              <Search
                className="pointer-events-none absolute left-2.5 top-1/2 size-4 -translate-y-1/2 text-mute"
                aria-hidden="true"
              />
              <TextInput
                id={id}
                className="pl-8"
                placeholder={searchPlaceholder}
                value={query}
                onChange={(event: ChangeEvent<HTMLInputElement>) =>
                  onQueryChange(event.target.value)
                }
              />
            </div>
          )}
        </Field>
        {facets.map((facet) => (
          <Field key={facet.key} label={facet.label}>
            {(id) => (
              <Select
                id={id}
                options={facet.options}
                value={facet.value}
                onChange={(event) => facet.onChange(event.target.value)}
              />
            )}
          </Field>
        ))}
      </div>
      <div className="flex flex-wrap items-center justify-between gap-2">
        <span role="status" className="text-xs tabular-nums text-mute">
          {total === null
            ? "Counting matches…"
            : `${total} matching result${total === 1 ? "" : "s"}`}
        </span>
        <Button
          type="button"
          variant="ghost"
          size="sm"
          disabled={!hasFilters}
          onClick={clearFilters}
        >
          <X className="size-3.5" aria-hidden="true" /> Clear filters
        </Button>
      </div>
    </div>
  )
}
