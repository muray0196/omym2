/**
 * Summary: Loads backend-owned Library choices for planning and Check forms.
 * Why: Prevents durable requests from accepting invented or ambiguous identities.
 */
import { queryOptions, useQuery } from "@tanstack/react-query";

import { getLibraries, type LibrariesData } from "../../api/generated";
import { libraryStatusLabel } from "../library/library-catalog";
import {
  InspectionUnexpectedDataError,
  throwInspectionResponseError,
} from "../inspection/query-errors";
import styles from "./planning.module.css";

const librariesQuery = queryOptions({
  queryKey: ["libraries", "operation-choices"] as const,
  queryFn: async (): Promise<LibrariesData> => {
    const response = await getLibraries({
      baseUrl: globalThis.location.origin,
    });
    if (response.error !== undefined) {
      throwInspectionResponseError(
        "Library choices",
        response.error,
        response.response,
      );
    }
    const data = response.data?.data;
    if (data == null)
      throw new InspectionUnexpectedDataError("Library choices");
    return data;
  },
});

export function LibrarySelection({
  allowEmpty = false,
  label = "Library",
  onChange,
  value,
}: {
  allowEmpty?: boolean;
  label?: string;
  onChange: (libraryId: string) => void;
  value: string;
}) {
  const query = useQuery(librariesQuery);
  const valueHasLoadedOption =
    value === "" ||
    query.data?.items.some((library) => library.library_id === value) === true;

  return (
    <div className={styles.field}>
      <label htmlFor="operation-library">{label}</label>
      <select
        id="operation-library"
        value={value}
        onChange={(event) => onChange(event.currentTarget.value)}
      >
        {allowEmpty ? <option value="">All available Libraries</option> : null}
        {!allowEmpty && value === "" ? (
          <option value="">Select a Library</option>
        ) : null}
        {!valueHasLoadedOption ? (
          <option value={value}>Selected Library · {value}</option>
        ) : null}
        {query.data?.items.map((library) => (
          <option key={library.library_id} value={library.library_id}>
            {library.root_path} · {libraryStatusLabel(library.status)}
          </option>
        ))}
      </select>
      {query.isPending ? <p role="status">Loading Library choices…</p> : null}
      {query.isError ? (
        <p className={styles.error} role="alert">
          Library choices could not be loaded. Refresh Bootstrap and try again.
        </p>
      ) : null}
    </div>
  );
}
