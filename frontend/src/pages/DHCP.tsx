import { useMemo, useState, useEffect } from 'react'
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query'
import { Plus, X, Search, ArrowUp, ArrowDown, ArrowUpDown, Network } from 'lucide-react'
import { dhcpApi, providersApi, addressesApi, subnetsApi, type DHCPReservation, type DHCPScope } from '../api/client'
import { rangeSize, ipInCidr, ipToNum, ipCompare, isValidIPv4, isValidIPv6, isValidEUI48, isValidEUI64 } from '../utils/ip'
import SyncBar from '../components/SyncBar'
import EmptyState from '../components/EmptyState'
import DetailPanel from '../components/DetailPanel'
import ConfirmModal from '../components/ConfirmModal'
import { useToast } from '../contexts/ToastContext'
import { rowActivation } from '../utils/a11y'

const SOURCE_LABEL: Record<string, string> = {
  msdhcp: 'MS DHCP', pihole: 'Pi-hole', keadhcp: 'Kea',
}

type ViewMode = 'combined' | 'by-server'
type SortKey = 'ip_address' | 'mac' | 'iaid' | 'name' | 'description'
type SortDir = 'asc' | 'desc'

const emptyForm = {
  ip_address: '', mac_address: '', client_duid: '', iaid: 0,
  name: '', description: '',
}

