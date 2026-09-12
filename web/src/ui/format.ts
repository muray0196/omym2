/**
 * Summary: Shares the "en-US" timestamp and count formatters used by independent list and detail surfaces.
 * Why: Keeps locale and date/time style consistent without duplicated Intl formatter instances.
 */
const TIMESTAMP_FORMATTER = new Intl.DateTimeFormat("en-US", {
  dateStyle: "medium",
  timeStyle: "short",
});

export const numberFormatter = new Intl.NumberFormat("en-US");

export function formatTimestamp(value: string) {
  const timestamp = new Date(value);
  return Number.isNaN(timestamp.valueOf())
    ? value
    : TIMESTAMP_FORMATTER.format(timestamp);
}
