/**
 * Summary: Covers Settings recovery, preview, debounced autosave, concurrency, and CSRF behavior.
 * Why: Protects revision-safe Config persistence and accessible draft status at the generated API boundary.
 */
import {
  act,
  fireEvent,
  render,
  screen,
  waitFor,
  within,
} from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { QueryClientProvider } from "@tanstack/react-query";
import { http, HttpResponse } from "msw";
import {
  createMemoryRouter,
  Link,
  Outlet,
  RouterProvider,
} from "react-router-dom";
import { describe, expect, it, vi } from "vitest";

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
  settingsEnvelope,
  settingsEnvelopeWithMusicBrainzMapping,
} from "../../test/fixtures/settings";
import { server } from "../../test/server";

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

  it("debounces a burst into one canonical save and keeps focus in the edited field", async () => {
    vi.useFakeTimers({ shouldAdvanceTime: true });
    try {
      const requests: SettingsCandidateRequest[] = [];
      let validateCount = 0;
      let settingsReadCount = 0;
      server.use(
        http.get("*/api/settings", () => {
          settingsReadCount += 1;
          return HttpResponse.json(settingsEnvelope);
        }),
        http.post("*/api/settings/validate", () => {
          validateCount += 1;
          return HttpResponse.json(savedSettingsEnvelope);
        }),
        http.put("*/api/settings", async ({ request }) => {
          const candidate = (await request.json()) as SettingsCandidateRequest;
          requests.push(candidate);
          return HttpResponse.json(
            savedEnvelopeFor(candidate, "settings-revision-two"),
          );
        }),
      );
      renderSettings();

      const libraryPath = await screen.findByLabelText("Library path");
      libraryPath.focus();
      fireEvent.change(libraryPath, { target: { value: "/music/a" } });
      fireEvent.change(libraryPath, { target: { value: "/music/ab" } });
      fireEvent.change(libraryPath, {
        target: { value: "/music/new-library" },
      });
      fireEvent.click(screen.getByLabelText("Require album"));
      fireEvent.change(screen.getByLabelText("Maximum artist ID length"), {
        target: { value: "10" },
      });
      fireEvent.change(screen.getByLabelText("Sample year"), {
        target: { value: "0" },
      });

      expect(autosaveStatus()).toHaveTextContent("Unsaved changes");
      expect(requests).toHaveLength(0);
      await advanceAutosave();

      await waitFor(() => expect(requests).toHaveLength(1));
      expect(requests[0]?.expected_config_revision).toBe(
        "settings-revision-one",
      );
      expect(requests[0]?.config.paths.library).toBe("/music/new-library");
      expect(requests[0]?.config.metadata.require_album).toBe(true);
      expect(requests[0]?.config.artist_ids.max_length).toBe(10);
      expect(validateCount).toBe(0);
      expect(settingsReadCount).toBe(1);
      expect(autosaveStatus()).toHaveTextContent("Saved");
      expect(screen.getAllByText("Saved")).toHaveLength(2);
      expect(libraryPath).toHaveFocus();
      expect(
        screen.queryByRole("button", { name: "Save Settings" }),
      ).not.toBeInTheDocument();
      expect(
        screen.queryByRole("button", { name: "Review changes" }),
      ).not.toBeInTheDocument();
      const diff = screen.getByRole("table");
      expect(within(diff).getByText("paths.library")).toBeInTheDocument();
    } finally {
      vi.useRealTimers();
    }
  });

  it("cancels a returned-to-acknowledged draft and blocks navigation only until persistence", async () => {
    vi.useFakeTimers({ shouldAdvanceTime: true });
    try {
      let saveCount = 0;
      server.use(
        http.put("*/api/settings", async ({ request }) => {
          saveCount += 1;
          const candidate = (await request.json()) as SettingsCandidateRequest;
          return HttpResponse.json(
            savedEnvelopeFor(candidate, "settings-revision-two"),
          );
        }),
      );
      renderSettings();

      const libraryPath = await screen.findByLabelText("Library path");
      fireEvent.change(libraryPath, { target: { value: "/music/draft" } });
      fireEvent.change(libraryPath, {
        target: { value: "/music/library" },
      });
      await advanceAutosave();
      expect(saveCount).toBe(0);
      expect(autosaveStatus()).toHaveTextContent("Saved");

      fireEvent.change(libraryPath, {
        target: { value: "/music/persist-me" },
      });
      const pendingUnload = new Event("beforeunload", { cancelable: true });
      window.dispatchEvent(pendingUnload);
      expect(pendingUnload.defaultPrevented).toBe(true);
      fireEvent.click(screen.getByRole("link", { name: "Next route" }));
      expect(
        await screen.findByRole("dialog", {
          name: "Leave with unsaved Settings?",
        }),
      ).toBeVisible();
      fireEvent.click(screen.getByRole("button", { name: "Keep editing" }));

      await advanceAutosave();
      await waitFor(() => expect(saveCount).toBe(1));
      expect(autosaveStatus()).toHaveTextContent("Saved");
      const savedUnload = new Event("beforeunload", { cancelable: true });
      window.dispatchEvent(savedUnload);
      expect(savedUnload.defaultPrevented).toBe(false);

      fireEvent.click(screen.getByRole("link", { name: "Next route" }));
      expect(
        await screen.findByRole("heading", { name: "Next" }),
      ).toBeVisible();
    } finally {
      vi.useRealTimers();
    }
  });

  it("checks browser field constraints before saving and waits for another edit", async () => {
    vi.useFakeTimers({ shouldAdvanceTime: true });
    try {
      let saveCount = 0;
      server.use(
        http.put("*/api/settings", async ({ request }) => {
          saveCount += 1;
          const candidate = (await request.json()) as SettingsCandidateRequest;
          return HttpResponse.json(
            savedEnvelopeFor(candidate, "settings-revision-two"),
          );
        }),
      );
      renderSettings();

      const maxLength = await screen.findByLabelText(
        "Maximum artist ID length",
      );
      fireEvent.change(maxLength, { target: { value: "0" } });
      expect(saveCount).toBe(0);
      expect(autosaveStatus()).toHaveTextContent("Needs attention");
      expect(
        screen.getByText(/browser-visible constraint/),
      ).toBeInTheDocument();
      await advanceAutosave();
      expect(saveCount).toBe(0);

      fireEvent.change(maxLength, { target: { value: "9" } });
      await advanceAutosave();
      await waitFor(() => expect(saveCount).toBe(1));
      expect(autosaveStatus()).toHaveTextContent("Saved");
    } finally {
      vi.useRealTimers();
    }
  });

  it("coalesces edits made during an in-flight save without overwriting them", async () => {
    vi.useFakeTimers({ shouldAdvanceTime: true });
    try {
      const requests: SettingsCandidateRequest[] = [];
      let activeSaves = 0;
      let maximumActiveSaves = 0;
      let releaseFirstSave: () => void = () => undefined;
      const firstSaveHeld = new Promise<void>((resolve) => {
        releaseFirstSave = resolve;
      });
      server.use(
        http.put("*/api/settings", async ({ request }) => {
          const candidate = (await request.json()) as SettingsCandidateRequest;
          requests.push(candidate);
          activeSaves += 1;
          maximumActiveSaves = Math.max(maximumActiveSaves, activeSaves);
          if (requests.length === 1) {
            await firstSaveHeld;
          }
          activeSaves -= 1;
          return HttpResponse.json(
            savedEnvelopeFor(
              candidate,
              requests.length === 1
                ? "settings-revision-two"
                : "settings-revision-three",
            ),
          );
        }),
      );
      renderSettings();

      const libraryPath = await screen.findByLabelText("Library path");
      fireEvent.change(libraryPath, {
        target: { value: "/music/first-candidate" },
      });
      await advanceAutosave();
      await waitFor(() => expect(requests).toHaveLength(1));
      expect(autosaveStatus()).toHaveTextContent("Saving");

      fireEvent.change(libraryPath, {
        target: { value: "/music/latest-candidate" },
      });
      await advanceAutosave();
      expect(requests).toHaveLength(1);
      expect(libraryPath).toHaveValue("/music/latest-candidate");

      act(() => releaseFirstSave());
      await waitFor(() => expect(requests).toHaveLength(2));
      await waitFor(() => expect(autosaveStatus()).toHaveTextContent("Saved"));
      expect(maximumActiveSaves).toBe(1);
      expect(requests[0]?.expected_config_revision).toBe(
        "settings-revision-one",
      );
      expect(requests[1]?.expected_config_revision).toBe(
        "settings-revision-two",
      );
      expect(requests[1]?.config.paths.library).toBe("/music/latest-candidate");
      expect(libraryPath).toHaveValue("/music/latest-candidate");
    } finally {
      vi.useRealTimers();
    }
  });

  it("retains an invalid draft, links diagnostics, and does not resubmit it unchanged", async () => {
    vi.useFakeTimers({ shouldAdvanceTime: true });
    try {
      let saveCount = 0;
      server.use(
        http.put("*/api/settings", async ({ request }) => {
          saveCount += 1;
          const candidate = (await request.json()) as SettingsCandidateRequest;
          if (saveCount === 1) {
            return HttpResponse.json(
              {
                data: null,
                errors: [
                  {
                    code: "validation_failed",
                    field: "body.config.path_policy.template",
                    message:
                      "The path template must contain a title placeholder.",
                    retryable: false,
                  },
                ],
              } satisfies ApiFailureEnvelope,
              { status: 422 },
            );
          }
          return HttpResponse.json(
            savedEnvelopeFor(candidate, "settings-revision-two"),
          );
        }),
      );
      renderSettings();

      const template = await screen.findByLabelText("Path template");
      template.focus();
      fireEvent.change(template, { target: { value: "{artist}" } });
      await advanceAutosave();
      const validationLink = await screen.findByRole("link", {
        name: "The path template must contain a title placeholder.",
      });
      expect(template).toHaveFocus();
      expect(template).toHaveValue("{artist}");
      expect(autosaveStatus()).toHaveTextContent("Needs attention");

      await advanceAutosave();
      expect(saveCount).toBe(1);
      fireEvent.click(validationLink);
      expect(template).toHaveFocus();
      fireEvent.change(template, { target: { value: "{artist}/{title}" } });
      await advanceAutosave();
      await waitFor(() => expect(saveCount).toBe(2));
      expect(autosaveStatus()).toHaveTextContent("Saved");
    } finally {
      vi.useRealTimers();
    }
  });

  it("keeps invalid persisted recovery guarded until a valid autosave replaces it", async () => {
    vi.useFakeTimers({ shouldAdvanceTime: true });
    try {
      server.use(
        http.get("*/api/settings", () =>
          HttpResponse.json(invalidPersistedSettingsEnvelope),
        ),
        http.put("*/api/settings", async ({ request }) => {
          const candidate = (await request.json()) as SettingsCandidateRequest;
          return HttpResponse.json(
            savedEnvelopeFor(candidate, "settings-revision-two"),
          );
        }),
      );
      renderSettings();

      expect(
        await screen.findByRole("heading", { name: "Configuration recovery" }),
      ).toBeVisible();
      expect(autosaveStatus()).toHaveTextContent("Needs attention");
      const guardedUnload = new Event("beforeunload", { cancelable: true });
      window.dispatchEvent(guardedUnload);
      expect(guardedUnload.defaultPrevented).toBe(true);

      fireEvent.change(screen.getByLabelText("Path template"), {
        target: { value: "{artist}/{title}" },
      });
      await advanceAutosave();
      await waitFor(() =>
        expect(
          screen.queryByRole("heading", { name: "Configuration recovery" }),
        ).not.toBeInTheDocument(),
      );
      expect(autosaveStatus()).toHaveTextContent("Saved");
    } finally {
      vi.useRealTimers();
    }
  });

  it("pauses after a revision conflict until Load latest Settings is chosen", async () => {
    vi.useFakeTimers({ shouldAdvanceTime: true });
    try {
      let saveCount = 0;
      server.use(
        http.put("*/api/settings", () => {
          saveCount += 1;
          return HttpResponse.json(configChangedEnvelope, { status: 409 });
        }),
      );
      renderSettings();

      const libraryPath = await screen.findByLabelText("Library path");
      fireEvent.change(libraryPath, {
        target: { value: "/music/conflicted" },
      });
      await advanceAutosave();
      expect(
        await screen.findByRole("heading", {
          name: "Configuration changed elsewhere",
        }),
      ).toBeVisible();

      fireEvent.change(libraryPath, {
        target: { value: "/music/still-conflicted" },
      });
      await advanceAutosave();
      expect(saveCount).toBe(1);
      fireEvent.click(
        screen.getByRole("button", { name: "Load latest Settings" }),
      );
      await waitFor(() =>
        expect(screen.getByLabelText("Library path")).toHaveValue(
          "/music/library",
        ),
      );
      expect(autosaveStatus()).toHaveTextContent("Saved");
    } finally {
      vi.useRealTimers();
    }
  });

  it("refreshes CSRF and resends the identical candidate exactly once", async () => {
    vi.useFakeTimers({ shouldAdvanceTime: true });
    try {
      const requests: Array<{ body: string; token: string | null }> = [];
      server.use(
        http.get("*/api/bootstrap", () =>
          HttpResponse.json({
            ...normalBootstrap,
            data:
              normalBootstrap.data === null
                ? null
                : {
                    ...normalBootstrap.data,
                    csrf_token: "refreshed-csrf-token",
                  },
          }),
        ),
        http.put("*/api/settings", async ({ request }) => {
          const body = await request.text();
          requests.push({
            body,
            token: request.headers.get("X-OMYM2-CSRF-Token"),
          });
          if (requests.length === 1) {
            return HttpResponse.json(csrfInvalidEnvelope, { status: 403 });
          }
          const candidate = JSON.parse(body) as SettingsCandidateRequest;
          return HttpResponse.json(
            savedEnvelopeFor(candidate, "settings-revision-two"),
          );
        }),
      );
      renderSettings();

      fireEvent.change(await screen.findByLabelText("Library path"), {
        target: { value: "/music/csrf-safe" },
      });
      await advanceAutosave();
      await waitFor(() => expect(requests).toHaveLength(2));
      expect(requests[0]?.token).toBe("fixture-csrf-token");
      expect(requests[1]?.token).toBe("refreshed-csrf-token");
      expect(requests[1]?.body).toBe(requests[0]?.body);
      expect(autosaveStatus()).toHaveTextContent("Saved");
    } finally {
      vi.useRealTimers();
    }
  });

  it("does not retry an uncertain failure until the explicit retry action", async () => {
    vi.useFakeTimers({ shouldAdvanceTime: true });
    try {
      let saveCount = 0;
      server.use(
        http.put("*/api/settings", async ({ request }) => {
          saveCount += 1;
          if (saveCount === 1) {
            return HttpResponse.error();
          }
          const candidate = (await request.json()) as SettingsCandidateRequest;
          return HttpResponse.json(
            savedEnvelopeFor(candidate, "settings-revision-two"),
          );
        }),
      );
      renderSettings();

      fireEvent.change(await screen.findByLabelText("Library path"), {
        target: { value: "/music/retry-explicitly" },
      });
      await advanceAutosave();
      const retry = await screen.findByRole("button", {
        name: "Retry autosave",
      });
      expect(autosaveStatus()).toHaveTextContent("Needs attention");
      await advanceAutosave(1_800);
      expect(saveCount).toBe(1);

      fireEvent.click(retry);
      await advanceAutosave();
      await waitFor(() => expect(saveCount).toBe(2));
      expect(autosaveStatus()).toHaveTextContent("Saved");
    } finally {
      vi.useRealTimers();
    }
  });
});

async function advanceAutosave(milliseconds = autosaveDelay()) {
  await act(async () => {
    await vi.advanceTimersByTimeAsync(milliseconds);
  });
}

function autosaveDelay(): number {
  const delay = settingsEnvelope.data?.choices.autosave_delay_ms;
  if (delay === undefined) {
    throw new Error("Settings fixture is missing the autosave delay.");
  }
  return delay;
}

function autosaveStatus(): HTMLElement {
  const status = screen
    .getByRole("heading", { name: "Automatic save" })
    .closest<HTMLElement>('[role="status"]');
  if (status === null) {
    throw new Error("Automatic save status region is missing.");
  }
  return status;
}

function savedEnvelopeFor(
  request: SettingsCandidateRequest,
  configRevision: string,
) {
  return {
    ...savedSettingsEnvelope,
    data: {
      ...savedSettingsEnvelope.data,
      changes: [
        {
          after: request.config.paths.library,
          before: settingsEnvelope.data?.config.paths.library ?? null,
          field: "paths.library",
        },
      ],
      config: request.config,
      config_revision: configRevision,
    },
  };
}

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
