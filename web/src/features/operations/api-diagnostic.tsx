/**
 * Summary: Presents one backend diagnostic with safe SPA and command remediation.
 * Why: Keeps capability, mutation, and Operation recovery guidance visible without executing it.
 */
import { Link } from "react-router-dom";

import type { ApiError } from "../../api/generated";
import { remediationRouteForSpa } from "./operation-routes";
import styles from "./operation.module.css";

export function ApiDiagnostic({ diagnostic }: { diagnostic: ApiError }) {
  const remediation = diagnostic.remediation;

  return (
    <div className={styles.diagnosticContent}>
      <p>{diagnostic.message}</p>
      {remediation === undefined ? null : (
        <div className={styles.remediation}>
          {remediation.route === undefined ? (
            <span>{remediation.label}</span>
          ) : (
            <Link to={remediationRouteForSpa(remediation.route)}>
              {remediation.label}
            </Link>
          )}
          {remediation.command === undefined ? null : (
            <code className={styles.command}>{remediation.command}</code>
          )}
        </div>
      )}
    </div>
  );
}
