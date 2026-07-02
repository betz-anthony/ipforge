import { useState } from 'react'
import { useMutation, useQueryClient, type QueryKey } from '@tanstack/react-query'
import { scanApi, type Collision, type CollisionResolveRequest } from '../api/client'

interface Props {
  collision: Collision
  queryKeys: QueryKey[]
  onClose: () => void
}

export default function CollisionResolveDialog({ collision, queryKeys, onClose }: Props) {
  const qc = useQueryClient()

  let details: Record<string, unknown> = {}
  try { details = collision.details ? JSON.parse(collision.details) : {} } catch { /* ignore */ }

  const [newStatus,         setNewStatus]         = useState<'assigned' | 'reserved'>('assigned')
  const [canonicalHostname, setCanonicalHostname] = useState<string>(String(details.ipam ?? ''))
  const [sourcesToRemove,   setSourcesToRemove]   = useState<string[]>([])

  const mutation = useMutation({
    mutationFn: (body: CollisionResolveRequest) => scanApi.resolveCollision(collision.id, body),
    onSuccess: () => {
      queryKeys.forEach(k => qc.invalidateQueries({ queryKey: k }))
      onClose()
    },
  })

  const handleSubmit = () => {
    if (collision.collision_type === 'active_but_available') {
      mutation.mutate({ new_status: newStatus })
    } else if (collision.collision_type === 'hostname_mismatch') {
      mutation.mutate({ canonical_hostname: canonicalHostname })
    } else if (collision.collision_type === 'multi_dhcp_scope') {
      mutation.mutate({ sources_to_remove: sourcesToRemove })
    }
  }

  const errRaw = mutation.error as { response?: { data?: { detail?: unknown } } } | null
  const errDetail = errRaw?.response?.data?.detail
  const errorMsg = errDetail
    ? (typeof errDetail === 'string' ? errDetail : (errDetail as { detail?: string }).detail ?? 'Server error.')
    : null

  const sources: string[] = Array.isArray(details.sources) ? (details.sources as string[]) : []

  const isDisabled =
    mutation.isPending ||
    (collision.collision_type === 'hostname_mismatch' && !canonicalHostname.trim()) ||
    (collision.collision_type === 'multi_dhcp_scope' && (sourcesToRemove.length === 0 || sourcesToRemove.length >= sources.length))

  return (
    <div
      style={{
        position: 'fixed', inset: 0, background: 'rgba(0,0,0,0.5)',
        display: 'flex', alignItems: 'center', justifyContent: 'center', zIndex: 1000,
      }}
      onClick={onClose}
    >
      <div
        style={{
          background: 'var(--surface)', border: '1px solid var(--border)',
          borderRadius: '8px', padding: '1.25rem', width: '420px', maxWidth: '90vw',
        }}
        onClick={e => e.stopPropagation()}
      >
        {/* Header */}
        <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: '0.75rem' }}>
          <strong style={{ fontSize: '0.95rem' }}>Resolve Collision</strong>
          <span className="badge badge-yellow" style={{ fontSize: '0.65rem' }}>
            {collision.collision_type.replace(/_/g, ' ')}
          </span>
        </div>

        <div style={{ fontSize: '0.75rem', color: 'var(--text-muted)', marginBottom: '0.75rem' }}>
          <span className="font-mono">{collision.ip_address}</span>
        </div>

        {/* active_but_available */}
        {collision.collision_type === 'active_but_available' && (
          <div>
            <p style={{ fontSize: '0.82rem', color: 'var(--text-secondary)', marginBottom: '0.5rem' }}>
              IP responds to ping but IPAM status is <em>available</em>. Set new status:
            </p>
            <div className="form-field" style={{ margin: 0 }}>
              <select value={newStatus} onChange={e => setNewStatus(e.target.value as 'assigned' | 'reserved')}>
                <option value="assigned">assigned</option>
                <option value="reserved">reserved</option>
              </select>
            </div>
          </div>
        )}

        {/* hostname_mismatch */}
        {collision.collision_type === 'hostname_mismatch' && (
          <div>
            <table style={{ width: '100%', fontSize: '0.78rem', marginBottom: '0.75rem', borderCollapse: 'collapse' }}>
              <tbody>
                {details.ipam != null && (
                  <tr>
                    <td style={{ color: 'var(--text-muted)', paddingRight: '0.75rem', paddingBottom: '0.2rem' }}>IPAM</td>
                    <td className="font-mono">{String(details.ipam)}</td>
                  </tr>
                )}
                {details.dns != null && (
                  <tr>
                    <td style={{ color: 'var(--text-muted)', paddingRight: '0.75rem', paddingBottom: '0.2rem' }}>DNS</td>
                    <td className="font-mono">{String(details.dns)}</td>
                  </tr>
                )}
                {details.dhcp != null && (
                  <tr>
                    <td style={{ color: 'var(--text-muted)', paddingRight: '0.75rem', paddingBottom: '0.2rem' }}>DHCP</td>
                    <td className="font-mono">{String(details.dhcp)}</td>
                  </tr>
                )}
              </tbody>
            </table>
            <div className="form-field" style={{ margin: 0 }}>
              <label htmlFor="collision-canonical" style={{ fontSize: '0.75rem' }}>Canonical hostname</label>
              <input
                id="collision-canonical"
                value={canonicalHostname}
                onChange={e => setCanonicalHostname(e.target.value)}
                placeholder="hostname"
              />
            </div>
            <p style={{ fontSize: '0.7rem', color: 'var(--text-muted)', marginTop: '0.35rem' }}>
              Updates DNS, DHCP, and IPAM.
            </p>
          </div>
        )}

        {/* multi_dhcp_scope */}
        {collision.collision_type === 'multi_dhcp_scope' && (
          <div>
            <p style={{ fontSize: '0.82rem', color: 'var(--text-secondary)', marginBottom: '0.5rem' }}>
              Remove reservation from:
            </p>
            {sources.map(source => (
              <label
                key={source}
                style={{
                  display: 'flex', alignItems: 'center', gap: '0.5rem',
                  padding: '0.4rem 0.5rem', background: 'var(--surface-2)',
                  borderRadius: '4px', marginBottom: '0.35rem', cursor: 'pointer',
                  fontSize: '0.82rem',
                }}
              >
                <input
                  type="checkbox"
                  checked={sourcesToRemove.includes(source)}
                  onChange={e =>
                    setSourcesToRemove(prev =>
                      e.target.checked ? [...prev, source] : prev.filter(s => s !== source)
                    )
                  }
                />
                {source}
              </label>
            ))}
            <p style={{ fontSize: '0.7rem', color: 'var(--text-muted)', marginTop: '0.25rem' }}>
              Must remove ≥1 and keep ≥1.
            </p>
          </div>
        )}

        {/* Error banner */}
        {errorMsg && (
          <div style={{
            marginTop: '0.75rem', padding: '0.5rem 0.75rem',
            background: 'rgba(239,68,68,0.1)', border: '1px solid rgba(239,68,68,0.5)',
            borderRadius: '4px', fontSize: '0.78rem', color: '#ef4444',
          }}>
            {errorMsg}
          </div>
        )}

        {/* Actions */}
        <div style={{ display: 'flex', gap: '0.5rem', justifyContent: 'flex-end', marginTop: '1rem' }}>
          <button className="btn-ghost btn-sm" onClick={onClose} disabled={mutation.isPending}>
            Cancel
          </button>
          <button className="btn-primary btn-sm" onClick={handleSubmit} disabled={isDisabled}>
            {mutation.isPending ? 'Resolving…' : 'Resolve'}
          </button>
        </div>
      </div>
    </div>
  )
}
