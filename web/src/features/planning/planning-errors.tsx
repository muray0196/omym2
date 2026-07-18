/**
 * Summary: Presents structured planning and Check mutation failures.
 * Why: Keeps server remediation visible without automatic retries or commands.
 */
import { Link } from "react-router-dom";

import { useFocusOnChange } from "../../ui/primitives/focus-on-change";
import { OperationApiError } from "../operations/operation-start";
import { remediationRouteForSpa } from "../operations/operation-routes";
import { planningCopy } from "./planning-copy";
import styles from "./planning.module.css";

export function PlanningMutationError({ error }: { error: Error }) {
  const summaryRef = useFocusOnChange<HTMLDivElement>(error);

  if (!(error instanceof OperationApiError)) {
    return (
      <div className={styles.error} ref={summaryRef} role="alert" tabIndex={-1}>
        <strong>{planningCopy.failure}</strong>
        <p>{error.message}</p>
      </div>
    );
  }

  return (
    <div className={styles.error} ref={summaryRef} role="alert" tabIndex={-1}>
      <strong>{planningCopy.failure}</strong>
      <ul>
        {error.envelope.errors.map((diagnostic) => (
          <li key={`${diagnostic.code}:${diagnostic.field ?? ""}`}>
            <p>
              {fieldTarget(diagnostic.field) === null ? (
                diagnostic.message
              ) : (
                <a
                  href={`#${fieldTarget(diagnostic.field)}`}
                  onClick={(event) => {
                    event.preventDefault();
                    const target = fieldTarget(diagnostic.field);
                    if (target !== null) {
                      document.getElementById(target)?.focus();
                    }
                  }}
                >
                  {diagnostic.message}
                </a>
              )}
            </p>
            {diagnostic.remediation?.route ? (
              <Link to={remediationRouteForSpa(diagnostic.remediation.route)}>
                {diagnostic.remediation.label}
              </Link>
            ) : diagnostic.remediation ? (
              <span>{diagnostic.remediation.label}</span>
            ) : null}
            {diagnostic.remediation?.command ? (
              <code className={styles.command}>
                {diagnostic.remediation.command}
              </code>
            ) : null}
          </li>
        ))}
      </ul>
    </div>
  );
}

function fieldTarget(field: string | undefined) {
  if (field === undefined) {
    return null;
  }
  const targets: Record<string, string> = {
    library_id: "operation-library",
    library_root: "organize-root",
    source_path: "add-source",
    target_kind: "refresh-scope",
    target_path: "refresh-target",
  };
  return targets[field.split(".").at(-1) ?? ""] ?? null;
}
