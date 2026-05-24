import { useState } from 'react'
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query'
import { Plus, Pencil, Trash2, Check, X, Send } from 'lucide-react'
import { alertChannelsApi, type AlertChannel, type AlertChannelIn } from '../api/client'
import { useToast } from '../contexts/ToastContext'

const KINDS = [
  { value: 'smtp',      label: 'SMTP (email)' },
  { value: 'generic',   label: 'Generic webhook' },
  { value: 'slack',     label: 'Slack webhook' },
  { value: 'teams',     label: 'Microsoft Teams' },
  { value: 'pagerduty', label: 'PagerDuty Events v2' },
] as const

const blank: AlertChannelIn = { name: '', kind: 'generic', config: { url: '' }, secret: null, enabled: true }

export default function AlertChannels() {
  const qc = useQueryClient()
  const { showToast } = useToast()
  const { data: channels = [] } = useQuery({
    queryKey: ['alert-channels'],
    queryFn: alertChannelsApi.list,
  })
  const [editing, setEditing] = useState<{ id?: number; form: AlertChannelIn } | null>(null)
  const [error, setError] = useState<string>('')

  const save = useMutation({
    mutationFn: async () => {
      if (!editing) return
      setError('')
      return editing.id != null
        ? alertChannelsApi.update(editing.id, editing.form)
        : alertChannelsApi.create(editing.form)
    },
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ['alert-channels'] })
      setEditing(null)
      showToast('Channel saved', 'success')
    },
    onError: (e: any) => setError(e?.response?.data?.detail ?? 'Save failed'),
  })

  const del = useMutation({
    mutationFn: (id: number) => alertChannelsApi.delete(id),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ['alert-channels'] })
      showToast('Channel deleted', 'success')
    },
  })

  const test = useMutation({
    mutationFn: (id: number) => alertChannelsApi.test(id),
    onSuccess: (r) => showToast(
      `Test ${r.status}${r.error ? ': ' + r.error : ''}`,
      r.status === 'sent' ? 'success' : 'error',
    ),
  })

  const startNew = () => { setEditing({ form: { ...blank, config: { url: '' } } }); setError('') }
  const startEdit = (c: AlertChannel) => {
    setEditing({ id: c.id, form: { name: c.name, kind: c.kind, config: { ...c.config }, secret: null, enabled: c.enabled } })
    setError('')
  }

  return (
    <div>
      <div className="settings-section-title" style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}>
        <span>Alert Channels</span>
        <button className="btn-primary btn-sm" onClick={startNew}><Plus size={13} /> Add Channel</button>
      </div>
      <table className="data-table" style={{ width: '100%', fontSize: '0.82rem' }}>
        <thead>
          <tr><th>Name</th><th>Kind</th><th>Enabled</th><th></th></tr>
        </thead>
        <tbody>
          {channels.map(c => (
            <tr key={c.id}>
              <td>{c.name}</td>
              <td>{KINDS.find(k => k.value === c.kind)?.label ?? c.kind}</td>
              <td>{c.enabled ? 'Yes' : 'No'}</td>
              <td style={{ textAlign: 'right' }}>
                <button className="btn-ghost btn-sm" onClick={() => startEdit(c)} title="Edit"><Pencil size={13} /></button>
                <button className="btn-ghost btn-sm" onClick={() => test.mutate(c.id)} disabled={test.isPending} title="Send test"><Send size={13} /></button>
                <button className="btn-ghost btn-sm" onClick={() => del.mutate(c.id)} title="Delete"><Trash2 size={13} /></button>
              </td>
            </tr>
          ))}
          {channels.length === 0 && (
            <tr><td colSpan={4} style={{ textAlign: 'center', color: 'var(--text-muted)' }}>No channels configured.</td></tr>
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
              <label>Kind</label>
              <select
                value={editing.form.kind}
                onChange={e => setEditing({ ...editing, form: { ...editing.form, kind: e.target.value as AlertChannel['kind'], config: { url: '' }, secret: null } })}
              >
                {KINDS.map(k => <option key={k.value} value={k.value}>{k.label}</option>)}
              </select>
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

            {editing.form.kind === 'smtp' ? (
              <>
                <div className="form-field">
                  <label>Host</label>
                  <input
                    value={editing.form.config.host ?? ''}
                    onChange={e => setEditing({ ...editing, form: { ...editing.form, config: { ...editing.form.config, host: e.target.value } } })}
                  />
                </div>
                <div className="form-field">
                  <label>Port</label>
                  <input
                    type="number"
                    value={editing.form.config.port ?? 25}
                    onChange={e => setEditing({ ...editing, form: { ...editing.form, config: { ...editing.form.config, port: +e.target.value } } })}
                  />
                </div>
                <div className="form-field">
                  <label>TLS (STARTTLS)</label>
                  <select
                    value={editing.form.config.tls ? 'yes' : 'no'}
                    onChange={e => setEditing({ ...editing, form: { ...editing.form, config: { ...editing.form.config, tls: e.target.value === 'yes' } } })}
                  >
                    <option value="no">No</option>
                    <option value="yes">Yes</option>
                  </select>
                </div>
                <div className="form-field">
                  <label>Username</label>
                  <input
                    value={editing.form.config.user ?? ''}
                    onChange={e => setEditing({ ...editing, form: { ...editing.form, config: { ...editing.form.config, user: e.target.value } } })}
                  />
                </div>
                <div className="form-field">
                  <label>From address</label>
                  <input
                    value={editing.form.config.from ?? ''}
                    onChange={e => setEditing({ ...editing, form: { ...editing.form, config: { ...editing.form.config, from: e.target.value } } })}
                  />
                </div>
                <div className="form-field">
                  <label>To address(es)</label>
                  <input
                    value={editing.form.config.to ?? ''}
                    placeholder="comma-separated"
                    onChange={e => setEditing({ ...editing, form: { ...editing.form, config: { ...editing.form.config, to: e.target.value } } })}
                  />
                </div>
                <div className="form-field">
                  <label>Password</label>
                  <input
                    type="password"
                    placeholder={editing.id != null ? '(leave blank to keep)' : ''}
                    onChange={e => setEditing({ ...editing, form: { ...editing.form, secret: e.target.value || null } })}
                  />
                </div>
              </>
            ) : (
              <>
                <div className="form-field">
                  <label>Webhook URL</label>
                  <input
                    value={editing.form.config.url ?? ''}
                    onChange={e => setEditing({ ...editing, form: { ...editing.form, config: { ...editing.form.config, url: e.target.value } } })}
                  />
                </div>
                <div className="form-field">
                  <label>Bearer Token (optional)</label>
                  <input
                    type="password"
                    placeholder={editing.id != null ? '(leave blank to keep)' : ''}
                    onChange={e => setEditing({ ...editing, form: { ...editing.form, secret: e.target.value || null } })}
                  />
                </div>
              </>
            )}
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
