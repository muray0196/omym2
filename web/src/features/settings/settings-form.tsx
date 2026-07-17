/**
 * Summary: Renders the recovery-capable Settings draft, preview, and revision-safe autosave flow.
 * Why: Persists idle drafts without losing local edits or weakening backend Config guarantees.
 */
import {
  useCallback,
  useContext,
  useEffect,
  useMemo,
  useRef,
  useState,
  type ChangeEvent,
} from "react";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { useForm, useWatch } from "react-hook-form";
import { useBeforeUnload, useBlocker } from "react-router-dom";

import type {
  ApiError,
  AppConfigResource,
  ArtistNameMappingEntry,
  ArtistNameMappingsData,
  PathPreview,
  PathPreviewRequest,
  SettingsCandidateData,
  SettingsChangeValue,
  SettingsData,
} from "../../api/generated";
import { bootstrapQuery } from "../bootstrap/bootstrap-query";
import { BootstrapContext } from "../bootstrap/bootstrap-context";
import { Button } from "../../ui/primitives/button";
import { Dialog } from "../../ui/primitives/dialog";
import { LiveRegion } from "../../ui/primitives/live-region";
import { PageHeader } from "../../ui/primitives/page-header";
import {
  hasSettingsErrorCode,
  isCsrfInvalidSettingsError,
  previewSettingsDraft,
  saveEnglishArtistNames,
  saveSettingsDraft,
  settingsQueryKey,
  SettingsApiError,
  SettingsTransportError,
} from "./settings-api";
import { defaultPreviewSample, settingsCopy } from "./settings-copy";
import styles from "./settings.module.css";

type PreviewSample = Pick<PathPreviewRequest, "file_extension" | "metadata">;
type SaveStatus = "attention" | "checking" | "saved" | "saving" | "unsaved";
type DraftCandidate = {
  config: AppConfigResource;
  fingerprint: string;
};

const PREVIEW_DEBOUNCE_MS = 250;

type SettingsEditorProps = {
  initial: SettingsData;
  onLoadLatest: () => Promise<void>;
};

