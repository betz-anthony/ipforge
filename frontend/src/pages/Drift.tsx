import { useState, useMemo } from 'react'
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query'
import { GitCompareArrows, RefreshCw } from 'lucide-react'
import { driftApi, type DriftItem, type Collision } from '../api/client'
import { useToast } from '../contexts/ToastContext'
import EmptyState from '../components/EmptyState'
import CollisionResolveDialog from './CollisionResolveDialog'

const CONFLICT = new Set(['active_but_available', 'multi_dhcp_scope', 'hostname_mismatch'])

const CATEGORY_LABEL: Record<string, string> = {
  active_but_available: 'Active but available',
  multi_dhcp_scope: 'Multi DHCP scope',
  hostname_mismatch: 'Hostname mismatch',
  missing_dns: 'Missing DNS',
  orphan_dns: 'Orphan DNS',
  orphan_dhcp: 'Orphan DHCP',
  mac_mismatch: 'MAC mismatch',
}

const SEV_BADGE: Record<string, string> = { error: 'badge-red', warning: 'badge-yellow', info: 'badge-gray' }

export default function DriftPage() {
  const qc = useQueryClient()
  const { showToast } = useToast()
  const [category, setCategory] = useState('')
  const [selected, setSelected] = useState<Set<number>>(new Set())
  const [resolveTarget, setResolveTarget] = useState<Collision | null>(null)

  const { data: stats } = useQuery({ queryKey: ['drift-stats'], queryFn: driftApi.stats })
  const { data: items, isLoading } = useQuery({
    queryKey: ['drift', category],
    queryFn: () => driftApi.list(category ? { category } : {}),
  })

  const invalidate = () => {
    qc.invalidateQueries({ queryKey: ['drift'] })
    qc.invalidateQueries({ queryKey: ['drift-stats'] })
    qc.invalidateQueries({ queryKey: ['subnets'] })
    setSelected(new Set())
  }

  const scanMut = useMutation({
    mutationFn: () => driftApi.scan(),
    onSuccess: () => { invalidate(); showToast('Drift scan complete', 'success') },
    onError: () => showToast('Scan failed', 'error'),
  })

  const resolveMut = useMutation({
    mutationFn: ({ id, action }: { id: number; action?: string }) => driftApi.resolve(id, action ? { action } : {}),
    onSuccess: () => { invalidate(); showToast('Resolved', 'success') },
    onError: (e: any) => showToast(e?.response?.data?.detail ?? 'Resolve failed', 'error'),
  })

  const bulkMut = useMutation({
    mutationFn: () => driftApi.resolveBulk([...selected]),
    onSuccess: (r) => { invalidate(); showToast(`Dismissed ${r.resolved.length}`, 'success') },
  })

  const rows = items ?? []
  const allChecked = rows.length > 0 && rows.every(d => selected.has(d.id))

  const categories = useMemo(() => Object.keys(stats?.by_category ?? {}), [stats])

  const openResolve = (d: DriftItem) => {
    if (CONFLICT.has(d.category)) {
      setResolveTarget({ ...d, collision_type: d.category } as unknown as Collision)
    }
  }

  const rowAction = (d: DriftItem) => {
    if (CONFLICT.has(d.category)) {
      return <button className="btn-ghost btn-sm" onClick={() => openResolve(d)}>Resolve…</button>
    }
    if (d.category === 'orphan_dns' || d.category === 'orphan_dhcp') {
      return (
        <span style={{ display: 'inline-flex', gap: '0.3rem' }}>
          <button className="btn-ghost btn-sm" onClick={() => resolveMut.mutate({ id: d.id, action: 'import' })}>Import</button>
          <button className="btn-ghost btn-sm" onClick={() => resolveMut.mutate({ id: d.id, action: 'delete' })}>Delete</button>
        </span>
      )
    }
    if (d.category === 'mac_mismatch') {
      return <button className="btn-ghost btn-sm" onClick={() => resolveMut.mutate({ id: d.id, action: 'update_ipam' })}>Use DHCP MAC</button>
    }
    return <button className="btn-ghost btn-sm" onClick={() => resolveMut.mutate({ id: d.id })}>Dismiss</button>
  }

  return (
    <div>
      <div className="page-header" style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}>
        <h1>Drift</h1>
        <button className="btn-primary btn-sm" onClick={() => scanMut.mutate()} disabled={scanMut.isPending}>
          <RefreshCw size={13} /> {scanMut.isPending ? 'Scanning…' : 'Scan for drift'}
        </button>
      </div>

      {stats && (
        <div className="stat-card" style={{ padding: '0.75rem 1rem', marginBottom: '1rem', display: 'flex', flexWrap: 'wrap', gap: '1rem' }}>
          <span><strong>{stats.total}</strong> open</span>
          {Object.entries(stats.by_severity).map(([sev, n]) => (
            <span key={sev} className={`badge ${SEV_BADGE[sev] ?? 'badge-gray'}`}>{sev}: {n}</span>
          ))}
        </div>
      )}

      <div style={{ display: 'flex', gap: '0.5rem', alignItems: 'center', marginBottom: '0.75rem' }}>
        <select value={category} onChange={e => setCategory(e.target.value)}>
          <option value="">All categories</option>
          {categories.map(c => <option key={c} value={c}>{CATEGORY_LABEL[c] ?? c} ({stats?.by_category[c]})</option>)}
        </select>
        {selected.size > 0 && (
          <button className="btn-ghost btn-sm" onClick={() => bulkMut.mutate()} disabled={bulkMut.isPending}>
            Dismiss {selected.size} selected
          </button>
        )}
      </div>

      {isLoading ? (
        <p className="loading">Loading…</p>
      ) : rows.length === 0 ? (
        <EmptyState icon={GitCompareArrows} title="No drift detected"
          description="IPAM, DNS, DHCP and live scan are in sync." />
      ) : (
        <div className="table-wrap">
          <table>
            <thead>
              <tr>
                <th style={{ width: 28 }}>
                  <input type="checkbox" checked={allChecked}
                    onChange={e => setSelected(e.target.checked ? new Set(rows.map(d => d.id)) : new Set())} />
                </th>
                <th>IP</th><th>Category</th><th>Severity</th><th>Details</th><th></th>
              </tr>
            </thead>
            <tbody>
              {rows.map(d => (
                <tr key={d.id}>
                  <td>
                    <input type="checkbox" checked={selected.has(d.id)}
                      onChange={e => {
                        const next = new Set(selected)
                        e.target.checked ? next.add(d.id) : next.delete(d.id)
                        setSelected(next)
                      }} />
                  </td>
                  <td><span className="font-mono">{d.ip_address}</span></td>
                  <td>{CATEGORY_LABEL[d.category] ?? d.category}</td>
                  <td><span className={`badge ${SEV_BADGE[d.severity] ?? 'badge-gray'}`}>{d.severity}</span></td>
                  <td style={{ fontSize: '0.72rem', color: 'var(--text-muted)', maxWidth: 320, overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap' }}>
                    {d.details}
                  </td>
                  <td>{rowAction(d)}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}

      {resolveTarget && (
        <CollisionResolveDialog
          collision={resolveTarget}
          queryKeys={[['drift'], ['drift-stats'], ['subnets']]}
          onClose={() => setResolveTarget(null)}
        />
      )}
    </div>
  )
}
