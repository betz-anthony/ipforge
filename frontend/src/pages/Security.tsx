import { useState } from 'react'
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query'
import { ShieldAlert } from 'lucide-react'
import { securityApi, type SecurityEvent } from '../api/client'
import { useToast } from '../contexts/ToastContext'
import EmptyState from '../components/EmptyState'

const TYPE_LABEL: Record<string, string> = {
  rogue_device: 'Rogue device', mac_move: 'MAC move', ip_conflict: 'IP conflict', new_mac: 'New MAC',
}
const SEV_BADGE: Record<string, string> = { error: 'badge-red', warning: 'badge-yellow', info: 'badge-gray' }

export default function SecurityPage() {
  const qc = useQueryClient()
  const { showToast } = useToast()
  const [type, setType] = useState('')
  const [hideAcked, setHideAcked] = useState(true)

  const { data: events, isLoading } = useQuery({
    queryKey: ['security-events', type, hideAcked],
    queryFn: () => securityApi.list({
      ...(type ? { event_type: type } : {}),
      ...(hideAcked ? { acknowledged: false } : {}),
    }),
  })

  const invalidate = () => qc.invalidateQueries({ queryKey: ['security-events'] })
  const ackMut = useMutation({ mutationFn: (id: number) => securityApi.ack(id), onSuccess: invalidate })
  const qMut = useMutation({
    mutationFn: (id: number) => securityApi.quarantine(id),
    onSuccess: () => { invalidate(); qc.invalidateQueries({ queryKey: ['addresses'] }); showToast('Quarantined', 'success') },
    onError: (e: any) => showToast(e?.response?.data?.detail ?? 'Quarantine failed', 'error'),
  })

  const rows = events ?? []

  return (
    <div>
      <div className="page-header"><h1><ShieldAlert size={20} style={{ verticalAlign: '-3px' }} /> Security</h1></div>

      <div style={{ display: 'flex', gap: '0.5rem', alignItems: 'center', marginBottom: '0.75rem' }}>
        <select value={type} onChange={e => setType(e.target.value)}>
          <option value="">All types</option>
          {Object.entries(TYPE_LABEL).map(([k, v]) => <option key={k} value={k}>{v}</option>)}
        </select>
        <label style={{ fontSize: '0.8rem', display: 'inline-flex', alignItems: 'center', gap: '0.3rem' }}>
          <input type="checkbox" checked={hideAcked} onChange={e => setHideAcked(e.target.checked)} />
          Hide acknowledged
        </label>
      </div>

      {isLoading ? (
        <p className="loading">Loading…</p>
      ) : rows.length === 0 ? (
        <EmptyState icon={ShieldAlert} title="No security events" description="Rogue devices, MAC moves and IP conflicts will show up here." />
      ) : (
        <div className="table-wrap">
          <table>
            <thead>
              <tr><th scope="col">Severity</th><th scope="col">Type</th><th scope="col">MAC</th><th scope="col">IP</th><th scope="col">Detected</th><th scope="col"></th></tr>
            </thead>
            <tbody>
              {rows.map((e: SecurityEvent) => (
                <tr key={e.id}>
                  <td><span className={`badge ${SEV_BADGE[e.severity] ?? 'badge-gray'}`}>{e.severity}</span></td>
                  <td>{TYPE_LABEL[e.event_type] ?? e.event_type}{e.quarantined && <span className="badge badge-blue" style={{ marginLeft: '0.4rem' }}>quarantined</span>}</td>
                  <td><span className="font-mono">{e.mac ?? '—'}</span></td>
                  <td><span className="font-mono">{e.ip ?? '—'}</span></td>
                  <td style={{ fontSize: '0.72rem', color: 'var(--text-muted)' }}>{e.detected_at ? new Date(e.detected_at).toLocaleString() : ''}</td>
                  <td style={{ display: 'flex', gap: '0.3rem' }}>
                    {!e.acknowledged && <button className="btn-ghost btn-sm" onClick={() => ackMut.mutate(e.id)}>Ack</button>}
                    {e.ip && !e.quarantined && <button className="btn-ghost btn-sm" onClick={() => qMut.mutate(e.id)}>Quarantine</button>}
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}
    </div>
  )
}
