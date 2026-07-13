/**
 * Summary: Provides reusable assistive-only text.
 * Why: Prevents accessible names from depending on visual iconography.
 */
import type { ReactNode } from "react";

import styles from "./visually-hidden.module.css";

export function VisuallyHidden({ children }: { children: ReactNode }) {
  return <span className={styles.hidden}>{children}</span>;
}
