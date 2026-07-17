/**
 * Summary: Covers Settings recovery, draft generation, optional review, direct save, concurrency, and CSRF behavior.
 * Why: Protects the revision-safe Config workflow at its generated API and accessible UI boundary.
 */
import { render, screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { QueryClientProvider } from "@tanstack/react-query";
import { http, HttpResponse } from "msw";
import {
  createMemoryRouter,
  Link,
  Outlet,
  RouterProvider,
} from "react-router-dom";
import { describe, expect, it } from "vitest";

import type {
  ApiFailureEnvelope,
  PathPreviewRequest,
  SaveArtistNameMappingsRequestResource,
  SettingsCandidateRequest,
} from "../../api/generated";
import { createQueryClient } from "../../app/query-client";
import { BootstrapContext } from "../bootstrap/bootstrap-context";
import { Component as SettingsRoute } from "../../routes/settings/route";
import { normalBootstrap } from "../../test/fixtures/bootstrap";
import {
  configChangedEnvelope,
  csrfInvalidEnvelope,
  invalidPersistedSettingsEnvelope,
  previewEnvelope,
  savedSettingsEnvelope,
  settingsEnvelopeWithMusicBrainzMapping,
} from "../../test/fixtures/settings";
import { server } from "../../test/server";

const UPDATED_UNPROCESSED_PREVIEW_LIMIT = 250;

describe("Settings route", () => {
  it("renders the default preview and updates it once after sample editing pauses", async () => {
    const user = userEvent.setup();
    const captured: PathPreviewRequest[] = [];
    server.use(
      http.post("*/api/settings/preview", async ({ request }) => {
        const previewRequest = (await request.json()) as PathPreviewRequest;
        captured.push(previewRequest);
        return HttpResponse.json({
          ...previewEnvelope,
          data: {
            ...previewEnvelope.data,
            path: `automatic/${previewRequest.metadata.title}.flac`,
          },
        });
      }),
    );
    renderSettings();

    expect(
      await screen.findByRole("heading", { name: "Settings" }),
    ).toBeInTheDocument();
    expect(await screen.findByLabelText("Library path")).toHaveValue(
      "/music/library",
    );
    expect(screen.getByLabelText("Path template")).toHaveValue(
      "{album_artist}/{year}_{album}/{disc}-{track}_{title}",
    );
    expect(screen.getByLabelText("Maximum artist ID length")).toHaveValue(8);
    expect(
      screen.getByRole("heading", { name: "Romanized artist names" }),
    ).toBeInTheDocument();
    expect(
      screen.getByText("No romanized artist-name mappings have been saved."),
    ).toBeInTheDocument();
    expect(
      screen.getByRole("heading", { name: "Automatic artist IDs" }),
    ).toBeInTheDocument();
    expect(
      screen.getByText(
        "OMYM2 generates {artist_id} automatically from source artist metadata when planning a path. Per-artist IDs are not edited or generated in Settings.",
      ),
    ).toBeInTheDocument();
    expect(
      screen.queryByText("Saved artist ID entries"),
    ).not.toBeInTheDocument();
    expect(
      screen.queryByLabelText("Artist names to generate"),
    ).not.toBeInTheDocument();
    expect(screen.queryByDisplayValue("NORTH")).not.toBeInTheDocument();
    expect(screen.getByLabelText("Require title")).toBeChecked();
    expect(screen.getByLabelText("When a target exists")).toHaveValue(
      "conflict",
    );
    expect(
      screen.getByRole("heading", { name: "MusicBrainz" }),
    ).toBeInTheDocument();
    expect(screen.getByLabelText("Enable MusicBrainz lookup")).toBeChecked();
    expect(screen.getByLabelText("Request timeout (seconds)")).toHaveValue(5);
    expect(screen.getByLabelText("Read chunk size (bytes)")).toHaveValue(
      1_048_576,
    );
    expect(screen.getByLabelText("Relative log destination")).toHaveValue("");
    expect(screen.getByLabelText("Log level")).toHaveValue("INFO");
    expect(
      screen.getByText(
        "Restart required: logging changes take effect the next time the application starts.",
      ),
    ).toBeInTheDocument();
    expect(
      screen.getByLabelText("Relative log destination"),
    ).toHaveAccessibleDescription(
      "Leave empty to use the application-data default destination. Restart required: logging changes take effect the next time the application starts.",
    );
    expect(
      screen.getByLabelText("Enable companion lyrics and artwork"),
    ).not.toBeChecked();
    expect(
      screen.getByLabelText("Enable unprocessed-file collection"),
    ).not.toBeChecked();
    expect(screen.getByLabelText("Destination directory name")).toHaveValue(
      "Unprocessed",
    );
    const resultPreviewLimit = screen.getByLabelText("Result preview limit");
    expect(resultPreviewLimit).toHaveValue(100);
    expect(resultPreviewLimit).toHaveAttribute("min", "1");
    expect(resultPreviewLimit).toHaveAttribute("max", "500");
    expect(resultPreviewLimit).toHaveAccessibleDescription(
      "Choose how many reviewed unprocessed results are shown at once. Allowed range: 1–500.",
    );
    expect(screen.getByText("{artist_id}")).toBeInTheDocument();
    expect(screen.getByLabelText("Sample artist")).toHaveValue("Aimer");
    expect(screen.getByLabelText("Sample title")).toHaveValue("Example Song");
    expect(screen.getByLabelText("Sample file extension")).toHaveValue(".FLAC");
    expect(
      screen.getByText("Aimer/2024_Example-Album/1-03_Example-Song.flac"),
    ).toBeInTheDocument();
    expect(
      screen.queryByRole("button", { name: "Update preview" }),
    ).not.toBeInTheDocument();

    const sampleTitle = screen.getByLabelText("Sample title");
    await user.clear(sampleTitle);
    await user.type(sampleTitle, "Live Preview");

    expect(
      await screen.findByText("automatic/Live Preview.flac"),
    ).toBeInTheDocument();
    expect(captured).toHaveLength(1);
    expect(captured[0]).toMatchObject({
      artist_ids: { fallback_id: "NOART", max_length: 8 },
      file_extension: ".FLAC",
      metadata: { artist: "Aimer", title: "Live Preview" },
      path_policy: {
        template: "{album_artist}/{year}_{album}/{disc}-{track}_{title}",
      },
    });
    expect(captured[0]).not.toHaveProperty("expected_config_revision");
  });

  it("saves editable romanized-name mappings without exposing compact artist IDs", async () => {
    const user = userEvent.setup();
    let captured: SaveArtistNameMappingsRequestResource | undefined;
    server.use(
      http.put("*/api/settings/artist-names", async ({ request }) => {
        captured =
          (await request.json()) as SaveArtistNameMappingsRequestResource;
        return HttpResponse.json({
          data: {
            entries: [
              {
                english_name: "Hikaru Utada",
                selected_locale: null,
                selected_name_kind: null,
                source: "user",
                source_name: "宇多田ヒカル",
              },
            ],
            revision: "artist-name-mappings-revision-two",
          },
          errors: [],
        });
      }),
    );
    renderSettings();

    await user.type(
      await screen.findByLabelText("New original artist name"),
      "宇多田ヒカル",
    );
    await user.type(
      screen.getByLabelText("New romanized artist name"),
      "Hikaru Utada",
    );
    await user.click(screen.getByRole("button", { name: "Add mapping" }));

    expect(await screen.findByDisplayValue("Hikaru Utada")).toBeInTheDocument();
    expect(screen.queryByDisplayValue("NORTH")).not.toBeInTheDocument();
    await user.click(
      screen.getByRole("button", { name: "Save artist-name mappings" }),
    );

    expect(captured).toEqual({
      entries: { 宇多田ヒカル: "Hikaru Utada" },
      expected_revision: "artist-name-mappings-revision-one",
    });
    expect(
      await screen.findByText("Artist-name mappings saved."),
    ).toBeInTheDocument();
  });

  it("shows the exact MusicBrainz fields used for saved artist names", async () => {
    const user = userEvent.setup();
    server.use(
      http.get("*/api/settings", () =>
        HttpResponse.json(settingsEnvelopeWithMusicBrainzMapping),
      ),
    );

    renderSettings();

    expect(
      await screen.findByText("MusicBrainz · ja-Latn alias sort-name"),
    ).toBeInTheDocument();
    expect(
      screen.getByText("MusicBrainz · artist sort-name"),
    ).toBeInTheDocument();
    expect(screen.getByDisplayValue("Sakamoto Ryuichi")).toBeInTheDocument();

    const japaneseLatinName = screen.getByDisplayValue("Sakamoto Ryuichi");
    await user.clear(japaneseLatinName);
    await user.type(japaneseLatinName, "Ryuichi Sakamoto");

    expect(screen.getByText("User-edited")).toBeInTheDocument();
  });

  it("keeps the last preview and offers an explicit retry after automatic failure", async () => {
    const user = userEvent.setup();
    let attempts = 0;
    server.use(
      http.post("*/api/settings/preview", () => {
        attempts += 1;
        if (attempts === 1) {
          return HttpResponse.json(
            {
              data: null,
              errors: [
                {
                  code: "internal_error",
                  message: "Preview failed.",
                  retryable: true,
                },
              ],
            } satisfies ApiFailureEnvelope,
            { status: 500 },
          );
        }
        return HttpResponse.json({
          ...previewEnvelope,
          data: { ...previewEnvelope.data, path: "Recovered-Preview.flac" },
        });
      }),
    );
    renderSettings();

    const sampleTitle = await screen.findByLabelText("Sample title");
    await user.clear(sampleTitle);
    await user.type(sampleTitle, "Retry Preview");

    expect(await screen.findByRole("alert")).toHaveTextContent(
      "Path preview could not be updated",
    );
    expect(
      screen.getByText("Aimer/2024_Example-Album/1-03_Example-Song.flac"),
    ).toBeInTheDocument();
    await user.click(screen.getByRole("button", { name: "Retry preview" }));

    expect(await screen.findByText("Recovered-Preview.flac")).toBeVisible();
    expect(screen.queryByRole("alert")).not.toBeInTheDocument();
    expect(attempts).toBe(2);
  });

  it("does not let a superseded preview response overwrite the latest result", async () => {
    const user = userEvent.setup();
    const requestedTitles: Array<string | null | undefined> = [];
    let releaseSlowPreview: () => void = () => undefined;
    let slowPreviewCompleted = false;
    const slowPreviewHeld = new Promise<void>((resolve) => {
      releaseSlowPreview = resolve;
    });
    server.use(
      http.post("*/api/settings/preview", async ({ request }) => {
        const previewRequest = (await request.json()) as PathPreviewRequest;
        const title = previewRequest.metadata.title;
        requestedTitles.push(title);
        if (title === "Slow Preview") {
          await slowPreviewHeld;
          slowPreviewCompleted = true;
        }
        return HttpResponse.json({
          ...previewEnvelope,
          data: { ...previewEnvelope.data, path: `${title}.flac` },
        });
      }),
    );
    renderSettings();

    const sampleTitle = await screen.findByLabelText("Sample title");
    await user.clear(sampleTitle);
    await user.type(sampleTitle, "Slow Preview");
    await waitFor(() => expect(requestedTitles).toEqual(["Slow Preview"]));

    await user.clear(sampleTitle);
    await user.type(sampleTitle, "Latest Preview");
    expect(await screen.findByText("Latest Preview.flac")).toBeVisible();

    releaseSlowPreview();
    await waitFor(() => expect(slowPreviewCompleted).toBe(true));
    expect(screen.getByText("Latest Preview.flac")).toBeVisible();
    expect(screen.queryByText("Slow Preview.flac")).not.toBeInTheDocument();
  });

  it("reviews a deterministic diff without saving the draft", async () => {
    const user = userEvent.setup();
    let saveCount = 0;
    server.use(
      http.put("*/api/settings", () => {
        saveCount += 1;
        return HttpResponse.json(savedSettingsEnvelope);
      }),
    );
    renderSettings();

    const libraryPath = await screen.findByLabelText("Library path");
    await user.clear(libraryPath);
    await user.type(libraryPath, "/music/new-library");
    await user.click(screen.getByRole("button", { name: "Review changes" }));

    const diff = await screen.findByRole("table");
    expect(within(diff).getByText("paths.library")).toBeInTheDocument();
    expect(within(diff).getByText("/music/library")).toBeInTheDocument();
    expect(within(diff).getByText("/music/new-library")).toBeInTheDocument();
    expect(saveCount).toBe(0);
  });

  it("validates and saves the complete Config in one action with CSRF", async () => {
    const user = userEvent.setup();
    const captured: {
      request?: SettingsCandidateRequest;
      token?: string | null;
    } = {};
    server.use(
      http.put("*/api/settings", async ({ request }) => {
        captured.token = request.headers.get("X-OMYM2-CSRF-Token");
        captured.request = (await request.json()) as SettingsCandidateRequest;
        return HttpResponse.json({
          ...savedSettingsEnvelope,
          data: {
            ...savedSettingsEnvelope.data,
            config: captured.request.config,
          },
        });
      }),
    );
    renderSettings();

    const libraryPath = await screen.findByLabelText("Library path");
    await user.clear(libraryPath);
    await user.type(libraryPath, "/music/new-library");

    const applicationName = screen.getByLabelText("Application name");
    await user.clear(applicationName);
    await user.type(applicationName, "OMYM2 Web Tests");
    const timeout = screen.getByLabelText("Request timeout (seconds)");
    await user.clear(timeout);
    await user.type(timeout, "7.5");
    const retryLimit = screen.getByLabelText("Retry limit");
    await user.clear(retryLimit);
    await user.type(retryLimit, "2");
    const rateLimit = screen.getByLabelText("Rate limit (seconds)");
    await user.clear(rateLimit);
    await user.type(rateLimit, "1.25");

    const chunkSize = screen.getByLabelText("Read chunk size (bytes)");
    await user.clear(chunkSize);
    await user.type(chunkSize, "2097152");

    const destination = screen.getByLabelText("Relative log destination");
    await user.type(destination, "logs/test.log");
    await user.clear(destination);
    await user.selectOptions(screen.getByLabelText("Log level"), "ERROR");
    const rotationSize = screen.getByLabelText("Rotation size (bytes)");
    await user.clear(rotationSize);
    await user.type(rotationSize, "10485760");
    const retainedFiles = screen.getByLabelText("Retained files");
    await user.clear(retainedFiles);
    await user.type(retainedFiles, "5");

    await user.click(
      screen.getByLabelText("Enable companion lyrics and artwork"),
    );
    await user.click(
      screen.getByLabelText("Enable unprocessed-file collection"),
    );
    const unprocessedDirectory = screen.getByLabelText(
      "Destination directory name",
    );
    await user.clear(unprocessedDirectory);
    await user.type(unprocessedDirectory, "Review Later");
    const resultPreviewLimit = screen.getByLabelText("Result preview limit");
    await user.clear(resultPreviewLimit);
    await user.type(
      resultPreviewLimit,
      String(UPDATED_UNPROCESSED_PREVIEW_LIMIT),
    );

    await user.click(screen.getByRole("button", { name: "Save Settings" }));
    const savedHeading = await screen.findByRole("heading", {
      name: "Settings saved.",
    });
    expect(savedHeading).toBeInTheDocument();
    expect(savedHeading.closest('[role="status"]')).toHaveAttribute(
      "aria-atomic",
      "true",
    );
    expect(savedHeading.parentElement?.parentElement).toHaveFocus();
    expect(captured.token).toBe("fixture-csrf-token");
    expect(captured.request?.expected_config_revision).toBe(
      "settings-revision-one",
    );
    expect(captured.request?.config.musicbrainz).toEqual({
      application_name: "OMYM2 Web Tests",
      cache_policy: "sticky_positive",
      contact: "https://github.com/muray0196/omym2",
      enabled: true,
      rate_limit_seconds: 1.25,
      retry_limit: 2,
      timeout_seconds: 7.5,
    });
    expect(captured.request?.config.hashing).toEqual({
      read_chunk_size_bytes: 2_097_152,
    });
    expect(captured.request?.config.logging).toEqual({
      destination: null,
      level: "ERROR",
      retention_files: 5,
      rotation_max_bytes: 10_485_760,
    });
    expect(captured.request?.config.companions).toEqual({ enabled: true });
    expect(captured.request?.config.unprocessed).toEqual({
      directory: "Review Later",
      enabled: true,
      result_preview_limit: UPDATED_UNPROCESSED_PREVIEW_LIMIT,
    });
    const diff = screen.getByRole("table");
    expect(within(diff).getByText("paths.library")).toBeInTheDocument();
    expect(within(diff).getByText("/music/library")).toBeInTheDocument();
    expect(within(diff).getByText("/music/new-library")).toBeInTheDocument();
  });

  it("refreshes Bootstrap and retries the identical save exactly once only for csrf_invalid", async () => {
    const user = userEvent.setup();
    const requests: Array<{ body: string; token: string | null }> = [];
    let saveAttempt = 0;
    server.use(
      http.get("*/api/bootstrap", () =>
        HttpResponse.json({
          ...normalBootstrap,
          data: normalBootstrap.data
            ? { ...normalBootstrap.data, csrf_token: "refreshed-csrf-token" }
            : null,
        }),
      ),
      http.put("*/api/settings", async ({ request }) => {
        saveAttempt += 1;
        requests.push({
          body: await request.text(),
          token: request.headers.get("X-OMYM2-CSRF-Token"),
        });
        return saveAttempt === 1
          ? HttpResponse.json(csrfInvalidEnvelope, { status: 403 })
          : HttpResponse.json(savedSettingsEnvelope);
      }),
    );
    renderSettings();

    const libraryPath = await screen.findByLabelText("Library path");
    await user.clear(libraryPath);
    await user.type(libraryPath, "/music/new-library");
    await user.click(screen.getByRole("button", { name: "Save Settings" }));

    expect(
      await screen.findByRole("heading", { name: "Settings saved." }),
    ).toBeInTheDocument();
    expect(requests).toHaveLength(2);
    expect(requests[0]?.token).toBe("fixture-csrf-token");
    expect(requests[1]?.token).toBe("refreshed-csrf-token");
    expect(requests[1]?.body).toBe(requests[0]?.body);
  });

  it("supports invalid persisted recovery, linked validation focus, and revision conflict guidance", async () => {
    const user = userEvent.setup();
    const invalidSave = {
      data: null,
      errors: [
        {
          code: "validation_failed",
          field: "body.config.path_policy.template",
          message: "The path template must contain a title placeholder.",
          retryable: false,
        },
      ],
    } satisfies ApiFailureEnvelope;
    let saveCount = 0;
    server.use(
      http.get("*/api/settings", () =>
        HttpResponse.json(invalidPersistedSettingsEnvelope),
      ),
      http.put("*/api/settings", () => {
        saveCount += 1;
        return saveCount === 1
          ? HttpResponse.json(invalidSave, { status: 422 })
          : HttpResponse.json(configChangedEnvelope, { status: 409 });
      }),
    );
    renderSettings();

    expect(
      await screen.findByRole("heading", { name: "Configuration recovery" }),
    ).toBeInTheDocument();
    await user.click(screen.getByRole("button", { name: "Save Settings" }));
    const validationLink = await screen.findByRole("link", {
      name: "The path template must contain a title placeholder.",
    });
    await user.click(validationLink);
    expect(screen.getByLabelText("Path template")).toHaveFocus();

    await user.click(screen.getByRole("button", { name: "Save Settings" }));
    const conflictHeading = await screen.findByRole("heading", {
      name: "Configuration changed elsewhere",
    });
    expect(conflictHeading).toBeInTheDocument();
    expect(conflictHeading.parentElement?.parentElement).toHaveFocus();
    expect(
      screen.getByRole("button", { name: "Load latest Settings" }),
    ).toBeInTheDocument();
  });

  it("clears persisted recovery diagnostics after a successful replacement save", async () => {
    const user = userEvent.setup();
    server.use(
      http.get("*/api/settings", () =>
        HttpResponse.json(invalidPersistedSettingsEnvelope),
      ),
      http.put("*/api/settings", () =>
        HttpResponse.json(savedSettingsEnvelope),
      ),
    );
    renderSettings();

    expect(
      await screen.findByRole("heading", { name: "Configuration recovery" }),
    ).toBeInTheDocument();
    await user.click(screen.getByRole("button", { name: "Save Settings" }));

    expect(
      await screen.findByRole("heading", { name: "Settings saved." }),
    ).toBeInTheDocument();
    await waitFor(() =>
      expect(
        screen.queryByRole("heading", { name: "Configuration recovery" }),
      ).not.toBeInTheDocument(),
    );
  });
});

function renderSettings() {
  const bootstrap = normalBootstrap.data;
  if (bootstrap === null) {
    throw new Error("The normal Bootstrap fixture must contain data.");
  }
  const router = createMemoryRouter(
    [
      {
        path: "/",
        Component: () => (
          <BootstrapContext value={bootstrap}>
            <nav>
              <Link to="/next">Next route</Link>
            </nav>
            <Outlet />
          </BootstrapContext>
        ),
        children: [
          { path: "settings", Component: SettingsRoute },
          { path: "next", Component: () => <h1>Next</h1> },
        ],
      },
    ],
    { initialEntries: ["/settings"] },
  );
  const queryClient = createQueryClient();
  return {
    queryClient,
    router,
    ...render(
      <QueryClientProvider client={queryClient}>
        <RouterProvider router={router} />
      </QueryClientProvider>,
    ),
  };
}
