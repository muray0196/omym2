/**
 * Summary: Renders URL-owned Track search, hierarchy groups, facets, and cursor pages.
 * Why: Delivers read-only Library inspection from persisted backend state in M2.
 */
import { useInfiniteQuery, useQuery } from "@tanstack/react-query";
import { useDeferredValue } from "react";
import { Link, useLocation } from "react-router-dom";

import { bootstrapQuery } from "../bootstrap/bootstrap-query";
import { useCursorPage, type CursorPageNavigation } from "../../ui/cursor-page";
import { Button } from "../../ui/primitives/button";
import { CursorPageControls } from "../../ui/primitives/cursor-page-controls";
import { RouteHeading } from "../../ui/primitives/route-heading";
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

export function LibraryList() {
  const location = useLocation();
  const browse = useLibraryBrowseFilters();
  const bootstrap = useQuery(bootstrapQuery);
  const libraryId = bootstrap.data?.data?.active_library?.library_id;
  const deferredQuery = useDeferredValue(browse.filters.query);
  const queryFilters = { ...browse.filters, query: deferredQuery };
  const tracks = useInfiniteQuery(tracksInfiniteQuery(libraryId, queryFilters));
  const facets = useQuery(trackFacetsQuery(libraryId, queryFilters));
  const groups = useInfiniteQuery(
    trackGroupsInfiniteQuery(libraryId, queryFilters),
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
  const total = tracks.data?.pages[0]?.page.total ?? 0;

  return (
    <article className={styles.page}>
      <header className={styles.header}>
        <p className={styles.eyebrow}>{libraryCopy.list.eyebrow}</p>
        <RouteHeading>{libraryCopy.list.title}</RouteHeading>
        <p className={styles.description}>{libraryCopy.list.description}</p>
      </header>

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
          />
          {tracks.isPending ? (
            <LoadingState message={libraryCopy.list.loading} />
          ) : tracks.isError ? (
            <LibraryErrorState
              error={tracks.error}
              onRetry={() => void tracks.refetch()}
              retryLabel={libraryCopy.list.retry}
              title={libraryCopy.list.loadError}
            />
          ) : (
            <div className={styles.browserGrid}>
              <GroupBrowser
                browse={browse}
                groups={groupItems}
                hasPage={groupPage.page !== undefined}
                isError={groups.isError}
                isPending={groups.isPending}
                onRetry={() => void groups.refetch()}
                pagination={groupPage}
              />
              <TrackBrowser
                detailSearch={location.search}
                hasActiveFilters={browse.hasActiveFilters}
                hasPage={trackPage.page !== undefined}
                pagination={trackPage}
                total={total}
                tracks={trackItems}
              />
            </div>
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
}: {
  browse: BrowseController;
  facets: FacetQueryData;
  facetsError: boolean;
  onRetryFacets: () => void;
}) {
  return (
    <section aria-label="Library browse filters" className={styles.filterPanel}>
      <div className={styles.filterGrid}>
        <div className={styles.field}>
          <label htmlFor="library-search">{libraryCopy.list.searchLabel}</label>
          <input
            data-list-search
            id="library-search"
            onChange={(event) =>
              browse.updateFilters({ query: event.target.value })
            }
            placeholder={libraryCopy.list.searchPlaceholder}
            type="search"
            value={browse.filters.query}
          />
        </div>
        <div className={styles.field}>
          <label htmlFor="library-status">{libraryCopy.list.statusLabel}</label>
          <select
            id="library-status"
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
        </div>
        <div className={styles.field}>
          <label htmlFor="library-grouping">
            {libraryCopy.list.groupingLabel}
          </label>
          <select
            id="library-grouping"
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
        </div>
      </div>

      <div className={styles.filterActions}>
        {browse.hasActiveFilters ? (
          <Button onClick={browse.resetFilters} variant="quiet">
            {libraryCopy.list.resetFilters}
          </Button>
        ) : null}
        {browse.filters.groupKey === undefined ? null : (
          <Button onClick={browse.clearGroup} variant="quiet">
            {libraryCopy.list.clearGroup}
          </Button>
        )}
      </div>

      {facetsError ? (
        <div className={styles.inlineError} role="alert">
          <p>{libraryCopy.list.facetsError}</p>
          <Button onClick={onRetryFacets} variant="quiet">
            {libraryCopy.list.retry}
          </Button>
        </div>
      ) : facets === undefined || facets.facets.status.length === 0 ? null : (
        <div aria-labelledby="track-status-facets" className={styles.facets}>
          <h2 id="track-status-facets">{libraryCopy.list.facetsTitle}</h2>
          <ul className={styles.facetList}>
            {facets.facets.status.map((facet) => (
              <li key={facet.value}>
                <button
                  aria-pressed={browse.filters.status === facet.value}
                  className={styles.facetButton}
                  onClick={() => browse.updateFilters({ status: facet.value })}
                  type="button"
                >
                  <span>{trackStatusLabel(facet.value)}</span>
                  <span className={styles.count}>{facet.count}</span>
                </button>
              </li>
            ))}
          </ul>
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
  pagination,
}: {
  browse: BrowseController;
  groups: { count: number; key: string; label: string }[];
  hasPage: boolean;
  isError: boolean;
  isPending: boolean;
  onRetry: () => void;
  pagination: CursorPageNavigation;
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

      {browse.filters.groupKey === undefined ? null : (
        <p className={styles.selectedGroup} role="status">
          {libraryCopy.list.selectedGroup}
        </p>
      )}
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
                  {group.count} {libraryCopy.labels.groupCount}
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

      {hasPage ? (
        <CursorPageControls collectionLabel="Library groups" {...pagination} />
      ) : null}
    </section>
  );
}

function TrackBrowser({
  detailSearch,
  hasActiveFilters,
  hasPage,
  pagination,
  total,
  tracks,
}: {
  detailSearch: string;
  hasActiveFilters: boolean;
  hasPage: boolean;
  pagination: CursorPageNavigation;
  total: number;
  tracks: LibraryTrack[];
}) {
  return (
    <section aria-labelledby="track-results" className={styles.section}>
      <div className={styles.sectionHeader}>
        <h2 id="track-results">{libraryCopy.list.title}</h2>
        <p className={styles.resultCount}>
          {total} {libraryCopy.list.resultCount}
        </p>
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
          {tracks.map((track) => (
            <TrackRow
              detailSearch={detailSearch}
              key={track.track_id}
              track={track}
            />
          ))}
        </ul>
      )}

      {hasPage ? (
        <CursorPageControls collectionLabel="Tracks" {...pagination} />
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

  return (
    <li className={styles.trackRow}>
      <Link
        className={styles.trackLink}
        data-list-item
        to={{ pathname: `/library/${track.track_id}`, search: detailSearch }}
      >
        <div className={styles.rowHeader}>
          <div>
            <p className={styles.trackTitle}>{title}</p>
            <p className={styles.trackArtist}>{artist}</p>
          </div>
          <TrackStatusBadge value={track.status} />
        </div>
        <p className={styles.path}>{track.current_path}</p>
        <p className={styles.identifier}>{track.track_id}</p>
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
