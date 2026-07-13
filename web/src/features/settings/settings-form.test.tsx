/**
 * Summary: Covers Settings recovery, draft generation, review, concurrency, and CSRF behavior.
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
  ApiEnvelopeSettingsCandidateData,
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
  reviewedSettingsEnvelope,
  savedSettingsEnvelope,
} from "../../test/fixtures/settings";
import { server } from "../../test/server";

describe("Settings route", () => {
  it("renders the generated Config draft, backend choices, and default preview", async () => {
    const user = userEvent.setup();
    const captured: { preview?: PathPreviewRequest } = {};
    server.use(
      http.post("*/api/settings/preview", async ({ request }) => {
        captured.preview = (await request.json()) as PathPreviewRequest;
        return HttpResponse.json(previewEnvelope);
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
    expect(screen.getByLabelText("Require title")).toBeChecked();
    expect(screen.getByLabelText("When a target exists")).toHaveValue(
      "conflict",
    );
    expect(screen.getByText("{artist_id}")).toBeInTheDocument();
    expect(
      screen.getByText("North Harbor/2026_Night Signals/1-1_First Light.flac"),
    ).toBeInTheDocument();

    await user.click(screen.getByRole("button", { name: "Update preview" }));
    await waitFor(() => expect(captured.preview).toBeDefined());
    expect(captured.preview).toMatchObject({
      artist_ids: { fallback_id: "NOART", max_length: 8 },
      file_extension: ".flac",
      metadata: { artist: "North Harbor", title: "First Light" },
      path_policy: {
        template: "{album_artist}/{year}_{album}/{disc}-{track}_{title}",
      },
    });
    expect(captured.preview).not.toHaveProperty("expected_config_revision");
  });

  it("reviews a deterministic diff and saves the complete Config with CSRF", async () => {
    const user = userEvent.setup();
    const captured: {
      request?: SettingsCandidateRequest;
      token?: string | null;
    } = {};
    server.use(
      http.put("*/api/settings", async ({ request }) => {
        captured.token = request.headers.get("X-OMYM2-CSRF-Token");
        captured.request = (await request.json()) as SettingsCandidateRequest;
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

    await user.click(screen.getByRole("button", { name: "Save Settings" }));
    const savedHeading = await screen.findByRole("heading", {
      name: "Settings saved.",
    });
    expect(savedHeading).toBeInTheDocument();
    expect(savedHeading.parentElement?.parentElement).toHaveFocus();
    expect(captured.token).toBe("fixture-csrf-token");
    expect(captured.request?.expected_config_revision).toBe(
      "settings-revision-one",
    );
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
    await user.click(screen.getByRole("button", { name: "Review changes" }));
    await user.click(
      await screen.findByRole("button", { name: "Save Settings" }),
    );

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
    const invalidCandidate = {
      data: {
        ...reviewedSettingsEnvelope.data,
        validation: {
          errors: [
            {
              code: "validation_failed",
              field: "body.config.path_policy.template",
              message: "The path template must contain a title placeholder.",
              retryable: false,
            },
          ],
          valid: false,
        },
      },
      errors: [],
    } satisfies ApiEnvelopeSettingsCandidateData;
    let validationCount = 0;
    server.use(
      http.get("*/api/settings", () =>
        HttpResponse.json(invalidPersistedSettingsEnvelope),
      ),
      http.post("*/api/settings/validate", () => {
        validationCount += 1;
        return HttpResponse.json(
          validationCount === 1 ? invalidCandidate : reviewedSettingsEnvelope,
        );
      }),
      http.put("*/api/settings", () =>
        HttpResponse.json(configChangedEnvelope, { status: 409 }),
      ),
    );
    renderSettings();

    expect(
      await screen.findByRole("heading", { name: "Configuration recovery" }),
    ).toBeInTheDocument();
    await user.click(screen.getByRole("button", { name: "Review changes" }));
    await waitFor(() => expect(validationCount).toBe(1));
    const validationLink = await screen.findByRole("link", {
      name: "The path template must contain a title placeholder.",
    });
    await user.click(validationLink);
    expect(screen.getByLabelText("Path template")).toHaveFocus();

    await user.click(screen.getByRole("button", { name: "Review changes" }));
    await user.click(
      await screen.findByRole("button", { name: "Save Settings" }),
    );
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
    expect(
      screen.getByRole("button", { name: "Review changes" }),
    ).toHaveFocus();

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
