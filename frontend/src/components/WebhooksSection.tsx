import { useState, useId, isValidElement, cloneElement } from 'react'
import type React from 'react'
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { Plus, Pencil, Trash2, Send, ScrollText, Check, X, RefreshCw } from 'lucide-react'
import { webhooksApi, type WebhookEndpoint, type WebhookEndpointIn, type WebhookDelivery } from '../api/client'
import { useToast } from '../contexts/ToastContext'
import Collapsible from './Collapsible'
import ModalDialog from './ModalDialog'
import ConfirmModal from './ConfirmModal'

const DELIVERY_STATUS_BADGE: Record<string, string> = { delivered: 'badge-green', pending: 'badge-yellow', delivering: 'badge-yellow', dead: 'badge-red' }

function parseHeaders(text: string): Record<string, string> {
  const out: Record<string, string> = {}
  for (const line of text.split('\n')) {
    const t = line.trim()
    if (!t) continue
    const idx = t.indexOf(':')
    if (idx === -1) continue
    const key = t.slice(0, idx).trim()
    const value = t.slice(idx + 1).trim()
    if (key) out[key] = value
  }
  return out
}

function headersToText(headers: Record<string, string> | undefined): string {
  return Object.entries(headers ?? {}).map(([k, v]) => `${k}: ${v}`).join('\n')
}

function csvToList(s: string): string[] {
  return s.split(',').map(x => x.trim()).filter(Boolean)
}

// Local field wrapper — mirrors the Field helper in Settings.tsx (not exported
// from there, so re-declared here for this standalone component).
function Field({ label, hint, wide, children }: { label: string; hint?: string; wide?: boolean; children: React.ReactNode }) {
  const fieldId = useId()
  const control = isValidElement(children) && !(children.props as { id?: string }).id
    ? cloneElement(children as React.ReactElement<{ id?: string }>, { id: fieldId })
    : children
  return (
    <div className={wide ? 'form-field form-field-wide' : 'form-field'}>
      <label htmlFor={fieldId}>
        {label}
        {hint && <span style={{ color: 'var(--text-muted)', marginLeft: '0.375rem', fontSize: '0.7rem', fontWeight: 400 }}>{hint}</span>}
      </label>
      {control}
    </div>
  )
}

