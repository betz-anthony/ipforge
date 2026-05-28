import { useState } from 'react'
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query'
import { Plus, Trash2 } from 'lucide-react'
import { automationApi, type AutomationRule } from '../api/client'
import { useToast } from '../contexts/ToastContext'
import Collapsible from '../components/Collapsible'
import ConfirmModal from '../components/ConfirmModal'

const STATUSES = ['', 'available', 'reserved', 'assigned', 'deprecated', 'discovered']

export default function AutomationRules() {
  const qc = useQueryClient()
  const { showToast } = useToast()
  const { data: rules = [] } = useQuery({ queryKey: ['automation-rules'], queryFn: automationApi.list })

  const [adding, setAdding] = useState(false)
  const [name, setName] = useState('')
  const [trigger, setTrigger] = useState<'rogue' | 'drift'>('rogue')
  const [category, setCategory] = useState('')
  const [status, setStatus] = useState('')
  const [tags, setTags] = useState('')
  const [confirmDelete, setConfirmDelete] = useState<{ id: number; name: string } | null>(null)

  const reset = () => { setName(''); setTrigger('rogue'); setCategory(''); setStatus(''); setTags(''); setAdding(false) }
  const invalidate = () => qc.invalidateQueries({ queryKey: ['automation-rules'] })

  const parsedTags = tags.split(',').map(t => t.trim()).filter(Boolean)
  const canAdd = name.trim() && (status || parsedTags.length > 0)

  const createMut = useMutation({
    mutationFn: () => automationApi.create({
      name: name.trim(),
      trigger_type: trigger,
      condition: trigger === 'drift' && category ? { category } : {},
      action: { ...(status ? { set_status: status } : {}), ...(parsedTags.length ? { add_tags: parsedTags } : {}) },
    }),
    onSuccess: () => { invalidate(); reset(); showToast('Rule added', 'success') },
    onError: (e: any) => showToast(e?.response?.data?.detail ?? 'Add failed', 'error'),
  })
  const toggleMut = useMutation({
    mutationFn: ({ id, enabled }: { id: number; enabled: boolean }) => automationApi.update(id, { enabled }),
    onSuccess: invalidate,
  })
  const deleteMut = useMutation({
    mutationFn: (id: number) => automationApi.remove(id),
    onSuccess: () => { invalidate(); setConfirmDelete(null); showToast('Rule deleted', 'success') },
  })

  const describe = (r: AutomationRule) => {
    const parts: string[] = []
    if (r.action.set_status) parts.push(`status→${r.action.set_status}`)
    if (r.action.add_tags?.length) parts.push(`+tags ${r.action.add_tags.join(', ')}`)
    return parts.join('; ')
  }

  return (
    <Collapsible title="Automation Rules" storageKey="automation-rules">
      <p style={{ fontSize: '0.8rem', color: 'var(--text-muted)', marginTop: 0 }}>
        On a <strong>rogue</strong> (new device) or <strong>drift</strong> event, tag and/or set the status of the
        matching address. Actions are reversible and audited.
      </p>
      <div className="table-wrap">
        <table>
          <thead><tr><th>Name</th><th>Trigger</th><th>Condition</th><th>Action</th><th>Enabled</th><th></th></tr></thead>
          <tbody>
            {rules.length === 0 && <tr><td colSpan={6} className="empty-state">No automation rules.</td></tr>}
            {rules.map((r: AutomationRule) => (
              <tr key={r.id}>
                <td>{r.name}</td>
                <td><span className="badge badge-blue">{r.trigger_type}</span></td>
                <td>{(r.condition as any)?.category ?? <span className="text-muted">—</span>}</td>
                <td style={{ fontSize: '0.78rem' }}>{describe(r)}</td>
                <td>
                  <input type="checkbox" checked={r.enabled}
                    onChange={e => toggleMut.mutate({ id: r.id, enabled: e.target.checked })} />
                </td>
                <td><button className="btn-ghost btn-sm" onClick={() => setConfirmDelete({ id: r.id, name: r.name })}><Trash2 size={13} /></button></td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>

      {adding ? (
        <form onSubmit={e => { e.preventDefault(); if (canAdd) createMut.mutate() }} style={{ marginTop: '0.75rem' }}>
          <div className="form-grid">
            <div className="form-field"><label>Name</label><input value={name} onChange={e => setName(e.target.value)} /></div>
            <div className="form-field">
              <label>Trigger</label>
              <select value={trigger} onChange={e => setTrigger(e.target.value as 'rogue' | 'drift')}>
                <option value="rogue">rogue (new device)</option>
                <option value="drift">drift</option>
              </select>
            </div>
            {trigger === 'drift' && (
              <div className="form-field">
                <label>Drift category (optional)</label>
                <input value={category} onChange={e => setCategory(e.target.value)} placeholder="e.g. orphan_dhcp — blank = any" />
              </div>
            )}
            <div className="form-field">
              <label>Set status</label>
              <select value={status} onChange={e => setStatus(e.target.value)}>
                {STATUSES.map(s => <option key={s} value={s}>{s || '— none —'}</option>)}
              </select>
            </div>
            <div className="form-field">
              <label>Add tags (comma-separated)</label>
              <input value={tags} onChange={e => setTags(e.target.value)} placeholder="unverified" />
            </div>
          </div>
          <div className="form-actions">
            <button type="submit" className="btn-primary" disabled={!canAdd || createMut.isPending}>Add Rule</button>
            <button type="button" className="btn-ghost" onClick={reset}>Cancel</button>
          </div>
        </form>
      ) : (
        <button className="btn-ghost btn-sm" style={{ marginTop: '0.5rem' }} onClick={() => setAdding(true)}>
          <Plus size={13} /> Add Rule
        </button>
      )}

      {confirmDelete && (
        <ConfirmModal title="Delete Automation Rule" message={`Delete "${confirmDelete.name}"?`}
          onConfirm={() => deleteMut.mutate(confirmDelete.id)} onCancel={() => setConfirmDelete(null)} />
      )}
    </Collapsible>
  )
}
