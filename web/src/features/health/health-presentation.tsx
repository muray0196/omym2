/**
 * Summary: Presents CheckIssue catalog values with explicit text, tone, and icons.
 * Why: Keeps persisted findings understandable without relying on color alone.
 */
import { CatalogBadge } from "../../ui/primitives/catalog-badge";
import { issueTypePresentation } from "./health-catalog";

export function IssueTypeValue({ value }: { value: string }) {
  const presentation = issueTypePresentation(value);
  return (
    <CatalogBadge
      icon={presentation.icon}
      label={presentation.label}
      tone={presentation.tone}
    />
  );
}