export default function WebhooksSection() {
  const qc = useQueryClient()
  const { showToast } = useToast()
  const { data: endpoints = [] } = useQuery({ queryKey: ['webhooks'], queryFn: webhooksApi.list })

  const [editing, setEditing] = useState<WebhookEndpoint | 'new' | null>(null)
  const [logFor, setLogFor] = useState<WebhookEndpoint | null>(null)
  const [confirmDelete, setConfirmDelete] = useState<WebhookEndpoint | null>(null)

  const invalidate = () => qc.invalidateQueries({ queryKey: ['webhooks'] })

  const saveMut = useMutation({
    mutationFn: (v: { id: number | null; body: WebhookEndpointIn }) =>
      v.id === null ? webhooksApi.create(v.body) : webhooksApi.update(v.id, v.body),
    onSuccess: () => { invalidate(); setEditing(null); showToast('Webhook saved', 'success') },
    onError: (e: any) => showToast(e?.response?.data?.detail ?? 'Save failed', 'error'),
  })
  const deleteMut = useMutation({
    mutationFn: (id: number) => webhooksApi.remove(id),
    onSuccess: () => { invalidate(); setConfirmDelete(null); showToast('Webhook deleted', 'success') },
    onError: (e: any) => { showToast(e?.response?.data?.detail ?? 'Delete failed', 'error'); setConfirmDelete(null) },
  })
  const testMut = useMutation({
    mutationFn: (id: number) => webhooksApi.test(id),
    onSuccess: (r) => {
      invalidate()
      showToast(
        r.status === 'sent' ? `Test delivered (HTTP ${r.response_status})` : `Test failed: ${r.error}`,
        r.status === 'sent' ? 'success' : 'error',
      )
    },
    onError: (e: any) => showToast(e?.response?.data?.detail ?? 'Test failed', 'error'),
  })
  const toggleMut = useMutation({
    mutationFn: (ep: WebhookEndpoint) => webhooksApi.update(ep.id, {
      name: ep.name,
      url: ep.url,
      enabled: !ep.enabled,
      custom_headers: ep.custom_headers,
      resource_types: ep.resource_types,
      actions: ep.actions,
    }),
    onSuccess: () => invalidate(),
    onError: (e: any) => showToast(e?.response?.data?.detail ?? 'Update failed', 'error'),
  })

  return (
    <Collapsible
      title="Webhooks"
      storageKey="webhooks"
      headerExtra={editing === null && (
        <button className="btn-ghost btn-sm" onClick={() => setEditing('new')}>
          <Plus size={13} /> Add
        </button>
      )}
    >
      <div className="table-wrap">
        <table>
          <thead>
            <tr>
              <th scope="col">Name</th>
              <th scope="col">URL</th>
              <th scope="col">Filters</th>
              <th scope="col">Enabled</th>
              <th scope="col">Last Status</th>
              <th scope="col">Dead</th>
              <th scope="col"></th>
            </tr>
          </thead>
          <tbody>
            {endpoints.length === 0 && (
              <tr><td colSpan={7} className="empty-state">No webhook endpoints configured.</td></tr>
            )}
            {endpoints.map(ep => (
              <tr key={ep.id}>
                <td>{ep.name}</td>
                <td><span className="font-mono" style={{ fontSize: '0.78rem' }}>{ep.url}</span></td>
                <td style={{ fontSize: '0.78rem', color: 'var(--text-muted)' }}>
                  {ep.resource_types.length ? ep.resource_types.join(', ') : 'all resources'}
                  {' / '}
                  {ep.actions.length ? ep.actions.join(', ') : 'all actions'}
                </td>
                <td>
                  <button
                    className="btn-ghost btn-sm"
                    onClick={() => toggleMut.mutate(ep)}
                    title={ep.enabled ? 'Disable' : 'Enable'}
                  >
                    {ep.enabled ? 'Enabled' : 'Disabled'}
                  </button>
                </td>
                <td>
                  <span className={`badge ${ep.last_status ? (DELIVERY_STATUS_BADGE[ep.last_status] ?? 'badge-gray') : 'badge-gray'}`}>
                    {ep.last_status ?? 'never'}
                  </span>
                </td>
                <td>
                  {ep.dead_count > 0
                    ? <span className="badge badge-red">{ep.dead_count}</span>
                    : <span className="text-muted">0</span>}
                </td>
                <td>
                  <div style={{ display: 'flex', gap: '0.3rem' }}>
                    <button className="btn-ghost btn-sm" title="Send test event" onClick={() => testMut.mutate(ep.id)} disabled={testMut.isPending}>
                      <Send size={12} />
                    </button>
                    <button className="btn-ghost btn-sm" title="Delivery log" onClick={() => setLogFor(ep)}>
                      <ScrollText size={12} />
                    </button>
                    <button className="btn-ghost btn-sm" title="Edit" onClick={() => setEditing(ep)}>
                      <Pencil size={12} />
                    </button>
                    <button className="btn-danger btn-sm" title="Delete" onClick={() => setConfirmDelete(ep)}>
                      <Trash2 size={12} />
                    </button>
                  </div>
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>

      {editing !== null && (
        <WebhookEditorModal
          endpoint={editing === 'new' ? null : editing}
          pending={saveMut.isPending}
          onCancel={() => setEditing(null)}
          onSave={body => saveMut.mutate({ id: editing === 'new' ? null : editing.id, body })}
        />
      )}

      {logFor && (
        <DeliveryLogModal endpoint={logFor} onClose={() => setLogFor(null)} />
      )}

      {confirmDelete && (
        <ConfirmModal
          title="Delete Webhook"
          message={`Delete webhook "${confirmDelete.name}"? Pending deliveries will be discarded.`}
          onConfirm={() => deleteMut.mutate(confirmDelete.id)}
          onCancel={() => setConfirmDelete(null)}
        />
      )}
    </Collapsible>
  )
}

// ── Create/edit modal ───────────────────────────────────────────────────────

function WebhookEditorModal({
  endpoint, pending, onCancel, onSave,
}: {
  endpoint: WebhookEndpoint | null
  pending: boolean
  onCancel: () => void
  onSave: (body: WebhookEndpointIn) => void
}) {
  const [name, setName] = useState(endpoint?.name ?? '')
  const [url, setUrl] = useState(endpoint?.url ?? '')
  const [enabled, setEnabled] = useState(endpoint?.enabled ?? true)
  const [secretInput, setSecretInput] = useState('')
  const [clearSecret, setClearSecret] = useState(false)
  const [headersText, setHeadersText] = useState(headersToText(endpoint?.custom_headers))
  const [resourceTypesText, setResourceTypesText] = useState((endpoint?.resource_types ?? []).join(', '))
  const [actionsText, setActionsText] = useState((endpoint?.actions ?? []).join(', '))

  const canSave = name.trim().length > 0 && url.trim().length > 0

  function submit(e: React.FormEvent) {
    e.preventDefault()
    if (!canSave) return
    const body: WebhookEndpointIn = {
      name: name.trim(),
      url: url.trim(),
      enabled,
      custom_headers: parseHeaders(headersText),
      resource_types: csvToList(resourceTypesText),
      actions: csvToList(actionsText),
      // undefined → key omitted → backend leaves secret unchanged
      // clearSecret checked → "" → backend clears
      // non-empty input → set new secret
      secret: clearSecret ? '' : (secretInput ? secretInput : undefined),
    }
    onSave(body)
  }

  return (
    <ModalDialog title={endpoint ? `Edit Webhook — ${endpoint.name}` : 'Add Webhook'} onClose={onCancel}>
      <form onSubmit={submit}>
        <div className="form-grid">
          <Field label="Name">
            <input value={name} onChange={e => setName(e.target.value)} placeholder="slack-notify" />
          </Field>
          <Field label="URL" wide>
            <input value={url} onChange={e => setUrl(e.target.value)} placeholder="https://example.com/hook" />
          </Field>
          <Field label="Secret" hint={endpoint?.has_secret ? 'leave blank to keep current' : 'optional — used for HMAC request signing'}>
            <input
              type="password"
              value={secretInput}
              onChange={e => setSecretInput(e.target.value)}
              placeholder={endpoint?.has_secret ? 'Leave blank to keep current' : ''}
              disabled={clearSecret}
            />
          </Field>
          {endpoint?.has_secret && (
            <div className="form-field">
              <label className="checkbox-label">
                <input
                  type="checkbox"
                  checked={clearSecret}
                  onChange={e => { setClearSecret(e.target.checked); if (e.target.checked) setSecretInput('') }}
                />
                <span>Clear secret (disables HMAC signing)</span>
              </label>
            </div>
          )}
          <div className="form-field form-field-wide">
            <label htmlFor="webhook-headers">
              Custom headers
              <span style={{ color: 'var(--text-muted)', marginLeft: '0.375rem', fontSize: '0.7rem', fontWeight: 400 }}>
                one "Name: value" per line
              </span>
            </label>
            <textarea
              id="webhook-headers"
              rows={3}
              value={headersText}
              onChange={e => setHeadersText(e.target.value)}
              placeholder="X-Custom-Header: value"
            />
          </div>
          <Field label="Resource types" hint="comma-separated, empty = all">
            <input value={resourceTypesText} onChange={e => setResourceTypesText(e.target.value)} placeholder="address, subnet" />
          </Field>
          <Field label="Actions" hint="comma-separated, empty = all">
            <input value={actionsText} onChange={e => setActionsText(e.target.value)} placeholder="create, update, delete" />
          </Field>
          <div className="form-field">
            <label className="checkbox-label">
              <input type="checkbox" checked={enabled} onChange={e => setEnabled(e.target.checked)} />
              <span>Enabled</span>
            </label>
          </div>
        </div>
        <div className="form-actions">
          <button type="submit" className="btn-primary btn-sm" disabled={!canSave || pending}>
            <Check size={13} /> {pending ? 'Saving…' : 'Save'}
          </button>
          <button type="button" className="btn-ghost btn-sm" onClick={onCancel}>
            <X size={13} /> Cancel
          </button>
        </div>
      </form>
    </ModalDialog>
  )
}

// ── Delivery log modal ───────────────────────────────────────────────────────

function DeliveryLogModal({ endpoint, onClose }: { endpoint: WebhookEndpoint; onClose: () => void }) {
  const qc = useQueryClient()
  const { showToast } = useToast()
  const [status, setStatus] = useState('')

  const { data, isLoading } = useQuery({
    queryKey: ['webhook-deliveries', endpoint.id, status],
    queryFn: () => webhooksApi.deliveries(endpoint.id, { ...(status ? { status } : {}), limit: 100 }),
  })

  const invalidate = () => {
    qc.invalidateQueries({ queryKey: ['webhook-deliveries', endpoint.id] })
    qc.invalidateQueries({ queryKey: ['webhooks'] })
  }

  const redeliverMut = useMutation({
    mutationFn: (id: number) => webhooksApi.redeliver(id),
    onSuccess: () => { invalidate(); showToast('Redelivery queued', 'success') },
    onError: (e: any) => showToast(e?.response?.data?.detail ?? 'Redeliver failed', 'error'),
  })
  const deleteMut = useMutation({
    mutationFn: (id: number) => webhooksApi.removeDelivery(id),
    onSuccess: () => { invalidate(); showToast('Delivery removed', 'success') },
    onError: (e: any) => showToast(e?.response?.data?.detail ?? 'Delete failed', 'error'),
  })

  const items: WebhookDelivery[] = data?.items ?? []

  return (
    <ModalDialog title={`Delivery Log — ${endpoint.name}`} onClose={onClose}>
      <div className="form-field" style={{ marginBottom: '0.75rem', maxWidth: '220px' }}>
        <label htmlFor="webhook-log-status">Status</label>
        <select id="webhook-log-status" value={status} onChange={e => setStatus(e.target.value)}>
          <option value="">All</option>
          <option value="pending">Pending</option>
          <option value="delivered">Delivered</option>
          <option value="dead">Dead</option>
        </select>
      </div>
      <div className="table-wrap">
        <table>
          <thead>
            <tr>
              <th scope="col">Event</th>
              <th scope="col">Status</th>
              <th scope="col">Attempts</th>
              <th scope="col">Response</th>
              <th scope="col">Last Error</th>
              <th scope="col">Created</th>
              <th scope="col"></th>
            </tr>
          </thead>
          <tbody>
            {!isLoading && items.length === 0 && (
              <tr><td colSpan={7} className="empty-state">No deliveries.</td></tr>
            )}
            {items.map(d => (
              <tr key={d.id}>
                <td><span className="font-mono">{d.event_type}</span></td>
                <td>
                  <span className={`badge ${DELIVERY_STATUS_BADGE[d.status] ?? 'badge-gray'}`}>{d.status}</span>
                </td>
                <td>{d.attempts}</td>
                <td>{d.response_status ?? <span className="text-muted">—</span>}</td>
                <td
                  style={{ maxWidth: '220px', overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap' }}
                  title={d.last_error ?? undefined}
                >
                  {d.last_error ?? <span className="text-muted">—</span>}
                </td>
                <td>{new Date(d.created_at).toLocaleString()}</td>
                <td>
                  <div style={{ display: 'flex', gap: '0.3rem' }}>
                    {(d.status === 'dead' || d.status === 'pending') && (
                      <button
                        className="btn-ghost btn-sm"
                        title="Redeliver"
                        onClick={() => redeliverMut.mutate(d.id)}
                        disabled={redeliverMut.isPending}
                      >
                        <RefreshCw size={12} />
                      </button>
                    )}
                    <button
                      className="btn-danger btn-sm"
                      title="Delete"
                      onClick={() => deleteMut.mutate(d.id)}
                      disabled={deleteMut.isPending}
                    >
                      <Trash2 size={12} />
                    </button>
                  </div>
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
      <div className="modal-actions">
        <button className="btn btn-ghost" onClick={onClose}>Close</button>
      </div>
    </ModalDialog>
  )
}
