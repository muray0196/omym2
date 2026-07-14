/**
 * Summary: Verifies Library URL state, opaque cursor/group transport, detail, and failure presentation.
 * Why: Protects the Track inspection contract through generated types and MSW.
 */
import { QueryClientProvider } from "@tanstack/react-query";
import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { http, HttpResponse } from "msw";
import { createMemoryRouter, RouterProvider } from "react-router-dom";
import { describe, expect, it } from "vitest";

import type {
  ApiEnvelopePaginatedDataTrackResource,
  ApiEnvelopeTrackFacetsData,
  ApiEnvelopeTrackGroupsData,
  ApiEnvelopeTrackResource,
  ApiFailureEnvelope,
  TrackResource,
} from "../../api/generated";
import { createQueryClient } from "../../app/query-client";
import { server } from "../../test/server";
import { trackGroupingLabel, trackStatusLabel } from "./library-catalog";
import { LibraryList } from "./library-list";
import { TrackStatusBadge } from "./library-presentation";
import { TrackDetail } from "./track-detail";

const TRACK_ID = "018f0000-0000-7000-8000-000000000101";
const SECOND_TRACK_ID = "018f0000-0000-7000-8000-000000000102";
const LIBRARY_ID = "018f0000-0000-7000-8000-000000000001";
const OPAQUE_CURSOR = "opaque.cursor+/=";
const OPAQUE_ARTIST_KEY = '["Miles Davis"]';
const OPAQUE_ALBUM_KEY = '["Miles Davis","Kind of Blue",1959]';

const trackFixture = {
  track_id: TRACK_ID,
  library_id: LIBRARY_ID,
  current_path: "Miles Davis/1959_Kind of Blue/1-1_So What.flac",
  canonical_path: "Miles Davis/1959_Kind of Blue/1-1_So What.flac",
  content_hash: "content-hash-so-what",
  metadata_hash: "metadata-hash-so-what",
  size: 1234567,
  mtime: "2026-07-10T05:30:00Z",
  metadata: {
    title: "So What",
    artist: "Miles Davis",
    album: "Kind of Blue",
    album_artist: "Miles Davis",
    genre: "Jazz",
    year: 1959,
    track_number: 1,
    track_total: 5,
    disc_number: 1,
    disc_total: 1,
  },
  status: "active",
  first_seen_at: "2026-07-01T00:00:00Z",
  last_seen_at: "2026-07-10T05:30:00Z",
  updated_at: "2026-07-10T05:30:00Z",
} satisfies TrackResource;

const secondTrackFixture = {
  ...trackFixture,
  track_id: SECOND_TRACK_ID,
  current_path: "Miles Davis/1959_Kind of Blue/1-2_Freddie Freeloader.flac",
  canonical_path: "Miles Davis/1959_Kind of Blue/1-2_Freddie Freeloader.flac",
  content_hash: "content-hash-freddie",
  metadata_hash: "metadata-hash-freddie",
  metadata: {
    ...trackFixture.metadata,
    title: "Freddie Freeloader",
    track_number: 2,
  },
} satisfies TrackResource;

