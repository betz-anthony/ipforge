import { useState } from 'react'
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query'
import { Plus, X } from 'lucide-react'
import { addressesApi, subnetsApi, dnsApi, dhcpApi, scanHistoryApi, type IPAddress } from '../api/client'
import { formatRelative } from '../utils/time'
import DetailDrawer from '../components/DetailDrawer'

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

const emptyEditForm = {
  hostname: '', status: 'assigned', mac_address: '', description: '', notes: '',
}

export default function Addresses() {
  const [showForm, setShowForm]               = useState(false)
  const [form, setForm]                       = useState(emptyForm)
  const [filterStatus, setFilter]             = useState('')
  const [filterSubnet, setFilterSubnet]       = useState<number | ''>('')
  const [selectedAddress, setSelectedAddress] = useState<IPAddress | null>(null)
  const [editForm, setEditForm]               = useState(emptyEditForm)
  const qc = useQueryClient()

  const { data: ipDnsRecords } = useQuery({
    queryKey: ['dns-by-ip', selectedAddress?.address],
    queryFn: () => dnsApi.byIp(selectedAddress!.address),
    enabled: !!selectedAddress,
    retry: false,
  })

  const { data: ipDhcpLeases } = useQuery({
    queryKey: ['dhcp-by-ip', selectedAddress?.address],
    queryFn: () => dhcpApi.byIp(selectedAddress!.address),
    enabled: !!selectedAddress,
    retry: false,
  })

  const { data: scanHistory } = useQuery({
    queryKey: ['scan-history', selectedAddress?.id],
    queryFn: () => scanHistoryApi.list(selectedAddress!.id),
    enabled: !!selectedAddress,
    retry: false,
  })

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
      notes:       null,
    }),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ['addresses'] })
      setForm(emptyForm)
      setShowForm(false)
    },
  })

  const updateMutation = useMutation({
    mutationFn: () => addressesApi.update(selectedAddress!.id, {
      hostname:    editForm.hostname    || null,
      status:      editForm.status      as IPAddress['status'],
      mac_address: editForm.mac_address || null,
      description: editForm.description || null,
      notes:       editForm.notes       || null,
    }),
    onSuccess: () => qc.invalidateQueries({ queryKey: ['addresses'] }),
  })

  const deleteMutation = useMutation({
    mutationFn: (id: number) => addressesApi.delete(id),
    onSuccess: () => qc.invalidateQueries({ queryKey: ['addresses'] }),
  })

  const set = (key: keyof typeof emptyForm) =>
    (e: React.ChangeEvent<HTMLInputElement | HTMLSelectElement>) =>
      setForm(f => ({ ...f, [key]: e.target.value }))

  const setEdit = (key: keyof typeof emptyEditForm) =>
    (e: React.ChangeEvent<HTMLInputElement | HTMLSelectElement | HTMLTextAreaElement>) =>
      setEditForm(f => ({ ...f, [key]: e.target.value }))

  const openDrawer = (a: IPAddress) => {
    setSelectedAddress(a)
    setEditForm({
      hostname:    a.hostname    ?? '',
      status:      a.status,
      mac_address: a.mac_address ?? '',
      description: a.description ?? '',
      notes:       a.notes       ?? '',
    })
  }

  const filtered = (data ?? []).filter(a =>
    (filterStatus === '' || a.status === filterStatus) &&
    (filterSubnet === '' || a.subnet_id === filterSubnet)
  )

  const SOURCE_LABEL: Record<string, string> = {
    msdhcp: 'MS DHCP', pihole: 'Pi-hole', keadhcp: 'Kea',
    msdns: 'MS DNS', bind: 'BIND',
  }

  const addressViewExtra = selectedAddress ? (
    <>
      {scanHistory && scanHistory.length > 0 && (() => {
        const last30 = scanHistory.slice(0, 30)
        const totalUp = last30.reduce((s, r) => s + r.up_count, 0)
        const totalScans = last30.reduce((s, r) => s + r.total_count, 0)
        const uptime30 = totalScans > 0 ? Math.round(totalUp / totalScans * 100) : 0
        const avgLatency = (() => {
          const rows = last30.filter(r => r.avg_latency_ms !== null && r.up_count > 0)
          if (!rows.length) return null
          return Math.round(rows.reduce((s, r) => s + r.avg_latency_ms! * r.up_count, 0) /
                            rows.reduce((s, r) => s + r.up_count, 0) * 10) / 10
        })()
        const uptimeColor = uptime30 >= 90 ? 'var(--success, #4ade80)'
          : uptime30 >= 50 ? 'var(--warning, #facc15)'
          : 'var(--danger, #f87171)'

        // Build last-7-days dot array (newest last = rightmost)
        const today = new Date()
        const days7 = Array.from({ length: 7 }, (_, i) => {
          const d = new Date(today)
          d.setDate(d.getDate() - (6 - i))
          const iso = d.toISOString().slice(0, 10)
          const DAY_LABELS = ['S','M','T','W','T','F','S']
          const label = DAY_LABELS[d.getDay()]
          const row = last30.find(r => r.date === iso)
          const color = !row ? '#555'
            : row.uptime_pct >= 90 ? 'var(--success, #4ade80)'
            : row.uptime_pct >= 50 ? 'var(--warning, #facc15)'
            : 'var(--danger, #f87171)'
          return { label, color }
        })

        return (
          <div style={{ marginTop: '1rem' }}>
            <div className="detail-section-title">Reachability</div>
            <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr 1fr', gap: '0.4rem', margin: '0.5rem 0' }}>
              <div style={{ background: 'var(--surface-2, #1e1e2e)', border: '1px solid var(--border)', borderRadius: '4px', padding: '0.4rem 0.5rem', textAlign: 'center' }}>
                <div style={{ fontSize: '0.95rem', fontWeight: 700, color: uptimeColor }}>{uptime30}%</div>
                <div style={{ fontSize: '0.6rem', color: 'var(--text-muted)', marginTop: '0.1rem' }}>30d uptime</div>
              </div>
              <div style={{ background: 'var(--surface-2, #1e1e2e)', border: '1px solid var(--border)', borderRadius: '4px', padding: '0.4rem 0.5rem', textAlign: 'center' }}>
                <div style={{ fontSize: '0.95rem', fontWeight: 700 }}>{avgLatency !== null ? `${avgLatency} ms` : '—'}</div>
                <div style={{ fontSize: '0.6rem', color: 'var(--text-muted)', marginTop: '0.1rem' }}>avg latency</div>
              </div>
              <div style={{ background: 'var(--surface-2, #1e1e2e)', border: '1px solid var(--border)', borderRadius: '4px', padding: '0.4rem 0.5rem', textAlign: 'center' }}>
                <div style={{ fontSize: '0.85rem', fontWeight: 700 }}>{formatRelative(selectedAddress.last_seen)}</div>
                <div style={{ fontSize: '0.6rem', color: 'var(--text-muted)', marginTop: '0.1rem' }}>last seen</div>
              </div>
            </div>
            <div style={{ display: 'flex', gap: '3px', marginTop: '0.4rem' }}>
              {days7.map((d, i) => (
                <div key={i} style={{ flex: 1, display: 'flex', flexDirection: 'column', alignItems: 'center', gap: '2px' }}>
                  <div style={{ width: '100%', height: '16px', borderRadius: '2px', background: d.color }} />
                  <span style={{ fontSize: '0.55rem', color: 'var(--text-muted)' }}>{d.label}</span>
                </div>
              ))}
            </div>
          </div>
        )
      })()}

      <div style={{ marginTop: '1rem' }}>
        <div className="detail-section-title">DNS Records</div>
        {!ipDnsRecords ? (
          <p className="loading">Loading…</p>
        ) : ipDnsRecords.length === 0 ? (
          <p style={{ fontSize: '0.8rem', color: 'var(--text-muted)', margin: '0.5rem 0' }}>
            No DNS records found for this IP.
          </p>
        ) : (
          <div className="detail-fields" style={{ marginTop: '0.5rem' }}>
            {ipDnsRecords.map((r, i) => (
              <div key={i} className="detail-field">
                <span className="detail-field-label">
                  <span className="badge badge-gray" style={{ fontSize: '0.6rem', marginRight: '0.3rem' }}>
                    {r.record_type}
                  </span>
                  {r.zone}
                </span>
                <span className="detail-field-value font-mono">{r.name}</span>
              </div>
            ))}
          </div>
        )}
      </div>

      <div style={{ marginTop: '1rem' }}>
        <div className="detail-section-title">DHCP</div>
        {!ipDhcpLeases ? (
          <p className="loading">Loading…</p>
        ) : ipDhcpLeases.length === 0 ? (
          <p style={{ fontSize: '0.8rem', color: 'var(--text-muted)', margin: '0.5rem 0' }}>
            No DHCP reservation found for this IP.
          </p>
        ) : (
          <div className="detail-fields" style={{ marginTop: '0.5rem' }}>
            {ipDhcpLeases.map((l, i) => (
              <div key={i} style={{ marginBottom: i < ipDhcpLeases.length - 1 ? '0.75rem' : 0 }}>
                <div className="detail-field">
                  <span className="detail-field-label">Scope</span>
                  <span className="detail-field-value font-mono">{l.scope_id}</span>
                </div>
                {l.mac_address && (
                  <div className="detail-field">
                    <span className="detail-field-label">MAC</span>
                    <span className="detail-field-value font-mono">{l.mac_address}</span>
                  </div>
                )}
                {l.client_duid && (
                  <div className="detail-field">
                    <span className="detail-field-label">DUID</span>
                    <span className="detail-field-value font-mono">{l.client_duid}</span>
                  </div>
                )}
                {l.name && (
                  <div className="detail-field">
                    <span className="detail-field-label">Name</span>
                    <span className="detail-field-value">{l.name}</span>
                  </div>
                )}
                <div className="detail-field">
                  <span className="detail-field-label">Source</span>
                  <span className="detail-field-value">
                    <span className="badge badge-gray" style={{ fontSize: '0.65rem' }}>
                      {SOURCE_LABEL[l.source ?? ''] ?? l.source ?? l.scope_id}
                    </span>
                  </span>
                </div>
              </div>
            ))}
          </div>
        )}
      </div>
    </>
  ) : null

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
          <select
            value={filterSubnet}
            onChange={e => setFilterSubnet(e.target.value === '' ? '' : Number(e.target.value))}
            style={{ fontSize: '0.8rem' }}
          >
            <option value="">All subnets</option>
            {(subnets ?? []).map(s => (
              <option key={s.id} value={s.id}>{s.name} ({s.cidr})</option>
            ))}
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
                <th>Last Seen</th>
                <th style={{ width: '2.5rem' }}></th>
              </tr>
            </thead>
            <tbody>
              {filtered.length === 0 && (
                <tr><td colSpan={7} className="empty-state">
                  {data?.length === 0 ? 'No addresses tracked. Add one above.' : 'No addresses match filters.'}
                </td></tr>
              )}
              {filtered.map((a: IPAddress) => (
                <tr key={a.id} className="clickable" onClick={() => openDrawer(a)}>
                  <td><span className="font-mono">{a.address}</span></td>
                  <td>{a.hostname ?? <span className="text-muted">—</span>}</td>
                  <td>
                    <span className={`badge ${STATUS_BADGE[a.status] ?? 'badge-gray'}`}>
                      {a.status}
                    </span>
                  </td>
                  <td><span className="font-mono">{a.mac_address ?? <span className="text-muted">—</span>}</span></td>
                  <td>{a.description ?? <span className="text-muted">—</span>}</td>
                  <td style={{ fontSize: '0.78rem', color: 'var(--text-muted)' }}>
                    {formatRelative(a.last_seen)}
                  </td>
                  <td onClick={e => e.stopPropagation()}>
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

      {selectedAddress && (
        <DetailDrawer
          title={selectedAddress.address}
          subtitle={selectedAddress.hostname ?? undefined}
          viewExtra={addressViewExtra}
          fields={[
            { label: 'Address',     value: <span className="font-mono">{selectedAddress.address}</span> },
            { label: 'Status',      value: <span className={`badge ${STATUS_BADGE[selectedAddress.status]}`}>{selectedAddress.status}</span> },
            { label: 'MAC',         value: selectedAddress.mac_address ? <span className="font-mono">{selectedAddress.mac_address}</span> : <span className="text-muted">—</span> },
            { label: 'Description', value: selectedAddress.description ?? <span className="text-muted">—</span> },
            { label: 'Notes',       value: selectedAddress.notes ?? <span className="text-muted">—</span> },
          ]}
          onSave={() => updateMutation.mutate()}
          isSaving={updateMutation.isPending}
          onClose={() => setSelectedAddress(null)}
        >
          <div className="form-field">
            <label>Hostname</label>
            <input value={editForm.hostname} onChange={setEdit('hostname')} />
          </div>
          <div className="form-field">
            <label>Status</label>
            <select value={editForm.status} onChange={setEdit('status')}>
              {STATUSES.map(s => <option key={s} value={s}>{s}</option>)}
            </select>
          </div>
          <div className="form-field">
            <label>MAC Address</label>
            <input value={editForm.mac_address} onChange={setEdit('mac_address')} />
          </div>
          <div className="form-field">
            <label>Description</label>
            <input value={editForm.description} onChange={setEdit('description')} />
          </div>
          <div className="form-field" style={{ gridColumn: '1 / -1' }}>
            <label>Notes</label>
            <textarea
              value={editForm.notes}
              onChange={setEdit('notes')}
              rows={4}
              style={{ resize: 'vertical', width: '100%' }}
            />
          </div>
        </DetailDrawer>
      )}
    </div>
  )
}