export function SettingsEditor({ initial, onLoadLatest }: SettingsEditorProps) {
  const bootstrap = useContext(BootstrapContext);
  const queryClient = useQueryClient();
  const form = useForm<AppConfigResource>({
    defaultValues: initial.config,
    mode: "onChange",
  });
  const { control, register, reset } = form;
  const draft = useWatch({ control }) as AppConfigResource;
  const previewArtistIds = useWatch({ control, name: "artist_ids" });
  const previewPathPolicy = useWatch({ control, name: "path_policy" });
  const draftFingerprint = stableFingerprint(draft);
  const initialFingerprint = useMemo(
    () => stableFingerprint(initial.config),
    [initial.config],
  );
  const [baseRevision, setBaseRevision] = useState(initial.config_revision);
  const [acknowledgedFingerprint, setAcknowledgedFingerprint] =
    useState(initialFingerprint);
  const [lastSavedCandidate, setLastSavedCandidate] =
    useState<SettingsCandidateData | null>(null);
  const [saveActivity, setSaveActivity] = useState<
    "checking" | "saving" | null
  >(null);
  const [inFlightCandidate, setInFlightCandidate] =
    useState<DraftCandidate | null>(null);
  const [failedFingerprint, setFailedFingerprint] = useState<string | null>(
    null,
  );
  const [autosavePaused, setAutosavePaused] = useState<
    "conflict" | "failure" | null
  >(null);
  const [clientDraftValid, setClientDraftValid] = useState(true);
  const [retryAvailable, setRetryAvailable] = useState(false);
  const [previewSample, setPreviewSample] =
    useState<PreviewSample>(defaultPreviewSample);
  const [englishArtistNames, setEnglishArtistNames] = useState<
    Record<string, string>
  >(() => artistNameMappingEntries(initial.artist_name_mappings));
  const [artistNameMappingDetails, setArtistNameMappingDetails] = useState(
    initial.artist_name_mappings.entries,
  );
  const [artistNameMappingsRevision, setArtistNameMappingsRevision] = useState(
    initial.artist_name_mappings.revision,
  );
  const [
    savedArtistNameMappingsFingerprint,
    setSavedArtistNameMappingsFingerprint,
  ] = useState(() =>
    stableFingerprint(artistNameMappingEntries(initial.artist_name_mappings)),
  );
  const [actionError, setActionError] = useState<unknown>(null);
  const [announcement, setAnnouncement] = useState("");
  const [persistedValidation, setPersistedValidation] = useState(
    initial.validation,
  );
  const formRef = useRef<HTMLFormElement>(null);
  const stayButtonRef = useRef<HTMLButtonElement>(null);
  const saveStatusRef = useRef<HTMLElement>(null);
  const latestCandidateRef = useRef<DraftCandidate>({
    config: initial.config,
    fingerprint: initialFingerprint,
  });
  const acknowledgedFingerprintRef = useRef(initialFingerprint);
  const baseRevisionRef = useRef(initial.config_revision);
  const inFlightCandidateRef = useRef<DraftCandidate | null>(null);
  const pendingCandidateRef = useRef<DraftCandidate | null>(null);
  const autosavePausedRef = useRef<"conflict" | "failure" | null>(null);
  const bootstrapRefreshTimerRef = useRef<number | null>(null);
  const artistNameMappingsFingerprint = stableFingerprint(englishArtistNames);
  const artistNameMappingsDirty =
    artistNameMappingsFingerprint !== savedArtistNameMappingsFingerprint;
  const canSave = bootstrap?.runtime_capabilities.can_change_settings ?? false;
  const saveStatus = resolveSaveStatus({
    acknowledgedFingerprint,
    autosavePaused,
    canSave,
    clientDraftValid,
    draftFingerprint,
    failedFingerprint,
    inFlightCandidate,
    persistedConfigValid: persistedValidation.valid,
    saveActivity,
  });
  const configDraftUnsafe =
    draftFingerprint !== acknowledgedFingerprint ||
    inFlightCandidate !== null ||
    saveStatus === "attention";
  const blocker = useBlocker(configDraftUnsafe || artistNameMappingsDirty);
  const previewRequest = useMemo(
    () => ({
      artist_ids: previewArtistIds,
      file_extension: previewSample.file_extension,
      metadata: previewSample.metadata,
      path_policy: previewPathPolicy,
    }),
    [previewArtistIds, previewPathPolicy, previewSample],
  );
  const debouncedPreviewRequest = useDebouncedValue(
    previewRequest,
    PREVIEW_DEBOUNCE_MS,
  );
  const debouncedPreviewFingerprint = stableFingerprint(
    debouncedPreviewRequest,
  );
  const initialPreviewFingerprint = useMemo(
    () =>
      stableFingerprint(
        createPreviewRequest(initial.config, defaultPreviewSample),
      ),
    [initial.config],
  );
  const previewQuery = useQuery<PathPreview>({
    enabled: debouncedPreviewFingerprint !== initialPreviewFingerprint,
    placeholderData: (previousPreview) => previousPreview,
    queryFn: ({ signal }) =>
      previewSettingsDraft(debouncedPreviewRequest, signal),
    queryKey: [
      ...settingsQueryKey,
      "path-preview",
      debouncedPreviewFingerprint,
    ],
    retry: false,
  });
  const preview = previewQuery.data ?? initial.preview;

  useBeforeUnload((event) => {
    if (configDraftUnsafe || artistNameMappingsDirty) {
      event.preventDefault();
      event.returnValue = "";
    }
  });
  const artistNameMappingsMutation = useMutation({
    mutationFn: async (request: {
      entries: Record<string, string>;
      expected_revision: string;
    }) => {
      const csrfToken = bootstrap?.csrf_token;
      if (csrfToken === undefined) {
        throw new SettingsCsrfRefreshError();
      }
      try {
        return await saveEnglishArtistNames(request, csrfToken);
      } catch (error) {
        if (!isCsrfInvalidSettingsError(error)) {
          throw error;
        }
      }

      const refreshed = await queryClient.fetchQuery({
        ...bootstrapQuery,
        staleTime: 0,
      });
      const refreshedToken = refreshed.data?.csrf_token;
      if (refreshedToken === undefined) {
        throw new SettingsCsrfRefreshError();
      }
      return saveEnglishArtistNames(request, refreshedToken);
    },
    retry: false,
  });

  const scheduleBootstrapRefresh = useCallback(() => {
    if (bootstrapRefreshTimerRef.current !== null) {
      globalThis.clearTimeout(bootstrapRefreshTimerRef.current);
    }
    bootstrapRefreshTimerRef.current = globalThis.setTimeout(() => {
      bootstrapRefreshTimerRef.current = null;
      void queryClient.invalidateQueries({
        queryKey: bootstrapQuery.queryKey,
      });
    }, initial.choices.autosave_delay_ms);
  }, [initial.choices.autosave_delay_ms, queryClient]);

  const { mutateAsync: saveSettings } = useMutation({
    mutationFn: async (request: {
      config: AppConfigResource;
      expected_config_revision: string;
    }) => {
      const csrfToken = bootstrap?.csrf_token;
      if (csrfToken === undefined) {
        throw new SettingsCsrfRefreshError();
      }
      try {
        return await saveSettingsDraft(request, csrfToken);
      } catch (error) {
        if (!isCsrfInvalidSettingsError(error)) {
          throw error;
        }
      }

      const refreshed = await queryClient.fetchQuery({
        ...bootstrapQuery,
        staleTime: 0,
      });
      const refreshedToken = refreshed.data?.csrf_token;
      if (refreshedToken === undefined) {
        throw new SettingsCsrfRefreshError();
      }
      return saveSettingsDraft(request, refreshedToken);
    },
    retry: false,
  });

  const persistCandidate = useCallback(
    async function persist(candidate: DraftCandidate) {
      if (
        inFlightCandidateRef.current !== null ||
        autosavePausedRef.current !== null ||
        candidate.fingerprint !== latestCandidateRef.current.fingerprint
      ) {
        return;
      }
      if (!configFieldsAreValid(formRef.current)) {
        setFailedFingerprint(candidate.fingerprint);
        setSaveActivity(null);
        return;
      }

      inFlightCandidateRef.current = candidate;
      setInFlightCandidate(candidate);
      setSaveActivity("saving");
      setActionError(null);
      setRetryAvailable(false);
      try {
        const result = await saveSettings({
          config: candidate.config,
          expected_config_revision: baseRevisionRef.current,
        });
        const savedFingerprint = stableFingerprint(result.config);
        baseRevisionRef.current = result.config_revision;
        acknowledgedFingerprintRef.current = savedFingerprint;
        setBaseRevision(result.config_revision);
        setAcknowledgedFingerprint(savedFingerprint);
        setLastSavedCandidate(result);
        setPersistedValidation(result.validation);
        setActionError(null);
        setFailedFingerprint(null);
        setRetryAvailable(false);
        queryClient.setQueryData<SettingsData>(settingsQueryKey, (current) =>
          current === undefined
            ? current
            : {
                ...current,
                config: result.config,
                config_revision: result.config_revision,
                preview: result.preview,
                validation: result.validation,
              },
        );
        if (latestCandidateRef.current.fingerprint === candidate.fingerprint) {
          reset(result.config);
        }
        scheduleBootstrapRefresh();
      } catch (error: unknown) {
        pendingCandidateRef.current = null;
        setFailedFingerprint(latestCandidateRef.current.fingerprint);
        setActionError(error);
        setAnnouncement(actionErrorAnnouncement(error));
        if (hasSettingsErrorCode(error, "config_changed")) {
          autosavePausedRef.current = "conflict";
          setAutosavePaused("conflict");
          setRetryAvailable(false);
        } else if (
          !hasSettingsErrorCode(error, "validation_failed") &&
          !hasSettingsErrorCode(error, "config_invalid")
        ) {
          autosavePausedRef.current = "failure";
          setAutosavePaused("failure");
          setRetryAvailable(true);
        } else {
          setRetryAvailable(false);
        }
      } finally {
        inFlightCandidateRef.current = null;
        setInFlightCandidate(null);
        setSaveActivity(null);
        const pending = pendingCandidateRef.current;
        pendingCandidateRef.current = null;
        if (
          pending !== null &&
          autosavePausedRef.current === null &&
          pending.fingerprint === latestCandidateRef.current.fingerprint &&
          pending.fingerprint !== acknowledgedFingerprintRef.current
        ) {
          void persist(pending);
        }
      }
    },
    [queryClient, reset, saveSettings, scheduleBootstrapRefresh],
  );

  useEffect(() => {
    const candidate = { config: draft, fingerprint: draftFingerprint };
    latestCandidateRef.current = candidate;
    pendingCandidateRef.current = null;

    if (
      draftFingerprint === acknowledgedFingerprint ||
      inFlightCandidate?.fingerprint === draftFingerprint ||
      !clientDraftValid ||
      !canSave ||
      autosavePaused !== null ||
      failedFingerprint === draftFingerprint
    ) {
      return;
    }

    const timer = globalThis.setTimeout(() => {
      if (candidate.fingerprint !== latestCandidateRef.current.fingerprint) {
        return;
      }
      setSaveActivity("checking");
      if (inFlightCandidateRef.current !== null) {
        pendingCandidateRef.current = candidate;
        return;
      }
      void persistCandidate(candidate);
    }, initial.choices.autosave_delay_ms);
    return () => globalThis.clearTimeout(timer);
  }, [
    acknowledgedFingerprint,
    autosavePaused,
    canSave,
    clientDraftValid,
    draft,
    draftFingerprint,
    failedFingerprint,
    inFlightCandidate,
    initial.choices.autosave_delay_ms,
    persistCandidate,
  ]);

  useEffect(
    () => () => {
      if (bootstrapRefreshTimerRef.current !== null) {
        globalThis.clearTimeout(bootstrapRefreshTimerRef.current);
        void queryClient.invalidateQueries({
          queryKey: bootstrapQuery.queryKey,
        });
      }
    },
    [queryClient],
  );

  function retryAutosave() {
    autosavePausedRef.current = null;
    setAutosavePaused(null);
    setFailedFingerprint(null);
    setActionError(null);
    setRetryAvailable(false);
  }

  async function handleSaveArtistNameMappings() {
    setActionError(null);
    try {
      const result = await artistNameMappingsMutation.mutateAsync({
        entries: englishArtistNames,
        expected_revision: artistNameMappingsRevision,
      });
      applyArtistNameMappings(result);
      setAnnouncement(settingsCopy.artistNameMappingsSaved);
    } catch (error) {
      presentActionError(error);
    }
  }

  function applyArtistNameMappings(result: ArtistNameMappingsData) {
    const entries = artistNameMappingEntries(result);
    setEnglishArtistNames(entries);
    setArtistNameMappingDetails(result.entries);
    setArtistNameMappingsRevision(result.revision);
    setSavedArtistNameMappingsFingerprint(stableFingerprint(entries));
  }

  function presentActionError(error: unknown) {
    setActionError(error);
    setRetryAvailable(false);
    setAnnouncement(actionErrorAnnouncement(error));
  }

  return (
    <article className={styles.page}>
      <PageHeader
        description={settingsCopy.description}
        eyebrow={settingsCopy.eyebrow}
        meta={
          <span className={styles.revision}>
            {settingsCopy.revisionLabel}: <code>{baseRevision}</code>
          </span>
        }
        title={settingsCopy.title}
      />

      <section
        aria-atomic="true"
        className={`${styles.autosaveStatus} ${styles[saveStatus]}`}
        ref={saveStatusRef}
        role="status"
        tabIndex={-1}
      >
        <div>
          <h2>{settingsCopy.autosaveTitle}</h2>
          <p>{saveStatusLabel(saveStatus)}</p>
        </div>
        <p>{saveStatusDescription(saveStatus)}</p>
        {!clientDraftValid ? (
          <p className={styles.warningText}>
            {settingsCopy.clientValidationFailed}
          </p>
        ) : null}
      </section>

      {!persistedValidation.valid ? (
        <ValidationPanel
          body={settingsCopy.recoveryBody}
          diagnostics={persistedValidation.errors}
          title={settingsCopy.recoveryTitle}
          variant="warning"
        />
      ) : null}

      {!canSave ? (
        <ValidationPanel
          body={settingsCopy.saveUnavailable}
          diagnostics={bootstrap?.runtime_capabilities.disabled_reasons ?? []}
          title={settingsCopy.saveUnavailable}
          variant="warning"
        />
      ) : null}

      <form
        className={styles.form}
        onChange={() =>
          setClientDraftValid(configFieldsAreValid(formRef.current))
        }
        onSubmit={(event) => event.preventDefault()}
        ref={formRef}
      >
        <SettingsSection
          description={settingsCopy.pathHelp}
          title={settingsCopy.pathsTitle}
        >
          <div className={styles.fieldGrid}>
            <label className={styles.field} htmlFor="settings-paths-library">
              {settingsCopy.libraryPath}
              <input
                id="settings-paths-library"
                {...register("paths.library", {
                  setValueAs: nullableString,
                })}
              />
            </label>
            <label className={styles.field} htmlFor="settings-paths-incoming">
              {settingsCopy.incomingPath}
              <input
                id="settings-paths-incoming"
                {...register("paths.incoming", {
                  setValueAs: nullableString,
                })}
              />
            </label>
          </div>
        </SettingsSection>

        <SettingsSection title={settingsCopy.pathPolicyTitle}>
          <label
            className={styles.field}
            htmlFor="settings-path-policy-template"
          >
            {settingsCopy.template}
            <input
              className={styles.monoInput}
              id="settings-path-policy-template"
              required
              {...register("path_policy.template")}
            />
          </label>
          <div className={styles.placeholderGroup}>
            <p>{settingsCopy.placeholders}</p>
            <ul>
              {initial.choices.path_placeholders.map((placeholder) => (
                <li key={placeholder}>
                  <code>{placeholder}</code>
                </li>
              ))}
            </ul>
          </div>
          <div className={styles.fieldGrid}>
            <label className={styles.field} htmlFor="settings-unknown-artist">
              {settingsCopy.unknownArtist}
              <input
                id="settings-unknown-artist"
                required
                {...register("path_policy.unknown_artist")}
              />
            </label>
            <label className={styles.field} htmlFor="settings-unknown-album">
              {settingsCopy.unknownAlbum}
              <input
                id="settings-unknown-album"
                required
                {...register("path_policy.unknown_album")}
              />
            </label>
            <label className={styles.field} htmlFor="settings-max-filename">
              {settingsCopy.maxFilenameLength}
              <input
                id="settings-max-filename"
                min="1"
                required
                type="number"
                {...register("path_policy.max_filename_length", {
                  setValueAs: requiredNumber,
                })}
              />
            </label>
            <ChoiceField
              id="settings-disc-style"
              label={settingsCopy.discNumberStyle}
              options={initial.choices.disc_number_styles}
              register={register("path_policy.disc_number_style")}
            />
            <ChoiceField
              id="settings-disc-condition"
              label={settingsCopy.discNumberCondition}
              options={initial.choices.disc_number_conditions}
              register={register("path_policy.disc_number_condition")}
            />
          </div>
          <label className={styles.checkbox} htmlFor="settings-sanitize">
            <input
              id="settings-sanitize"
              type="checkbox"
              {...register("path_policy.sanitize")}
            />
            <span>{settingsCopy.sanitize}</span>
          </label>
        </SettingsSection>

        <SettingsSection
          description={settingsCopy.artistDisplayNamesHelp}
          id="settings-artist-name-mappings"
          title={settingsCopy.artistDisplayNamesTitle}
        >
          <ArtistNameMappings
            entries={englishArtistNames}
            mappingDetails={artistNameMappingDetails}
            onChange={setEnglishArtistNames}
          />
          <Button
            disabled={
              !canSave ||
              !artistNameMappingsDirty ||
              artistNameMappingsMutation.isPending
            }
            onClick={() => void handleSaveArtistNameMappings()}
            variant="secondary"
          >
            {artistNameMappingsMutation.isPending
              ? settingsCopy.savingArtistNameMappings
              : settingsCopy.saveArtistNameMappings}
          </Button>
        </SettingsSection>

        <SettingsSection
          description={settingsCopy.artistIdsHelp}
          id="settings-artist-ids"
          title={settingsCopy.artistIdsTitle}
        >
          <div className={styles.fieldGrid}>
            <label
              className={styles.field}
              htmlFor="settings-artist-max-length"
            >
              {settingsCopy.artistIdMaxLength}
              <input
                id="settings-artist-max-length"
                min="1"
                required
                type="number"
                {...register("artist_ids.max_length", {
                  setValueAs: requiredNumber,
                })}
              />
            </label>
            <label className={styles.field} htmlFor="settings-artist-fallback">
              {settingsCopy.artistIdFallback}
              <input
                className={styles.monoInput}
                id="settings-artist-fallback"
                required
                {...register("artist_ids.fallback_id")}
              />
            </label>
          </div>
        </SettingsSection>

        <SettingsSection title={settingsCopy.metadataTitle}>
          <div className={styles.checkboxGrid}>
            <BooleanField
              id="settings-prefer-album-artist"
              label={settingsCopy.preferAlbumArtist}
              register={register("metadata.prefer_album_artist")}
            />
            <BooleanField
              id="settings-require-title"
              label={settingsCopy.requireTitle}
              register={register("metadata.require_title")}
            />
            <BooleanField
              id="settings-require-artist"
              label={settingsCopy.requireArtist}
              register={register("metadata.require_artist")}
            />
            <BooleanField
              id="settings-require-album"
              label={settingsCopy.requireAlbum}
              register={register("metadata.require_album")}
            />
          </div>
          <ChoiceField
            id="settings-album-year"
            label={settingsCopy.albumYearResolution}
            options={initial.choices.album_year_resolutions}
            register={register("metadata.album_year_resolution")}
          />
        </SettingsSection>

        <SettingsSection title={settingsCopy.collisionTitle}>
          <div className={styles.fieldGrid}>
            <ChoiceField
              id="settings-target-exists"
              label={settingsCopy.targetExists}
              options={initial.choices.target_exists_policies}
              register={register("collision.on_target_exists")}
            />
            <ChoiceField
              id="settings-duplicate-hash"
              label={settingsCopy.duplicateHash}
              options={initial.choices.duplicate_hash_policies}
              register={register("collision.on_duplicate_hash")}
            />
            <ChoiceField
              id="settings-missing-metadata"
              label={settingsCopy.missingMetadata}
              options={initial.choices.missing_metadata_policies}
              register={register("collision.on_missing_metadata")}
            />
          </div>
        </SettingsSection>

        <SettingsSection
          description={settingsCopy.musicbrainzHelp}
          title={settingsCopy.musicbrainzTitle}
        >
          <BooleanField
            id="settings-musicbrainz-enabled"
            label={settingsCopy.musicbrainzEnabled}
            register={register("musicbrainz.enabled")}
          />
          <div className={styles.fieldGrid}>
            <label
              className={styles.field}
              htmlFor="settings-musicbrainz-application-name"
            >
              {settingsCopy.musicbrainzApplicationName}
              <input
                id="settings-musicbrainz-application-name"
                {...register("musicbrainz.application_name")}
              />
            </label>
            <label
              className={styles.field}
              htmlFor="settings-musicbrainz-contact"
            >
              {settingsCopy.musicbrainzContact}
              <input
                id="settings-musicbrainz-contact"
                {...register("musicbrainz.contact")}
              />
            </label>
            <label
              className={styles.field}
              htmlFor="settings-musicbrainz-timeout"
            >
              {settingsCopy.musicbrainzTimeout}
              <input
                id="settings-musicbrainz-timeout"
                min="0.001"
                required
                step="any"
                type="number"
                {...register("musicbrainz.timeout_seconds", {
                  setValueAs: requiredNumber,
                })}
              />
            </label>
            <label
              className={styles.field}
              htmlFor="settings-musicbrainz-retry-limit"
            >
              {settingsCopy.musicbrainzRetryLimit}
              <input
                id="settings-musicbrainz-retry-limit"
                min="0"
                required
                step="1"
                type="number"
                {...register("musicbrainz.retry_limit", {
                  setValueAs: requiredNumber,
                })}
              />
            </label>
            <label
              className={styles.field}
              htmlFor="settings-musicbrainz-rate-limit"
            >
              {settingsCopy.musicbrainzRateLimit}
              <input
                id="settings-musicbrainz-rate-limit"
                min="1"
                required
                step="any"
                type="number"
                {...register("musicbrainz.rate_limit_seconds", {
                  setValueAs: requiredNumber,
                })}
              />
            </label>
            <ChoiceField
              id="settings-musicbrainz-cache-policy"
              label={settingsCopy.musicbrainzCachePolicy}
              options={initial.choices.musicbrainz_cache_policies}
              register={register("musicbrainz.cache_policy")}
            />
          </div>
        </SettingsSection>

        <SettingsSection
          description={settingsCopy.hashingHelp}
          title={settingsCopy.hashingTitle}
        >
          <label className={styles.field} htmlFor="settings-hashing-chunk-size">
            {settingsCopy.hashingReadChunkSize}
            <input
              id="settings-hashing-chunk-size"
              min="1"
              required
              step="1"
              type="number"
              {...register("hashing.read_chunk_size_bytes", {
                setValueAs: requiredNumber,
              })}
            />
          </label>
        </SettingsSection>

        <SettingsSection
          description={settingsCopy.loggingHelp}
          title={settingsCopy.loggingTitle}
        >
          <p className={styles.help} id="settings-logging-restart">
            {settingsCopy.loggingRestart}
          </p>
          <div className={styles.fieldGrid}>
            <div className={styles.field}>
              <label htmlFor="settings-logging-destination">
                {settingsCopy.loggingDestination}
              </label>
              <input
                aria-describedby="settings-logging-destination-help settings-logging-restart"
                id="settings-logging-destination"
                {...register("logging.destination", {
                  setValueAs: nullableString,
                })}
              />
              <span
                className={styles.help}
                id="settings-logging-destination-help"
              >
                {settingsCopy.loggingDestinationHelp}
              </span>
            </div>
            <ChoiceField
              describedBy="settings-logging-restart"
              id="settings-logging-level"
              label={settingsCopy.loggingLevel}
              options={initial.choices.logging_levels}
              register={register("logging.level")}
            />
            <label className={styles.field} htmlFor="settings-logging-rotation">
              {settingsCopy.loggingRotationMaxBytes}
              <input
                aria-describedby="settings-logging-restart"
                id="settings-logging-rotation"
                min="1"
                required
                step="1"
                type="number"
                {...register("logging.rotation_max_bytes", {
                  setValueAs: requiredNumber,
                })}
              />
            </label>
            <label
              className={styles.field}
              htmlFor="settings-logging-retention"
            >
              {settingsCopy.loggingRetentionFiles}
              <input
                aria-describedby="settings-logging-restart"
                id="settings-logging-retention"
                min="1"
                required
                step="1"
                type="number"
                {...register("logging.retention_files", {
                  setValueAs: requiredNumber,
                })}
              />
            </label>
          </div>
        </SettingsSection>

        <SettingsSection
          description={settingsCopy.companionsHelp}
          title={settingsCopy.companionsTitle}
        >
          <BooleanField
            id="settings-companions-enabled"
            label={settingsCopy.companionsEnabled}
            register={register("companions.enabled")}
          />
        </SettingsSection>

        <SettingsSection
          description={settingsCopy.unprocessedHelp}
          title={settingsCopy.unprocessedTitle}
        >
          <BooleanField
            id="settings-unprocessed-enabled"
            label={settingsCopy.unprocessedEnabled}
            register={register("unprocessed.enabled")}
          />
          <div className={styles.fieldGrid}>
            <div className={styles.field}>
              <label htmlFor="settings-unprocessed-directory">
                {settingsCopy.unprocessedDirectory}
              </label>
              <input
                aria-describedby="settings-unprocessed-directory-help"
                id="settings-unprocessed-directory"
                required
                {...register("unprocessed.directory")}
              />
              <span
                className={styles.help}
                id="settings-unprocessed-directory-help"
              >
                {settingsCopy.unprocessedDirectoryHelp}
              </span>
            </div>
            <div className={styles.field}>
              <label htmlFor="settings-unprocessed-preview-limit">
                {settingsCopy.unprocessedResultPreviewLimit}
              </label>
              <input
                aria-describedby="settings-unprocessed-preview-limit-help"
                id="settings-unprocessed-preview-limit"
                max={initial.choices.unprocessed_result_preview_limit_max}
                min={initial.choices.unprocessed_result_preview_limit_min}
                required
                step="1"
                type="number"
                {...register("unprocessed.result_preview_limit", {
                  setValueAs: requiredNumber,
                })}
              />
              <span
                className={styles.help}
                id="settings-unprocessed-preview-limit-help"
              >
                {settingsCopy.unprocessedResultPreviewLimitHelp}{" "}
                {initial.choices.unprocessed_result_preview_limit_min}–
                {initial.choices.unprocessed_result_preview_limit_max}.
              </span>
            </div>
          </div>
        </SettingsSection>

        <SettingsSection
          description={settingsCopy.previewBody}
          title={settingsCopy.previewTitle}
        >
          <PreviewResult preview={preview} updating={previewQuery.isFetching} />
          <div className={styles.fieldGrid}>
            <SampleTextField
              id="settings-sample-artist"
              label={settingsCopy.sampleArtist}
              onChange={(value) =>
                setPreviewSample((current) => ({
                  ...current,
                  metadata: { ...current.metadata, artist: value },
                }))
              }
              value={previewSample.metadata.artist ?? ""}
            />
            <SampleTextField
              id="settings-sample-album-artist"
              label={settingsCopy.sampleAlbumArtist}
              onChange={(value) =>
                setPreviewSample((current) => ({
                  ...current,
                  metadata: { ...current.metadata, album_artist: value },
                }))
              }
              value={previewSample.metadata.album_artist ?? ""}
            />
            <SampleTextField
              id="settings-sample-album"
              label={settingsCopy.sampleAlbum}
              onChange={(value) =>
                setPreviewSample((current) => ({
                  ...current,
                  metadata: { ...current.metadata, album: value },
                }))
              }
              value={previewSample.metadata.album ?? ""}
            />
            <SampleTextField
              id="settings-sample-title"
              label={settingsCopy.sampleTitle}
              onChange={(value) =>
                setPreviewSample((current) => ({
                  ...current,
                  metadata: { ...current.metadata, title: value },
                }))
              }
              value={previewSample.metadata.title ?? ""}
            />
            <SampleNumberField
              id="settings-sample-year"
              label={settingsCopy.sampleYear}
              onChange={(value) =>
                setPreviewSample((current) => ({
                  ...current,
                  metadata: { ...current.metadata, year: value },
                }))
              }
              value={previewSample.metadata.year}
            />
            <SampleNumberField
              id="settings-sample-disc"
              label={settingsCopy.sampleDisc}
              onChange={(value) =>
                setPreviewSample((current) => ({
                  ...current,
                  metadata: { ...current.metadata, disc_number: value },
                }))
              }
              value={previewSample.metadata.disc_number}
            />
            <SampleNumberField
              id="settings-sample-track"
              label={settingsCopy.sampleTrack}
              onChange={(value) =>
                setPreviewSample((current) => ({
                  ...current,
                  metadata: { ...current.metadata, track_number: value },
                }))
              }
              value={previewSample.metadata.track_number}
            />
            <SampleTextField
              id="settings-sample-extension"
              label={settingsCopy.sampleExtension}
              onChange={(value) =>
                setPreviewSample((current) => ({
                  ...current,
                  file_extension: value,
                }))
              }
              value={previewSample.file_extension}
            />
          </div>
          {previewQuery.isError ? (
            <div className={styles.previewError} role="alert">
              <p>{settingsCopy.previewError}</p>
              <Button
                onClick={() => void previewQuery.refetch()}
                variant="secondary"
              >
                {settingsCopy.retryPreview}
              </Button>
            </div>
          ) : null}
        </SettingsSection>
      </form>

      {lastSavedCandidate === null ? null : (
        <section className={styles.review}>
          <h2>{settingsCopy.lastSavedChanges}</h2>
          <ReviewResult result={lastSavedCandidate} />
        </section>
      )}

      {actionError === null ? null : (
        <ActionError
          error={actionError}
          onLoadLatest={onLoadLatest}
          onRetry={retryAvailable ? retryAutosave : undefined}
        />
      )}

      <LiveRegion>{saveStatusLabel(saveStatus)}</LiveRegion>
      <LiveRegion>{announcement}</LiveRegion>

      <Dialog
        closeLabel={settingsCopy.closeUnsaved}
        initialFocusRef={stayButtonRef}
        label={settingsCopy.unsavedTitle}
        onRequestClose={() => blocker.reset?.()}
        open={blocker.state === "blocked"}
        returnFocusRef={saveStatusRef}
      >
        <p>{settingsCopy.unsavedBody}</p>
        <div className={styles.dialogActions}>
          <Button onClick={() => blocker.reset?.()} ref={stayButtonRef}>
            {settingsCopy.stay}
          </Button>
          <Button onClick={() => blocker.proceed?.()} variant="quiet">
            {settingsCopy.leave}
          </Button>
        </div>
      </Dialog>
    </article>
  );
}

