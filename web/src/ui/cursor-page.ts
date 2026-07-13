/**
 * Summary: Selects one loaded opaque-cursor page for bounded list rendering.
 * Why: Keeps long-running inspection sessions from growing the rendered DOM without limit.
 */
import { useCallback, useState } from "react";

export type CursorPageNavigation = {
  goToNextPage: () => void;
  goToPreviousPage: () => void;
  hasNextPage: boolean;
  hasPreviousPage: boolean;
  isFetchingNextPage: boolean;
  pageNumber: number;
};

type CursorPageOptions<Page> = {
  fetchNextPage: () => Promise<unknown>;
  hasNextPage: boolean;
  isFetchingNextPage: boolean;
  pages: readonly Page[] | undefined;
  resetKey: string;
};

type CursorPageResult<Page> = CursorPageNavigation & {
  page: Page | undefined;
};

type CursorPosition = {
  index: number;
  resetKey: string;
};

export function useCursorPage<Page>({
  fetchNextPage,
  hasNextPage,
  isFetchingNextPage,
  pages,
  resetKey,
}: CursorPageOptions<Page>): CursorPageResult<Page> {
  const [position, setPosition] = useState<CursorPosition>({
    index: 0,
    resetKey,
  });
  const resetRequired = position.resetKey !== resetKey;
  if (resetRequired) {
    setPosition({ index: 0, resetKey });
  }
  const pageCount = pages?.length ?? 0;
  const lastLoadedIndex = Math.max(pageCount - 1, 0);
  const selectedIndex = resetRequired
    ? 0
    : Math.min(position.index, lastLoadedIndex);
  const hasLoadedNextPage = selectedIndex + 1 < pageCount;

  const goToPreviousPage = useCallback(() => {
    setPosition({ index: Math.max(selectedIndex - 1, 0), resetKey });
  }, [resetKey, selectedIndex]);

  const goToNextPage = useCallback(() => {
    if (isFetchingNextPage || (!hasLoadedNextPage && !hasNextPage)) {
      return;
    }

    setPosition({ index: selectedIndex + 1, resetKey });
    if (!hasLoadedNextPage) {
      void fetchNextPage();
    }
  }, [
    fetchNextPage,
    hasLoadedNextPage,
    hasNextPage,
    isFetchingNextPage,
    resetKey,
    selectedIndex,
  ]);

  return {
    goToNextPage,
    goToPreviousPage,
    hasNextPage: hasLoadedNextPage || hasNextPage,
    hasPreviousPage: selectedIndex > 0,
    isFetchingNextPage,
    page: pages?.[selectedIndex],
    pageNumber: selectedIndex + 1,
  };
}
