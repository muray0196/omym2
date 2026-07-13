/**
 * Summary: Presents typed and transport failures for read-only inspection routes.
 * Why: Keeps diagnostics visible without treating failures as empty persisted state.
 */
import { Button } from "../../ui/primitives/button";
import { InspectionApiError } from "./query-errors";
import styles from "./inspection.module.css";

export function InspectionErrorState({
  error,
  onRetry,
  title,
}: {
  error: Error;
  onRetry: () => void;
  title: string;
}) {
  const messages =
    error instanceof InspectionApiError
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
      <Button onClick={onRetry} variant="secondary">
        Try again
      </Button>
    </section>
  );
}
