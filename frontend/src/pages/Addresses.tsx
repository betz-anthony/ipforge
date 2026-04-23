import { useState } from 'react'
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query'
import { Plus, X } from 'lucide-react'
import { addressesApi, subnetsApi, type IPAddress } from '../api/client'

const STATUS_BADGE: Record<string, string> = {
  available:  'badge-green',
  assigned:   'badge-blue',
  reserved:   'badge-yellow',
  deprecated: 'badge-gray',
}

const STATUSES = ['available', 'assigned', 'reserved', 'deprecated'] as const

const emptyForm = {
  address: '', subnet_id: '', hostname: '', status: 'assigned' as string,
  mac_address: '', description: '',
}

export default function Addresses() {
  const [showForm, setShowForm]     = useState(false)
  const [form, setForm]             = useState(emptyForm)
  const [filterStatus, setFilter]   = useState('')
  const qc = useQueryClient()

  const { data, isLoading, error } = useQuery({
    queryKey: ['addresses'],
    queryFn: () => addressesApi.list(),
  })

  const { data: subnets } = useQuery({
    queryKey: ['subnets'],
    queryFn: subnetsApi.list,
  })

  const createMutation = useMutation({
    mutationFn: () => addressesApi.create({
      address:     form.address,
      subnet_id:   Number(form.subnet_id),
      hostname:    form.hostname || null,
      status:      form.status as IPAddress['status'],
      mac_address: form.mac_address || null,
      description: form.description || null,
    }),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ['addresses'] })
      setForm(emptyForm)
      setShowForm(false)
    },
  })

  const deleteMutation = useMutation({
    mutationFn: (id: number) => addressesApi.delete(id),
    onSuccess: () => qc.invalidateQueries({ queryKey: ['addresses'] }),
  })

  const set = (key: keyof typeof emptyForm) =>
    (e: React.ChangeEvent<HTMLInputElement | HTMLSelectElement>) =>
      setForm(f => ({ ...f, [key]: e.target.value }))

  const filtered = filterStatus
    ? (data ?? []).filter(a => a.status === filterStatus)
    : (data ?? [])

  return (
    <div>
      <div className="page-header">
        <h1>IP Addresses</h1>
        <div className="page-header-actions">
          <select
            value={filterStatus}
            onChange={e => setFilter(e.target.value)}
            style={{ fontSize: '0.8rem' }}
          >
            <option value="">All statuses</option>
            {STATUSES.map(s => <option key={s} value={s}>{s}</option>)}
          </select>
          {!showForm && (
            <button className="btn-primary btn-sm" onClick={() => setShowForm(true)}>
              <Plus size={13} /> Add Address
            </button>
          )}
        </div>
      </div>

      {showForm && (
        <div className="inline-form">
          <div className="form-grid">
            <div className="form-field">
              <label>IP Address</label>
              <input placeholder="10.0.1.50" value={form.address} onChange={set('address')} autoFocus />
            </div>
            <div className="form-field">
              <label>Subnet</label>
              <select value={form.subnet_id} onChange={set('subnet_id')}>
                <option value="">— select —</option>
                {(subnets ?? []).map(s => (
                  <option key={s.id} value={s.id}>{s.name} ({s.cidr})</option>
                ))}
              </select>
            </div>
            <div className="form-field">
              <label>Status</label>
              <select value={form.status} onChange={set('status')}>
                {STATUSES.map(s => <option key={s} value={s}>{s}</option>)}
              </select>
            </div>
            <div className="form-field">
              <label>Hostname</label>
              <input placeholder="Optional" value={form.hostname} onChange={set('hostname')} />
            </div>
            <div className="form-field">
              <label>MAC Address</label>
              <input placeholder="Optional" value={form.mac_address} onChange={set('mac_address')} />
            </div>
            <div className="form-field">
              <label>Description</label>
              <input placeholder="Optional" value={form.description} onChange={set('description')} />
            </div>
          </div>
          <div className="form-actions">
            <button
              className="btn-primary btn-sm"
              onClick={() => createMutation.mutate()}
              disabled={createMutation.isPending || !form.address || !form.subnet_id}
            >
              {createMutation.isPending ? 'Adding…' : 'Add'}
            </button>
            <button className="btn-ghost btn-sm" onClick={() => { setShowForm(false); setForm(emptyForm) }}>
              <X size={13} /> Cancel
            </button>
            {createMutation.isError && (
              <span className="feedback-error">
                {String((createMutation.error as Error).message)}
              </span>
            )}
          </div>
        </div>
      )}

      {isLoading && <p className="loading">Loading…</p>}
      {error    && <p className="feedback-error">Failed to load addresses.</p>}

      {data && (
        <div className="table-wrap">
          <table>
            <thead>
              <tr>
                <th>Address</th>
                <th>Hostname</th>
                <th>Status</th>
                <th>MAC</th>
                <th>Description</th>
                <th style={{ width: '2.5rem' }}></th>
              </tr>
            </thead>
            <tbody>
              {filtered.length === 0 && (
                <tr><td colSpan={6} className="empty-state">
                  {data.length === 0 ? 'No addresses tracked. Add one above.' : 'No addresses match filter.'}
                </td></tr>
              )}
              {filtered.map((a: IPAddress) => (
                <tr key={a.id}>
                  <td><span className="font-mono">{a.address}</span></td>
                  <td>{a.hostname ?? <span className="text-muted">—</span>}</td>
                  <td>
                    <span className={`badge ${STATUS_BADGE[a.status] ?? 'badge-gray'}`}>
                      {a.status}
                    </span>
                  </td>
                  <td><span className="font-mono">{a.mac_address ?? <span className="text-muted">—</span>}</span></td>
                  <td>{a.description ?? <span className="text-muted">—</span>}</td>
                  <td>
                    <button
                      className="btn-danger btn-sm"
                      onClick={() =>
                        window.confirm(`Delete address ${a.address}?`) &&
                        deleteMutation.mutate(a.id)
                      }
                      disabled={deleteMutation.isPending}
                    >
                      <X size={12} />
                    </button>
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
