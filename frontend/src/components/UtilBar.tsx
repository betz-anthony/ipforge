export default function UtilBar({ pct, warn, critical, reservedPct = 0 }: { pct: number; warn: number; critical: number; reservedPct?: number }) {
  const color = pct >= critical ? 'var(--danger)' : pct >= warn ? '#fbbf24' : '#4ade80'
  const usedW = Math.min(100, pct)
  const resW = Math.min(100 - usedW, Math.max(0, reservedPct))
  return (
    <div style={{ display: 'flex', alignItems: 'center', gap: '0.4rem' }}>
      <div style={{ width: '56px', height: '5px', background: 'var(--surface-2)', borderRadius: '3px', overflow: 'hidden', display: 'flex' }}>
        <div style={{ width: `${usedW}%`, height: '100%', background: color }} />
        {resW > 0 && (
          <div
            title="Reserved"
            style={{ width: `${resW}%`, height: '100%', background: 'repeating-linear-gradient(45deg, var(--text-muted) 0 2px, transparent 2px 4px)' }}
          />
        )}
      </div>
      <span style={{ fontSize: '0.72rem', color, fontFamily: 'var(--font-mono)' }}>
        {pct.toFixed(1)}%
      </span>
    </div>
  )
}