function SettingsSection({
  children,
  description,
  id,
  title,
}: {
  children: React.ReactNode;
  description?: string;
  id?: string;
  title: string;
}) {
  return (
    <section
      className={styles.section}
      id={id}
      tabIndex={id === undefined ? undefined : -1}
    >
      <div className={styles.sectionHeader}>
        <h2>{title}</h2>
        {description === undefined ? null : <p>{description}</p>}
      </div>
      {children}
    </section>
  );
}

function ChoiceField({
  describedBy,
  id,
  label,
  options,
  register,
}: {
  describedBy?: string;
  id: string;
  label: string;
  options: string[];
  register: ReturnType<
    ReturnType<typeof useForm<AppConfigResource>>["register"]
  >;
}) {
  return (
    <label className={styles.field} htmlFor={id}>
      {label}
      <select aria-describedby={describedBy} id={id} {...register}>
        {options.map((option) => (
          <option key={option} value={option}>
            {humanize(option)}
          </option>
        ))}
      </select>
    </label>
  );
}

function BooleanField({
  id,
  label,
  register,
}: {
  id: string;
  label: string;
  register: ReturnType<
    ReturnType<typeof useForm<AppConfigResource>>["register"]
  >;
}) {
  return (
    <label className={styles.checkbox} htmlFor={id}>
      <input id={id} type="checkbox" {...register} />
      <span>{label}</span>
    </label>
  );
}

