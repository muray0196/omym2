/**
 * Summary: Renders the recovery-capable Settings draft, preview, review, and atomic save flow.
 * Why: Gives users a revision-safe form without reimplementing backend Config or PathPolicy rules.
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
import { Controller, useForm, useWatch } from "react-hook-form";
import { useBeforeUnload, useBlocker } from "react-router-dom";

import type {
  ApiError,
  AppConfigResource,
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
  generateArtistIds,
  hasSettingsErrorCode,
  isCsrfInvalidSettingsError,
  previewSettingsDraft,
  saveSettingsDraft,
  settingsQueryKey,
  SettingsApiError,
  SettingsTransportError,
  validateSettingsDraft,
} from "./settings-api";
import { defaultPreviewSample, settingsCopy } from "./settings-copy";
import styles from "./settings.module.css";

type PreviewSample = Pick<PathPreviewRequest, "file_extension" | "metadata">;

const PREVIEW_DEBOUNCE_MS = 250;

type SettingsEditorProps = {
  initial: SettingsData;
  onLoadLatest: () => Promise<void>;
};

export function SettingsEditor({ initial, onLoadLatest }: SettingsEditorProps) {
  const bootstrap = useContext(BootstrapContext);
  const queryClient = useQueryClient();
  const form = useForm<AppConfigResource>({ defaultValues: initial.config });
  const {
    control,
    formState,
    getValues,
    handleSubmit,
    register,
    reset,
    setValue,
  } = form;
  const draft = useWatch({ control });
  const previewArtistIds = useWatch({ control, name: "artist_ids" });
  const previewArtistNames = useWatch({ control, name: "artist_names" });
  const previewPathPolicy = useWatch({ control, name: "path_policy" });
  const draftFingerprint = stableFingerprint(draft);
  const [baseRevision, setBaseRevision] = useState(initial.config_revision);
  const [review, setReview] = useState<SettingsCandidateData | null>(null);
  const [reviewedFingerprint, setReviewedFingerprint] = useState<string | null>(
    null,
  );
  const [previewSample, setPreviewSample] =
    useState<PreviewSample>(defaultPreviewSample);
  const [artistNames, setArtistNames] = useState("");
  const [overwriteArtistIds, setOverwriteArtistIds] = useState(false);
  const [actionError, setActionError] = useState<unknown>(null);
  const [savedRevision, setSavedRevision] = useState<string | null>(null);
  const [announcement, setAnnouncement] = useState("");
  const saveButtonRef = useRef<HTMLButtonElement>(null);
  const stayButtonRef = useRef<HTMLButtonElement>(null);
  const reviewRegionRef = useRef<HTMLElement>(null);
  const errorRegionRef = useRef<HTMLDivElement>(null);
  const savedNotificationRef = useRef<HTMLDivElement>(null);
  const blocker = useBlocker(formState.isDirty);
  const reviewIsCurrent =
    review !== null && reviewedFingerprint === draftFingerprint;
  const canSave = bootstrap?.runtime_capabilities.can_change_settings ?? false;
  const previewRequest = useMemo(
    () => ({
      artist_ids: previewArtistIds,
      artist_names: previewArtistNames,
      file_extension: previewSample.file_extension,
      metadata: previewSample.metadata,
      path_policy: previewPathPolicy,
    }),
    [previewArtistIds, previewArtistNames, previewPathPolicy, previewSample],
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

  useBeforeUnload(
    useCallback(
      (event) => {
        if (formState.isDirty) {
          event.preventDefault();
          event.returnValue = "";
        }
      },
      [formState.isDirty],
    ),
  );

  const validateMutation = useMutation({
    mutationFn: validateSettingsDraft,
    retry: false,
  });
  const artistIdMutation = useMutation({
    mutationFn: generateArtistIds,
    retry: false,
  });
  const saveMutation = useMutation({
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

  async function handleReview(config: AppConfigResource) {
    setActionError(null);
    setSavedRevision(null);
    const fingerprint = stableFingerprint(config);
    try {
      const result = await validateMutation.mutateAsync({
        config,
        expected_config_revision: baseRevision,
      });
      setReview(result);
      setReviewedFingerprint(fingerprint);
      setAnnouncement(
        result.validation.valid ? settingsCopy.valid : settingsCopy.invalid,
      );
      reviewRegionRef.current?.focus();
    } catch (error) {
      presentActionError(error);
    }
  }

  async function handleArtistIdGeneration() {
    setActionError(null);
    const names = artistNames
      .split("\n")
      .map((name) => name.trim())
      .filter((name) => name.length > 0);
    try {
      const result = await artistIdMutation.mutateAsync({
        artist_ids: getValues("artist_ids"),
        artist_names: names,
        overwrite: overwriteArtistIds,
      });
      const entries = { ...getValues("artist_ids.entries") };
      for (const generated of result.entries) {
        entries[generated.source_artist] = generated.artist_id;
      }
      setValue("artist_ids.entries", entries, {
        shouldDirty: true,
        shouldTouch: true,
      });
      setAnnouncement(
        `${result.entries.length} artist ID ${result.entries.length === 1 ? "entry was" : "entries were"} merged into the draft.`,
      );
    } catch (error) {
      presentActionError(error);
    }
  }

  async function handleSave(config: AppConfigResource) {
    setActionError(null);
    setSavedRevision(null);
    try {
      const result = await saveMutation.mutateAsync({
        config,
        expected_config_revision: baseRevision,
      });
      setBaseRevision(result.config_revision);
      setReview(result);
      const savedFingerprint = stableFingerprint(result.config);
      setReviewedFingerprint(savedFingerprint);
      setSavedRevision(result.config_revision);
      reset(result.config);
      setAnnouncement(settingsCopy.saved);
      savedNotificationRef.current?.focus();
      void Promise.all([
        queryClient.invalidateQueries({
          queryKey: settingsQueryKey,
          refetchType: "none",
        }),
        queryClient.invalidateQueries({
          queryKey: bootstrapQuery.queryKey,
        }),
      ]);
    } catch (error) {
      presentActionError(error);
    }
  }

  function presentActionError(error: unknown) {
    setActionError(error);
    setAnnouncement(actionErrorAnnouncement(error));
    errorRegionRef.current?.focus();
  }

  return (
    <article className={styles.page}>
      <div
        className={styles.savedNotificationRegion}
        ref={savedNotificationRef}
        tabIndex={-1}
      >
        {savedRevision === null ? null : (
          <section
            aria-atomic="true"
            className={styles.savedNotification}
            role="status"
          >
            <h2>{settingsCopy.saved}</h2>
            <p>{settingsCopy.savedBody}</p>
            <p className={styles.revision}>
              {settingsCopy.revisionLabel}: <code>{savedRevision}</code>
            </p>
          </section>
        )}
      </div>

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

      {!initial.validation.valid ? (
        <ValidationPanel
          body={settingsCopy.recoveryBody}
          diagnostics={initial.validation.errors}
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
        onSubmit={(event) => void handleSubmit(handleSave)(event)}
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
                {...register("path_policy.unknown_artist")}
              />
            </label>
            <label className={styles.field} htmlFor="settings-unknown-album">
              {settingsCopy.unknownAlbum}
              <input
                id="settings-unknown-album"
                {...register("path_policy.unknown_album")}
              />
            </label>
            <label className={styles.field} htmlFor="settings-max-filename">
              {settingsCopy.maxFilenameLength}
              <input
                id="settings-max-filename"
                min="1"
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
          id="settings-artist-name-preferences"
          title={settingsCopy.artistDisplayNamesTitle}
        >
          <Controller
            control={control}
            name="artist_names.preferences"
            render={({ field }) => (
              <ArtistNamePreferences
                preferences={field.value}
                onChange={field.onChange}
              />
            )}
          />
        </SettingsSection>

        <SettingsSection
          description={settingsCopy.artistIdsHelp}
          id="settings-artist-id-entries"
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
                {...register("artist_ids.fallback_id")}
              />
            </label>
          </div>

          <Controller
            control={control}
            name="artist_ids.entries"
            render={({ field }) => (
              <ArtistIdEntries
                entries={field.value}
                onChange={field.onChange}
              />
            )}
          />

          <div className={styles.generator}>
            <label className={styles.field} htmlFor="settings-artist-names">
              {settingsCopy.artistNames}
              <textarea
                aria-describedby="settings-artist-names-help"
                id="settings-artist-names"
                onChange={(event) => setArtistNames(event.currentTarget.value)}
                rows={4}
                value={artistNames}
              />
            </label>
            <p className={styles.help} id="settings-artist-names-help">
              {settingsCopy.artistNamesHelp}
            </p>
            <label
              className={styles.checkbox}
              htmlFor="settings-overwrite-artists"
            >
              <input
                checked={overwriteArtistIds}
                id="settings-overwrite-artists"
                onChange={(event) =>
                  setOverwriteArtistIds(event.currentTarget.checked)
                }
                type="checkbox"
              />
              <span>{settingsCopy.overwrite}</span>
            </label>
            <Button
              disabled={
                artistIdMutation.isPending || artistNames.trim().length === 0
              }
              onClick={() => void handleArtistIdGeneration()}
              variant="secondary"
            >
              {artistIdMutation.isPending
                ? settingsCopy.generating
                : settingsCopy.generate}
            </Button>
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
          description={settingsCopy.fasttextHelp}
          title={settingsCopy.fasttextTitle}
        >
          <div className={styles.fieldGrid}>
            <div className={styles.field}>
              <label htmlFor="settings-fasttext-model">
                {settingsCopy.fasttextModelPath}
              </label>
              <input
                aria-describedby="settings-fasttext-model-help"
                id="settings-fasttext-model"
                {...register("fasttext.model_path", {
                  setValueAs: nullableString,
                })}
              />
              <span className={styles.help} id="settings-fasttext-model-help">
                {settingsCopy.fasttextModelPathHelp}
              </span>
            </div>
            <label
              className={styles.field}
              htmlFor="settings-fasttext-confidence"
            >
              {settingsCopy.fasttextMinimumConfidence}
              <input
                id="settings-fasttext-confidence"
                max="1"
                min="0"
                step="0.01"
                type="number"
                {...register("fasttext.minimum_confidence", {
                  setValueAs: requiredNumber,
                })}
              />
            </label>
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

        <section className={styles.review} ref={reviewRegionRef} tabIndex={-1}>
          <h2>{settingsCopy.reviewTitle}</h2>
          {review === null ? <p>{settingsCopy.reviewNeeded}</p> : null}
          {review !== null && !reviewIsCurrent ? (
            <p className={styles.warningText}>{settingsCopy.reviewOutdated}</p>
          ) : null}
          {review !== null && reviewIsCurrent ? (
            <ReviewResult result={review} />
          ) : null}
          <div className={styles.reviewActions}>
            <Button
              disabled={validateMutation.isPending || saveMutation.isPending}
              onClick={() => void handleSubmit(handleReview)()}
              type="button"
              variant="secondary"
            >
              {validateMutation.isPending
                ? settingsCopy.reviewing
                : settingsCopy.review}
            </Button>
            <Button
              disabled={
                !canSave || saveMutation.isPending || validateMutation.isPending
              }
              ref={saveButtonRef}
              type="submit"
              variant="primary"
            >
              {saveMutation.isPending ? settingsCopy.saving : settingsCopy.save}
            </Button>
          </div>
        </section>
      </form>

      <div className={styles.focusRegion} ref={errorRegionRef} tabIndex={-1}>
        {actionError === null ? null : (
          <ActionError error={actionError} onLoadLatest={onLoadLatest} />
        )}
      </div>

      <LiveRegion>{announcement}</LiveRegion>

      <Dialog
        closeLabel={settingsCopy.closeUnsaved}
        initialFocusRef={stayButtonRef}
        label={settingsCopy.unsavedTitle}
        onRequestClose={() => blocker.reset?.()}
        open={blocker.state === "blocked"}
        returnFocusRef={saveButtonRef}
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

function ArtistIdEntries({
  entries,
  onChange,
}: {
  entries: Record<string, string>;
  onChange: (entries: Record<string, string>) => void;
}) {
  return (
    <StringMappingEntries
      addLabel={settingsCopy.addEntry}
      entries={entries}
      entriesTitle={settingsCopy.entriesTitle}
      idPrefix="settings-artist-id"
      manualSourceLabel={settingsCopy.manualSource}
      manualValueLabel={settingsCopy.manualId}
      monospaceValue
      noEntriesLabel={settingsCopy.noEntries}
      onChange={onChange}
      sourceLabel={settingsCopy.sourceArtist}
      valueLabel={settingsCopy.artistId}
    />
  );
}

function ArtistNamePreferences({
  preferences,
  onChange,
}: {
  preferences: Record<string, string>;
  onChange: (preferences: Record<string, string>) => void;
}) {
  return (
    <StringMappingEntries
      addLabel={settingsCopy.addDisplayName}
      entries={preferences}
      entriesTitle={settingsCopy.displayNameEntriesTitle}
      idPrefix="settings-artist-name"
      manualSourceLabel={settingsCopy.manualDisplayNameSource}
      manualValueLabel={settingsCopy.manualDisplayName}
      noEntriesLabel={settingsCopy.noDisplayNameEntries}
      onChange={onChange}
      requireValue
      sourceLabel={settingsCopy.sourceArtist}
      valueLabel={settingsCopy.displayName}
    />
  );
}

function StringMappingEntries({
  addLabel,
  entries,
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
          {sortedEntries.map(([source, value]) => (
            <li className={styles.entry} key={source}>
              <div>
                <span className={styles.entryLabel}>{sourceLabel}</span>
                <code>{source}</code>
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
          ))}
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
    artist_names: config.artist_names,
    file_extension: sample.file_extension,
    metadata: sample.metadata,
    path_policy: config.path_policy,
  };
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
}: {
  error: unknown;
  onLoadLatest: () => Promise<void>;
}) {
  if (hasSettingsErrorCode(error, "config_changed")) {
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
      />
    );
  }
  if (hasSettingsErrorCode(error, "config_io_failed")) {
    return (
      <ValidationPanel
        body={settingsCopy.ioBody}
        diagnostics={settingsDiagnostics(error)}
        title={settingsCopy.ioTitle}
        variant="error"
      />
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
      />
    );
  }
  if (error instanceof SettingsCsrfRefreshError) {
    return (
      <ValidationPanel
        body={settingsCopy.csrfRefreshFailed}
        diagnostics={[]}
        title={settingsCopy.unexpectedTitle}
        variant="error"
      />
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
    />
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
    ["artist_ids.entries", "settings-artist-id-entries"],
    ["artist_ids.max_length", "settings-artist-max-length"],
    ["artist_ids.fallback_id", "settings-artist-fallback"],
    ["artist_names.preferences", "settings-artist-name-preferences"],
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
    ["fasttext.model_path", "settings-fasttext-model"],
    ["fasttext.minimum_confidence", "settings-fasttext-confidence"],
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
