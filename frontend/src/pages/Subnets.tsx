import { useState, useMemo } from 'react'
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query'
import { Plus, X, Scan, AlertTriangle } from 'lucide-react'
import { subnetsApi, dhcpApi, addressesApi, scanApi, type Subnet, type DHCPScope, type Collision } from '../api/client'
import { ipInCidr } from '../utils/ip'
import DetailDrawer from '../components/DetailDrawer'

const emptyForm = { name: '', cidr: '', vlan_id: '', description: '' }

const emptyEditForm = { name: '', vlan_id: '', description: '', notes: '' }

export default function Subnets() {
  const [showForm, setShowForm]             = useState(false)
  const [form, setForm]                     = useState(emptyForm)
  const [selectedSubnet, setSelectedSubnet] = useState<Subnet | null>(null)
  const [editForm, setEditForm]             = useState(emptyEditForm)
  const qc = useQueryClient()
  const [showRangePicker, setShowRangePicker] = useState(false)
  const [rangeForm, setRangeForm]             = useState({ start_ip: '', end_ip: '' })

  const { data: allScopes } = useQuery({
    queryKey: ['dhcp-scopes'],
    queryFn: dhcpApi.listScopes,
  })

  const { data: subnetAddresses } = useQuery({
    queryKey: ['addresses', selectedSubnet?.id],
    queryFn: () => addressesApi.list({ subnet_id: selectedSubnet!.id }),
    enabled: !!selectedSubnet,
  })

  const matchedScopes = useMemo((): DHCPScope[] => {
    if (!selectedSubnet || !allScopes) return []
    return allScopes.filter(s =>
      s.ip_version === selectedSubnet.ip_version &&
      s.start_range &&
      ipInCidr(s.start_range, selectedSubnet.cidr)
    )
  }, [selectedSubnet, allScopes])

  const { data: scanStatus, refetch: refetchScan } = useQuery({
    queryKey: ['scan-status', selectedSubnet?.id],
    queryFn: () => scanApi.status(selectedSubnet!.id),
    enabled: !!selectedSubnet,
    refetchInterval: (query) => query.state.data?.status === 'running' ? 3000 : false,
  })

  const { data: subnetCollisions } = useQuery({
    queryKey: ['collisions', selectedSubnet?.id],
    queryFn: () => scanApi.collisions({ resolved: false, subnet_id: selectedSubnet!.id }),
    enabled: !!selectedSubnet,
  })

  const { data: allUnresolvedCollisions } = useQuery({
    queryKey: ['collisions-all'],
    queryFn: () => scanApi.collisions({ resolved: false }),
  })

  const triggerScanMutation = useMutation({
    mutationFn: (range?: { start_ip: string; end_ip: string }) =>
      scanApi.trigger(selectedSubnet!.id, range),
    onSuccess: () => {
      setShowRangePicker(false)
      refetchScan()
    },
  })

  const resolveCollisionMutation = useMutation({
    mutationFn: (id: number) => scanApi.resolveCollision(id),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ['collisions', selectedSubnet?.id] })
      qc.invalidateQueries({ queryKey: ['collisions-all'] })
    },
  })

  const { data, isLoading, error } = useQuery({
    queryKey: ['subnets'],
    queryFn: subnetsApi.list,
  })

  const createMutation = useMutation({
    mutationFn: () => subnetsApi.create({
      name:        form.name,
      cidr:        form.cidr,
      vlan_id:     form.vlan_id ? Number(form.vlan_id) : null,
      description: form.description || null,
      ip_version:  4,
      notes:       null,
    }),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ['subnets'] })
      setForm(emptyForm)
      setShowForm(false)
    },
  })

  const updateMutation = useMutation({
    mutationFn: () => subnetsApi.update(selectedSubnet!.id, {
      name:        editForm.name        || undefined,
      vlan_id:     editForm.vlan_id ? Number(editForm.vlan_id) : null,
      description: editForm.description || null,
      notes:       editForm.notes       || null,
    }),
    onSuccess: () => qc.invalidateQueries({ queryKey: ['subnets'] }),
  })

  const deleteMutation = useMutation({
    mutationFn: (id: number) => subnetsApi.delete(id),
    onSuccess: () => qc.invalidateQueries({ queryKey: ['subnets'] }),
  })

  const set = (key: keyof typeof emptyForm) =>
    (e: React.ChangeEvent<HTMLInputElement>) =>
      setForm(f => ({ ...f, [key]: e.target.value }))

  const setEdit = (key: keyof typeof emptyEditForm) =>
    (e: React.ChangeEvent<HTMLInputElement | HTMLTextAreaElement>) =>
      setEditForm(f => ({ ...f, [key]: e.target.value }))

  const openDrawer = (s: Subnet) => {
    setSelectedSubnet(s)
    setEditForm({
      name:        s.name,
      vlan_id:     s.vlan_id != null ? String(s.vlan_id) : '',
      description: s.description ?? '',
      notes:       s.notes       ?? '',
    })
    setShowRangePicker(false)
    setRangeForm({ start_ip: '', end_ip: '' })
  }

  const collisionCountForSubnet = (subnet: Subnet): number => {
    if (!allUnresolvedCollisions) return 0
    return allUnresolvedCollisions.filter((c: Collision) => {
      try {
        const [base, bits] = subnet.cidr.split('/')
        const prefixLen = parseInt(bits)
        const ipParts   = c.ip_address.split('.').map(Number)
        const baseParts = base.split('.').map(Number)
        const fullBytes = Math.floor(prefixLen / 8)
        for (let i = 0; i < fullBytes; i++) {
          if (ipParts[i] !== baseParts[i]) return false
        }
        return true
      } catch { return false }
    }).length
  }

  const prefixLen     = selectedSubnet ? parseInt(selectedSubnet.cidr.split('/')[1]) : 0
  const isLargeSubnet = prefixLen < 24

  const subnetViewExtra = selectedSubnet ? (
    <>
      <div style={{ marginTop: '1rem' }}>
        <div className="detail-section-title">IP Addresses</div>
        {!subnetAddresses ? (
          <p className="loading">Loading…</p>
        ) : subnetAddresses.length === 0 ? (
          <p style={{ fontSize: '0.8rem', color: 'var(--text-muted)', margin: '0.5rem 0' }}>
            No addresses tracked in this subnet.
          </p>
        ) : (
          <div className="table-wrap" style={{ marginTop: '0.5rem' }}>
            <table>
              <thead>
                <tr>
                  <th>Address</th>
                  <th>Hostname</th>
                  <th>Status</th>
                </tr>
              </thead>
              <tbody>
                {subnetAddresses.map(a => (
                  <tr key={a.id}>
                    <td><span className="font-mono">{a.address}</span></td>
                    <td>{a.hostname ?? <span className="text-muted">—</span>}</td>
                    <td>
                      <span className={`badge ${
                        a.status === 'assigned'   ? 'badge-blue'   :
                        a.status === 'available'  ? 'badge-green'  :
                        a.status === 'reserved'   ? 'badge-yellow' :
                        a.status === 'discovered' ? 'badge-yellow' :
                        'badge-gray'
                      }`}>{a.status}</span>
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}
      </div>

      <div style={{ marginTop: '1rem' }}>
        <div className="detail-section-title">DHCP Scope</div>
        {matchedScopes.length === 0 ? (
          <p style={{ fontSize: '0.8rem', color: 'var(--text-muted)', margin: '0.5rem 0' }}>
            No matching DHCP scope found.
          </p>
        ) : matchedScopes.map(s => (
          <div key={`${s.source}:${s.scope_id}`} className="detail-fields" style={{ marginTop: '0.5rem' }}>
            <div className="detail-field">
              <span className="detail-field-label">Scope</span>
              <span className="detail-field-value font-mono">{s.scope_id}</span>
            </div>
            <div className="detail-field">
              <span className="detail-field-label">Name</span>
              <span className="detail-field-value">{s.name || <span className="text-muted">—</span>}</span>
            </div>
            <div className="detail-field">
              <span className="detail-field-label">Range</span>
              <span className="detail-field-value font-mono">
                {s.start_range} – {s.end_range}
              </span>
            </div>
            <div className="detail-field">
              <span className="detail-field-label">Status</span>
              <span className="detail-field-value">
                <span className={`badge ${s.active ? 'badge-green' : 'badge-gray'}`}>
                  {s.active ? 'Active' : 'Inactive'}
                </span>
              </span>
            </div>
            {s.description && (
              <div className="detail-field">
                <span className="detail-field-label">Description</span>
                <span className="detail-field-value">{s.description}</span>
              </div>
            )}
          </div>
        ))}
      </div>

      {/* Scan section */}
      <div style={{ marginTop: '1rem' }}>
        <div className="detail-section-title" style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}>
          <span>Scan</span>
          {scanStatus?.scanned_at && (
            <span style={{ fontSize: '0.65rem', color: 'var(--text-muted)', fontWeight: 400 }}>
              Last scanned {Math.floor((Date.now() - new Date(scanStatus.scanned_at).getTime()) / 1000)}s ago
            </span>
          )}
        </div>

        {scanStatus?.status === 'running' ? (
          <p className="loading" style={{ fontSize: '0.8rem' }}>Scanning…</p>
        ) : (
          <button
            className="btn-ghost btn-sm"
            onClick={() => isLargeSubnet ? setShowRangePicker(true) : triggerScanMutation.mutate(undefined)}
            disabled={triggerScanMutation.isPending}
            style={{ fontSize: '0.75rem', marginBottom: '0.5rem' }}
          >
            <Scan size={12} /> {isLargeSubnet ? 'Scan Range…' : 'Scan Subnet'}
          </button>
        )}

        {showRangePicker && (
          <div style={{ background: 'var(--surface-2)', border: '1px solid var(--border)', borderRadius: '6px', padding: '0.75rem', marginBottom: '0.5rem' }}>
            <div style={{ fontSize: '0.75rem', color: 'var(--text-muted)', marginBottom: '0.5rem' }}>
              Subnet is larger than /24. Specify a range (max 1,024 hosts).
            </div>
            <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: '0.5rem', marginBottom: '0.5rem' }}>
              <div className="form-field">
                <label>Start IP</label>
                <input placeholder="10.0.0.1" value={rangeForm.start_ip} onChange={e => setRangeForm(f => ({ ...f, start_ip: e.target.value }))} />
              </div>
              <div className="form-field">
                <label>End IP</label>
                <input placeholder="10.0.0.254" value={rangeForm.end_ip} onChange={e => setRangeForm(f => ({ ...f, end_ip: e.target.value }))} />
              </div>
            </div>
            <div className="form-actions">
              <button
                className="btn-primary btn-sm"
                onClick={() => triggerScanMutation.mutate({ start_ip: rangeForm.start_ip, end_ip: rangeForm.end_ip })}
                disabled={!rangeForm.start_ip || !rangeForm.end_ip || triggerScanMutation.isPending}
              >
                Start Scan
              </button>
              <button className="btn-ghost btn-sm" onClick={() => setShowRangePicker(false)}>
                Cancel
              </button>
            </div>
          </div>
        )}

        {scanStatus?.status === 'error' && (
          <p style={{ fontSize: '0.75rem', color: 'var(--danger)', margin: '0.25rem 0' }}>
            Error: {scanStatus.error}
          </p>
        )}

        {scanStatus?.results && scanStatus.results.length > 0 && (
          <div className="table-wrap" style={{ marginTop: '0.5rem' }}>
            <table>
              <thead>
                <tr><th>IP</th><th>Status</th><th>Latency</th></tr>
              </thead>
              <tbody>
                {scanStatus.results.filter(r => r.reachable).map(r => {
                  const inIpam = subnetAddresses?.some(a => a.address === r.ip)
                  return (
                    <tr key={r.ip}>
                      <td><span className="font-mono">{r.ip}</span></td>
                      <td>
                        {inIpam
                          ? <span className="badge badge-green">tracked</span>
                          : <span className="badge badge-yellow">discovered</span>
                        }
                      </td>
                      <td><span className="text-muted">{r.latency_ms != null ? `${r.latency_ms.toFixed(1)}ms` : '—'}</span></td>
                    </tr>
                  )
                })}
              </tbody>
            </table>
          </div>
        )}

        {subnetCollisions && subnetCollisions.length > 0 && (
          <div style={{ marginTop: '0.75rem' }}>
            <div style={{ fontSize: '0.75rem', fontWeight: 600, color: 'var(--warning, #f59e0b)', marginBottom: '0.4rem', display: 'flex', alignItems: 'center', gap: '4px' }}>
              <AlertTriangle size={12} /> {subnetCollisions.length} collision{subnetCollisions.length > 1 ? 's' : ''}
            </div>
            {subnetCollisions.map(c => (
              <div key={c.id} style={{ fontSize: '0.75rem', display: 'flex', justifyContent: 'space-between', alignItems: 'center', padding: '0.25rem 0', borderBottom: '1px solid var(--border)' }}>
                <span>
                  <span className="font-mono">{c.ip_address}</span>{' '}
                  <span className="badge badge-yellow" style={{ fontSize: '0.55rem' }}>
                    {c.collision_type.replace(/_/g, ' ')}
                  </span>
                </span>
                <button
                  className="btn-ghost btn-sm"
                  onClick={() => resolveCollisionMutation.mutate(c.id)}
                  style={{ fontSize: '0.65rem' }}
                >
                  Resolve
                </button>
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
        <h1>Subnets</h1>
        <div className="page-header-actions">
          {!showForm && (
            <button className="btn-primary btn-sm" onClick={() => setShowForm(true)}>
              <Plus size={13} /> Add Subnet
            </button>
          )}
        </div>
      </div>

      {showForm && (
        <div className="inline-form">
          <div className="form-grid">
            <div className="form-field">
              <label>Name</label>
              <input placeholder="Server Network" value={form.name} onChange={set('name')} autoFocus />
            </div>
            <div className="form-field">
              <label>CIDR</label>
              <input placeholder="10.0.1.0/24" value={form.cidr} onChange={set('cidr')} />
            </div>
            <div className="form-field">
              <label>VLAN ID</label>
              <input type="number" placeholder="Optional" value={form.vlan_id} onChange={set('vlan_id')} />
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
              disabled={createMutation.isPending || !form.name || !form.cidr}
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
      {error    && <p className="feedback-error">Failed to load subnets.</p>}

      {data && (
        <div className="table-wrap">
          <table>
            <thead>
              <tr>
                <th>Name</th>
                <th>CIDR</th>
                <th>Version</th>
                <th>VLAN</th>
                <th>Description</th>
                <th style={{ width: '2.5rem' }}></th>
              </tr>
            </thead>
            <tbody>
              {data.length === 0 && (
                <tr><td colSpan={6} className="empty-state">No subnets defined. Add one above.</td></tr>
              )}
              {data.map((s: Subnet) => (
                <tr key={s.id} className="clickable" onClick={() => openDrawer(s)}>
                  <td>
                    <span style={{ display: 'flex', alignItems: 'center', gap: '6px' }}>
                      {s.name}
                      {collisionCountForSubnet(s) > 0 && (
                        <span style={{ fontSize: '0.65rem', fontWeight: 600, color: 'var(--warning, #f59e0b)', display: 'flex', alignItems: 'center', gap: '2px' }}>
                          <AlertTriangle size={10} /> {collisionCountForSubnet(s)}
                        </span>
                      )}
                    </span>
                  </td>
                  <td><span className="font-mono">{s.cidr}</span></td>
                  <td><span className="badge badge-blue">IPv{s.ip_version}</span></td>
                  <td>{s.vlan_id ?? <span className="text-muted">—</span>}</td>
                  <td>{s.description ?? <span className="text-muted">—</span>}</td>
                  <td onClick={e => e.stopPropagation()}>
                    <button
                      className="btn-danger btn-sm"
                      onClick={() =>
                        window.confirm(`Delete subnet "${s.name}" (${s.cidr})?`) &&
                        deleteMutation.mutate(s.id)
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

      {selectedSubnet && (
        <DetailDrawer
          title={selectedSubnet.name}
          subtitle={selectedSubnet.cidr}
          viewExtra={subnetViewExtra}
          fields={[
            { label: 'Name',        value: selectedSubnet.name },
            { label: 'CIDR',        value: <span className="font-mono">{selectedSubnet.cidr}</span> },
            { label: 'IP Version',  value: <span className="badge badge-blue">IPv{selectedSubnet.ip_version}</span> },
            { label: 'VLAN',        value: selectedSubnet.vlan_id ?? <span className="text-muted">—</span> },
            { label: 'Description', value: selectedSubnet.description ?? <span className="text-muted">—</span> },
            { label: 'Notes',       value: selectedSubnet.notes ?? <span className="text-muted">—</span> },
          ]}
          onSave={() => updateMutation.mutate()}
          isSaving={updateMutation.isPending}
          onClose={() => setSelectedSubnet(null)}
        >
          <div className="form-field">
            <label>Name</label>
            <input value={editForm.name} onChange={setEdit('name')} />
          </div>
          <div className="form-field">
            <label>VLAN ID</label>
            <input type="number" value={editForm.vlan_id} onChange={setEdit('vlan_id')} />
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
