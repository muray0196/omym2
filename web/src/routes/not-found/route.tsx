/**
 * Summary: Renders the client-owned fallback for unmatched browser routes.
 * Why: Distinguishes unknown SPA locations from API and asset failures.
 */
import { Link } from "react-router-dom";

import { PageHeader } from "../../ui/primitives/page-header";
import { routeCopy } from "../route-copy";
import styles from "../route.module.css";

export function Component() {
  return (
    <article className={styles.page}>
      <PageHeader
        description={routeCopy.notFound.description}
        eyebrow={routeCopy.notFound.eyebrow}
        title={routeCopy.notFound.title}
      />
      <Link className={styles.homeLink} to="/">
        {routeCopy.notFound.action}
      </Link>
    </article>
  );
}
