import { useState } from 'react'
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query'
import { Plus, Trash2, X, Copy } from 'lucide-react'
import { tokensApi, type ApiTokenCreated } from '../api/client'
import ConfirmModal from '../components/ConfirmModal'
import { useToast } from '../contexts/ToastContext'

export default function ApiTokens() {
  const qc = useQueryClient()
  const { showToast } = useToast()
  const [showForm, setShowForm]     = useState(false)
  const [name, setName]             = useState('')
  const [readOnly, setReadOnly]     = useState(false)
  const [expiresAt, setExpiresAt]   = useState('')
  const [created, setCreated]       = useState<ApiTokenCreated | null>(null)
  const [confirmId, setConfirmId]   = useState<number | null>(null)

  const { data: tokens, isLoading } = useQuery({
    queryKey: ['api-tokens'],
    queryFn: tokensApi.list,
  })

  const createMutation = useMutation({
    mutationFn: () => tokensApi.create({
      name,
      read_only: readOnly,
      expires_at: expiresAt || null,
    }),
    onSuccess: (token) => {
      qc.invalidateQueries({ queryKey: ['api-tokens'] })
      setCreated(token)
      setShowForm(false)
      setName(''); setReadOnly(false); setExpiresAt('')
    },
  })

  const deleteMutation = useMutation({
    mutationFn: (id: number) => tokensApi.remove(id),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ['api-tokens'] })
      setConfirmId(null)
      showToast('Token revoked', 'success')
    },
  })

  return (
    <div>
      <div className="page-header">
        <h1>API Tokens</h1>
        {!showForm && (
          <button className="btn-primary btn-sm" onClick={() => setShowForm(true)}>
            <Plus size={13} /> Create Token
          </button>
        )}
      </div>

      {showForm && (
        <div className="inline-form">
          <div className="form-grid">
            <div className="form-field">
              <label htmlFor="token-name">Name</label>
              <input
                id="token-name"
                placeholder="ci-pipeline"
                value={name}
                onChange={e => setName(e.target.value)}
              />
            </div>
            <div className="form-field">
              <label htmlFor="token-expiry">Expires (optional)</label>
              <input
                id="token-expiry"
                type="date"
                value={expiresAt}
                onChange={e => setExpiresAt(e.target.value)}
              />
            </div>
          </div>
          <div className="form-field form-field-wide">
            <label className="checkbox-label">
              <input
                type="checkbox"
                checked={readOnly}
                onChange={e => setReadOnly(e.target.checked)}
              />
              <span>Read-only (the token may only make GET requests)</span>
            </label>
          </div>
          <div className="form-actions">
            <button
              className="btn-primary btn-sm"
              onClick={() => createMutation.mutate()}
              disabled={createMutation.isPending || !name.trim()}
            >
              {createMutation.isPending ? 'Creating…' : 'Create'}
            </button>
            <button
              className="btn-ghost btn-sm"
              onClick={() => { setShowForm(false); setName(''); setReadOnly(false); setExpiresAt('') }}
            >
              <X size={13} /> Cancel
            </button>
          </div>
        </div>
      )}

      <div className="table-wrap">
        <table>
          <thead>
            <tr>
              <th scope="col">Name</th>
              <th scope="col">Token</th>
              <th scope="col">Mode</th>
              <th scope="col">Expires</th>
              <th scope="col">Last used</th>
              <th scope="col" style={{ width: '2.5rem' }}></th>
            </tr>
          </thead>
          <tbody>
            {isLoading && (
              <tr><td colSpan={6} className="empty-state">Loading…</td></tr>
            )}
            {!isLoading && (tokens ?? []).length === 0 && (
              <tr><td colSpan={6} className="empty-state">No API tokens.</td></tr>
            )}
            {(tokens ?? []).map(t => (
              <tr key={t.id}>
                <td>{t.name}</td>
                <td><span className="font-mono">{t.token_prefix}…</span></td>
                <td>{t.read_only ? 'Read-only' : 'Full'}</td>
                <td><span className="text-muted">{t.expires_at?.slice(0, 10) ?? 'Never'}</span></td>
                <td><span className="text-muted">{t.last_used_at?.slice(0, 10) ?? '—'}</span></td>
                <td>
                  <button
                    className="btn-danger btn-sm"
                    aria-label={`Revoke token ${t.name}`}
                    onClick={() => setConfirmId(t.id)}
                    disabled={deleteMutation.isPending}
                  >
                    <Trash2 size={12} />
                  </button>
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>

      {created && (
        <ConfirmModal
          title="Token created"
          message="Copy this token now — it will not be shown again."
          confirmLabel="Done"
          danger={false}
          onConfirm={() => setCreated(null)}
          onCancel={() => setCreated(null)}
          extra={
            <div style={{ display: 'flex', alignItems: 'center', gap: '0.5rem' }}>
              <span className="font-mono" style={{ wordBreak: 'break-all', flex: 1 }}>
                {created.token}
              </span>
              <button
                className="btn-ghost btn-sm"
                aria-label="Copy token"
                onClick={() => {
                  navigator.clipboard.writeText(created.token)
                  showToast('Token copied', 'success')
                }}
              >
                <Copy size={13} />
              </button>
            </div>
          }
        />
      )}

      {confirmId !== null && (
        <ConfirmModal
          title="Revoke token"
          message="Revoke this API token? Any client using it will stop working immediately."
          onConfirm={() => deleteMutation.mutate(confirmId)}
          onCancel={() => setConfirmId(null)}
        />
      )}
    </div>
  )
}
