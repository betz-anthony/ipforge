import { useState } from 'react'
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query'
import { Plus, Pencil, Trash2, Check, X } from 'lucide-react'
import {
  alertRulesApi, alertChannelsApi,
  type AlertRule, type AlertRuleIn, type AlertChannel,
} from '../api/client'
import { useToast } from '../contexts/ToastContext'

const TRIGGERS = [
  { value: 'collision',    label: 'Collision detected' },
  { value: 'utilization',  label: 'Subnet utilization threshold' },
  { value: 'rogue',        label: 'Rogue device on scan' },
  { value: 'sync_error',   label: 'Provider sync error' },
  { value: 'stale_queue',         label: 'Stale-IP queue threshold' },
  { value: 'ip_request_submitted', label: 'IP request submitted' },
  { value: 'ip_request_resolved',  label: 'IP request resolved (approved/denied)' },
] as const

const blank: AlertRuleIn = {
  name: '', trigger_type: 'collision', condition: {},
  channel_ids: [], recipients: [], renotify_minutes: null, enabled: true,
}

export default function AlertRules() {
  const qc = useQueryClient()
  const { showToast } = useToast()
  const { data: rules = [] } = useQuery({ queryKey: ['alert-rules'], queryFn: alertRulesApi.list })
  const { data: channels = [] } = useQuery({ queryKey: ['alert-channels'], queryFn: alertChannelsApi.list })

  const [editing, setEditing] = useState<{ id?: number; form: AlertRuleIn } | null>(null)
  const [error, setError] = useState('')

  const save = useMutation({
    mutationFn: async () => {
      if (!editing) return
      setError('')
      return editing.id != null
        ? alertRulesApi.update(editing.id, editing.form)
        : alertRulesApi.create(editing.form)
    },
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ['alert-rules'] })
      setEditing(null)
      showToast('Rule saved', 'success')
    },
    onError: (e: any) => setError(e?.response?.data?.detail ?? 'Save failed'),
  })

  const del = useMutation({
    mutationFn: (id: number) => alertRulesApi.delete(id),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ['alert-rules'] })
      showToast('Rule deleted', 'success')
    },
  })

  const startNew = () => { setEditing({ form: { ...blank } }); setError('') }
  const startEdit = (r: AlertRule) => {
    setEditing({ id: r.id, form: { ...r, condition: { ...r.condition } } })
    setError('')
  }

  const showRecipients = !!editing?.form.channel_ids.some(
    id => channels.find((c: AlertChannel) => c.id === id)?.kind === 'smtp'
  )

  const channelName = (id: number) => channels.find((c: AlertChannel) => c.id === id)?.name ?? `#${id}`

  return (
    <div>
      <div className="settings-section-title" style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}>
        <span>Alert Rules</span>
        <button className="btn-primary btn-sm" onClick={startNew}><Plus size={13} /> Add Rule</button>
      </div>
      <table className="data-table" style={{ width: '100%', fontSize: '0.82rem' }}>
        <thead>
          <tr><th>Name</th><th>Trigger</th><th>Channels</th><th>Re-notify</th><th>Enabled</th><th></th></tr>
        </thead>
        <tbody>
          {rules.map((r: AlertRule) => (
            <tr key={r.id}>
              <td>{r.name}</td>
              <td>{TRIGGERS.find(t => t.value === r.trigger_type)?.label ?? r.trigger_type}</td>
              <td>{r.channel_ids.map(channelName).join(', ') || '—'}</td>
              <td>{r.renotify_minutes ? `${r.renotify_minutes} min` : '—'}</td>
              <td>{r.enabled ? 'Yes' : 'No'}</td>
              <td style={{ textAlign: 'right' }}>
                <button className="btn-ghost btn-sm" onClick={() => startEdit(r)} title="Edit"><Pencil size={13} /></button>
                <button className="btn-ghost btn-sm" onClick={() => del.mutate(r.id)} title="Delete"><Trash2 size={13} /></button>
              </td>
            </tr>
          ))}
          {rules.length === 0 && (
            <tr><td colSpan={6} style={{ textAlign: 'center', color: 'var(--text-muted)' }}>No rules configured.</td></tr>
          )}
        </tbody>
      </table>

      {editing && (
        <div className="inline-form" style={{ marginTop: '0.75rem' }}>
          <div className="form-grid">
            <div className="form-field">
              <label>Name</label>
              <input
                value={editing.form.name}
                onChange={e => setEditing({ ...editing, form: { ...editing.form, name: e.target.value } })}
              />
            </div>
            <div className="form-field">
              <label>Trigger</label>
              <select
                value={editing.form.trigger_type}
                onChange={e => setEditing({ ...editing, form: { ...editing.form, trigger_type: e.target.value as AlertRule['trigger_type'], condition: {} } })}
              >
                {TRIGGERS.map(t => <option key={t.value} value={t.value}>{t.label}</option>)}
              </select>
            </div>

            {editing.form.trigger_type === 'utilization' && (
              <div className="form-field">
                <label>Threshold %</label>
                <input
                  type="number"
                  min={1}
                  max={100}
                  value={editing.form.condition.threshold_pct ?? 90}
                  onChange={e => setEditing({ ...editing, form: { ...editing.form, condition: { threshold_pct: +e.target.value } } })}
                />
              </div>
            )}
            {editing.form.trigger_type === 'stale_queue' && (
              <div className="form-field">
                <label>Threshold (count)</label>
                <input
                  type="number"
                  min={1}
                  value={editing.form.condition.threshold ?? 10}
                  onChange={e => setEditing({ ...editing, form: { ...editing.form, condition: { threshold: +e.target.value } } })}
                />
              </div>
            )}

            <div className="form-field">
              <label>Channels</label>
              <select
                multiple
                value={editing.form.channel_ids.map(String)}
                onChange={e => setEditing({ ...editing, form: { ...editing.form, channel_ids: Array.from(e.target.selectedOptions).map(o => +o.value) } })}
              >
                {channels.map((c: AlertChannel) => <option key={c.id} value={c.id}>{c.name} ({c.kind})</option>)}
              </select>
            </div>

            {showRecipients && (
              <div className="form-field">
                <label>Recipients (comma-separated)</label>
                <input
                  value={editing.form.recipients.join(', ')}
                  onChange={e => setEditing({ ...editing, form: { ...editing.form, recipients: e.target.value.split(',').map(s => s.trim()).filter(Boolean) } })}
                />
              </div>
            )}

            <div className="form-field">
              <label>Re-notify minutes (blank = never)</label>
              <input
                type="number"
                min={1}
                value={editing.form.renotify_minutes ?? ''}
                onChange={e => setEditing({ ...editing, form: { ...editing.form, renotify_minutes: e.target.value ? +e.target.value : null } })}
              />
            </div>
            <div className="form-field">
              <label>Enabled</label>
              <select
                value={editing.form.enabled ? 'yes' : 'no'}
                onChange={e => setEditing({ ...editing, form: { ...editing.form, enabled: e.target.value === 'yes' } })}
              >
                <option value="yes">Yes</option>
                <option value="no">No</option>
              </select>
            </div>
          </div>

          <div className="form-actions">
            <button className="btn-primary btn-sm" onClick={() => save.mutate()} disabled={save.isPending || !editing.form.name}>
              <Check size={13} /> {save.isPending ? 'Saving…' : 'Save'}
            </button>
            <button className="btn-ghost btn-sm" onClick={() => setEditing(null)}><X size={13} /> Cancel</button>
            {error && <span className="feedback-error">{error}</span>}
          </div>
        </div>
      )}
    </div>
  )
}
