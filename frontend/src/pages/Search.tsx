import { useState } from 'react'
import { useQuery, useQueries } from '@tanstack/react-query'
import { addressesApi, dhcpApi, dnsApi } from '../api/client'

export default function Search() {
  const [input, setInput] = useState('')
  const q = input.toLowerCase().trim()

  const { data: addresses } = useQuery({
    queryKey: ['addresses'],
    queryFn: () => addressesApi.list(),
  })

  const { data: scopes } = useQuery({
    queryKey: ['dhcp-scopes'],
    queryFn: dhcpApi.listScopes,
  })

  const leaseQueries = useQueries({
    queries: (scopes ?? []).map(s => ({
      queryKey: ['dhcp-leases', s.scope_id],
      queryFn: () => dhcpApi.listLeases(s.scope_id),
    })),
  })

  const { data: zones } = useQuery({
    queryKey: ['dns-zones'],
    queryFn: dnsApi.listZones,
  })

  const recordQueries = useQueries({
    queries: (zones ?? []).map(z => ({
      queryKey: ['dns-records', z],
      queryFn: () => dnsApi.listRecords(z),
    })),
  })

  const dhcpLoading = leaseQueries.some(r => r.isLoading)
  const dnsLoading = recordQueries.some(r => r.isLoading)
  const allLeases = leaseQueries.flatMap(r => r.data ?? [])
  const allRecords = recordQueries.flatMap(r => r.data ?? [])

  const matchedAddresses = q
    ? (addresses ?? []).filter(a =>
        a.address.includes(q) ||
        a.hostname?.toLowerCase().includes(q) ||
        a.mac_address?.toLowerCase().includes(q)
      )
    : []

  const matchedLeases = q
    ? allLeases.filter(l =>
        l.ip_address.includes(q) ||
        l.name.toLowerCase().includes(q) ||
        l.mac_address.toLowerCase().includes(q)
      )
    : []

  const matchedRecords = q
    ? allRecords.filter(r =>
        r.name.toLowerCase().includes(q) ||
        r.value.toLowerCase().includes(q)
      )
    : []

  return (
    <div>
      <h1>Search</h1>
      <input
        placeholder="Search by IP, MAC, or hostname…"
        value={input}
        onChange={e => setInput(e.target.value)}
        style={{ width: '100%', padding: '0.5rem', marginBottom: '1.5rem', fontSize: '1rem' }}
        autoFocus
      />

      {q && (
        <>
          <section style={{ marginBottom: '1.5rem' }}>
            <h2>IP Addresses ({matchedAddresses.length})</h2>
            {matchedAddresses.length > 0 ? (
              <table>
                <thead>
                  <tr><th>IP</th><th>Hostname</th><th>Status</th><th>MAC</th><th>Description</th></tr>
                </thead>
                <tbody>
                  {matchedAddresses.map(a => (
                    <tr key={a.id}>
                      <td>{a.address}</td>
                      <td>{a.hostname ?? '—'}</td>
                      <td>{a.status}</td>
                      <td>{a.mac_address ?? '—'}</td>
                      <td>{a.description ?? '—'}</td>
                    </tr>
                  ))}
                </tbody>
              </table>
            ) : <p style={{ color: '#999' }}>No matches.</p>}
          </section>

          <section style={{ marginBottom: '1.5rem' }}>
            <h2>DHCP Leases / Reservations ({matchedLeases.length}){dhcpLoading ? ' — loading…' : ''}</h2>
            {matchedLeases.length > 0 ? (
              <table>
                <thead>
                  <tr><th>IP</th><th>Name</th><th>MAC</th><th>Scope</th><th>Description</th></tr>
                </thead>
                <tbody>
                  {matchedLeases.map((l, i) => (
                    <tr key={i}>
                      <td>{l.ip_address}</td>
                      <td>{l.name}</td>
                      <td>{l.mac_address}</td>
                      <td>{l.scope_id}</td>
                      <td>{l.description || '—'}</td>
                    </tr>
                  ))}
                </tbody>
              </table>
            ) : !dhcpLoading && <p style={{ color: '#999' }}>No matches.</p>}
          </section>

          <section>
            <h2>DNS Records ({matchedRecords.length}){dnsLoading ? ' — loading…' : ''}</h2>
            {matchedRecords.length > 0 ? (
              <table>
                <thead>
                  <tr><th>Name</th><th>Type</th><th>Value</th><th>Zone</th><th>TTL</th></tr>
                </thead>
                <tbody>
                  {matchedRecords.map((r, i) => (
                    <tr key={i}>
                      <td>{r.name}</td>
                      <td>{r.record_type}</td>
                      <td>{r.value}</td>
                      <td>{r.zone}</td>
                      <td>{r.ttl}</td>
                    </tr>
                  ))}
                </tbody>
              </table>
            ) : !dnsLoading && <p style={{ color: '#999' }}>No matches.</p>}
          </section>
        </>
      )}
    </div>
  )
}
