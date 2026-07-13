/**
 * Summary: Presents typed and transport Library inspection failures with retry controls.
 * Why: Keeps failed reads accessible instead of treating them as empty persisted state.
 */
import { Button } from "../../ui/primitives/button";
import { LibraryApiError } from "./library-query";
import styles from "./library-inspection.module.css";

export function LibraryErrorState({
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
    error instanceof LibraryApiError
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
