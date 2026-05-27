import { useState, type ReactElement } from 'react'
import { ArrowUp, ArrowDown, ArrowUpDown } from 'lucide-react'

export type SortDir = 'asc' | 'desc'

export function useTableSort<K extends string>(initialKey: K, initialDir: SortDir = 'asc') {
  const [sortKey, setSortKey] = useState<K>(initialKey)
  const [sortDir, setSortDir] = useState<SortDir>(initialDir)

  const toggleSort = (key: K) => {
    if (sortKey === key) setSortDir(d => (d === 'asc' ? 'desc' : 'asc'))
    else { setSortKey(key); setSortDir('asc') }
  }

  const sortIcon = (key: K): ReactElement =>
    sortKey !== key ? <ArrowUpDown size={11} className="sort-icon-idle" />
    : sortDir === 'asc' ? <ArrowUp size={11} />
    : <ArrowDown size={11} />

  const dir = sortDir === 'asc' ? 1 : -1

  return { sortKey, sortDir, toggleSort, sortIcon, dir }
}
