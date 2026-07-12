/**
 * Summary: Renders an honest non-interactive boundary for later milestone routes.
 * Why: Freezes routing and accessibility without exposing unavailable operations.
 */
import { Icon } from "../ui/icon";
import { RouteHeading } from "../ui/primitives/route-heading";
import { routeCopy } from "./route-copy";
import styles from "./route.module.css";

type PlaceholderRouteProps = {
  description: string;
  title: string;
};

export function PlaceholderRoute({
  description,
  title,
}: PlaceholderRouteProps) {
  return (
    <article className={styles.page}>
      <header className={styles.header}>
        <p className={styles.eyebrow}>{routeCopy.placeholderLabel}</p>
        <RouteHeading>{title}</RouteHeading>
        <p className={styles.description}>{description}</p>
      </header>
      <section className={styles.placeholder}>
        <p className={styles.status}>
          <Icon name="info" />
          {routeCopy.placeholderLabel}
        </p>
        <p>{description}</p>
      </section>
    </article>
  );
}
