import { useState } from 'react'
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query'
import { dhcpApi, type DHCPScope } from '../api/client'

const emptyForm = { ip_address: '', mac_address: '', name: '', description: '' }

export default function DHCP() {
  const [selectedScope, setSelectedScope] = useState<DHCPScope | null>(null)
  const [showForm, setShowForm] = useState(false)
  const [form, setForm] = useState(emptyForm)
  const qc = useQueryClient()

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

  return (
    <div style={{ display: 'flex', gap: '2rem' }}>
      <div style={{ minWidth: '220px' }}>
        <h2>Scopes</h2>
        {loadingScopes && <p>Loading...</p>}
        <ul style={{ listStyle: 'none', padding: 0, margin: 0 }}>
          {scopes?.map(s => (
            <li
              key={s.scope_id}
              onClick={() => { setSelectedScope(s); setShowForm(false) }}
              style={{
                cursor: 'pointer',
                fontWeight: selectedScope?.scope_id === s.scope_id ? 'bold' : 'normal',
                padding: '4px 0',
                borderBottom: '1px solid #eee',
              }}
            >
              <div>{s.name}</div>
              <div style={{ fontSize: '0.8em', color: '#666' }}>{s.scope_id}</div>
            </li>
          ))}
        </ul>
      </div>

      <div style={{ flex: 1 }}>
        {selectedScope ? (
          <>
            <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: '0.75rem' }}>
              <h2 style={{ margin: 0 }}>{selectedScope.name} — {selectedScope.scope_id}</h2>
              <button onClick={() => setShowForm(f => !f)}>+ Add Reservation</button>
            </div>

            {showForm && (
              <form
                onSubmit={e => { e.preventDefault(); addMutation.mutate() }}
                style={{ display: 'flex', gap: '0.5rem', flexWrap: 'wrap', marginBottom: '1rem', padding: '0.75rem', background: '#f9f9f9', borderRadius: '4px' }}
              >
                <input
                  placeholder="IP Address"
                  value={form.ip_address}
                  onChange={e => setForm(f => ({ ...f, ip_address: e.target.value }))}
                  required
                />
                <input
                  placeholder="MAC (xx-xx-xx-xx-xx-xx)"
                  value={form.mac_address}
                  onChange={e => setForm(f => ({ ...f, mac_address: e.target.value }))}
                  required
                />
                <input
                  placeholder="Hostname / Name"
                  value={form.name}
                  onChange={e => setForm(f => ({ ...f, name: e.target.value }))}
                  required
                />
                <input
                  placeholder="Description"
                  value={form.description}
                  onChange={e => setForm(f => ({ ...f, description: e.target.value }))}
                />
                <button type="submit" disabled={addMutation.isPending}>
                  {addMutation.isPending ? 'Adding…' : 'Add'}
                </button>
                <button type="button" onClick={() => setShowForm(false)}>Cancel</button>
                {addMutation.isError && (
                  <span style={{ color: 'red', width: '100%' }}>
                    Error: {String((addMutation.error as Error).message)}
                  </span>
                )}
              </form>
            )}

            {loadingLeases ? (
              <p>Loading leases…</p>
            ) : (
              <table>
                <thead>
                  <tr>
                    <th>IP Address</th>
                    <th>MAC</th>
                    <th>Name</th>
                    <th>Description</th>
                    <th></th>
                  </tr>
                </thead>
                <tbody>
                  {leases?.length === 0 && (
                    <tr><td colSpan={5} style={{ color: '#999' }}>No leases in this scope.</td></tr>
                  )}
                  {leases?.map(l => (
                    <tr key={l.ip_address}>
                      <td>{l.ip_address}</td>
                      <td>{l.mac_address}</td>
                      <td>{l.name}</td>
                      <td>{l.description || '—'}</td>
                      <td>
                        <button
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
            )}
          </>
        ) : (
          <p style={{ color: '#999' }}>Select a scope.</p>
        )}
      </div>
    </div>
  )
}
