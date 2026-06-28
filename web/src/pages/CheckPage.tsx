import { useEffect, useState } from "react";

import { getCheck } from "../api/client";
import { Notice } from "../components/Notice";
import type { CheckResponse } from "../types";

export function CheckPage() {
  const [data, setData] = useState<CheckResponse | null>(null);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    getCheck()
      .then(setData)
      .catch((unknownError: unknown) =>
        setError(unknownError instanceof Error ? unknownError.message : "Check failed.")
      );
  }, []);

  if (error !== null) {
    return <Notice tone="error" messages={[error]} />;
  }
  if (data === null) {
    return <div className="empty-state">Loading check.</div>;
  }

  return (
    <div className="page">
      <div className="page-heading">
        <h1>Check</h1>
      </div>
      <Notice tone="error" messages={data.errors} />
      {data.issues.length === 0 ? (
        <div className="empty-state">No issues.</div>
      ) : (
        <table>
          <thead>
            <tr>
              <th>Issue</th>
              <th>Library</th>
              <th>Path</th>
              <th>Track</th>
              <th>Plan</th>
              <th>Detail</th>
            </tr>
          </thead>
          <tbody>
            {data.issues.map((issue, index) => (
              <tr key={`${issue.issue_type}-${index}`}>
                <td>{issue.issue_type}</td>
                <td>{issue.library_id}</td>
                <td>{issue.path ?? ""}</td>
                <td>{issue.track_id ?? ""}</td>
                <td>{issue.plan_id ?? ""}</td>
                <td>{issue.detail ?? ""}</td>
              </tr>
            ))}
          </tbody>
        </table>
      )}
    </div>
  );
}
