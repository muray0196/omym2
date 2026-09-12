/**
 * Summary: Defines the lazy Settings route and recovery-capable query boundary.
 * Why: Makes revision-safe Config editing available without coupling the route to storage.
 */
import { useState } from "react";
import { useQuery } from "@tanstack/react-query";

import { SettingsEditor } from "../../features/settings/settings-form";
import {
  readSettings,
  settingsQueryKey,
} from "../../features/settings/settings-api";
import { settingsCopy } from "../../features/settings/settings-copy";
import styles from "../../features/settings/settings.module.css";
import { InspectionErrorState } from "../../features/inspection/inspection-error-state";
import { PageHeader } from "../../ui/primitives/page-header";

export function Component() {
  const [editorVersion, setEditorVersion] = useState(0);
  const settingsQuery = useQuery({
    queryFn: readSettings,
    queryKey: settingsQueryKey,
  });

  if (settingsQuery.isPending) {
    return (
      <article className={styles.page}>
        <SettingsHeader />
        <p role="status">{settingsCopy.loading}</p>
      </article>
    );
  }

  if (settingsQuery.isError) {
    return (
      <article className={styles.page}>
        <SettingsHeader />
        <InspectionErrorState
          error={settingsQuery.error}
          onRetry={() => void settingsQuery.refetch()}
          title={settingsCopy.loadError}
        />
      </article>
    );
  }

  return (
    <SettingsEditor
      initial={settingsQuery.data}
      key={`${settingsQuery.data.artist_name_mappings.revision}:${editorVersion}`}
      onLoadLatest={async () => {
        await settingsQuery.refetch();
        setEditorVersion((current) => current + 1);
      }}
    />
  );
}

function SettingsHeader() {
  return (
    <PageHeader
      description={settingsCopy.description}
      eyebrow={settingsCopy.eyebrow}
      title={settingsCopy.title}
    />
  );
}
