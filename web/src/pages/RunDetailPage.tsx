import { useEffect, useState } from "react";

import { getRunDetail } from "../api/client";
import { Notice } from "../components/Notice";
import { StatusChip } from "../components/StatusChip";
import type { RunDetailResponse } from "../types";

type RunDetailPageProps = {
  runId: string;
};

export function RunDetailPage({ runId }: RunDetailPageProps) {
  const [data, setData] = useState<RunDetailResponse | null>(null);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    getRunDetail(runId)
      .then(setData)
      .catch((unknownError: unknown) => setError(unknownError instanceof Error ? unknownError.message : "Run failed."));
  }, [runId]);

  if (error !== null) {
    return <Notice tone="error" messages={[error]} />;
  }
  if (data === null) {
    return <div className="empty-state">Loading run.</div>;
  }
  if (data.detail === null) {
    return <Notice tone="error" messages={data.errors} />;
  }

  const { run, file_events: fileEvents } = data.detail;
  return (
    <div className="page">
      <div className="page-heading">
        <h1>Run Detail</h1>
      </div>
      <Notice tone="error" messages={data.errors} />
      <section className="summary-grid">
        <div>
          <span>Run</span>
          <strong>{run.run_id}</strong>
        </div>
        <div>
          <span>Plan</span>
          <strong>{run.plan_id}</strong>
        </div>
        <div>
          <span>Library</span>
          <strong>{run.library_id}</strong>
        </div>
        <div>
          <span>Status</span>
          <strong>{run.status}</strong>
        </div>
      </section>
      {fileEvents.length === 0 ? (
        <div className="empty-state">No file events.</div>
      ) : (
        <table>
          <thead>
            <tr>
              <th>Seq</th>
              <th>Event</th>
              <th>Status</th>
              <th>Source</th>
              <th>Target</th>
              <th>Error</th>
            </tr>
          </thead>
          <tbody>
            {fileEvents.map((event) => (
              <tr key={event.event_id}>
                <td>{event.sequence_no}</td>
                <td>{event.event_type}</td>
                <td>
                  <StatusChip value={event.status} />
                </td>
                <td>{event.source_path}</td>
                <td>{event.target_path}</td>
                <td>{event.error_message ?? event.error_code ?? ""}</td>
              </tr>
            ))}
          </tbody>
        </table>
      )}
    </div>
  );
}
