import { useEffect, useState } from "react";

import { getHistory } from "../api/client";
import { Notice } from "../components/Notice";
import { StatusChip } from "../components/StatusChip";
import type { HistoryResponse } from "../types";

export function HistoryPage() {
  const [data, setData] = useState<HistoryResponse | null>(null);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    getHistory()
      .then(setData)
      .catch((unknownError: unknown) =>
        setError(unknownError instanceof Error ? unknownError.message : "History failed.")
      );
  }, []);

  if (error !== null) {
    return <Notice tone="error" messages={[error]} />;
  }
  if (data === null) {
    return <div className="empty-state">Loading history.</div>;
  }

  return (
    <div className="page">
      <div className="page-heading">
        <h1>History</h1>
      </div>
      <Notice tone="error" messages={data.errors} />
      {data.runs.length === 0 ? (
        <div className="empty-state">No runs.</div>
      ) : (
        <table>
          <thead>
            <tr>
              <th>Run</th>
              <th>Plan</th>
              <th>Library</th>
              <th>Status</th>
              <th>Started</th>
              <th>Completed</th>
            </tr>
          </thead>
          <tbody>
            {data.runs.map((run) => (
              <tr key={run.run_id}>
                <td>
                  <a href={`/history/${run.run_id}`}>{run.run_id}</a>
                </td>
                <td>{run.plan_id}</td>
                <td>{run.library_id}</td>
                <td>
                  <StatusChip value={run.status} />
                </td>
                <td>{formatDate(run.started_at)}</td>
                <td>{run.completed_at === null ? "Not completed" : formatDate(run.completed_at)}</td>
              </tr>
            ))}
          </tbody>
        </table>
      )}
    </div>
  );
}

function formatDate(value: string) {
  return new Date(value).toLocaleString();
}
