/**
 * Summary: Renders URL-owned Track search, hierarchy groups, facets, and cursor pages.
 * Why: Delivers read-only Library inspection from persisted backend state.
 */
import { useInfiniteQuery, useQuery } from "@tanstack/react-query";
import { useDeferredValue } from "react";
import { Link, useLocation } from "react-router-dom";

import { bootstrapQuery } from "../bootstrap/bootstrap-query";
import { useCursorPage, type CursorPageNavigation } from "../../ui/cursor-page";
import { Button } from "../../ui/primitives/button";
import { CursorPageControls } from "../../ui/primitives/cursor-page-controls";
import { PageHeader } from "../../ui/primitives/page-header";
import { VisuallyHidden } from "../../ui/primitives/visually-hidden";
import toolbarStyles from "../../ui/primitives/toolbar.module.css";
import { trackGroupingLabel, trackStatusLabel } from "./library-catalog";
import { libraryCopy } from "./library-copy";
import { LibraryErrorState } from "./library-error-state";
import styles from "./library-inspection.module.css";
import { TrackStatusBadge } from "./library-presentation";
import {
  trackFacetsQuery,
  trackGroupsInfiniteQuery,
  tracksInfiniteQuery,
  type LibraryTrack,
  type LibraryTrackFacets,
} from "./library-query";
import {
  rootGroupingOptions,
  trackStatusOptions,
  useLibraryBrowseFilters,
} from "./library-url-state";

const numberFormatter = new Intl.NumberFormat("en-US");

export function LibraryList() {
  const location = useLocation();
  const browse = useLibraryBrowseFilters();
  const bootstrap = useQuery(bootstrapQuery);
  const libraryId = bootstrap.data?.data?.active_library?.library_id;
  const deferredQuery = useDeferredValue(browse.filters.query);
  const queryFilters = { ...browse.filters, query: deferredQuery };
  const tracks = useInfiniteQuery(
    tracksInfiniteQuery(
      browse.filters.view === "tracks" ? libraryId : undefined,
      queryFilters,
    ),
  );
  const facets = useQuery(trackFacetsQuery(libraryId, queryFilters));
  const groups = useInfiniteQuery(
    trackGroupsInfiniteQuery(
      browse.filters.view === "groups" ? libraryId : undefined,
      queryFilters,
    ),
  );
  const resetKey = JSON.stringify({ libraryId, ...queryFilters });
  const trackPage = useCursorPage({
    fetchNextPage: tracks.fetchNextPage,
    hasNextPage: tracks.hasNextPage,
    isFetchingNextPage: tracks.isFetchingNextPage,
    pages: tracks.data?.pages,
    resetKey,
  });
  const groupPage = useCursorPage({
    fetchNextPage: groups.fetchNextPage,
    hasNextPage: groups.hasNextPage,
    isFetchingNextPage: groups.isFetchingNextPage,
    pages: groups.data?.pages,
    resetKey,
  });
  const trackItems = trackPage.page?.items ?? [];
  const groupItems = groupPage.page?.items ?? [];
  const facetTotal =
    browse.filters.status === undefined
      ? facets.data?.total
      : facets.data?.facets.status.find(
          (facet) => facet.value === browse.filters.status,
        )?.count;
  const total = tracks.data?.pages[0]?.page.total ?? facetTotal ?? 0;

  return (
    <article className={styles.page}>
      <PageHeader
        description={libraryCopy.list.description}
        eyebrow={libraryCopy.list.eyebrow}
        title={libraryCopy.list.title}
      />

      {bootstrap.isPending ? (
        <LoadingState message={libraryCopy.list.loading} />
      ) : libraryId === undefined ? (
        <EmptyState
          body={libraryCopy.list.noLibraryBody}
          title={libraryCopy.list.noLibraryTitle}
        />
      ) : (
        <>
          <LibraryFilters
            browse={browse}
            facets={facets.data}
            facetsError={facets.isError}
            onRetryFacets={() => void facets.refetch()}
            total={total}
          />
          {browse.filters.view === "groups" ? (
            <GroupBrowser
              browse={browse}
              groups={groupItems}
              hasPage={groupPage.page !== undefined}
              isError={groups.isError}
              isPending={groups.isPending}
              onRetry={() => void groups.refetch()}
              pageSize={groupPage.page?.page.limit}
              pagination={groupPage}
              totalItems={groupPage.page?.page.total}
            />
          ) : tracks.isPending ? (
            <LoadingState message={libraryCopy.list.loading} />
          ) : tracks.isError ? (
            <LibraryErrorState
              error={tracks.error}
              onRetry={() => void tracks.refetch()}
              retryLabel={libraryCopy.list.retry}
              title={libraryCopy.list.loadError}
            />
          ) : (
            <TrackBrowser
              detailSearch={location.search}
              hasActiveFilters={browse.hasActiveFilters}
              hasPage={trackPage.page !== undefined}
              hasSelectedGroup={browse.filters.groupKey !== undefined}
              onClearGroup={browse.clearGroup}
              pageSize={trackPage.page?.page.limit}
              pagination={trackPage}
              totalItems={trackPage.page?.page.total}
              tracks={trackItems}
            />
          )}
        </>
      )}
    </article>
  );
}

