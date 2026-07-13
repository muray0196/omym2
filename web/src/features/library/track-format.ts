/**
 * Summary: Formats persisted Track values for read-only presentation.
 * Why: Keeps missing metadata, timestamps, counts, and sizes consistent outside React components.
 */
import { libraryCopy } from "./library-copy";

const TRACK_TIMESTAMP_FORMATTER = new Intl.DateTimeFormat(undefined, {
  dateStyle: "medium",
  timeStyle: "medium",
});

export function displayValue(value: number | string | null | undefined) {
  return value === null || value === undefined || value === ""
    ? libraryCopy.missingValue
    : String(value);
}

export function displayNumberPair(value: number | null, total: number | null) {
  if (value === null && total === null) {
    return libraryCopy.missingValue;
  }
  return `${displayValue(value)} / ${displayValue(total)}`;
}

export function displayTimestamp(value: string | null) {
  if (value === null) {
    return libraryCopy.missingValue;
  }
  return TRACK_TIMESTAMP_FORMATTER.format(new Date(value));
}

export function displaySize(value: number | null) {
  return value === null
    ? libraryCopy.missingValue
    : `${value.toLocaleString()} bytes`;
}