function ArtistNameMappings({
  entries,
  mappingDetails,
  onChange,
}: {
  entries: Record<string, string>;
  mappingDetails: ArtistNameMappingEntry[];
  onChange: (entries: Record<string, string>) => void;
}) {
  return (
    <StringMappingEntries
      addLabel={settingsCopy.addDisplayName}
      entries={entries}
      entriesTitle={settingsCopy.displayNameEntriesTitle}
      idPrefix="settings-artist-name"
      manualSourceLabel={settingsCopy.manualDisplayNameSource}
      manualValueLabel={settingsCopy.manualDisplayName}
      noEntriesLabel={settingsCopy.noDisplayNameEntries}
      onChange={onChange}
      entryDetail={(source) =>
        artistNameMappingSourceLabel(source, entries[source], mappingDetails)
      }
      requireValue
      sourceLabel={settingsCopy.originalArtistName}
      valueLabel={settingsCopy.displayName}
    />
  );
}

function StringMappingEntries({
  addLabel,
  entries,
  entryDetail,
  entriesTitle,
  idPrefix,
  manualSourceLabel,
  manualValueLabel,
  monospaceValue = false,
  noEntriesLabel,
  onChange,
  requireValue = false,
  sourceLabel,
  valueLabel,
}: {
  addLabel: string;
  entries: Record<string, string>;
  entryDetail?: (source: string) => string;
  entriesTitle: string;
  idPrefix: string;
  manualSourceLabel: string;
  manualValueLabel: string;
  monospaceValue?: boolean;
  noEntriesLabel: string;
  onChange: (entries: Record<string, string>) => void;
  requireValue?: boolean;
  sourceLabel: string;
  valueLabel: string;
}) {
  const [newSource, setNewSource] = useState("");
  const [newValue, setNewValue] = useState("");
  const sortedEntries = Object.entries(entries).sort(([left], [right]) =>
    left.localeCompare(right),
  );

  function addEntry() {
    const source = newSource.trim();
    if (source.length === 0) {
      return;
    }
    if (requireValue && newValue.trim().length === 0) {
      return;
    }
    onChange({ ...entries, [source]: newValue });
    setNewSource("");
    setNewValue("");
  }

  return (
    <div className={styles.entries}>
      <h3>{entriesTitle}</h3>
      {sortedEntries.length === 0 ? <p>{noEntriesLabel}</p> : null}
      {sortedEntries.length > 0 ? (
        <ul className={styles.entryList}>
          {sortedEntries.map(([source, value]) => {
            const detail = entryDetail?.(source);
            return (
              <li className={styles.entry} key={source}>
                <div>
                  <span className={styles.entryLabel}>{sourceLabel}</span>
                  <code>{source}</code>
                  {detail === undefined ? null : (
                    <>
                      <span className={styles.entryLabel}>
                        {settingsCopy.artistNameSource}
                      </span>
                      <span className={styles.entryMetadata}>{detail}</span>
                    </>
                  )}
                </div>
                <label className={styles.field}>
                  {valueLabel}
                  <input
                    className={monospaceValue ? styles.monoInput : undefined}
                    onChange={(event) =>
                      onChange({
                        ...entries,
                        [source]: event.currentTarget.value,
                      })
                    }
                    value={value}
                  />
                </label>
                <Button
                  onClick={() => {
                    const nextEntries = { ...entries };
                    delete nextEntries[source];
                    onChange(nextEntries);
                  }}
                  variant="quiet"
                >
                  {settingsCopy.removeEntry}
                </Button>
              </li>
            );
          })}
        </ul>
      ) : null}
      <div className={styles.entryComposer}>
        <label className={styles.field} htmlFor={`${idPrefix}-new-source`}>
          {manualSourceLabel}
          <input
            id={`${idPrefix}-new-source`}
            onChange={(event) => setNewSource(event.currentTarget.value)}
            value={newSource}
          />
        </label>
        <label className={styles.field} htmlFor={`${idPrefix}-new-value`}>
          {manualValueLabel}
          <input
            className={monospaceValue ? styles.monoInput : undefined}
            id={`${idPrefix}-new-value`}
            onChange={(event) => setNewValue(event.currentTarget.value)}
            value={newValue}
          />
        </label>
        <Button
          disabled={
            newSource.trim().length === 0 ||
            (requireValue && newValue.trim().length === 0)
          }
          onClick={addEntry}
        >
          {addLabel}
        </Button>
      </div>
    </div>
  );
}