type BrowseController = ReturnType<typeof useLibraryBrowseFilters>;
type FacetQueryData = LibraryTrackFacets | undefined;

function LibraryFilters({
  browse,
  facets,
  facetsError,
  onRetryFacets,
  total,
}: {
  browse: BrowseController;
  facets: FacetQueryData;
  facetsError: boolean;
  onRetryFacets: () => void;
  total: number;
}) {
  return (
    <section
      aria-label="Library browse filters"
      className={toolbarStyles.toolbar}
    >
      <div
        aria-label={libraryCopy.list.viewLabel}
        className={styles.viewSwitch}
        role="group"
      >
        <Button
          aria-pressed={browse.filters.view === "tracks"}
          onClick={browse.showTracks}
          variant={browse.filters.view === "tracks" ? "secondary" : "quiet"}
        >
          {libraryCopy.list.tracksView}
        </Button>
        <Button
          aria-pressed={browse.filters.view === "groups"}
          onClick={browse.showGroups}
          variant={browse.filters.view === "groups" ? "secondary" : "quiet"}
        >
          {libraryCopy.list.groupsView}
        </Button>
      </div>
      <label className={toolbarStyles.search} htmlFor="library-search">
        <VisuallyHidden>{libraryCopy.list.searchLabel}</VisuallyHidden>
        <input
          autoComplete="off"
          data-list-search
          id="library-search"
          name="library-search"
          onChange={(event) =>
            browse.updateFilters({ query: event.target.value })
          }
          placeholder={libraryCopy.list.searchPlaceholder}
          type="search"
          value={browse.filters.query}
        />
      </label>
      <label className={toolbarStyles.control} htmlFor="library-status">
        <VisuallyHidden>{libraryCopy.list.statusLabel}</VisuallyHidden>
        <select
          id="library-status"
          name="library-status"
          onChange={(event) => {
            const selected = trackStatusOptions.find(
              (option) => option.value === event.target.value,
            );
            browse.updateFilters({ status: selected?.value });
          }}
          value={browse.filters.status ?? ""}
        >
          <option value="">{libraryCopy.list.allStatuses}</option>
          {trackStatusOptions.map((option) => (
            <option key={option.value} value={option.value}>
              {option.label}
            </option>
          ))}
        </select>
      </label>
      {browse.filters.view === "groups" ? (
        <label className={toolbarStyles.wideControl} htmlFor="library-grouping">
          <VisuallyHidden>{libraryCopy.list.groupingLabel}</VisuallyHidden>
          <select
            id="library-grouping"
            name="library-grouping"
            onChange={(event) => {
              const selected = rootGroupingOptions.find(
                (option) => option.value === event.target.value,
              );
              if (selected !== undefined) {
                browse.changeRootGrouping(selected.value);
              }
            }}
            value={
              browse.filters.groupBy === "artist_album"
                ? "artist_album"
                : "artist"
            }
          >
            {rootGroupingOptions.map((option) => (
              <option key={option.value} value={option.value}>
                {option.label}
              </option>
            ))}
          </select>
        </label>
      ) : null}

      <div className={toolbarStyles.actions}>
        {browse.hasActiveFilters ? (
          <Button onClick={browse.resetFilters} variant="quiet">
            {libraryCopy.list.resetFilters}
          </Button>
        ) : null}
        <p aria-live="polite" className={toolbarStyles.resultCount}>
          {numberFormatter.format(total)} {libraryCopy.list.resultCount}
        </p>
      </div>

      {facetsError ? (
        <div className={toolbarStyles.secondaryRow}>
          <div className={styles.inlineError} role="alert">
            <p>{libraryCopy.list.facetsError}</p>
            <Button onClick={onRetryFacets} variant="quiet">
              {libraryCopy.list.retry}
            </Button>
          </div>
        </div>
      ) : facets === undefined || facets.facets.status.length === 0 ? null : (
        <div className={toolbarStyles.secondaryRow}>
          <div aria-labelledby="track-status-facets" className={styles.facets}>
            <h2 id="track-status-facets">{libraryCopy.list.facetsTitle}</h2>
            <ul className={styles.facetList}>
              {facets.facets.status.map((facet) => (
                <li key={facet.value}>
                  <button
                    aria-pressed={browse.filters.status === facet.value}
                    className={styles.facetButton}
                    onClick={() =>
                      browse.updateFilters({ status: facet.value })
                    }
                    type="button"
                  >
                    <span>{trackStatusLabel(facet.value)}</span>
                    <span className={styles.count}>
                      {numberFormatter.format(facet.count)}
                    </span>
                  </button>
                </li>
              ))}
            </ul>
          </div>
        </div>
      )}
    </section>
  );
}

