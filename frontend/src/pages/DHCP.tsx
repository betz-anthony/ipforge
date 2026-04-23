import { useMemo, useState } from 'react'
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query'
import { Plus, X } from 'lucide-react'
import { dhcpApi, type DHCPReservation, type DHCPScope } from '../api/client'
import SyncBar from '../components/SyncBar'
import DetailPanel from '../components/DetailPanel'

const SOURCE_LABEL: Record<string, string> = {
  msdhcp: 'MS DHCP', pihole: 'Pi-hole', keadhcp: 'Kea',
}

type ViewMode = 'combined' | 'by-server'

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
  const qc = useQueryClient()

  const isV6 = (scope: DHCPScope | null) => scope ? scope.ip_version === 6 : false

  const { data: scopes, isLoading: loadingScopes } = useQuery({
    queryKey: ['dhcp-scopes'],
    queryFn: dhcpApi.listScopes,
  })

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
      qc.invalidateQueries({ queryKey: ['dhcp-leases', selectedScope?.scope_id, selectedScope?.source] })
      setSelectedLease(null)
    },
  })

  const uniqueSources = useMemo(
    () => [...new Set((scopes ?? []).map(s => s.source).filter(Boolean))],
    [scopes]
  )
  const multiProvider = uniqueSources.length > 1

  const groupedScopes = useMemo(() => {
    const groups = new Map<string, DHCPScope[]>()
    for (const s of scopes ?? []) {
      const src = s.source || 'unknown'
      if (!groups.has(src)) groups.set(src, [])
      groups.get(src)!.push(s)
    }
    return groups
  }, [scopes])

  const set = (key: keyof typeof emptyForm) =>
    (e: React.ChangeEvent<HTMLInputElement>) =>
      setForm(f => ({ ...f, [key]: key === 'iaid' ? Number(e.target.value) : e.target.value }))

  const canSubmit = form.ip_address && form.name && (
    isV6(selectedScope) ? form.client_duid : form.mac_address
  )

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
            scopes?.map(s => renderScopeItem(s))
          ) : (
            [...groupedScopes.entries()].map(([src, scopeList]) => (
              <div key={src}>
                <div className="panel-list-group-label">{SOURCE_LABEL[src] ?? src}</div>
                {scopeList.map(s => renderScopeItem(s))}
              </div>
            ))
          )}
          {scopes?.length === 0 && <p className="loading" style={{ padding: '0.75rem' }}>No scopes found.</p>}
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
                    </div>

                    {isV6(selectedScope) ? (
                      <>
                        <div className="form-field">
                          <label>Client DUID</label>
                          <input
                            placeholder="00-01-00-01-12-34-56-78-AA-BB-CC-DD-EE-FF"
                            value={form.client_duid}
                            onChange={set('client_duid')}
                          />
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
                          placeholder="AA-BB-CC-DD-EE-FF"
                          value={form.mac_address}
                          onChange={set('mac_address')}
                        />
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

              {loadingLeases ? (
                <p className="loading">Loading leases…</p>
              ) : (
                <div className="table-wrap">
                  <table>
                    <thead>
                      <tr>
                        <th>IP Address</th>
                        <th>{isV6(selectedScope) ? 'Client DUID' : 'MAC'}</th>
                        {isV6(selectedScope) && <th>IAID</th>}
                        <th>Hostname</th>
                        <th>Description</th>
                        <th></th>
                      </tr>
                    </thead>
                    <tbody>
                      {leases?.length === 0 && (
                        <tr>
                          <td colSpan={isV6(selectedScope) ? 6 : 5} className="empty-state">
                            No leases in this scope.
                          </td>
                        </tr>
                      )}
                      {leases?.map(l => (
                        <tr
                          key={l.ip_address}
                          className="clickable"
                          onClick={() => setSelectedLease(l)}
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
                              onClick={() =>
                                window.confirm(`Delete reservation for ${l.ip_address}?`) &&
                                deleteMutation.mutate(l.ip_address)
                              }
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
          syncedAt={selectedLease.synced_at}
          onClose={() => setSelectedLease(null)}
        />
      )}
    </div>
  )
}
