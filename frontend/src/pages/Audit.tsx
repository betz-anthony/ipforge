import { useState } from 'react'
import { useQuery } from '@tanstack/react-query'
import { auditApi, type AuditEntry } from '../api/client'

const RESOURCE_TYPES = ['subnet', 'address', 'dns_record', 'dhcp_reservation']

const ACTION_COLORS: Record<string, string> = {
  create: 'var(--accent)',
  update: '#f59e0b',
  delete: 'var(--danger)',
}

function ActionBadge({ action }: { action: string }) {
  return (
    <span style={{
      display: 'inline-block', padding: '0.1rem 0.45rem',
      borderRadius: '4px', fontSize: '0.7rem', fontWeight: 600,
      background: ACTION_COLORS[action] ?? 'var(--surface-2)',
      color: action === 'update' ? '#052e16' : (ACTION_COLORS[action] ? 'var(--bg)' : 'var(--text)'),
      textTransform: 'uppercase',
    }}>
      {action}
    </span>
  )
}

function StateViewer({ label, json }: { label: string; json: string | null }) {
  if (!json) return null
  let parsed: unknown
  try { parsed = JSON.parse(json) } catch { parsed = json }
  return (
    <div style={{ marginTop: '0.5rem' }}>
      <div style={{ fontSize: '0.7rem', color: 'var(--text-muted)', marginBottom: '0.25rem' }}>{label}</div>
      <pre style={{
        background: 'var(--surface-2)', padding: '0.5rem', borderRadius: '4px',
        fontSize: '0.72rem', overflowX: 'auto', margin: 0,
        maxHeight: '160px', overflowY: 'auto',
      }}>
        {JSON.stringify(parsed, null, 2)}
      </pre>
    </div>
  )
}

export default function AuditPage() {
  const [filterType, setFilterType] = useState('')
  const [filterUser, setFilterUser] = useState('')
  const [fromDate,   setFromDate]   = useState('')
  const [toDate,     setToDate]     = useState('')
  const [expanded,   setExpanded]   = useState<number | null>(null)

  const { data: entries = [], isLoading, isError } = useQuery({
    queryKey: ['audit', filterType, filterUser, fromDate, toDate],
    queryFn: () => auditApi.list({
      resource_type: filterType || undefined,
      username:      filterUser || undefined,
      from_date:     fromDate   || undefined,
      to_date:       toDate     || undefined,
      limit: 200,
    }),
  })

  return (
    <div style={{ maxWidth: '1000px' }}>
      <div className="page-header"><h1>Audit Log</h1></div>

      {/* Filters */}
      <div style={{ display: 'flex', gap: '0.75rem', flexWrap: 'wrap', marginBottom: '1rem' }}>
        <div className="form-field" style={{ margin: 0, minWidth: '160px' }}>
          <label>Resource Type</label>
          <select value={filterType} onChange={e => setFilterType(e.target.value)}>
            <option value="">All</option>
            {RESOURCE_TYPES.map(t => <option key={t} value={t}>{t}</option>)}
          </select>
        </div>
        <div className="form-field" style={{ margin: 0, minWidth: '140px' }}>
          <label>Username</label>
          <input value={filterUser} onChange={e => setFilterUser(e.target.value)} placeholder="any" />
        </div>
        <div className="form-field" style={{ margin: 0 }}>
          <label>From</label>
          <input type="date" value={fromDate} onChange={e => setFromDate(e.target.value)} />
        </div>
        <div className="form-field" style={{ margin: 0 }}>
          <label>To</label>
          <input type="date" value={toDate} onChange={e => setToDate(e.target.value)} />
        </div>
      </div>

      {isLoading && <p className="loading">Loading…</p>}
      {isError   && <p className="feedback-error">Failed to load audit log.</p>}

      {!isLoading && entries.length === 0 && (
        <p style={{ color: 'var(--text-muted)', fontSize: '0.85rem' }}>No entries found.</p>
      )}

      {entries.map((e: AuditEntry) => (
        <div
          key={e.id}
          style={{
            border: '1px solid var(--border)', borderRadius: '6px',
            marginBottom: '0.4rem', overflow: 'hidden',
          }}
        >
          <div
            style={{
              display: 'flex', alignItems: 'center', gap: '0.6rem',
              padding: '0.45rem 0.75rem', cursor: 'pointer',
              background: 'var(--surface)',
            }}
            onClick={() => setExpanded(expanded === e.id ? null : e.id)}
          >
            <span style={{ fontSize: '0.72rem', color: 'var(--text-muted)', flexShrink: 0, minWidth: '140px' }}>
              {new Date(e.timestamp + 'Z').toLocaleString()}
            </span>
            <ActionBadge action={e.action} />
            <span style={{ fontSize: '0.75rem', color: 'var(--text-muted)', flexShrink: 0 }}>
              {e.resource_type}
            </span>
            <span style={{ flex: 1, fontSize: '0.82rem', overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap' }}>
              {e.summary ?? e.resource_id}
            </span>
            <span style={{ fontSize: '0.75rem', fontFamily: 'var(--font-mono)', color: 'var(--text-muted)', flexShrink: 0 }}>
              {e.username}
            </span>
          </div>

          {expanded === e.id && (e.before_state || e.after_state) && (
            <div style={{ padding: '0.5rem 0.75rem 0.75rem', background: 'var(--surface-2)', borderTop: '1px solid var(--border)' }}>
              <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: '0.75rem' }}>
                <StateViewer label="Before" json={e.before_state} />
                <StateViewer label="After"  json={e.after_state}  />
              </div>
            </div>
          )}
        </div>
      ))}
    </div>
  )
}