function GroupBrowser({
  browse,
  groups,
  hasPage,
  isError,
  isPending,
  onRetry,
  pageSize,
  pagination,
  totalItems,
}: {
  browse: BrowseController;
  groups: { count: number; key: string; label: string }[];
  hasPage: boolean;
  isError: boolean;
  isPending: boolean;
  onRetry: () => void;
  pageSize: number | undefined;
  pagination: CursorPageNavigation;
  totalItems: number | undefined;
}) {
  return (
    <section aria-labelledby="track-groups" className={styles.section}>
      <div className={styles.sectionHeader}>
        <div>
          <h2 id="track-groups">{libraryCopy.list.groupsTitle}</h2>
          <p className={styles.subtle}>
            {trackGroupingLabel(browse.filters.groupBy)}
          </p>
        </div>
        {browse.filters.groupBy === "album" ? (
          <Button onClick={browse.backOneLevel} variant="quiet">
            {libraryCopy.list.backToArtists}
          </Button>
        ) : browse.filters.groupBy === "disc" ? (
          <Button onClick={browse.backOneLevel} variant="quiet">
            {libraryCopy.list.backToAlbums}
          </Button>
        ) : null}
      </div>

      {isPending ? (
        <p className={styles.subtle}>{libraryCopy.list.groupsLoading}</p>
      ) : isError ? (
        <div className={styles.inlineError} role="alert">
          <p>{libraryCopy.list.groupsError}</p>
          <Button onClick={onRetry} variant="quiet">
            {libraryCopy.list.retry}
          </Button>
        </div>
      ) : groups.length === 0 ? (
        <p className={styles.subtle}>{libraryCopy.list.noGroups}</p>
      ) : (
        <ul className={styles.groupList}>
          {groups.map((group) => (
            <li className={styles.groupRow} key={group.key}>
              <div className={styles.groupHeader}>
                <span className={styles.groupLabel}>{group.label}</span>
                <span className={styles.count}>
                  {numberFormatter.format(group.count)}{" "}
                  {libraryCopy.labels.groupCount}
                </span>
              </div>
              <div className={styles.groupActions}>
                <Button
                  aria-pressed={browse.filters.groupKey === group.key}
                  onClick={() => browse.selectGroup(group.key)}
                  variant="quiet"
                >
                  {libraryCopy.list.viewTracks}
                </Button>
                {browse.filters.groupBy === "artist" ? (
                  <Button
                    onClick={() => browse.browseGroup(group.key)}
                    variant="secondary"
                  >
                    {libraryCopy.list.browseAlbums}
                  </Button>
                ) : browse.filters.groupBy === "album" ? (
                  <Button
                    onClick={() => browse.browseGroup(group.key)}
                    variant="secondary"
                  >
                    {libraryCopy.list.browseDiscs}
                  </Button>
                ) : null}
              </div>
            </li>
          ))}
        </ul>
      )}

      {hasPage && groups.length > 0 ? (
        <CursorPageControls
          collectionLabel="Library groups"
          pageSize={pageSize}
          totalItems={totalItems}
          {...pagination}
        />
      ) : null}
    </section>
  );
}