describe("Library inspection", () => {
  it("sends URL-owned search, status, and opaque group selection through the generated queries", async () => {
    const observedQueries: URLSearchParams[] = [];
    useDefaultLibraryHandlers({ observedQueries });

    const { router } = renderLibrary(
      `/library?query=So+What&status=active&group_by=artist_album&group_key=${encodeURIComponent(OPAQUE_ALBUM_KEY)}`,
    );

    expect(await screen.findByRole("link", { name: /So What/ })).toBeVisible();
    expect(
      screen.getByText("The Track list is filtered to the selected group."),
    ).toBeVisible();
    await waitFor(() => expect(observedQueries.length).toBeGreaterThan(0));
    const request = observedQueries.at(-1);
    expect(request?.get("query")).toBe("So What");
    expect(request?.get("status")).toBe("active");
    expect(request?.get("group_by")).toBe("artist_album");
    expect(request?.get("group_key")).toBe(OPAQUE_ALBUM_KEY);
    expect(request?.get("library_id")).toBe(LIBRARY_ID);

    expect(screen.getByRole("link", { name: /So What/ })).toHaveAttribute(
      "href",
      expect.stringContaining(`/library/${TRACK_ID}?query=So+What`),
    );
    expect(router.state.location.search).toContain("group_key=");
    expect(
      screen.queryByRole("button", { name: /refresh/i }),
    ).not.toBeInTheDocument();
  });

  it("shows one tracks-first Library surface and switches into group browsing", async () => {
    useDefaultLibraryHandlers();
    const { router, user } = renderLibrary();

    expect(
      await screen.findByRole("heading", { name: "Tracks" }),
    ).toBeVisible();
    expect(screen.getByRole("link", { name: /So What/ })).toBeVisible();
    expect(screen.getByText("Kind of Blue")).toBeVisible();
    expect(screen.getByText("1959")).toBeVisible();
    expect(screen.queryByText("Track ID")).not.toBeInTheDocument();
    expect(
      screen.queryByRole("heading", { name: "Browse Library" }),
    ).not.toBeInTheDocument();

    await user.click(screen.getByRole("button", { name: "Browse groups" }));

    expect(
      await screen.findByRole("heading", { name: "Browse Library" }),
    ).toBeVisible();
    expect(screen.getByText("Miles Davis")).toBeVisible();
    expect(
      screen.queryByRole("link", { name: /So What/ }),
    ).not.toBeInTheDocument();
    expect(new URLSearchParams(router.state.location.search).get("view")).toBe(
      "groups",
    );

    await user.click(screen.getByRole("button", { name: "View Tracks" }));

    expect(await screen.findByRole("link", { name: /So What/ })).toBeVisible();
    const parameters = new URLSearchParams(router.state.location.search);
    expect(parameters.get("view")).toBeNull();
    expect(parameters.get("group_key")).toBe(OPAQUE_ARTIST_KEY);
  });

  it("bounds Track cursor pages and resets paging for a changed filter", async () => {
    const cursors: Array<string | null> = [];
    useDefaultLibraryHandlers({
      listResponse(url) {
        const cursor = url.searchParams.get("cursor");
        cursors.push(cursor);
        return paginatedTracks(
          cursor === null ? [trackFixture] : [secondTrackFixture],
          cursor === null ? OPAQUE_CURSOR : null,
          2,
        );
      },
    });
    const { user } = renderLibrary();

    expect(await screen.findByText("So What")).toBeVisible();
    await user.click(
      screen.getByRole("button", { name: "Next page of Tracks" }),
    );

    expect(await screen.findByText("Freddie Freeloader")).toBeVisible();
    expect(screen.queryByText("So What")).not.toBeInTheDocument();
    expect(screen.getAllByText("Page 2 of 2").length).toBeGreaterThan(0);
    expect(cursors).toEqual([null, OPAQUE_CURSOR]);

    await user.selectOptions(
      screen.getByRole("combobox", { name: "Track status" }),
      "active",
    );

    expect(await screen.findByText("So What")).toBeVisible();
    expect(screen.queryByText("Freddie Freeloader")).not.toBeInTheDocument();
    expect(screen.getAllByText("Page 1 of 2").length).toBeGreaterThan(0);
  });

  it("renders only the selected Library group cursor page", async () => {
    const groupCursors: Array<string | null> = [];
    useDefaultLibraryHandlers({
      groupsResponse(url) {
        const cursor = url.searchParams.get("cursor");
        groupCursors.push(cursor);
        return groupedTracks(
          [
            {
              count: 1,
              key: cursor === null ? "group-one" : "group-two",
              label:
                cursor === null ? "First artist group" : "Second artist group",
            },
          ],
          "artist",
          cursor === null ? OPAQUE_CURSOR : null,
          2,
        );
      },
    });
    const { user } = renderLibrary("/library?view=groups");

    expect(await screen.findByText("First artist group")).toBeVisible();
    await user.click(
      screen.getByRole("button", {
        name: "Next page of Library groups",
      }),
    );

    expect(await screen.findByText("Second artist group")).toBeVisible();
    expect(screen.queryByText("First artist group")).not.toBeInTheDocument();
    expect(groupCursors).toEqual([null, OPAQUE_CURSOR]);
  });

  it("drills from an opaque artist key into albums and keeps the hierarchy in the URL", async () => {
    const groupRequests: Array<{
      groupBy: string | null;
      parentKey: string | null;
    }> = [];
    useDefaultLibraryHandlers({
      groupsResponse(url) {
        const groupBy = url.searchParams.get("group_by");
        const parentKey = url.searchParams.get("parent_key");
        groupRequests.push({ groupBy, parentKey });
        return groupedTracks(
          groupBy === "album"
            ? [{ key: OPAQUE_ALBUM_KEY, label: "Kind of Blue", count: 5 }]
            : [{ key: OPAQUE_ARTIST_KEY, label: "Miles Davis", count: 5 }],
          groupBy === "album" ? "album" : "artist",
        );
      },
    });
    const { router, user } = renderLibrary("/library?view=groups");

    await user.click(
      await screen.findByRole("button", { name: "Browse albums" }),
    );

    expect(await screen.findByText("Kind of Blue")).toBeVisible();
    await waitFor(() => {
      expect(groupRequests).toContainEqual({
        groupBy: "album",
        parentKey: OPAQUE_ARTIST_KEY,
      });
    });
    const parameters = new URLSearchParams(router.state.location.search);
    expect(parameters.get("group_by")).toBe("album");
    expect(parameters.get("artist_key")).toBe(OPAQUE_ARTIST_KEY);
  });

  it("renders persisted metadata, paths, hashes, and a browse-state-preserving back link", async () => {
    server.use(
      http.get("*/api/tracks/:trackId", () =>
        HttpResponse.json({
          data: trackFixture,
          errors: [],
        } satisfies ApiEnvelopeTrackResource),
      ),
    );
    renderLibrary(`/library/${TRACK_ID}?query=So+What&status=active`);

    const loadingHeading = screen.getByRole("heading", {
      name: "Track detail",
    });
    const backLink = screen.getByRole("link", { name: "Back to Library" });
    expect(loadingHeading).toHaveFocus();
    backLink.focus();

    const detailHeading = await screen.findByRole("heading", {
      name: "So What",
    });
    expect(detailHeading).toBe(loadingHeading);
    expect(backLink).toHaveFocus();
    expect(screen.getAllByText(trackFixture.current_path)).toHaveLength(2);
    expect(screen.getByText("content-hash-so-what")).toBeVisible();
    expect(screen.getByText("metadata-hash-so-what")).toBeVisible();
    expect(screen.getByText("Jazz")).toBeVisible();
    expect(screen.getByText("1 / 5")).toBeVisible();
    expect(backLink).toHaveAttribute(
      "href",
      "/library?query=So+What&status=active",
    );
    expect(
      screen.queryByRole("button", { name: /refresh/i }),
    ).not.toBeInTheDocument();
  });

  it("distinguishes an unknown Track from an empty or disconnected detail", async () => {
    const failure = {
      data: null,
      errors: [
        {
          code: "track_not_found",
          field: "path.track_id",
          message: "Track was not found.",
          retryable: false,
        },
      ],
    } satisfies ApiFailureEnvelope;
    server.use(
      http.get("*/api/tracks/:trackId", () =>
        HttpResponse.json(failure, { status: 404 }),
      ),
    );
    renderLibrary(`/library/${TRACK_ID}`);

    expect(
      await screen.findByRole("heading", { name: "Track not found" }),
    ).toBeVisible();
    expect(
      screen.getByText(/not available in persisted Library state/),
    ).toBeVisible();
    expect(screen.queryByRole("alert")).not.toBeInTheDocument();
  });

  it("presents an empty persisted Library separately from a failed read", async () => {
    useDefaultLibraryHandlers({
      listResponse: () => paginatedTracks([], null, 0),
    });
    renderLibrary();

    expect(
      await screen.findByRole("heading", {
        name: "No Tracks have been recorded",
      }),
    ).toBeVisible();
    expect(
      screen.queryByRole("heading", { name: "Browse Library" }),
    ).not.toBeInTheDocument();
    expect(screen.queryByRole("alert")).not.toBeInTheDocument();
  });

  it("shows a typed Track list failure with its backend message and retry", async () => {
    const failure = {
      data: null,
      errors: [
        {
          code: "storage_unavailable",
          message: "Persisted Track state is unavailable.",
          retryable: true,
        },
      ],
    } satisfies ApiFailureEnvelope;
    useDefaultLibraryHandlers();
    server.use(
      http.get("*/api/tracks", () =>
        HttpResponse.json(failure, { status: 500 }),
      ),
    );
    renderLibrary();

    const alert = await screen.findByRole("alert");
    expect(alert).toHaveTextContent("Library Tracks could not be loaded");
    expect(alert).toHaveTextContent("Persisted Track state is unavailable.");
    expect(screen.getByRole("button", { name: "Try again" })).toBeVisible();
  });

  it("keeps unknown status and grouping values visible and neutral", () => {
    render(<TrackStatusBadge value="future_status" />);

    expect(screen.getByText("Unknown status: future_status")).toBeVisible();
    expect(trackStatusLabel("future_status")).toBe(
      "Unknown status: future_status",
    );
    expect(trackGroupingLabel("future_group")).toBe(
      "Unknown grouping: future_group",
    );
  });
});

