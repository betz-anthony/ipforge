import { useState } from 'react'
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query'
import { Link } from 'react-router-dom'
import { Trash2, Clock, X } from 'lucide-react'
import { reclaimApi, subnetsApi, settingsApi, type StaleAddress } from '../api/client'
import { useAuth } from '../contexts/AuthContext'

function formatDate(iso: string | null): string {
  if (!iso) return '—'
  return new Date(iso).toLocaleDateString()
}

export default function ReclaimPage() {
  const qc = useQueryClient()
  const { user } = useAuth()
  const isOperator = user?.role === 'operator' || user?.role === 'admin'

  const [subnetFilter, setSubnetFilter] = useState<number | undefined>(undefined)

  const { data: appSettings } = useQuery({
    queryKey: ['settings'],
    queryFn: settingsApi.get,
  })

  const { data: subnets = [] } = useQuery({
    queryKey: ['subnets'],
    queryFn: subnetsApi.list,
  })

  const { data: staleIPs = [], isLoading } = useQuery({
    queryKey: ['stale', subnetFilter],
    queryFn: () => reclaimApi.listStale(subnetFilter !== undefined ? { subnet_id: subnetFilter } : {}),
  })

  const invalidate = () => {
    qc.invalidateQueries({ queryKey: ['stale'] })
    qc.invalidateQueries({ queryKey: ['stale-count'] })
  }

  const reclaimMut = useMutation({
    mutationFn: ({ id, action }: { id: number; action: 'deprecate' | 'extend' | 'dismiss' }) =>
      reclaimApi.reclaim(id, action),
    onSuccess: () => invalidate(),
  })

  const bulkMut = useMutation({
    mutationFn: () => reclaimApi.bulkDeprecate(subnetFilter!),
    onSuccess: (data) => {
      invalidate()
      alert(`Deprecated ${data.deprecated} IP(s).`)
    },
  })

  const isDisabled = appSettings?.stale_reclaim_days === 0

  if (!isOperator) {
    return (
      <div>
        <div className="page-header"><h1>Reclaim</h1></div>
        <p style={{ color: 'var(--text-muted)', fontSize: '0.85rem' }}>
          Operator or admin role required.
        </p>
      </div>
    )
  }

  return (
    <div>
      <div className="page-header">
        <h1>Stale IP Reclaim</h1>
      </div>

      {isDisabled && (
        <div style={{
          padding: '0.75rem 1rem', background: 'var(--surface-2)',
          borderRadius: '6px', border: '1px solid var(--border)',
          marginBottom: '1rem', fontSize: '0.85rem', color: 'var(--text-muted)',
        }}>
          Stale reclaim is disabled — set a threshold in{' '}
          <Link to="/settings" style={{ color: 'var(--accent)' }}>Settings</Link>.
        </div>
      )}

      {!isDisabled && (
        <>
          <div style={{ display: 'flex', gap: '0.75rem', alignItems: 'center', marginBottom: '1rem', flexWrap: 'wrap' }}>
            <select
              value={subnetFilter ?? ''}
              onChange={e => setSubnetFilter(e.target.value ? Number(e.target.value) : undefined)}
              style={{ fontSize: '0.82rem' }}
            >
              <option value="">All subnets</option>
              {subnets.map(s => (
                <option key={s.id} value={s.id}>{s.name} ({s.cidr})</option>
              ))}
            </select>

            {subnetFilter !== undefined && (
              <button
                className="btn-danger btn-sm"
                disabled={bulkMut.isPending || staleIPs.length === 0}
                onClick={() => {
                  if (window.confirm(`Deprecate all ${staleIPs.length} stale IPs in this subnet?`)) {
                    bulkMut.mutate()
                  }
                }}
              >
                <Trash2 size={13} />
                {bulkMut.isPending ? 'Deprecating…' : `Bulk Deprecate (${staleIPs.length})`}
              </button>
            )}
          </div>

          {isLoading ? (
            <p className="loading">Loading…</p>
          ) : staleIPs.length === 0 ? (
            <div style={{
              padding: '2rem', textAlign: 'center',
              color: 'var(--text-muted)', fontSize: '0.85rem',
              background: 'var(--surface)', borderRadius: '8px',
              border: '1px solid var(--border)',
            }}>
              No stale IPs found{subnetFilter !== undefined ? ' in this subnet' : ''}.
            </div>
          ) : (
            <div style={{ overflowX: 'auto' }}>
              <table className="data-table" style={{ width: '100%', fontSize: '0.82rem' }}>
                <thead>
                  <tr>
                    <th scope="col">IP Address</th>
                    <th scope="col">Hostname</th>
                    <th scope="col">Subnet</th>
                    <th scope="col">Status</th>
                    <th scope="col">Last Seen</th>
                    <th scope="col">Days Stale</th>
                    <th scope="col">Actions</th>
                  </tr>
                </thead>
                <tbody>
                  {staleIPs.map((ip: StaleAddress) => (
                    <tr key={ip.id}>
                      <td className="font-mono">{ip.address}</td>
                      <td>{ip.hostname ?? <span style={{ color: 'var(--text-muted)' }}>—</span>}</td>
                      <td className="font-mono" style={{ fontSize: '0.75rem' }}>{ip.subnet_cidr}</td>
                      <td>
                        <span className="badge badge-gray" style={{ fontSize: '0.65rem' }}>
                          {ip.status}
                        </span>
                      </td>
                      <td style={{ color: 'var(--text-muted)' }}>{formatDate(ip.last_seen)}</td>
                      <td style={{ color: 'var(--warning, #f59e0b)', fontWeight: 600 }}>
                        {ip.days_stale}d
                      </td>
                      <td>
                        <div style={{ display: 'flex', gap: '0.3rem' }}>
                          <button
                            className="btn-danger btn-sm"
                            style={{ fontSize: '0.7rem' }}
                            disabled={reclaimMut.isPending}
                            onClick={() => {
                              if (window.confirm(`Deprecate ${ip.address}?`)) {
                                reclaimMut.mutate({ id: ip.id, action: 'deprecate' })
                              }
                            }}
                            title="Deprecate"
                          >
                            <Trash2 size={11} /> Deprecate
                          </button>
                          <button
                            className="btn-ghost btn-sm"
                            style={{ fontSize: '0.7rem' }}
                            disabled={reclaimMut.isPending}
                            onClick={() => reclaimMut.mutate({ id: ip.id, action: 'extend' })}
                            title="Extend 90 days"
                          >
                            <Clock size={11} /> Extend
                          </button>
                          <button
                            className="btn-ghost btn-sm"
                            style={{ fontSize: '0.7rem' }}
                            disabled={reclaimMut.isPending}
                            onClick={() => reclaimMut.mutate({ id: ip.id, action: 'dismiss' })}
                            title="Dismiss permanently"
                          >
                            <X size={11} /> Dismiss
                          </button>
                        </div>
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          )}
        </>
      )}
    </div>
  )
}
