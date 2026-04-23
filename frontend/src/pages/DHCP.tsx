import { useState } from 'react'
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query'
import { Plus, X } from 'lucide-react'
import { dhcpApi, type DHCPScope } from '../api/client'

const emptyForm = {
  ip_address: '', mac_address: '', client_duid: '', iaid: 0,
  name: '', description: '',
}

export default function DHCP() {
  const [selectedScope, setSelectedScope] = useState<DHCPScope | null>(null)
  const [showForm, setShowForm]           = useState(false)
  const [form, setForm]                   = useState(emptyForm)
  const qc = useQueryClient()

  const isV6 = (scope: DHCPScope | null) => scope ? scope.ip_version === 6 : false

  const { data: scopes, isLoading: loadingScopes } = useQuery({
    queryKey: ['dhcp-scopes'],
    queryFn: dhcpApi.listScopes,
  })

  const { data: leases, isLoading: loadingLeases } = useQuery({
    queryKey: ['dhcp-leases', selectedScope?.scope_id],
    queryFn: () => dhcpApi.listLeases(selectedScope!.scope_id),
    enabled: !!selectedScope,
  })

  const addMutation = useMutation({
    mutationFn: () => dhcpApi.addReservation(selectedScope!.scope_id, form),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ['dhcp-leases', selectedScope?.scope_id] })
      setForm(emptyForm)
      setShowForm(false)
    },
  })

  const deleteMutation = useMutation({
    mutationFn: (ip: string) => dhcpApi.deleteReservation(selectedScope!.scope_id, ip),
    onSuccess: () => qc.invalidateQueries({ queryKey: ['dhcp-leases', selectedScope?.scope_id] }),
  })

  const set = (key: keyof typeof emptyForm) =>
    (e: React.ChangeEvent<HTMLInputElement>) =>
      setForm(f => ({ ...f, [key]: key === 'iaid' ? Number(e.target.value) : e.target.value }))

  const canSubmit = form.ip_address && form.name && (
    isV6(selectedScope) ? form.client_duid : form.mac_address
  )

  return (
    <div>
      <div className="page-header">
        <h1>DHCP</h1>
      </div>

      <div className="two-panel">
        <div className="panel-list">
          <div className="panel-list-header">Scopes</div>
          {loadingScopes && <p className="loading" style={{ padding: '0.75rem' }}>Loading…</p>}
          {scopes?.map(s => (
            <div
              key={s.scope_id}
              className={'panel-list-item' + (selectedScope?.scope_id === s.scope_id ? ' active' : '')}
              onClick={() => { setSelectedScope(s); setShowForm(false); setForm(emptyForm) }}
            >
              <div style={{ display: 'flex', alignItems: 'center', gap: '0.4rem' }}>
                <span className={`badge ${s.ip_version === 6 ? 'badge-blue' : 'badge-green'}`} style={{ fontSize: '0.6rem' }}>
                  IPv{s.ip_version}
                </span>
                {s.name}
              </div>
              <div className="panel-list-item-sub font-mono">{s.scope_id}</div>
            </div>
          ))}
          {scopes?.length === 0 && <p className="loading" style={{ padding: '0.75rem' }}>No scopes found.</p>}
        </div>

        <div className="panel-main">
          {selectedScope ? (
            <>
              <div className="page-header">
                <div>
                  <h1>{selectedScope.name}</h1>
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
                        <tr><td colSpan={isV6(selectedScope) ? 6 : 5} className="empty-state">No leases in this scope.</td></tr>
                      )}
                      {leases?.map(l => (
                        <tr key={l.ip_address}>
                          <td><span className="font-mono">{l.ip_address}</span></td>
                          <td><span className="font-mono">{isV6(selectedScope) ? l.client_duid : l.mac_address}</span></td>
                          {isV6(selectedScope) && <td><span className="font-mono">{l.iaid || <span className="text-muted">—</span>}</span></td>}
                          <td>{l.name || <span className="text-muted">—</span>}</td>
                          <td>{l.description || <span className="text-muted">—</span>}</td>
                          <td>
                            <button
                              className="btn-danger btn-sm"
                              onClick={() => deleteMutation.mutate(l.ip_address)}
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
    </div>
  )
}
