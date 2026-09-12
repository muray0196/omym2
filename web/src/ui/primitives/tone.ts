/**
 * Summary: Maps the shared presentation tone union to CatalogBadge CSS classes.
 * Why: Keeps tone-to-color mapping centralized for every badge and catalog-value consumer.
 */
import styles from "./catalog-badge.module.css";

export type Tone = "info" | "success" | "warning" | "danger" | "neutral";

export function toneClassName(tone: Tone) {
  switch (tone) {
    case "info":
      return styles.toneInfo;
    case "success":
      return styles.toneSuccess;
    case "warning":
      return styles.toneWarning;
    case "danger":
      return styles.toneDanger;
    case "neutral":
      return styles.toneNeutral;
  }
}
