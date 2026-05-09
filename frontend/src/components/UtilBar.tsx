export default function UtilBar({ pct, warn, critical }: { pct: number; warn: number; critical: number }) {
  const color = pct >= critical ? 'var(--danger)' : pct >= warn ? '#fbbf24' : '#4ade80'
  return (
    <div style={{ display: 'flex', alignItems: 'center', gap: '0.4rem' }}>
      <div style={{ width: '56px', height: '5px', background: 'var(--surface-2)', borderRadius: '3px', overflow: 'hidden' }}>
        <div style={{ width: `${Math.min(100, pct)}%`, height: '100%', background: color, borderRadius: '3px' }} />
      </div>
      <span style={{ fontSize: '0.72rem', color, fontFamily: 'var(--font-mono)' }}>
        {pct.toFixed(1)}%
      </span>
    </div>
  )
}
