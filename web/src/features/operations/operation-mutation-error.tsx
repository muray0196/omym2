/**
 * Summary: Presents and focuses execution-control mutation failures.
 * Why: Makes typed backend recovery guidance immediately discoverable after Apply, Cancel, or Undo starts fail.
 */
import { useFocusOnChange } from "../../ui/primitives/focus-on-change";
import { ApiDiagnostic } from "./api-diagnostic";
import { ApiMutationError } from "./operation-start";
import styles from "./operation.module.css";

export function OperationMutationError({
  error,
  title,
}: {
  error: Error;
  title: string;
}) {
  const summaryRef = useFocusOnChange<HTMLDivElement>(error);

  return (
    <div
      className={styles.mutationError}
      ref={summaryRef}
      role="alert"
      tabIndex={-1}
    >
      <strong>{title}</strong>
      {error instanceof ApiMutationError ? (
        <ul className={styles.diagnosticList}>
          {error.envelope.errors.map((diagnostic) => (
            <li
              key={`${diagnostic.code}:${diagnostic.field ?? ""}:${diagnostic.message}`}
            >
              <ApiDiagnostic diagnostic={diagnostic} />
            </li>
          ))}
        </ul>
      ) : (
        <p>{error.message}</p>
      )}
    </div>
  );
}
