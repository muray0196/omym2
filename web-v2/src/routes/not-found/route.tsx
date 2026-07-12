/**
 * Summary: Renders the client-owned fallback for unmatched browser routes.
 * Why: Distinguishes unknown SPA locations from API and asset failures.
 */
import { Link } from "react-router-dom";

import { RouteHeading } from "../../ui/primitives/route-heading";
import { routeCopy } from "../route-copy";
import styles from "../route.module.css";

export function Component() {
  return (
    <article className={styles.page}>
      <header className={styles.header}>
        <p className={styles.eyebrow}>{routeCopy.notFound.eyebrow}</p>
        <RouteHeading>{routeCopy.notFound.title}</RouteHeading>
        <p className={styles.description}>{routeCopy.notFound.description}</p>
      </header>
      <Link className={styles.homeLink} to="/">
        {routeCopy.notFound.action}
      </Link>
    </article>
  );
}
