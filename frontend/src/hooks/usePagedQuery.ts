import { useState, useCallback, useRef } from 'react'
import { useQuery, keepPreviousData } from '@tanstack/react-query'
import type { Paged } from '../api/client'

export type SortDir = 'asc' | 'desc'

export interface PagedParams {
  limit: number
  offset: number
  sort: string
  dir: SortDir
  q: string
}

interface UsePagedQueryOptions<T, F extends Record<string, unknown>> {
  queryKey: (string | number | boolean | undefined | null)[]
  queryFn: (params: PagedParams & F) => Promise<Paged<T>>
  filters?: F
  defaultSort?: string
  defaultDir?: SortDir
  defaultPageSize?: number
}

interface UsePagedQueryResult<T> {
  items: T[]
  total: number
  page: number
  setPage: (page: number) => void
  sort: string
  dir: SortDir
  setSort: (sort: string) => void
  q: string
  setQuery: (q: string) => void
  pageSize: number
  setPageSize: (size: number) => void
  isFetching: boolean
  isLoading: boolean
  error: unknown
}

export function usePagedQuery<T, F extends Record<string, unknown> = Record<string, never>>(
  options: UsePagedQueryOptions<T, F>
): UsePagedQueryResult<T> {
  const {
    queryKey,
    queryFn,
    filters = {} as F,
    defaultSort = '',
    defaultDir = 'asc',
    defaultPageSize = 50,
  } = options

  const [page, setPageState] = useState(1)
  const [pageSize, setPageSizeState] = useState(defaultPageSize)
  const [sort, setSortState] = useState(defaultSort)
  const [dir, setDirState] = useState<SortDir>(defaultDir)
  const [q, setQState] = useState('')
  const [debouncedQ, setDebouncedQ] = useState('')

  const debounceTimer = useRef<ReturnType<typeof setTimeout> | null>(null)
  const setQuery = useCallback((val: string) => {
    setQState(val)
    if (debounceTimer.current) clearTimeout(debounceTimer.current)
    debounceTimer.current = setTimeout(() => {
      setDebouncedQ(val)
      setPageState(1)
    }, 300)
  }, [])

  const setPage = useCallback((p: number) => setPageState(p), [])

  const setSort = useCallback((newSort: string) => {
    if (newSort === sort) {
      setDirState(d => d === 'asc' ? 'desc' : 'asc')
    } else {
      setSortState(newSort)
      setDirState('asc')
    }
    setPageState(1)
  }, [sort])

  const setPageSize = useCallback((size: number) => {
    setPageSizeState(size)
    setPageState(1)
  }, [])

  const offset = (page - 1) * pageSize

  const params = {
    limit: pageSize,
    offset,
    sort,
    dir,
    q: debouncedQ,
    ...filters,
  } as PagedParams & F

  const { data, isFetching, isLoading, error } = useQuery({
    queryKey: [...queryKey, pageSize, offset, sort, dir, debouncedQ, ...Object.values(filters)],
    queryFn: () => queryFn(params),
    placeholderData: keepPreviousData,
  })

  return {
    items: data?.items ?? [],
    total: data?.total ?? 0,
    page,
    setPage,
    sort,
    dir,
    setSort,
    q,
    setQuery,
    pageSize,
    setPageSize,
    isFetching,
    isLoading,
    error,
  }
}
