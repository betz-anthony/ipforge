import { useState } from 'react'
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query'
import { Plus, Check, X, Trash2 } from 'lucide-react'
import { useAuth } from '../contexts/AuthContext'
import { useToast } from '../contexts/ToastContext'
import {
  ipRequestsApi, type IPRequest, type IPRequestIn, type ApproveIn, type EligibleSubnet,
} from '../api/client'

export default function Requests() {
  const { user } = useAuth()
  const isRequester = user?.role === 'requester'
  const isOperator = user?.role === 'operator' || user?.role === 'admin'

  const qc = useQueryClient()
  const { showToast } = useToast()
  const [statusFilter, setStatusFilter] = useState<string>(isOperator ? 'pending' : '')

  const { data: requests = [] } = useQuery({
    queryKey: ['ip-requests', statusFilter],
    queryFn: () => ipRequestsApi.list(statusFilter || undefined),
  })

  const [submitOpen, setSubmitOpen] = useState(false)
  const [approveTarget, setApproveTarget] = useState<IPRequest | null>(null)
  const [denyTarget, setDenyTarget] = useState<IPRequest | null>(null)

  const del = useMutation({
    mutationFn: (id: number) => ipRequestsApi.delete(id),
    onSuccess: () => { qc.invalidateQueries({ queryKey: ['ip-requests'] }); showToast('Request deleted', 'success') },
    onError: () => showToast('Delete failed', 'error'),
  })

  return (
    <div>
      <div className="page-header">
        <h1>IP Requests</h1>
        {!isOperator && (
          <button className="btn-primary btn-sm" onClick={() => setSubmitOpen(true)}>
            <Plus size={13} /> Request IP
          </button>
        )}
      </div>

      <div style={{ marginBottom: '0.75rem' }}>
        <select value={statusFilter} onChange={e => setStatusFilter(e.target.value)}>
          <option value="">All statuses</option>
          <option value="pending">Pending</option>
          <option value="approved">Approved</option>
          <option value="denied">Denied</option>
        </select>
      </div>

      <div className="table-wrap">
        <table>
          <thead>
            <tr>
              <th>Requester</th><th>Subnet</th><th>Hostname</th><th>MAC</th>
              <th>Purpose</th><th>Status</th><th>Allocated</th><th>Submitted</th><th></th>
            </tr>
          </thead>
          <tbody>
            {requests.length === 0 && (
              <tr><td colSpan={9} className="empty-state">No requests.</td></tr>
            )}
            {requests.map(r => (
              <tr key={r.id}>
                <td>{r.requester_username}</td>
                <td><span className="font-mono">{r.subnet_cidr ?? '—'}</span></td>
                <td>{r.hostname}</td>
                <td><span className="font-mono">{r.mac_address ?? '—'}</span></td>
                <td title={r.purpose}>{r.purpose.slice(0, 60)}{r.purpose.length > 60 ? '…' : ''}</td>
                <td>
                  <span className={
                    r.status === 'pending'  ? 'badge badge-yellow' :
                    r.status === 'approved' ? 'badge badge-green'  : 'badge badge-red'
                  }>{r.status}</span>
                </td>
                <td><span className="font-mono">{r.allocated_ip ?? '—'}</span></td>
                <td>{r.created_at.slice(0, 16).replace('T', ' ')}</td>
                <td onClick={e => e.stopPropagation()} style={{ display: 'flex', gap: '0.3rem' }}>
                  {isOperator && r.status === 'pending' && (
                    <>
                      <button className="btn-ghost btn-sm" onClick={() => setApproveTarget(r)}><Check size={13} /> Approve</button>
                      <button className="btn-ghost btn-sm" onClick={() => setDenyTarget(r)}><X size={13} /> Deny</button>
                    </>
                  )}
                  {isRequester && r.status === 'pending' && r.requester_username === user?.username && (
                    <button className="btn-ghost btn-sm" onClick={() => del.mutate(r.id)}><Trash2 size={13} /> Cancel</button>
                  )}
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>

      {submitOpen && (
        <SubmitForm
          onClose={() => setSubmitOpen(false)}
          onSaved={() => { qc.invalidateQueries({ queryKey: ['ip-requests'] }); showToast('Request submitted', 'success') }}
        />
      )}
      {approveTarget && (
        <ApproveForm
          request={approveTarget}
          onClose={() => setApproveTarget(null)}
          onSaved={() => { qc.invalidateQueries({ queryKey: ['ip-requests'] }); showToast('Approved + allocated', 'success') }}
        />
      )}
      {denyTarget && (
        <DenyForm
          request={denyTarget}
          onClose={() => setDenyTarget(null)}
          onSaved={() => { qc.invalidateQueries({ queryKey: ['ip-requests'] }); showToast('Denied', 'success') }}
        />
      )}
    </div>
  )
}

function SubmitForm({ onClose, onSaved }: { onClose: () => void; onSaved: () => void }) {
  const { data: subnets = [] } = useQuery({ queryKey: ['eligible-subnets'], queryFn: ipRequestsApi.eligibleSubnets })
  const [form, setForm] = useState<IPRequestIn>({ subnet_id: 0, hostname: '', mac_address: '', purpose: '' })
  const [error, setError] = useState('')
  const save = useMutation({
    mutationFn: () => ipRequestsApi.submit({ ...form, mac_address: form.mac_address || null }),
    onSuccess: () => { onSaved(); onClose() },
    onError: (e: unknown) => {
      const detail = (e as { response?: { data?: { detail?: string } } })?.response?.data?.detail
      setError(detail ?? 'Submit failed')
    },
  })
  return (
    <div className="inline-form" style={{ marginTop: '0.75rem' }}>
      <div className="form-grid">
        <div className="form-field">
          <label>Subnet</label>
          <select value={form.subnet_id} onChange={e => setForm({ ...form, subnet_id: +e.target.value })}>
            <option value={0}>— select —</option>
            {subnets.map((s: EligibleSubnet) => (
              <option key={s.id} value={s.id}>{s.cidr}{s.name ? ` (${s.name})` : ''}</option>
            ))}
          </select>
        </div>
        <div className="form-field">
          <label>Hostname</label>
          <input value={form.hostname} onChange={e => setForm({ ...form, hostname: e.target.value })} />
        </div>
        <div className="form-field">
          <label>MAC (optional)</label>
          <input value={form.mac_address ?? ''} onChange={e => setForm({ ...form, mac_address: e.target.value })} />
        </div>
        <div className="form-field" style={{ gridColumn: 'span 2' }}>
          <label>Purpose</label>
          <textarea value={form.purpose} onChange={e => setForm({ ...form, purpose: e.target.value })} rows={3} />
        </div>
      </div>
      <div className="form-actions">
        <button className="btn-primary btn-sm" disabled={!form.subnet_id || !form.hostname || form.purpose.length < 5 || save.isPending} onClick={() => save.mutate()}>
          <Check size={13} /> Submit
        </button>
        <button className="btn-ghost btn-sm" onClick={onClose}><X size={13} /> Cancel</button>
        {error && <span className="feedback-error">{error}</span>}
      </div>
    </div>
  )
}

function ApproveForm({ request, onClose, onSaved }: { request: IPRequest; onClose: () => void; onSaved: () => void }) {
  const [body, setBody] = useState<ApproveIn>({
    description: '', register_dns: false, register_dhcp: false, register_ptr: false,
  })
  const [error, setError] = useState('')
  const save = useMutation({
    mutationFn: () => ipRequestsApi.approve(request.id, body),
    onSuccess: () => { onSaved(); onClose() },
    onError: (e: unknown) => {
      const detail = (e as { response?: { data?: { detail?: string } } })?.response?.data?.detail
      setError(detail ?? 'Approval failed')
    },
  })
  return (
    <div className="inline-form" style={{ marginTop: '0.75rem' }}>
      <div style={{ marginBottom: '0.5rem', color: 'var(--text-muted)' }}>
        Approving request from <strong>{request.requester_username}</strong> for <strong>{request.hostname}</strong> in {request.subnet_cidr}
      </div>
      <div className="form-grid">
        <div className="form-field" style={{ gridColumn: 'span 2' }}>
          <label>Description (optional)</label>
          <input value={body.description ?? ''} onChange={e => setBody({ ...body, description: e.target.value })} />
        </div>
        <div className="form-field">
          <label><input type="checkbox" checked={body.register_dns} onChange={e => setBody({ ...body, register_dns: e.target.checked })} /> Register DNS</label>
        </div>
        {body.register_dns && (
          <>
            <div className="form-field">
              <label>DNS Zone</label>
              <input value={body.dns_zone ?? ''} onChange={e => setBody({ ...body, dns_zone: e.target.value })} />
            </div>
            <div className="form-field">
              <label>DNS Provider</label>
              <input value={body.dns_provider ?? ''} onChange={e => setBody({ ...body, dns_provider: e.target.value })} placeholder="leave blank for subnet default" />
            </div>
            <div className="form-field">
              <label><input type="checkbox" checked={body.register_ptr} onChange={e => setBody({ ...body, register_ptr: e.target.checked })} /> Register PTR</label>
            </div>
          </>
        )}
        <div className="form-field">
          <label><input type="checkbox" checked={body.register_dhcp} onChange={e => setBody({ ...body, register_dhcp: e.target.checked })} /> Register DHCP</label>
        </div>
        {body.register_dhcp && (
          <div className="form-field">
            <label>DHCP Provider</label>
            <input value={body.dhcp_provider ?? ''} onChange={e => setBody({ ...body, dhcp_provider: e.target.value })} placeholder="leave blank for subnet default" />
          </div>
        )}
      </div>
      <div className="form-actions">
        <button className="btn-primary btn-sm" onClick={() => save.mutate()} disabled={save.isPending}>
          <Check size={13} /> Approve + Allocate
        </button>
        <button className="btn-ghost btn-sm" onClick={onClose}><X size={13} /> Cancel</button>
        {error && <span className="feedback-error">{error}</span>}
      </div>
    </div>
  )
}

function DenyForm({ request, onClose, onSaved }: { request: IPRequest; onClose: () => void; onSaved: () => void }) {
  const [notes, setNotes] = useState('')
  const [error, setError] = useState('')
  const save = useMutation({
    mutationFn: () => ipRequestsApi.deny(request.id, notes),
    onSuccess: () => { onSaved(); onClose() },
    onError: (e: unknown) => {
      const detail = (e as { response?: { data?: { detail?: string } } })?.response?.data?.detail
      setError(detail ?? 'Deny failed')
    },
  })
  return (
    <div className="inline-form" style={{ marginTop: '0.75rem' }}>
      <div style={{ marginBottom: '0.5rem', color: 'var(--text-muted)' }}>
        Denying request from <strong>{request.requester_username}</strong> for <strong>{request.hostname}</strong>
      </div>
      <div className="form-grid">
        <div className="form-field" style={{ gridColumn: 'span 2' }}>
          <label>Reason / Notes</label>
          <textarea value={notes} onChange={e => setNotes(e.target.value)} rows={3} />
        </div>
      </div>
      <div className="form-actions">
        <button className="btn-primary btn-sm" onClick={() => save.mutate()} disabled={!notes || save.isPending}>
          <X size={13} /> Deny
        </button>
        <button className="btn-ghost btn-sm" onClick={onClose}><X size={13} /> Cancel</button>
        {error && <span className="feedback-error">{error}</span>}
      </div>
    </div>
  )
}
