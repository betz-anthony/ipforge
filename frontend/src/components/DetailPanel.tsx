import { useEffect } from 'react'
import { useQuery } from '@tanstack/react-query'
import { X, Wifi, WifiOff } from 'lucide-react'
import { toolsApi } from '../api/client'

function fmtAge(isoStr: string | null | undefined): string {
  if (!isoStr) return 'N/A'
  const diff = Math.floor((Date.now() - new Date(isoStr).getTime()) / 1000)
  if (diff < 60) return `${diff}s ago`
  if (diff < 3600) return `${Math.floor(diff / 60)}m ago`
  if (diff < 86400) return `${Math.floor(diff / 3600)}h ago`
  return `${Math.floor(diff / 86400)}d ago`
}

export interface DetailField {
  label: string
  value: React.ReactNode
}

interface Props {
  title: string
  subtitle?: string
  pingTarget?: string
  fields: DetailField[]
  syncedAt?: string | null
  onClose: () => void
}

export default function DetailPanel({ title, subtitle, pingTarget, fields, syncedAt, onClose }: Props) {
  useEffect(() => {
    const handler = (e: KeyboardEvent) => { if (e.key === 'Escape') onClose() }
    window.addEventListener('keydown', handler)
    return () => window.removeEventListener('keydown', handler)
  }, [onClose])

  const { data: ping, isLoading: pingLoading, isError: pingError } = useQuery({
    queryKey: ['ping', pingTarget],
    queryFn: () => toolsApi.ping(pingTarget!),
    enabled: !!pingTarget,
    staleTime: 30_000,
    retry: false,
  })

  return (
    <>
      <div className="detail-backdrop" onClick={onClose} />
      <div className="detail-panel">
        <div className="detail-panel-header">
          <div style={{ minWidth: 0 }}>
            <div className="detail-panel-title">{title}</div>
            {subtitle && <div className="detail-panel-subtitle">{subtitle}</div>}
          </div>
          <button
            className="btn-ghost btn-sm"
            onClick={onClose}
            style={{ padding: '0.25rem', flexShrink: 0 }}
          >
            <X size={14} />
          </button>
        </div>

        <div className="detail-panel-body">
          <div>
            <div className="detail-section-title">Details</div>
            <div className="detail-fields">
              {fields.map((f, i) => (
                <div key={i} className="detail-field">
                  <span className="detail-field-label">{f.label}</span>
                  <span className="detail-field-value">{f.value}</span>
                </div>
              ))}
            </div>
          </div>

          <div>
            <div className="detail-section-title">Connectivity</div>
            {!pingTarget ? (
              <div className="ping-card">
                <div className="ping-loading" style={{ color: 'var(--text-muted)' }}>N/A — no pingable target for this record type</div>
              </div>
            ) : (
              <div className="ping-card">
                <div className="ping-host">{pingTarget}</div>
                {pingLoading ? (
                  <div className="ping-loading">Pinging…</div>
                ) : pingError ? (
                  <div className="ping-loading" style={{ color: 'var(--danger)' }}>Ping unavailable</div>
                ) : ping ? (
                  <>
                    <div className="ping-status">
                      {ping.reachable ? (
                        <>
                          <Wifi size={13} style={{ color: 'var(--accent)', flexShrink: 0 }} />
                          <span style={{ color: 'var(--accent)' }}>Reachable</span>
                        </>
                      ) : (
                        <>
                          <WifiOff size={13} style={{ color: 'var(--danger)', flexShrink: 0 }} />
                          <span style={{ color: 'var(--danger)' }}>Unreachable</span>
                        </>
                      )}
                    </div>
                    {ping.avg_ms !== null && (
                      <div className="ping-stats">
                        <span>Avg <strong>{ping.avg_ms.toFixed(1)}ms</strong></span>
                        <span>Min {ping.min_ms?.toFixed(1)}ms</span>
                        <span>Max {ping.max_ms?.toFixed(1)}ms</span>
                        <span>Loss {ping.loss_pct}%</span>
                      </div>
                    )}
                    {ping.avg_ms === null && (
                      <div className="ping-stats"><span>Loss {ping.loss_pct}%</span></div>
                    )}
                  </>
                ) : null}
              </div>
            )}
          </div>

          <div>
            <div className="detail-section-title">Record Info</div>
            <div className="detail-fields">
              <div className="detail-field">
                <span className="detail-field-label">Last Synced</span>
                <span className="detail-field-value">{fmtAge(syncedAt)}</span>
              </div>
              <div className="detail-field">
                <span className="detail-field-label">Creation Date</span>
                <span className="detail-field-value" style={{ color: 'var(--text-muted)' }}>N/A</span>
              </div>
              <div className="detail-field">
                <span className="detail-field-label">Created By</span>
                <span className="detail-field-value" style={{ color: 'var(--text-muted)' }}>N/A</span>
              </div>
            </div>
          </div>
        </div>
      </div>
    </>
  )
}
