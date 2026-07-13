/**
 * Summary: Defines the lazy Settings route and recovery-capable query boundary.
 * Why: Makes revision-safe Config editing available without coupling the route to storage.
 */
import { useQuery } from "@tanstack/react-query";

import { SettingsEditor } from "../../features/settings/settings-form";
import {
  readSettings,
  settingsQueryKey,
} from "../../features/settings/settings-api";
import { settingsCopy } from "../../features/settings/settings-copy";
import styles from "../../features/settings/settings.module.css";
import { InspectionErrorState } from "../../features/inspection/inspection-error-state";
import { RouteHeading } from "../../ui/primitives/route-heading";

export function Component() {
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
      key={settingsQuery.data.config_revision}
      onLoadLatest={async () => {
        await settingsQuery.refetch();
      }}
    />
  );
}

function SettingsHeader() {
  return (
    <header className={styles.header}>
      <p className={styles.eyebrow}>{settingsCopy.eyebrow}</p>
      <RouteHeading>{settingsCopy.title}</RouteHeading>
      <p className={styles.description}>{settingsCopy.description}</p>
    </header>
  );
}
