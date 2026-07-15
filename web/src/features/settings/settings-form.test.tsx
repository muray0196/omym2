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
      screen.getByRole("heading", { name: "Artist display names" }),
    ).toBeInTheDocument();
    expect(
      screen.getByText("No artist display-name preferences are in this draft."),
    ).toBeInTheDocument();
    expect(screen.getByLabelText("Require title")).toBeChecked();
    expect(screen.getByLabelText("When a target exists")).toHaveValue(
      "conflict",
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
      artist_names: { preferences: {} },
      file_extension: ".FLAC",
      metadata: { artist: "Aimer", title: "Live Preview" },
      path_policy: {
        template: "{album_artist}/{year}_{album}/{disc}-{track}_{title}",
      },
    });
    expect(captured[0]).not.toHaveProperty("expected_config_revision");
  });

  it("edits full display-name preferences independently from compact artist IDs", async () => {
    const user = userEvent.setup();
    const captured: PathPreviewRequest[] = [];
    server.use(
      http.post("*/api/settings/preview", async ({ request }) => {
        captured.push((await request.json()) as PathPreviewRequest);
        return HttpResponse.json(previewEnvelope);
      }),
    );
    renderSettings();

    await user.type(
      await screen.findByLabelText("New display-name source artist"),
      "宇多田ヒカル",
    );
    await user.type(
      screen.getByLabelText("New full display name"),
      "Hikaru Utada",
    );
    await user.click(screen.getByRole("button", { name: "Add display name" }));

    const displayName = await screen.findByDisplayValue("Hikaru Utada");
    expect(screen.getByDisplayValue("NORTH")).toBeInTheDocument();
    await waitFor(() =>
      expect(captured.at(-1)?.artist_names.preferences).toEqual({
        宇多田ヒカル: "Hikaru Utada",
      }),
    );

    await user.clear(displayName);
    await user.type(displayName, "Utada Hikaru");
    await waitFor(() =>
      expect(captured.at(-1)?.artist_names.preferences).toEqual({
        宇多田ヒカル: "Utada Hikaru",
      }),
    );

    const preferenceRow = displayName.closest("li");
    expect(preferenceRow).not.toBeNull();
    await user.click(
      within(preferenceRow as HTMLElement).getByRole("button", {
        name: "Remove",
      }),
    );
    expect(
      screen.getByText("No artist display-name preferences are in this draft."),
    ).toBeInTheDocument();
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

    await user.type(
      await screen.findByLabelText("New display-name source artist"),
      "宇多田ヒカル",
    );
    await user.type(
      screen.getByLabelText("New full display name"),
      "Hikaru Utada",
    );
    await user.click(screen.getByRole("button", { name: "Add display name" }));
    const libraryPath = await screen.findByLabelText("Library path");
    await user.clear(libraryPath);
    await user.type(libraryPath, "/music/new-library");
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
    expect(captured.request?.config.artist_names.preferences).toEqual({
      宇多田ヒカル: "Hikaru Utada",
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

  it("merges generated artist IDs into the draft and protects unsaved navigation", async () => {
    const user = userEvent.setup();
    const { router } = renderSettings();

    const names = await screen.findByLabelText("Artist names to generate");
    await user.type(names, "Glass Harbor");
    await user.click(
      screen.getByRole("button", { name: "Generate and merge into draft" }),
    );
    expect(await screen.findByDisplayValue("GLASS")).toBeInTheDocument();

    await user.click(screen.getByRole("link", { name: "Next route" }));
    expect(
      await screen.findByRole("heading", {
        name: "Leave with unsaved Settings?",
      }),
    ).toBeInTheDocument();
    await user.click(screen.getByRole("button", { name: "Keep editing" }));
    expect(router.state.location.pathname).toBe("/settings");
    expect(screen.getByRole("button", { name: "Save Settings" })).toHaveFocus();

    await user.click(screen.getByRole("link", { name: "Next route" }));
    await user.click(
      await screen.findByRole("button", {
        name: "Discard draft and leave",
      }),
    );
    expect(
      await screen.findByRole("heading", { name: "Next" }),
    ).toBeInTheDocument();
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