function useDefaultLibraryHandlers({
  groupsResponse = () =>
    groupedTracks(
      [{ key: OPAQUE_ARTIST_KEY, label: "Miles Davis", count: 1 }],
      "artist",
    ),
  listResponse = () => paginatedTracks([trackFixture], null, 1),
  observedQueries,
}: {
  groupsResponse?: (url: URL) => ApiEnvelopeTrackGroupsData;
  listResponse?: (url: URL) => ApiEnvelopePaginatedDataTrackResource;
  observedQueries?: URLSearchParams[];
} = {}) {
  server.use(
    http.get("*/api/tracks", ({ request }) => {
      const url = new URL(request.url);
      observedQueries?.push(new URLSearchParams(url.searchParams));
      return HttpResponse.json(listResponse(url));
    }),
    http.get("*/api/tracks/facets", () =>
      HttpResponse.json({
        data: {
          facets: { status: [{ value: "active", count: 1 }] },
          total: 1,
        },
        errors: [],
      } satisfies ApiEnvelopeTrackFacetsData),
    ),
    http.get("*/api/tracks/groups", ({ request }) =>
      HttpResponse.json(groupsResponse(new URL(request.url))),
    ),
  );
}

function paginatedTracks(
  items: TrackResource[],
  nextCursor: string | null,
  total: number,
) {
  return {
    data: {
      items,
      page: {
        limit: total > items.length ? Math.max(items.length, 1) : 100,
        next_cursor: nextCursor,
        total,
      },
    },
    errors: [],
  } satisfies ApiEnvelopePaginatedDataTrackResource;
}

function groupedTracks(
  items: Array<{ count: number; key: string; label: string }>,
  groupBy: "album" | "artist",
  nextCursor: string | null = null,
  total = items.length,
) {
  return {
    data: {
      group_by: groupBy,
      items,
      page: {
        limit: total > items.length ? Math.max(items.length, 1) : 100,
        next_cursor: nextCursor,
        total,
      },
    },
    errors: [],
  } satisfies ApiEnvelopeTrackGroupsData;
}

function renderLibrary(initialEntry = "/library") {
  const router = createMemoryRouter(
    [
      { path: "/library", Component: LibraryList },
      { path: "/library/:trackId", Component: TrackDetail },
    ],
    { initialEntries: [initialEntry] },
  );
  const user = userEvent.setup();
  return {
    router,
    user,
    ...render(
      <QueryClientProvider client={createQueryClient()}>
        <RouterProvider router={router} />
      </QueryClientProvider>,
    ),
  };
}
