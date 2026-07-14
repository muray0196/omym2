/**
 * Summary: Renders the compact shared heading block for every application route.
 * Why: Preserves route focus while keeping context and actions above the fold.
 */
import type { ReactNode } from "react";

import { RouteHeading } from "./route-heading";
import styles from "./page-header.module.css";

type PageHeaderProps = {
  actions?: ReactNode;
  description?: ReactNode;
  eyebrow: ReactNode;
  meta?: ReactNode;
  title: ReactNode;
};

export function PageHeader({
  actions,
  description,
  eyebrow,
  meta,
  title,
}: PageHeaderProps) {
  return (
    <header className={styles.header}>
      <div className={styles.context}>
        <div className={styles.headingLine}>
          <p className={styles.eyebrow}>{eyebrow}</p>
          <RouteHeading>{title}</RouteHeading>
        </div>
        {description === undefined ? null : (
          <p className={styles.description}>{description}</p>
        )}
      </div>
      {meta === undefined && actions === undefined ? null : (
        <div className={styles.aside}>
          {meta === undefined ? null : (
            <div className={styles.meta}>{meta}</div>
          )}
          {actions === undefined ? null : (
            <div className={styles.actions}>{actions}</div>
          )}
        </div>
      )}
    </header>
  );
}
