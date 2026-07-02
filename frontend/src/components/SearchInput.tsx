import { Search, X } from 'lucide-react'

type Props = {
  value: string
  onChange: (v: string) => void
  placeholder?: string
  width?: string
  id?: string
  ariaLabel?: string
}

export default function SearchInput({
  value,
  onChange,
  placeholder = 'Search…',
  width = '15rem',
  id,
  ariaLabel,
}: Props) {
  return (
    <div style={{ position: 'relative', display: 'flex', alignItems: 'center' }}>
      <Search size={13} style={{ position: 'absolute', left: '0.5rem', color: 'var(--text-muted)', pointerEvents: 'none' }} />
      <input
        type="text"
        id={id}
        aria-label={ariaLabel ?? (id ? undefined : placeholder)}
        placeholder={placeholder}
        value={value}
        onChange={e => onChange(e.target.value)}
        style={{ fontSize: '0.75rem', padding: '0.3rem 1.8rem 0.3rem 1.7rem', width }}
      />
      {value && (
        <button
          type="button"
          onClick={() => onChange('')}
          aria-label="Clear search"
          style={{ position: 'absolute', right: '0.3rem', background: 'transparent', border: 'none', cursor: 'pointer', padding: '2px', display: 'flex', color: 'var(--text-muted)' }}
        >
          <X size={12} />
        </button>
      )}
    </div>
  )
}
