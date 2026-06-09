import { ChevronLeft, ChevronRight } from 'lucide-react'

interface Props {
  page: number
  total: number
  pageSize: number
  isFetching?: boolean
  onPage: (page: number) => void
  onPageSize: (size: number) => void
}

const PAGE_SIZES = [50, 100, 200]

export function Pager({ page, total, pageSize, isFetching, onPage, onPageSize }: Props) {
  const totalPages = Math.max(1, Math.ceil(total / pageSize))
  const from = Math.min((page - 1) * pageSize + 1, total)
  const to = Math.min(page * pageSize, total)

  return (
    <div className="pager">
      <span className="pager-info">
        {total === 0 ? '0 results' : `${from}–${to} of ${total}`}
        {isFetching && <span className="pager-loading"> …</span>}
      </span>
      <div className="pager-controls">
        <button
          className="btn-ghost btn-sm pager-btn"
          disabled={page <= 1}
          onClick={() => onPage(page - 1)}
          aria-label="Previous page"
        >
          <ChevronLeft size={14} />
        </button>
        <span className="pager-page">
          {page} / {totalPages}
        </span>
        <button
          className="btn-ghost btn-sm pager-btn"
          disabled={page >= totalPages}
          onClick={() => onPage(page + 1)}
          aria-label="Next page"
        >
          <ChevronRight size={14} />
        </button>
        <select
          className="pager-size-select"
          value={pageSize}
          onChange={e => { onPageSize(Number(e.target.value)); onPage(1) }}
          aria-label="Rows per page"
        >
          {PAGE_SIZES.map(s => (
            <option key={s} value={s}>{s} / page</option>
          ))}
        </select>
      </div>
    </div>
  )
}
