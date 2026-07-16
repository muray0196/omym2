/**
 * Summary: Presents CheckIssue catalog values with explicit text, tone, and icons.
 * Why: Keeps persisted findings understandable without relying on color alone.
 */
import { Icon } from "../../ui/icon";
import { issueTypePresentation, type HealthTone } from "./health-catalog";
import styles from "../inspection/inspection.module.css";

export function IssueTypeValue({ value }: { value: string }) {
  const presentation = issueTypePresentation(value);
  return (
    <span className={`${styles.badge} ${toneClass(presentation.tone)}`}>
      <Icon name={presentation.icon} />
      {presentation.label}
    </span>
  );
}

function toneClass(tone: HealthTone) {
  if (tone === "warning") return styles.warningTone;
  return styles.danger;
}
