/*
Summary: Loads cursor-paginated Web API lists for client screens.
Why: Prevents full-table browser loads while keeping pagination state reusable.
*/

"use client"

import {
  useCallback,
  useEffect,
  useMemo,
  useRef,
  useState,
  type Dispatch,
  type SetStateAction,
} from "react"
import type { PageInfo, PagedResponse } from "./types"

type PageLoader<T> = (cursor?: string) => Promise<PagedResponse<T>>

export interface PagedListState<T> {
  items: T[]
  page: PageInfo | null
  errors: string[]
  loaded: boolean
  loading: boolean
  loadingMore: boolean
  hasMore: boolean
  reload: () => Promise<void>
  loadMore: () => Promise<void>
  setItems: Dispatch<SetStateAction<T[]>>
}

export function usePagedList<T>({
  errorMessage,
  loadPage,
}: {
  errorMessage: string
  loadPage: PageLoader<T>
}): PagedListState<T> {
  const [items, setItems] = useState<T[]>([])
  const [page, setPage] = useState<PageInfo | null>(null)
  const [errors, setErrors] = useState<string[]>([])
  const [loaded, setLoaded] = useState(false)
  const [loading, setLoading] = useState(false)
  const [loadingMore, setLoadingMore] = useState(false)
  const activeRequest = useRef(0)
  const loadingMoreRef = useRef(false)
  const mounted = useRef(true)

  useEffect(() => {
    return () => {
      mounted.current = false
    }
  }, [])

  const reload = useCallback(async () => {
    const requestId = activeRequest.current + 1
    activeRequest.current = requestId
    loadingMoreRef.current = false
    setItems([])
    setPage(null)
    setErrors([])
    setLoaded(false)
    setLoading(true)
    setLoadingMore(false)

    try {
      const response = await loadPage()
      if (!mounted.current || activeRequest.current !== requestId) return
      setItems(response.items)
      setPage(response.page)
      setErrors(response.errors)
    } catch (error: unknown) {
      if (!mounted.current || activeRequest.current !== requestId) return
      setItems([])
      setPage(null)
      setErrors([error instanceof Error ? error.message : errorMessage])
    } finally {
      if (mounted.current && activeRequest.current === requestId) {
        setLoading(false)
        setLoaded(true)
      }
    }
  }, [errorMessage, loadPage])

  useEffect(() => {
    void reload()
  }, [reload])

  const loadMore = useCallback(async () => {
    const cursor = page?.next_cursor
    if (!cursor || loading || loadingMoreRef.current) return

    const requestId = activeRequest.current
    loadingMoreRef.current = true
    setLoadingMore(true)

    try {
      const response = await loadPage(cursor)
      if (!mounted.current || activeRequest.current !== requestId) return
      setItems((current) => [...current, ...response.items])
      setPage(response.page)
      setErrors(response.errors)
    } catch (error: unknown) {
      if (!mounted.current || activeRequest.current !== requestId) return
      setErrors([error instanceof Error ? error.message : errorMessage])
    } finally {
      if (mounted.current && activeRequest.current === requestId) {
        loadingMoreRef.current = false
        setLoadingMore(false)
      }
    }
  }, [errorMessage, loadPage, loading, page?.next_cursor])

  return useMemo(
    () => ({
      items,
      page,
      errors,
      loaded,
      loading,
      loadingMore,
      hasMore: Boolean(page?.next_cursor),
      reload,
      loadMore,
      setItems,
    }),
    [errors, items, loadMore, loaded, loading, loadingMore, page, reload],
  )
}
