/**
 * Summary: Presents typed and transport Plan inspection failures with an explicit retry.
 * Why: Keeps API errors accessible without treating read failures as empty collections.
 */
import { Button } from "../../ui/primitives/button";
import { PlansApiError } from "./plan-query";
import styles from "./plan-inspection.module.css";

export function PlanErrorState({
  error,
  onRetry,
  retryLabel,
  title,
}: {
  error: Error;
  onRetry: () => void;
  retryLabel: string;
  title: string;
}) {
  const messages =
    error instanceof PlansApiError
      ? error.envelope.errors.map((diagnostic) => diagnostic.message)
      : [error.message];

  return (
    <section className={`${styles.state} ${styles.error}`} role="alert">
      <h2>{title}</h2>
      <ul>
        {messages.map((message) => (
          <li key={message}>{message}</li>
        ))}
      </ul>
      <div>
        <Button onClick={onRetry} variant="secondary">
          {retryLabel}
        </Button>
      </div>
    </section>
  );
}
