/**
 * Summary: Renders shared accessible controls for bounded cursor-page navigation.
 * Why: Makes cached inspection pages reversible and announces page changes consistently.
 */
import type { CursorPageNavigation } from "../cursor-page";
import { Button } from "./button";
import styles from "./cursor-page-controls.module.css";

type CursorPageControlsProps = CursorPageNavigation & {
  collectionLabel: string;
};

export function CursorPageControls({
  collectionLabel,
  goToNextPage,
  goToPreviousPage,
  hasNextPage,
  hasPreviousPage,
  isFetchingNextPage,
  pageNumber,
}: CursorPageControlsProps) {
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
        Page {pageNumber}
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
