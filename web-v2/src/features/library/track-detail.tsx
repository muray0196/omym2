/**
 * Summary: Renders persisted Track identity, metadata, paths, hashes, and observations.
 * Why: Gives deep-linked Library inspection a complete read-only detail surface.
 */
import { useQuery } from "@tanstack/react-query";
import { Link, useLocation, useParams } from "react-router-dom";

import { RouteHeading } from "../../ui/primitives/route-heading";
import { libraryCopy } from "./library-copy";
import { LibraryErrorState } from "./library-error-state";
import styles from "./library-inspection.module.css";
import { DefinitionItem, TrackStatusBadge } from "./library-presentation";
import {
  libraryErrorHasCode,
  trackDetailQuery,
  type LibraryTrack,
} from "./library-query";
import {
  displayNumberPair,
  displaySize,
  displayTimestamp,
  displayValue,
} from "./track-format";

export function TrackDetail() {
  const { trackId = "" } = useParams();
  const location = useLocation();
  const query = useQuery(trackDetailQuery(trackId));

  return (
    <article className={styles.page}>
      <div className={styles.backLinkRow}>
        <Link
          className={styles.backLink}
          to={{ pathname: "/library", search: location.search }}
        >
          {libraryCopy.detail.back}
        </Link>
      </div>

      {query.isPending ? (
        <section className={styles.state} role="status">
          <p>{libraryCopy.detail.loading}</p>
        </section>
      ) : query.isError ? (
        libraryErrorHasCode(query.error, "track_not_found") ? (
          <section className={styles.state}>
            <p className={styles.eyebrow}>{libraryCopy.detail.eyebrow}</p>
            <RouteHeading>{libraryCopy.detail.notFoundTitle}</RouteHeading>
            <p>{libraryCopy.detail.notFoundBody}</p>
          </section>
        ) : (
          <LibraryErrorState
            error={query.error}
            onRetry={() => void query.refetch()}
            retryLabel={libraryCopy.detail.retry}
            title={libraryCopy.detail.loadError}
          />
        )
      ) : (
        <TrackDetailContent track={query.data} />
      )}
    </article>
  );
}

function TrackDetailContent({ track }: { track: LibraryTrack }) {
  const metadata = track.metadata;
  const title = metadata.title ?? libraryCopy.detail.untitled;
  const artist =
    metadata.album_artist ??
    metadata.artist ??
    libraryCopy.detail.unknownArtist;

  return (
    <>
      <header className={styles.header}>
        <p className={styles.eyebrow}>{libraryCopy.detail.eyebrow}</p>
        <RouteHeading>{title}</RouteHeading>
        <p className={styles.description}>{artist}</p>
      </header>

      <DetailSection title={libraryCopy.detail.identity}>
        <DefinitionItem label={libraryCopy.labels.trackId} mono>
          {track.track_id}
        </DefinitionItem>
        <DefinitionItem label={libraryCopy.labels.libraryId} mono>
          {track.library_id}
        </DefinitionItem>
        <DefinitionItem label={libraryCopy.labels.status}>
          <TrackStatusBadge value={track.status} />
        </DefinitionItem>
      </DetailSection>

      <DetailSection title={libraryCopy.detail.paths}>
        <DefinitionItem label={libraryCopy.labels.currentPath} mono>
          {track.current_path}
        </DefinitionItem>
        <DefinitionItem label={libraryCopy.labels.canonicalPath} mono>
          {track.canonical_path}
        </DefinitionItem>
      </DetailSection>

      <DetailSection title={libraryCopy.detail.metadata}>
        <DefinitionItem label={libraryCopy.labels.title}>
          {displayValue(metadata.title)}
        </DefinitionItem>
        <DefinitionItem label={libraryCopy.labels.artist}>
          {displayValue(metadata.artist)}
        </DefinitionItem>
        <DefinitionItem label={libraryCopy.labels.albumArtist}>
          {displayValue(metadata.album_artist)}
        </DefinitionItem>
        <DefinitionItem label={libraryCopy.labels.album}>
          {displayValue(metadata.album)}
        </DefinitionItem>
        <DefinitionItem label={libraryCopy.labels.genre}>
          {displayValue(metadata.genre)}
        </DefinitionItem>
        <DefinitionItem label={libraryCopy.labels.year}>
          {displayValue(metadata.year)}
        </DefinitionItem>
        <DefinitionItem label={libraryCopy.labels.trackNumber}>
          {displayNumberPair(metadata.track_number, metadata.track_total)}
        </DefinitionItem>
        <DefinitionItem label={libraryCopy.labels.discNumber}>
          {displayNumberPair(metadata.disc_number, metadata.disc_total)}
        </DefinitionItem>
      </DetailSection>

      <DetailSection title={libraryCopy.detail.hashes}>
        <DefinitionItem label={libraryCopy.labels.contentHash} mono>
          {track.content_hash}
        </DefinitionItem>
        <DefinitionItem label={libraryCopy.labels.metadataHash} mono>
          {track.metadata_hash}
        </DefinitionItem>
      </DetailSection>

      <DetailSection title={libraryCopy.detail.fileState}>
        <DefinitionItem label={libraryCopy.labels.size}>
          {displaySize(track.size)}
        </DefinitionItem>
        <DefinitionItem label={libraryCopy.labels.modified}>
          {displayTimestamp(track.mtime)}
        </DefinitionItem>
      </DetailSection>

      <DetailSection title={libraryCopy.detail.timestamps}>
        <DefinitionItem label={libraryCopy.labels.firstSeen}>
          {displayTimestamp(track.first_seen_at)}
        </DefinitionItem>
        <DefinitionItem label={libraryCopy.labels.lastSeen}>
          {displayTimestamp(track.last_seen_at)}
        </DefinitionItem>
        <DefinitionItem label={libraryCopy.labels.updated}>
          {displayTimestamp(track.updated_at)}
        </DefinitionItem>
      </DetailSection>
    </>
  );
}

function DetailSection({
  children,
  title,
}: {
  children: React.ReactNode;
  title: string;
}) {
  return (
    <section className={styles.section}>
      <h2>{title}</h2>
      <dl className={styles.definitionList}>{children}</dl>
    </section>
  );
}
