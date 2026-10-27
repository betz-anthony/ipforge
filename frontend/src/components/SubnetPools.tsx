import { useState } from 'react'
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query'
import { Plus, Pencil, Trash2 } from 'lucide-react'
import { subnetPoolsApi, type Subnet, type SubnetPool } from '../api/client'
import { isValidIPv4, isValidIPv6 } from '../utils/ip'
import { useToast } from '../contexts/ToastContext'
import { apiError } from '../utils/apiError'
import ConfirmModal from './ConfirmModal'
import UtilBar from './UtilBar'

const NAME_RE = /^[a-z0-9][a-z0-9_-]{0,63}$/
const emptyForm = { name: '', start_ip: '', end_ip: '', description: '' }

/**
 * Allocation pools: named IP windows inside a subnet that the allocate API can
 * target. Unrelated to the "dhcp_pool" reserved-range kind.
 */
export default function SubnetPools({ subnet }: { subnet: Subnet }) {
  const qc = useQueryClient()
  const { showToast } = useToast()
  const isV6 = subnet.ip_version === 6

  const { data: pools } = useQuery({
    queryKey: ['pools', subnet.id],
    queryFn: () => subnetPoolsApi.list(subnet.id),
  })

  const [editing, setEditing] = useState<SubnetPool | 'new' | null>(null)
  const [form, setForm] = useState(emptyForm)
  const [confirmDelete, setConfirmDelete] = useState<SubnetPool | null>(null)

  const validIp = (v: string) => (isV6 ? isValidIPv6(v) : isValidIPv4(v))
  const nameOk = NAME_RE.test(form.name.trim().toLowerCase())
  const startOk = !!form.start_ip && validIp(form.start_ip.trim())
  const endOk = !!form.end_ip && validIp(form.end_ip.trim())
  const canSave = nameOk && startOk && endOk

  const close = () => { setEditing(null); setForm(emptyForm) }

  const startEdit = (p: SubnetPool | 'new') => {
    setEditing(p)
    setForm(p === 'new'
      ? emptyForm
      : { name: p.name, start_ip: p.start_ip, end_ip: p.end_ip, description: p.description ?? '' })
  }

  const body = () => ({
    name: form.name.trim().toLowerCase(),
    start_ip: form.start_ip.trim(),
    end_ip: form.end_ip.trim(),
    description: form.description.trim() || null,
  })

  const refresh = () => qc.invalidateQueries({ queryKey: ['pools', subnet.id] })

  const saveMut = useMutation({
    mutationFn: () => editing === 'new'
      ? subnetPoolsApi.create(subnet.id, body())
      : subnetPoolsApi.update(subnet.id, (editing as SubnetPool).id, body()),
    onSuccess: () => {
      const verb = editing === 'new' ? 'added' : 'updated'
      refresh()
      showToast(`Pool "${form.name.trim().toLowerCase()}" ${verb}`, 'success')
      close()
    },
    onError: (err: unknown) => {
      const e = apiError(err, 'Save failed')
      showToast(e.message, 'error', { hint: e.hint, detail: e.detail })
    },
  })

  const deleteMut = useMutation({
    mutationFn: (p: SubnetPool) => subnetPoolsApi.remove(subnet.id, p.id),
    onSuccess: (_d, p) => {
      refresh()
      showToast(`Pool "${p.name}" deleted`, 'success')
      setConfirmDelete(null)
    },
    onError: (err: unknown) => {
      const e = apiError(err, 'Delete failed')
      showToast(e.message, 'error', { hint: e.hint, detail: e.detail })
      setConfirmDelete(null)
    },
  })

  return (
    <div style={{ marginTop: '1rem' }}>
      <div className="detail-section-title">Allocation Pools</div>
      {(pools ?? []).length === 0 && !editing && (
        <p style={{ fontSize: '0.8rem', color: 'var(--text-muted)', margin: '0.4rem 0' }}>
          No allocation pools. A pool lets an allocation request take the next free IP from a named range.
        </p>
      )}
      {(pools ?? []).map(p => {
        const pct = p.total ? (p.used / p.total) * 100 : 0
        const resPct = p.total ? (p.reserved / p.total) * 100 : 0
        return (
          <div key={p.id} style={{ display: 'flex', alignItems: 'center', gap: '0.5rem', fontSize: '0.8rem', padding: '0.25rem 0', flexWrap: 'wrap' }}>
            <span className="badge badge-blue">{p.name}</span>
            <span className="font-mono">{p.start_ip}–{p.end_ip}</span>
            <UtilBar pct={pct} reservedPct={resPct} warn={80} critical={95} />
            <span style={{ color: 'var(--text-muted)', fontSize: '0.72rem' }}>
              {p.free.toLocaleString()} free of {p.total.toLocaleString()}
            </span>
            {p.description && <span style={{ color: 'var(--text-muted)' }}>{p.description}</span>}
            <span style={{ marginLeft: 'auto', display: 'inline-flex', gap: '0.25rem' }}>
              <button className="btn-ghost btn-sm" aria-label={`Edit pool ${p.name}`} onClick={() => startEdit(p)}>
                <Pencil size={12} />
              </button>
              <button className="btn-ghost btn-sm" aria-label={`Delete pool ${p.name}`} onClick={() => setConfirmDelete(p)}>
                <Trash2 size={12} />
              </button>
            </span>
          </div>
        )
      })}

      {editing ? (
        <div className="inline-form" style={{ marginTop: '0.5rem' }}>
          <div className="form-grid">
            <div className={`form-field${form.name && !nameOk ? ' form-field-error' : ''}`}>
              <label htmlFor="pool-name">Name</label>
              <input id="pool-name" value={form.name} placeholder="linux"
                onChange={e => setForm(f => ({ ...f, name: e.target.value }))} />
              {form.name && !nameOk && (
                <span className="form-field-error-msg">Lowercase letters, digits, - and _</span>
              )}
            </div>
            <div className={`form-field${form.start_ip && !startOk ? ' form-field-error' : ''}`}>
              <label htmlFor="pool-start">Start IP</label>
              <input id="pool-start" value={form.start_ip}
                onChange={e => setForm(f => ({ ...f, start_ip: e.target.value }))} />
            </div>
            <div className={`form-field${form.end_ip && !endOk ? ' form-field-error' : ''}`}>
              <label htmlFor="pool-end">End IP</label>
              <input id="pool-end" value={form.end_ip}
                onChange={e => setForm(f => ({ ...f, end_ip: e.target.value }))} />
            </div>
            <div className="form-field">
              <label htmlFor="pool-desc">Description</label>
              <input id="pool-desc" value={form.description} placeholder="optional"
                onChange={e => setForm(f => ({ ...f, description: e.target.value }))} />
            </div>
          </div>
          <div className="form-actions">
            <button className="btn-primary btn-sm" disabled={!canSave || saveMut.isPending} onClick={() => saveMut.mutate()}>
              {saveMut.isPending ? 'Saving…' : editing === 'new' ? 'Add Pool' : 'Save Pool'}
            </button>
            <button className="btn-ghost btn-sm" onClick={close}>Cancel</button>
          </div>
        </div>
      ) : (
        <button className="btn-ghost btn-sm" style={{ marginTop: '0.4rem' }} onClick={() => startEdit('new')}>
          <Plus size={12} /> Add Pool
        </button>
      )}

      {confirmDelete && (
        <ConfirmModal
          title="Delete Allocation Pool"
          message={`Delete pool "${confirmDelete.name}"? Addresses in this range are not affected.`}
          onConfirm={() => deleteMut.mutate(confirmDelete)}
          onCancel={() => setConfirmDelete(null)}
        />
      )}
    </div>
  )
}