export default function DHCP() {
  const [selectedScope, setSelectedScope] = useState<DHCPScope | null>(null)
  const [showForm, setShowForm]           = useState(false)
  const [form, setForm]                   = useState(emptyForm)
  const [viewMode, setViewMode]           = useState<ViewMode>('combined')
  const [selectedLease, setSelectedLease] = useState<DHCPReservation | null>(null)
  const [confirmIp, setConfirmIp] = useState<string | null>(null)
  const { showToast } = useToast()
  const [editingNotes, setEditingNotes]       = useState(false)
  const [notesValue, setNotesValue]           = useState('')
  const [selectedAddSubnetId, setSelectedAddSubnetId] = useState<number | null>(null)
  const [searchTerm, setSearchTerm] = useState('')
  const [sortKey, setSortKey] = useState<SortKey>('ip_address')
  const [sortDir, setSortDir] = useState<SortDir>('asc')
  const qc = useQueryClient()

  const isV6 = (scope: DHCPScope | null) => scope ? scope.ip_version === 6 : false

  const { data: scopes, isLoading: loadingScopes } = useQuery({
    queryKey: ['dhcp-scopes'],
    queryFn: dhcpApi.listScopes,
  })

  const { data: providers } = useQuery({
    queryKey: ['providers'],
    queryFn: providersApi.get,
  })

  const dhcpProviders = providers?.dhcp ?? []

  const { data: leases, isLoading: loadingLeases } = useQuery({
    queryKey: ['dhcp-leases', selectedScope?.scope_id, selectedScope?.source],
    queryFn: () => dhcpApi.listLeases(selectedScope!.scope_id, selectedScope!.source),
    enabled: !!selectedScope,
  })

  const addMutation = useMutation({
    mutationFn: () => dhcpApi.addReservation(selectedScope!.scope_id, form, selectedScope!.source),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ['dhcp-leases', selectedScope?.scope_id, selectedScope?.source] })
      setForm(emptyForm)
      setShowForm(false)
    },
  })

  const deleteMutation = useMutation({
    mutationFn: (ip: string) => dhcpApi.deleteReservation(selectedScope!.scope_id, ip, selectedScope!.source),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ['dhcp-leases', selectedScope?.scope_id] })
      showToast('Reservation deleted', 'success')
      setConfirmIp(null)
    },
    onError: (err: any) => {
      showToast(err?.response?.data?.detail ?? 'Delete failed', 'error')
      setConfirmIp(null)
    },
  })

  const { data: subnets } = useQuery({ queryKey: ['subnets'], queryFn: subnetsApi.list })

  const ipamQuery = useQuery({
    queryKey: ['ipam-address', selectedLease?.ip_address],
    queryFn: () => addressesApi.byIp(selectedLease!.ip_address),
    enabled: !!selectedLease,
    retry: false,
  })

  const matchingSubnet = useMemo(() => {
    if (!selectedLease || !subnets) return null
    return subnets.find(s => ipInCidr(selectedLease.ip_address, s.cidr)) ?? null
  }, [selectedLease, subnets])

  const effectiveSubnetId = matchingSubnet?.id ?? selectedAddSubnetId

  const createIpamMutation = useMutation({
    mutationFn: () => addressesApi.create({
      address: selectedLease!.ip_address,
      subnet_id: effectiveSubnetId!,
      status: 'assigned',
      hostname: selectedLease!.name || null,
      mac_address: selectedLease!.mac_address || null,
      description: null,
      notes: null,
    }),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ['ipam-address', selectedLease?.ip_address] })
      setEditingNotes(true)
    },
  })

  const updateNotesMutation = useMutation({
    mutationFn: () => addressesApi.update(ipamQuery.data!.id, { notes: notesValue || null }),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ['ipam-address', selectedLease?.ip_address] })
      setEditingNotes(false)
    },
  })

  useEffect(() => {
    setNotesValue(ipamQuery.data?.notes ?? '')
    setEditingNotes(false)
    setSelectedAddSubnetId(null)
  }, [ipamQuery.data])

  const filteredScopes = useMemo(
    () => dhcpProviders.length
      ? (scopes ?? []).filter(s => dhcpProviders.includes(s.source))
      : (scopes ?? []),
    [scopes, dhcpProviders]
  )

  const uniqueSources = useMemo(
    () => [...new Set(filteredScopes.map(s => s.source).filter(Boolean))],
    [filteredScopes]
  )
  const multiProvider = uniqueSources.length > 1 || dhcpProviders.length > 1

  const groupedScopes = useMemo(() => {
    const groups = new Map<string, DHCPScope[]>()
    for (const s of filteredScopes) {
      const src = s.source || 'unknown'
      if (!groups.has(src)) groups.set(src, [])
      groups.get(src)!.push(s)
    }
    return groups
  }, [filteredScopes])

  const set = (key: keyof typeof emptyForm) =>
    (e: React.ChangeEvent<HTMLInputElement>) =>
      setForm(f => ({ ...f, [key]: key === 'iaid' ? Number(e.target.value) : e.target.value }))

  const ipError = useMemo(() => {
    const ip = form.ip_address
    if (!ip) return null
    const v6 = isV6(selectedScope)
    if (v6 ? !isValidIPv6(ip) : !isValidIPv4(ip))
      return `Invalid IPv${v6 ? 6 : 4} address`
    if (!v6 && selectedScope?.scope_id.includes('/') && !ipInCidr(ip, selectedScope.scope_id))
      return `IP not in scope ${selectedScope.scope_id}`
    if (!v6 && selectedScope?.start_range && selectedScope.end_range &&
        (ipToNum(ip) < ipToNum(selectedScope.start_range) || ipToNum(ip) > ipToNum(selectedScope.end_range)))
      return `IP outside pool range (${selectedScope.start_range}–${selectedScope.end_range})`
    return null
  }, [form.ip_address, selectedScope])

  const macError = useMemo(() => {
    if (isV6(selectedScope)) {
      const duid = form.client_duid
      if (!duid) return null
      if (!isValidEUI48(duid) && !isValidEUI64(duid))
        return 'Client DUID must be EUI-48 or EUI-64 format'
    } else {
      const mac = form.mac_address
      if (!mac) return null
      if (!isValidEUI48(mac))
        return 'MAC must be EUI-48 (AA:BB:CC:DD:EE:FF, AA-BB-CC-DD-EE-FF, or AABB.CCDD.EEFF)'
    }
    return null
  }, [form.mac_address, form.client_duid, selectedScope])

  const canSubmit = form.ip_address && !ipError && form.name && !macError && (
    isV6(selectedScope) ? form.client_duid : form.mac_address
  )

  const visibleLeases = useMemo(() => {
    if (!leases) return []
    const v6 = isV6(selectedScope)
    const q = searchTerm.trim().toLowerCase()
    const filtered = q
      ? leases.filter(l => {
          const idField = v6 ? l.client_duid : l.mac_address
          return (
            l.ip_address.toLowerCase().includes(q) ||
            (idField || '').toLowerCase().includes(q) ||
            (l.name || '').toLowerCase().includes(q) ||
            (l.description || '').toLowerCase().includes(q) ||
            (v6 && l.iaid ? String(l.iaid).includes(q) : false)
          )
        })
      : leases.slice()
    const dir = sortDir === 'asc' ? 1 : -1
    const cmp = (a: DHCPReservation, b: DHCPReservation) => {
      switch (sortKey) {
        case 'ip_address': return ipCompare(a.ip_address, b.ip_address) * dir
        case 'mac': {
          const av = (v6 ? a.client_duid : a.mac_address) || ''
          const bv = (v6 ? b.client_duid : b.mac_address) || ''
          return av.localeCompare(bv) * dir
        }
        case 'iaid': return ((a.iaid ?? 0) - (b.iaid ?? 0)) * dir
        case 'name': return (a.name || '').localeCompare(b.name || '') * dir
        case 'description': return (a.description || '').localeCompare(b.description || '') * dir
      }
    }
    return filtered.sort(cmp)
  }, [leases, selectedScope, searchTerm, sortKey, sortDir])

  const toggleSort = (key: SortKey) => {
    if (sortKey === key) setSortDir(d => d === 'asc' ? 'desc' : 'asc')
    else { setSortKey(key); setSortDir('asc') }
  }

  const sortIcon = (key: SortKey) =>
    sortKey !== key ? <ArrowUpDown size={11} className="sort-icon-idle" />
    : sortDir === 'asc' ? <ArrowUp size={11} />
    : <ArrowDown size={11} />

  useEffect(() => { setSearchTerm('') }, [selectedScope])

  const renderScopeItem = (s: DHCPScope) => (
    <div
      key={`${s.source}:${s.scope_id}`}
      className={'panel-list-item' + (
        selectedScope?.scope_id === s.scope_id && selectedScope?.source === s.source ? ' active' : ''
      )}
      onClick={() => { setSelectedScope(s); setShowForm(false); setForm(emptyForm); setSelectedLease(null) }}
    >
      <div style={{ display: 'flex', alignItems: 'center', gap: '0.4rem' }}>
        <span className={`badge ${s.ip_version === 6 ? 'badge-blue' : 'badge-green'}`} style={{ fontSize: '0.6rem' }}>
          IPv{s.ip_version}
        </span>
        {s.name}
      </div>
      <div style={{ display: 'flex', alignItems: 'center', gap: '0.4rem', marginTop: '2px' }}>
        <span className="panel-list-item-sub font-mono">{s.scope_id}</span>
        {s.source && viewMode === 'combined' && (
          <span className="badge badge-gray" style={{ fontSize: '0.55rem' }}>
            {SOURCE_LABEL[s.source] ?? s.source}
          </span>
        )}
      </div>
    </div>
  )

  return (
    <div>
      <div className="page-header">
        <h1>DHCP</h1>
        <div style={{ display: 'flex', alignItems: 'center', gap: '0.625rem' }}>
          <SyncBar type="dhcp" />
        </div>
      </div>

      <div className="two-panel">
        <div className="panel-list">
          <div className="panel-list-header" style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}>
            <span>Scopes</span>
            {multiProvider && (
              <div className="view-toggle">
                <button
                  className={viewMode === 'combined' ? 'active' : ''}
                  onClick={() => setViewMode('combined')}
                >
                  All
                </button>
                <button
                  className={viewMode === 'by-server' ? 'active' : ''}
                  onClick={() => setViewMode('by-server')}
                >
                  By Server
                </button>
              </div>
            )}
          </div>
          {loadingScopes && <p className="loading" style={{ padding: '0.75rem' }}>Loading…</p>}
          {viewMode === 'combined' ? (
            filteredScopes.map(s => renderScopeItem(s))
          ) : (
            [...groupedScopes.entries()].map(([src, scopeList]) => (
              <div key={src}>
                <div className="panel-server-header">
                  <span>{SOURCE_LABEL[src] ?? src}</span>
                  <span className="panel-server-count">{scopeList.length}</span>
                </div>
                {scopeList.map(s => renderScopeItem(s))}
              </div>
            ))
          )}
          {filteredScopes.length === 0 && !loadingScopes && <p className="loading" style={{ padding: '0.75rem' }}>No scopes found.</p>}
        </div>

        <div className="panel-main">
          {selectedScope ? (
            <>
              <div className="page-header">
                <div>
                  <h1 style={{ display: 'flex', alignItems: 'center', gap: '0.5rem' }}>
                    {selectedScope.name}
                    {selectedScope.source && (
                      <span className="badge badge-gray" style={{ fontSize: '0.65rem', fontWeight: 400 }}>
                        {SOURCE_LABEL[selectedScope.source] ?? selectedScope.source}
                      </span>
                    )}
                  </h1>
                  <p style={{ fontSize: '0.775rem', marginTop: '2px' }}>
                    <span className="font-mono">{selectedScope.scope_id}</span>
                    {selectedScope.ip_version === 4 && selectedScope.start_range &&
                      <> · {selectedScope.start_range} – {selectedScope.end_range}</>
                    }
                    {selectedScope.ip_version === 6 &&
                      <> · prefix length {selectedScope.subnet_mask}</>
                    }
                  </p>
                </div>
                <div className="page-header-actions">
                  {!showForm && (
                    <button className="btn-primary btn-sm" onClick={() => setShowForm(true)}>
                      <Plus size={13} /> Add Reservation
                    </button>
                  )}
                </div>
              </div>

              {showForm && (
                <div className="inline-form">
                  <div className="form-grid">
                    <div className="form-field">
                      <label>IP Address</label>
                      <input
                        placeholder={isV6(selectedScope) ? '2001:db8::100' : '10.0.0.100'}
                        value={form.ip_address}
                        onChange={set('ip_address')}
                      />
                      {ipError && <span className="feedback-error" style={{ fontSize: '0.72rem' }}>{ipError}</span>}
                    </div>

                    {isV6(selectedScope) ? (
                      <>
                        <div className="form-field">
                          <label>Client DUID</label>
                          <input
                            placeholder="AA:BB:CC:DD:EE:FF or AA:BB:CC:DD:EE:FF:00:11"
                            value={form.client_duid}
                            onChange={set('client_duid')}
                          />
                          {macError && <span className="feedback-error" style={{ fontSize: '0.72rem' }}>{macError}</span>}
                        </div>
                        <div className="form-field">
                          <label>IAID</label>
                          <input
                            type="number"
                            placeholder="12345678"
                            value={form.iaid || ''}
                            onChange={set('iaid')}
                          />
                        </div>
                      </>
                    ) : (
                      <div className="form-field">
                        <label>MAC Address</label>
                        <input
                          placeholder="AA:BB:CC:DD:EE:FF"
                          value={form.mac_address}
                          onChange={set('mac_address')}
                        />
                        {macError && <span className="feedback-error" style={{ fontSize: '0.72rem' }}>{macError}</span>}
                      </div>
                    )}

                    <div className="form-field">
                      <label>Hostname / Name</label>
                      <input placeholder="server01" value={form.name} onChange={set('name')} />
                    </div>
                    <div className="form-field">
                      <label>Description</label>
                      <input placeholder="Optional" value={form.description} onChange={set('description')} />
                    </div>
                  </div>
                  <div className="form-actions">
                    <button
                      className="btn-primary btn-sm"
                      onClick={() => addMutation.mutate()}
                      disabled={addMutation.isPending || !canSubmit}
                    >
                      {addMutation.isPending ? 'Adding…' : 'Add'}
                    </button>
                    <button className="btn-ghost btn-sm" onClick={() => { setShowForm(false); setForm(emptyForm) }}>
                      <X size={13} /> Cancel
                    </button>
                    {addMutation.isError && (
                      <span className="feedback-error">
                        {String((addMutation.error as Error).message)}
                      </span>
                    )}
                  </div>
                </div>
              )}

              {!loadingLeases && leases && (
                <div style={{
                  display: 'flex', flexWrap: 'wrap', gap: '1.5rem', alignItems: 'center',
                  padding: '0.5rem 0', marginBottom: '0.75rem',
                  fontSize: '0.8rem', borderBottom: '1px solid var(--border)',
                }}>
                  <span>
                    <strong>{searchTerm ? `${visibleLeases.length} / ${leases.length}` : leases.length}</strong> reservation{leases.length !== 1 ? 's' : ''}
                  </span>
                  {selectedScope.ip_version === 4 && selectedScope.start_range && selectedScope.end_range && (() => {
                    const size = rangeSize(selectedScope.start_range, selectedScope.end_range)
                    const pct  = size > 0 ? Math.round(leases.length / size * 100) : 0
                    return (
                      <>
                        <span>
                          Pool: <span className="font-mono">
                            {selectedScope.start_range} – {selectedScope.end_range}
                          </span>
                        </span>
                        <span>Size: <strong>{size}</strong></span>
                        <span>Utilization: <strong>{pct}%</strong></span>
                      </>
                    )
                  })()}
                  <span>
                    <span className={`badge ${selectedScope.active ? 'badge-green' : 'badge-gray'}`}>
                      {selectedScope.active ? 'Active' : 'Inactive'}
                    </span>
                  </span>
                  <div style={{ marginLeft: 'auto', position: 'relative', display: 'flex', alignItems: 'center' }}>
                    <Search size={13} style={{ position: 'absolute', left: '0.5rem', color: 'var(--text-muted)', pointerEvents: 'none' }} />
                    <input
                      type="text"
                      placeholder="Search IP, MAC, hostname…"
                      value={searchTerm}
                      onChange={e => setSearchTerm(e.target.value)}
                      style={{ fontSize: '0.75rem', padding: '0.3rem 1.8rem 0.3rem 1.7rem', width: '15rem' }}
                    />
                    {searchTerm && (
                      <button
                        onClick={() => setSearchTerm('')}
                        aria-label="Clear search"
                        style={{ position: 'absolute', right: '0.3rem', background: 'transparent', border: 'none', cursor: 'pointer', padding: '2px', display: 'flex', color: 'var(--text-muted)' }}
                      >
                        <X size={12} />
                      </button>
                    )}
                  </div>
                </div>
              )}

              {loadingLeases ? (
                <p className="loading">Loading leases…</p>
              ) : (
                <div className="table-wrap">
                  <table>
                    <thead>
                      <tr>
                        <th className="th-sortable" onClick={() => toggleSort('ip_address')}>
                          <span>IP Address {sortIcon('ip_address')}</span>
                        </th>
                        <th className="th-sortable" onClick={() => toggleSort('mac')}>
                          <span>{isV6(selectedScope) ? 'Client DUID' : 'MAC'} {sortIcon('mac')}</span>
                        </th>
                        {isV6(selectedScope) && (
                          <th className="th-sortable" onClick={() => toggleSort('iaid')}>
                            <span>IAID {sortIcon('iaid')}</span>
                          </th>
                        )}
                        <th className="th-sortable" onClick={() => toggleSort('name')}>
                          <span>Hostname {sortIcon('name')}</span>
                        </th>
                        <th className="th-sortable" onClick={() => toggleSort('description')}>
                          <span>Description {sortIcon('description')}</span>
                        </th>
                        <th></th>
                      </tr>
                    </thead>
                    <tbody>
                      {visibleLeases.length === 0 && (
                        <tr>
                          <td colSpan={isV6(selectedScope) ? 6 : 5}>
                            {leases && leases.length > 0 ? (
                              <EmptyState
                                icon={Network}
                                title="No leases match search"
                                action={<button className="btn-ghost btn-sm" onClick={() => setSearchTerm('')}>Clear search</button>}
                              />
                            ) : (
                              <EmptyState icon={Network} title="No leases in this scope" description="Reservations and active leases will appear here." />
                            )}
                          </td>
                        </tr>
                      )}
                      {visibleLeases.map(l => (
                        <tr
                          key={l.ip_address}
                          className="clickable"
                          {...rowActivation(() => setSelectedLease(l))}
                        >
                          <td><span className="font-mono">{l.ip_address}</span></td>
                          <td><span className="font-mono">{isV6(selectedScope) ? l.client_duid : l.mac_address}</span></td>
                          {isV6(selectedScope) && (
                            <td><span className="font-mono">{l.iaid || <span className="text-muted">—</span>}</span></td>
                          )}
                          <td>{l.name || <span className="text-muted">—</span>}</td>
                          <td>{l.description || <span className="text-muted">—</span>}</td>
                          <td onClick={e => e.stopPropagation()}>
                            <button
                              className="btn-danger btn-sm"
                              onClick={() => setConfirmIp(l.ip_address)}
                              disabled={deleteMutation.isPending}
                            >
                              Delete
                            </button>
                          </td>
                        </tr>
                      ))}
                    </tbody>
                  </table>
                </div>
              )}
            </>
          ) : (
            <div className="empty-state">Select a scope from the list.</div>
          )}
        </div>
      </div>

      {confirmIp && (
        <ConfirmModal
          title="Delete DHCP Reservation"
          message={`Delete reservation for ${confirmIp}?`}
          onConfirm={() => deleteMutation.mutate(confirmIp)}
          onCancel={() => setConfirmIp(null)}
        />
      )}

      {selectedLease && selectedScope && (
        <DetailPanel
          title={selectedLease.ip_address}
          subtitle={`${selectedScope.name} · ${selectedScope.source ? (SOURCE_LABEL[selectedScope.source] ?? selectedScope.source) : ''}`}
          pingTarget={selectedLease.ip_address}
          fields={[
            { label: 'IP Address', value: <span className="font-mono">{selectedLease.ip_address}</span> },
            isV6(selectedScope)
              ? { label: 'Client DUID', value: <span className="font-mono">{selectedLease.client_duid || '—'}</span> }
              : { label: 'MAC',         value: <span className="font-mono">{selectedLease.mac_address || '—'}</span> },
            ...(isV6(selectedScope)
              ? [{ label: 'IAID', value: selectedLease.iaid ? String(selectedLease.iaid) : '—' }]
              : []),
            { label: 'Hostname',    value: selectedLease.name || '—' },
            { label: 'Description', value: selectedLease.description || '—' },
            { label: 'Scope',       value: <span className="font-mono">{selectedScope.scope_id}</span> },
            { label: 'Source',      value: (SOURCE_LABEL[selectedScope.source] ?? selectedScope.source) || '—' },
          ]}
          extra={(
            <div>
              <div className="detail-section-title" style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}>
                IPAM Notes
                <span className="badge badge-gray" style={{ fontSize: '0.6rem' }}>IPAM</span>
              </div>
              {ipamQuery.isLoading ? (
                <p className="loading" style={{ fontSize: '0.8rem' }}>Loading…</p>
              ) : !ipamQuery.data ? (
                <div style={{ margin: '0.5rem 0' }}>
                  <div style={{ fontSize: '0.8rem', color: 'var(--text-muted)', marginBottom: '0.4rem' }}>Not tracked in IPAM.</div>
                  {!matchingSubnet && subnets && subnets.length > 0 && (
                    <select
                      value={selectedAddSubnetId ?? ''}
                      onChange={e => setSelectedAddSubnetId(Number(e.target.value) || null)}
                      style={{ fontSize: '0.75rem', marginBottom: '0.4rem', width: '100%' }}
                    >
                      <option value="">Select subnet…</option>
                      {subnets.map(s => (
                        <option key={s.id} value={s.id}>{s.name} ({s.cidr})</option>
                      ))}
                    </select>
                  )}
                  <button
                    className="btn-ghost btn-sm"
                    onClick={() => createIpamMutation.mutate()}
                    disabled={createIpamMutation.isPending || !effectiveSubnetId}
                    style={{ fontSize: '0.7rem' }}
                  >
                    {createIpamMutation.isPending ? 'Adding…' : 'Add to IPAM'}
                  </button>
                </div>
              ) : editingNotes ? (
                <div>
                  <textarea
                    value={notesValue}
                    onChange={e => setNotesValue(e.target.value)}
                    rows={4}
                    autoFocus
                    style={{ resize: 'vertical', width: '100%', marginBottom: '0.5rem' }}
                  />
                  <div className="form-actions">
                    <button
                      className="btn-primary btn-sm"
                      onClick={() => updateNotesMutation.mutate()}
                      disabled={updateNotesMutation.isPending}
                    >
                      {updateNotesMutation.isPending ? 'Saving…' : 'Save'}
                    </button>
                    <button className="btn-ghost btn-sm" onClick={() => setEditingNotes(false)}>Cancel</button>
                  </div>
                </div>
              ) : (
                <div style={{ display: 'flex', gap: '0.5rem', alignItems: 'flex-start' }}>
                  <span style={{ flex: 1, fontSize: '0.82rem', color: notesValue ? 'inherit' : 'var(--text-muted)', whiteSpace: 'pre-wrap' }}>
                    {notesValue || '—'}
                  </span>
                  <button
                    className="btn-ghost btn-sm"
                    onClick={() => setEditingNotes(true)}
                    style={{ fontSize: '0.7rem', fontWeight: 500, flexShrink: 0 }}
                  >
                    Edit
                  </button>
                </div>
              )}
            </div>
          )}
          syncedAt={selectedLease.synced_at}
          onClose={() => { setSelectedLease(null); setEditingNotes(false) }}
        />
      )}
    </div>
  )
}