function PreviewResult({
  preview,
  updating,
}: {
  preview: PathPreview;
  updating: boolean;
}) {
  return (
    <div aria-busy={updating} className={styles.preview} role="status">
      {preview.path === null ? (
        <p>{settingsCopy.previewUnavailable}</p>
      ) : (
        <code>{preview.path}</code>
      )}
      {updating ? (
        <span className={styles.previewActivity}>
          {settingsCopy.previewing}
        </span>
      ) : null}
      <DiagnosticList diagnostics={preview.errors} />
    </div>
  );
}

function createPreviewRequest(
  config: AppConfigResource,
  sample: PreviewSample,
): PathPreviewRequest {
  return {
    artist_ids: config.artist_ids,
    file_extension: sample.file_extension,
    metadata: sample.metadata,
    path_policy: config.path_policy,
  };
}

function artistNameMappingEntries(
  result: ArtistNameMappingsData,
): Record<string, string> {
  return Object.fromEntries(
    result.entries.map((entry) => [entry.source_name, entry.english_name]),
  );
}

function artistNameMappingSourceLabel(
  sourceName: string,
  currentName: string | undefined,
  mappings: ArtistNameMappingEntry[],
): string {
  const mapping = mappings.find((entry) => entry.source_name === sourceName);
  if (mapping === undefined) {
    return settingsCopy.artistNameSourceUserEntered;
  }
  if (mapping.source === "user" || mapping.english_name !== currentName) {
    return settingsCopy.artistNameSourceUserEdited;
  }
  const locale = mapping.selected_locale;
  switch (mapping.selected_name_kind) {
    case "alias_sort_name":
      return `${settingsCopy.artistNameSourceMusicBrainz} · ${locale ?? settingsCopy.artistNameSourceUnknownLocale} ${settingsCopy.artistNameSourceAliasSortName}`;
    case "alias":
      return `${settingsCopy.artistNameSourceMusicBrainz} · ${locale ?? settingsCopy.artistNameSourceUnknownLocale} ${settingsCopy.artistNameSourceAliasName}`;
    case "sort_name":
      return `${settingsCopy.artistNameSourceMusicBrainz} · ${settingsCopy.artistNameSourceArtistSortName}`;
    case "name":
      return `${settingsCopy.artistNameSourceMusicBrainz} · ${settingsCopy.artistNameSourceArtistName}`;
    case null:
      return settingsCopy.artistNameSourceMusicBrainz;
  }
}

