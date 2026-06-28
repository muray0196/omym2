import { useEffect, useState } from "react";

import { getTracks } from "../api/client";
import { Notice } from "../components/Notice";
import { StatusChip } from "../components/StatusChip";
import type { TracksResponse } from "../types";

export function TracksPage() {
  const [data, setData] = useState<TracksResponse | null>(null);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    getTracks()
      .then(setData)
      .catch((unknownError: unknown) =>
        setError(unknownError instanceof Error ? unknownError.message : "Tracks failed.")
      );
  }, []);

  if (error !== null) {
    return <Notice tone="error" messages={[error]} />;
  }
  if (data === null) {
    return <div className="empty-state">Loading tracks.</div>;
  }

  return (
    <div className="page">
      <div className="page-heading">
        <h1>Tracks</h1>
      </div>
      <Notice tone="error" messages={data.errors} />
      {data.tracks.length === 0 ? (
        <div className="empty-state">No tracks.</div>
      ) : (
        <table>
          <thead>
            <tr>
              <th>Track</th>
              <th>Library</th>
              <th>Status</th>
              <th>Current path</th>
              <th>Canonical path</th>
              <th>Title</th>
              <th>Artist</th>
              <th>Album</th>
            </tr>
          </thead>
          <tbody>
            {data.tracks.map((track) => (
              <tr key={track.track_id}>
                <td>{track.track_id}</td>
                <td>{track.library_id}</td>
                <td>
                  <StatusChip value={track.status} />
                </td>
                <td>{track.current_path}</td>
                <td>{track.canonical_path}</td>
                <td>{track.metadata.title ?? ""}</td>
                <td>{track.metadata.artist ?? ""}</td>
                <td>{track.metadata.album ?? ""}</td>
              </tr>
            ))}
          </tbody>
        </table>
      )}
    </div>
  );
}
