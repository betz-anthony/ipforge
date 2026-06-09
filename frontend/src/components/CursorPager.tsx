import { ChevronLeft, ChevronRight } from 'lucide-react'

interface Props {
  hasPrev: boolean
  hasNext: boolean
  isFetching?: boolean
  onPrev: () => void
  onNext: () => void
}

export function CursorPager({ hasPrev, hasNext, isFetching, onPrev, onNext }: Props) {
  return (
    <div className="pager">
      <span className="pager-info">
        {isFetching && <span className="pager-loading">Loading…</span>}
      </span>
      <div className="pager-controls">
        <button
          className="btn-ghost btn-sm pager-btn"
          disabled={!hasPrev}
          onClick={onPrev}
          aria-label="Newer entries"
        >
          <ChevronLeft size={14} /> Newer
        </button>
        <button
          className="btn-ghost btn-sm pager-btn"
          disabled={!hasNext}
          onClick={onNext}
          aria-label="Older entries"
        >
          Older <ChevronRight size={14} />
        </button>
      </div>
    </div>
  )
}