function useDebouncedValue<Value>(value: Value, delayMs: number): Value {
  const [debouncedValue, setDebouncedValue] = useState(value);

  useEffect(() => {
    const timer = globalThis.setTimeout(() => {
      setDebouncedValue(value);
    }, delayMs);
    return () => globalThis.clearTimeout(timer);
  }, [delayMs, value]);

  return debouncedValue;
}

function saveStatusLabel(status: SaveStatus): string {
  switch (status) {
    case "attention":
      return settingsCopy.autosaveNeedsAttention;
    case "checking":
      return settingsCopy.autosaveChecking;
    case "saved":
      return settingsCopy.autosaveSaved;
    case "saving":
      return settingsCopy.autosaveSaving;
    case "unsaved":
      return settingsCopy.autosaveUnsaved;
  }
}

function resolveSaveStatus({
  acknowledgedFingerprint,
  autosavePaused,
  canSave,
  clientDraftValid,
  draftFingerprint,
  failedFingerprint,
  inFlightCandidate,
  persistedConfigValid,
  saveActivity,
}: {
  acknowledgedFingerprint: string;
  autosavePaused: "conflict" | "failure" | null;
  canSave: boolean;
  clientDraftValid: boolean;
  draftFingerprint: string;
  failedFingerprint: string | null;
  inFlightCandidate: DraftCandidate | null;
  persistedConfigValid: boolean;
  saveActivity: "checking" | "saving" | null;
}): SaveStatus {
  if (
    !clientDraftValid ||
    autosavePaused !== null ||
    failedFingerprint === draftFingerprint
  ) {
    return "attention";
  }
  if (draftFingerprint === acknowledgedFingerprint) {
    if (inFlightCandidate !== null) {
      return "saving";
    }
    return persistedConfigValid ? "saved" : "attention";
  }
  if (!canSave) {
    return "attention";
  }
  if (saveActivity === "checking") {
    return "checking";
  }
  if (inFlightCandidate?.fingerprint === draftFingerprint) {
    return "saving";
  }
  return "unsaved";
}

