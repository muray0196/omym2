/**
 * Summary: Renders the initial overview foundation route.
 * Why: Establishes the safe operating loop without fabricating backend readiness.
 */
import { Icon } from "../../ui/icon";
import { RouteHeading } from "../../ui/primitives/route-heading";
import { routeCopy } from "../route-copy";
import styles from "../route.module.css";

export function Component() {
  return (
    <article className={styles.page}>
      <header className={styles.header}>
        <p className={styles.eyebrow}>{routeCopy.overview.eyebrow}</p>
        <RouteHeading>{routeCopy.overview.title}</RouteHeading>
        <p className={styles.description}>{routeCopy.overview.description}</p>
      </header>
      <p className={styles.status}>
        <Icon name="info" />
        {routeCopy.placeholderLabel}
      </p>
      <div className={styles.cards}>
        {routeCopy.overviewCards.map((card) => (
          <section className={styles.card} key={card.title}>
            <h2>{card.title}</h2>
            <p>{card.body}</p>
          </section>
        ))}
      </div>
    </article>
  );
}
