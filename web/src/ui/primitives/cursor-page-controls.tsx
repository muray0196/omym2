/**
 * Summary: Renders shared accessible controls for bounded cursor-page navigation.
 * Why: Makes cached inspection pages reversible and announces page changes consistently.
 */
import type { CursorPageNavigation } from "../cursor-page";
import { Button } from "./button";
import styles from "./cursor-page-controls.module.css";

type CursorPageControlsProps = CursorPageNavigation & {
  collectionLabel: string;
  pageSize?: number;
  totalItems?: number;
};

const numberFormatter = new Intl.NumberFormat("en-US");

export function CursorPageControls({
  collectionLabel,
  goToNextPage,
  goToPreviousPage,
  hasNextPage,
  hasPreviousPage,
  isFetchingNextPage,
  pageSize,
  pageNumber,
  totalItems,
}: CursorPageControlsProps) {
  const totalPages =
    totalItems === undefined || pageSize === undefined || pageSize < 1
      ? undefined
      : Math.max(1, Math.ceil(totalItems / pageSize));
  const position =
    totalPages === undefined
      ? `Page ${numberFormatter.format(pageNumber)}`
      : `Page ${numberFormatter.format(pageNumber)} of ${numberFormatter.format(totalPages)}`;

  return (
    <nav
      aria-label={`${collectionLabel} pagination`}
      className={styles.controls}
    >
      <Button
        aria-label={`Previous page of ${collectionLabel}`}
        disabled={!hasPreviousPage}
        onClick={goToPreviousPage}
        variant="secondary"
      >
        Previous
      </Button>
      <p aria-atomic="true" aria-live="polite" className={styles.position}>
        {position}
      </p>
      <Button
        aria-label={
          isFetchingNextPage
            ? `Loading next page of ${collectionLabel}`
            : `Next page of ${collectionLabel}`
        }
        disabled={!hasNextPage || isFetchingNextPage}
        onClick={goToNextPage}
        variant="secondary"
      >
        {isFetchingNextPage ? "Loading…" : "Next"}
      </Button>
    </nav>
  );
}