function saveStatusDescription(status: SaveStatus): string {
  switch (status) {
    case "attention":
      return settingsCopy.autosaveAttentionBody;
    case "checking":
      return settingsCopy.autosaveCheckingBody;
    case "saved":
      return settingsCopy.autosaveSavedBody;
    case "saving":
      return settingsCopy.autosaveSavingBody;
    case "unsaved":
      return settingsCopy.autosaveUnsavedBody;
  }
}

function ReviewResult({ result }: { result: SettingsCandidateData }) {
  return (
    <div className={styles.reviewResult}>
      <p className={result.validation.valid ? styles.valid : styles.invalid}>
        {result.validation.valid ? settingsCopy.valid : settingsCopy.invalid}
      </p>
      <DiagnosticList
        diagnostics={result.validation.errors}
        label={settingsCopy.validationErrors}
        linked
      />
      {result.changes.length === 0 ? (
        <p>{settingsCopy.noChanges}</p>
      ) : (
        <div className={styles.diffScroller}>
          <table className={styles.diff}>
            <thead>
              <tr>
                <th scope="col">{settingsCopy.field}</th>
                <th scope="col">{settingsCopy.before}</th>
                <th scope="col">{settingsCopy.after}</th>
              </tr>
            </thead>
            <tbody>
              {result.changes.map((change) => (
                <tr key={change.field}>
                  <th scope="row">
                    <code>{change.field}</code>
                  </th>
                  <td>{formatChangeValue(change.before)}</td>
                  <td>{formatChangeValue(change.after)}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}
    </div>
  );
}

function ActionError({
  error,
  onLoadLatest,
  onRetry,
}: {
  error: unknown;
  onLoadLatest: () => Promise<void>;
  onRetry?: () => void;
}) {
  if (
    hasSettingsErrorCode(error, "config_changed") ||
    hasSettingsErrorCode(error, "artist_name_mappings_changed")
  ) {
    return (
      <ValidationPanel
        body={settingsCopy.conflictBody}
        diagnostics={settingsDiagnostics(error)}
        title={settingsCopy.conflictTitle}
        variant="error"
      >
        <Button onClick={() => void onLoadLatest()} variant="secondary">
          {settingsCopy.loadLatest}
        </Button>
      </ValidationPanel>
    );
  }
  if (hasSettingsErrorCode(error, "operation_in_progress")) {
    return (
      <ValidationPanel
        body={settingsCopy.lockBody}
        diagnostics={settingsDiagnostics(error)}
        title={settingsCopy.lockTitle}
        variant="warning"
      >
        <RetryAutosaveButton onRetry={onRetry} />
      </ValidationPanel>
    );
  }
  if (hasSettingsErrorCode(error, "config_io_failed")) {
    return (
      <ValidationPanel
        body={settingsCopy.ioBody}
        diagnostics={settingsDiagnostics(error)}
        title={settingsCopy.ioTitle}
        variant="error"
      >
        <RetryAutosaveButton onRetry={onRetry} />
      </ValidationPanel>
    );
  }
  if (
    hasSettingsErrorCode(error, "validation_failed") ||
    hasSettingsErrorCode(error, "config_invalid")
  ) {
    return (
      <ValidationPanel
        body={settingsCopy.invalid}
        diagnostics={settingsDiagnostics(error)}
        title={settingsCopy.validationTitle}
        variant="warning"
      />
    );
  }
  if (error instanceof SettingsTransportError) {
    return (
      <ValidationPanel
        body={settingsCopy.disconnectedBody}
        diagnostics={[]}
        title={settingsCopy.disconnectedTitle}
        variant="error"
      >
        <RetryAutosaveButton onRetry={onRetry} />
      </ValidationPanel>
    );
  }
  if (error instanceof SettingsCsrfRefreshError) {
    return (
      <ValidationPanel
        body={settingsCopy.csrfRefreshFailed}
        diagnostics={[]}
        title={settingsCopy.unexpectedTitle}
        variant="error"
      >
        <RetryAutosaveButton onRetry={onRetry} />
      </ValidationPanel>
    );
  }
  return (
    <ValidationPanel
      body={
        error instanceof Error ? error.message : settingsCopy.unexpectedTitle
      }
      diagnostics={settingsDiagnostics(error)}
      title={settingsCopy.unexpectedTitle}
      variant="error"
    >
      <RetryAutosaveButton onRetry={onRetry} />
    </ValidationPanel>
  );
}

function RetryAutosaveButton({ onRetry }: { onRetry?: () => void }) {
  return onRetry === undefined ? null : (
    <Button onClick={onRetry} variant="secondary">
      {settingsCopy.retryAutosave}
    </Button>
  );
}

function ValidationPanel({
  body,
  children,
  diagnostics,
  title,
  variant,
}: {
  body: string;
  children?: React.ReactNode;
  diagnostics: ApiError[];
  title: string;
  variant: "error" | "warning";
}) {
  return (
    <section
      className={`${styles.notice} ${styles[variant]}`}
      role={variant === "error" ? "alert" : "status"}
    >
      <h2>{title}</h2>
      <p>{body}</p>
      <DiagnosticList diagnostics={diagnostics} linked />
      {children}
    </section>
  );
}

function DiagnosticList({
  diagnostics,
  label = settingsCopy.validationErrors,
  linked = false,
}: {
  diagnostics: ApiError[];
  label?: string;
  linked?: boolean;
}) {
  if (diagnostics.length === 0) {
    return null;
  }
  return (
    <ul aria-label={label} className={styles.diagnostics}>
      {diagnostics.map((diagnostic) => {
        const target = linked ? errorFieldTarget(diagnostic.field) : null;
        return (
          <li
            key={`${diagnostic.code}:${diagnostic.field ?? ""}:${diagnostic.message}`}
          >
            {target === null ? (
              diagnostic.message
            ) : (
              <a
                href={`#${target}`}
                onClick={(event) => {
                  event.preventDefault();
                  document.getElementById(target)?.focus();
                }}
              >
                {diagnostic.message}
              </a>
            )}
          </li>
        );
      })}
    </ul>
  );
}

function SampleTextField({
  id,
  label,
  onChange,
  value,
}: {
  id: string;
  label: string;
  onChange: (value: string) => void;
  value: string;
}) {
  return (
    <label className={styles.field} htmlFor={id}>
      {label}
      <input
        id={id}
        onChange={(event) => onChange(event.currentTarget.value)}
        value={value}
      />
    </label>
  );
}

function SampleNumberField({
  id,
  label,
  onChange,
  value,
}: {
  id: string;
  label: string;
  onChange: (value: number | null) => void;
  value: number | null | undefined;
}) {
  return (
    <label className={styles.field} htmlFor={id}>
      {label}
      <input
        id={id}
        min="1"
        onChange={(event) => onChange(optionalNumber(event))}
        type="number"
        value={value ?? ""}
      />
    </label>
  );
}

class SettingsCsrfRefreshError extends Error {
  constructor() {
    super(settingsCopy.csrfRefreshFailed);
    this.name = "SettingsCsrfRefreshError";
  }
}

function nullableString(value: unknown): string | null {
  return typeof value === "string" && value.length > 0 ? value : null;
}

function requiredNumber(value: unknown): number {
  if (typeof value === "number") {
    return value;
  }
  return typeof value === "string" && value.length > 0 ? Number(value) : 0;
}

function optionalNumber(event: ChangeEvent<HTMLInputElement>): number | null {
  return event.currentTarget.value.length === 0
    ? null
    : event.currentTarget.valueAsNumber;
}

function humanize(value: string): string {
  return value.replaceAll("_", " ");
}

function formatChangeValue(value: SettingsChangeValue): string {
  if (value === null) {
    return "Not set";
  }
  if (typeof value === "boolean") {
    return value ? "Enabled" : "Disabled";
  }
  return String(value);
}

function settingsDiagnostics(error: unknown): ApiError[] {
  return error instanceof SettingsApiError ? error.envelope.errors : [];
}

function actionErrorAnnouncement(error: unknown): string {
  if (hasSettingsErrorCode(error, "config_changed")) {
    return settingsCopy.conflictTitle;
  }
  if (hasSettingsErrorCode(error, "operation_in_progress")) {
    return settingsCopy.lockTitle;
  }
  if (hasSettingsErrorCode(error, "config_io_failed")) {
    return settingsCopy.ioTitle;
  }
  if (
    hasSettingsErrorCode(error, "validation_failed") ||
    hasSettingsErrorCode(error, "config_invalid")
  ) {
    return settingsCopy.validationTitle;
  }
  if (error instanceof SettingsTransportError) {
    return settingsCopy.disconnectedTitle;
  }
  return settingsCopy.unexpectedTitle;
}

function errorFieldTarget(field: string | undefined): string | null {
  if (field === undefined) {
    return null;
  }
  const targets: Array<[string, string]> = [
    ["paths.library", "settings-paths-library"],
    ["paths.incoming", "settings-paths-incoming"],
    ["path_policy.template", "settings-path-policy-template"],
    ["path_policy.unknown_artist", "settings-unknown-artist"],
    ["path_policy.unknown_album", "settings-unknown-album"],
    ["path_policy.max_filename_length", "settings-max-filename"],
    ["path_policy.disc_number_style", "settings-disc-style"],
    ["path_policy.disc_number_condition", "settings-disc-condition"],
    ["path_policy.sanitize", "settings-sanitize"],
    ["artist_ids.max_length", "settings-artist-max-length"],
    ["artist_ids.fallback_id", "settings-artist-fallback"],
    ["metadata.prefer_album_artist", "settings-prefer-album-artist"],
    ["metadata.require_title", "settings-require-title"],
    ["metadata.require_artist", "settings-require-artist"],
    ["metadata.require_album", "settings-require-album"],
    ["metadata.album_year_resolution", "settings-album-year"],
    ["collision.on_target_exists", "settings-target-exists"],
    ["collision.on_duplicate_hash", "settings-duplicate-hash"],
    ["collision.on_missing_metadata", "settings-missing-metadata"],
    ["musicbrainz.enabled", "settings-musicbrainz-enabled"],
    ["musicbrainz.application_name", "settings-musicbrainz-application-name"],
    ["musicbrainz.contact", "settings-musicbrainz-contact"],
    ["musicbrainz.timeout_seconds", "settings-musicbrainz-timeout"],
    ["musicbrainz.retry_limit", "settings-musicbrainz-retry-limit"],
    ["musicbrainz.rate_limit_seconds", "settings-musicbrainz-rate-limit"],
    ["musicbrainz.cache_policy", "settings-musicbrainz-cache-policy"],
    ["hashing.read_chunk_size_bytes", "settings-hashing-chunk-size"],
    ["logging.destination", "settings-logging-destination"],
    ["logging.level", "settings-logging-level"],
    ["logging.rotation_max_bytes", "settings-logging-rotation"],
    ["logging.retention_files", "settings-logging-retention"],
    ["companions.enabled", "settings-companions-enabled"],
    ["unprocessed.enabled", "settings-unprocessed-enabled"],
    ["unprocessed.directory", "settings-unprocessed-directory"],
    ["unprocessed.result_preview_limit", "settings-unprocessed-preview-limit"],
  ];
  return targets.find(([path]) => field.includes(path))?.[1] ?? null;
}

function stableFingerprint(value: unknown): string {
  return JSON.stringify(sortFingerprintValue(value));
}

function configFieldsAreValid(form: HTMLFormElement | null): boolean {
  if (form === null) {
    return true;
  }
  return Array.from(form.elements).every(
    (element) =>
      !(
        element instanceof HTMLInputElement ||
        element instanceof HTMLSelectElement ||
        element instanceof HTMLTextAreaElement
      ) ||
      element.name.length === 0 ||
      element.validity.valid,
  );
}

function sortFingerprintValue(value: unknown): unknown {
  if (Array.isArray(value)) {
    return value.map(sortFingerprintValue);
  }
  if (value !== null && typeof value === "object") {
    return Object.fromEntries(
      Object.entries(value)
        .sort(([left], [right]) => left.localeCompare(right))
        .map(([key, nestedValue]) => [key, sortFingerprintValue(nestedValue)]),
    );
  }
  return value;
}