function TrackBrowser({
  detailSearch,
  hasActiveFilters,
  hasPage,
  hasSelectedGroup,
  onClearGroup,
  pageSize,
  pagination,
  totalItems,
  tracks,
}: {
  detailSearch: string;
  hasActiveFilters: boolean;
  hasPage: boolean;
  hasSelectedGroup: boolean;
  onClearGroup: () => void;
  pageSize: number | undefined;
  pagination: CursorPageNavigation;
  totalItems: number | undefined;
  tracks: LibraryTrack[];
}) {
  return (
    <section aria-labelledby="track-results" className={styles.section}>
      <div className={styles.sectionHeader}>
        <div>
          <h2 id="track-results">{libraryCopy.list.tracksTitle}</h2>
          {hasSelectedGroup ? (
            <p className={styles.selectedGroup} role="status">
              {libraryCopy.list.selectedGroup}
            </p>
          ) : null}
        </div>
        {hasSelectedGroup ? (
          <Button onClick={onClearGroup} variant="quiet">
            {libraryCopy.list.clearGroup}
          </Button>
        ) : null}
      </div>

      {tracks.length === 0 ? (
        <EmptyState
          body={
            hasActiveFilters
              ? libraryCopy.list.emptyBody
              : libraryCopy.list.noTracksBody
          }
          title={
            hasActiveFilters
              ? libraryCopy.list.emptyTitle
              : libraryCopy.list.noTracksTitle
          }
        />
      ) : (
        <ul className={styles.trackList}>
          <li aria-hidden="true" className={styles.trackColumnHeader}>
            <span>Track</span>
            <span>{libraryCopy.list.albumColumn}</span>
            <span>{libraryCopy.list.pathColumn}</span>
            <span>Status</span>
          </li>
          {tracks.map((track) => (
            <TrackRow
              detailSearch={detailSearch}
              key={track.track_id}
              track={track}
            />
          ))}
        </ul>
      )}

      {hasPage && tracks.length > 0 ? (
        <CursorPageControls
          collectionLabel="Tracks"
          pageSize={pageSize}
          totalItems={totalItems}
          {...pagination}
        />
      ) : null}
    </section>
  );
}

function TrackRow({
  detailSearch,
  track,
}: {
  detailSearch: string;
  track: LibraryTrack;
}) {
  const title = track.metadata.title ?? libraryCopy.detail.untitled;
  const artist =
    track.metadata.album_artist ??
    track.metadata.artist ??
    libraryCopy.detail.unknownArtist;
  const album = track.metadata.album ?? libraryCopy.missingValue;
  const year = track.metadata.year ?? libraryCopy.missingValue;

  return (
    <li className={styles.trackRow}>
      <Link
        className={styles.trackLink}
        data-list-item
        to={{ pathname: `/library/${track.track_id}`, search: detailSearch }}
      >
        <div className={styles.trackIdentity}>
          <p className={styles.trackTitle}>{title}</p>
          <p className={styles.trackArtist}>{artist}</p>
        </div>
        <div className={styles.trackAlbum}>
          <p>{album}</p>
          <p>{year}</p>
        </div>
        <p
          className={`${styles.path} ${styles.trackPath}`}
          title={track.current_path}
          translate="no"
        >
          {track.current_path}
        </p>
        <span className={styles.trackStatus}>
          <TrackStatusBadge value={track.status} />
        </span>
      </Link>
    </li>
  );
}

function LoadingState({ message }: { message: string }) {
  return (
    <section className={styles.state} role="status">
      <p>{message}</p>
    </section>
  );
}

function EmptyState({ body, title }: { body: string; title: string }) {
  return (
    <section className={styles.state}>
      <h2>{title}</h2>
      <p>{body}</p>
    </section>
  );
}
