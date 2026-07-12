/*
Summary: Shares Track browsing request validation and mock parity helpers.
Why: Keeps browser-mode requests and static previews aligned with the local API.
*/

import type { TrackGroupBy } from "./types"

export const TRACK_GROUP_METADATA_WHITESPACE = " \t\r\n\v\f"

const TRACK_GROUP_FILTER_PAIR_MESSAGE =
  "Query parameters group_by and group_key must be provided together."
const TRACK_GROUP_PARENT_KEY_REQUIRED_MESSAGE =
  "Query parameter parent_key is required for this group_by."
const TRACK_GROUP_PARENT_KEY_UNSUPPORTED_MESSAGE =
  "Query parameter parent_key is not supported for this group_by."
const UTF8_ENCODER = new TextEncoder()

export function assertTrackGroupFilter({
  groupBy,
  groupKey,
}: {
  groupBy?: TrackGroupBy
  groupKey?: string
}): void {
  const hasGroupBy = groupBy !== undefined
  const hasGroupKey = groupKey !== undefined && groupKey !== ""
  if (hasGroupBy !== hasGroupKey) {
    throw new Error(TRACK_GROUP_FILTER_PAIR_MESSAGE)
  }
}

export function assertTrackGroupParentKey({
  groupBy,
  parentKey,
}: {
  groupBy: TrackGroupBy
  parentKey?: string
}): void {
  const hasParentKey = parentKey !== undefined && parentKey !== ""
  if (groupBy === "album" || groupBy === "disc") {
    if (!hasParentKey) {
      throw new Error(TRACK_GROUP_PARENT_KEY_REQUIRED_MESSAGE)
    }
    return
  }
  if (hasParentKey) {
    throw new Error(TRACK_GROUP_PARENT_KEY_UNSUPPORTED_MESSAGE)
  }
}

/** Return whether a value has content after the API's explicit ASCII whitespace trim set. */
export function hasTrackGroupMetadataText(value: string | null): value is string {
  if (value === null) {
    return false
  }
  let start = 0
  let end = value.length
  while (start < end && TRACK_GROUP_METADATA_WHITESPACE.includes(value[start])) {
    start += 1
  }
  while (end > start && TRACK_GROUP_METADATA_WHITESPACE.includes(value[end - 1])) {
    end -= 1
  }
  return start !== end
}

/** Compare valid text exactly as SQLite's UTF-8 BINARY collation compares it. */
export function compareSqliteBinaryText(left: string, right: string): number {
  if (left === right) {
    return 0
  }
  const leftBytes = UTF8_ENCODER.encode(left)
  const rightBytes = UTF8_ENCODER.encode(right)
  const sharedLength = Math.min(leftBytes.length, rightBytes.length)
  for (let index = 0; index < sharedLength; index += 1) {
    const difference = leftBytes[index] - rightBytes[index]
    if (difference !== 0) {
      return difference
    }
  }
  return leftBytes.length - rightBytes.length
}
