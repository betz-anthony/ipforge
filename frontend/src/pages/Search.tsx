import { useState } from 'react'
import { useQuery, useQueries } from '@tanstack/react-query'
import { Search } from 'lucide-react'
import { addressesApi, dhcpApi, dnsApi } from '../api/client'

export default function SearchPage() {
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
      queryFn: () => dhcpApi.listLeases(s.scope_id, s.source),
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

  const dhcpLoading   = leaseQueries.some(r => r.isLoading)
  const dnsLoading    = recordQueries.some(r => r.isLoading)
  const allLeases     = leaseQueries.flatMap(r => r.data ?? [])
  const allRecords    = recordQueries.flatMap(r => r.data ?? [])

  const matchedAddresses = q
    ? (addresses ?? []).filter(a =>
        a.address.includes(q) ||
        a.hostname?.toLowerCase().includes(q) ||
        a.mac_address?.toLowerCase().includes(q))
    : []

  const matchedLeases = q
    ? allLeases.filter(l =>
        l.ip_address.includes(q) ||
        l.name.toLowerCase().includes(q) ||
        l.mac_address.toLowerCase().includes(q))
    : []

  const matchedRecords = q
    ? allRecords.filter(r =>
        r.name.toLowerCase().includes(q) ||
        r.value.toLowerCase().includes(q))
    : []

  return (
    <div>
      <div className="page-header">
        <h1>Search</h1>
      </div>

      <div className="search-wrap">
        <Search size={16} className="search-icon" />
        <input
          placeholder="Search by IP address, MAC, or hostname…"
          value={input}
          onChange={e => setInput(e.target.value)}
          autoFocus
        />
      </div>

      {q && (
        <>
          <div className="search-results-section">
            <h2>IP Addresses ({matchedAddresses.length})</h2>
            {matchedAddresses.length > 0 ? (
              <div className="table-wrap">
                <table>
                  <thead>
                    <tr><th>IP</th><th>Hostname</th><th>Status</th><th>MAC</th></tr>
                  </thead>
                  <tbody>
                    {matchedAddresses.map(a => (
                      <tr key={a.id}>
                        <td><span className="font-mono">{a.address}</span></td>
                        <td>{a.hostname ?? <span className="text-muted">—</span>}</td>
                        <td><span className="badge badge-blue">{a.status}</span></td>
                        <td><span className="font-mono">{a.mac_address ?? <span className="text-muted">—</span>}</span></td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            ) : <p className="text-muted" style={{ fontSize: '0.8125rem' }}>No matches.</p>}
          </div>

          <div className="search-results-section">
            <h2>DHCP Leases / Reservations ({matchedLeases.length}){dhcpLoading ? ' — loading…' : ''}</h2>
            {matchedLeases.length > 0 ? (
              <div className="table-wrap">
                <table>
                  <thead>
                    <tr><th>IP</th><th>Hostname</th><th>MAC</th><th>Scope</th></tr>
                  </thead>
                  <tbody>
                    {matchedLeases.map((l, i) => (
                      <tr key={i}>
                        <td><span className="font-mono">{l.ip_address}</span></td>
                        <td>{l.name || <span className="text-muted">—</span>}</td>
                        <td><span className="font-mono">{l.mac_address}</span></td>
                        <td><span className="font-mono">{l.scope_id}</span></td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            ) : !dhcpLoading && <p className="text-muted" style={{ fontSize: '0.8125rem' }}>No matches.</p>}
          </div>

          <div className="search-results-section">
            <h2>DNS Records ({matchedRecords.length}){dnsLoading ? ' — loading…' : ''}</h2>
            {matchedRecords.length > 0 ? (
              <div className="table-wrap">
                <table>
                  <thead>
                    <tr><th>Name</th><th>Type</th><th>Value</th><th>Zone</th></tr>
                  </thead>
                  <tbody>
                    {matchedRecords.map((r, i) => (
                      <tr key={i}>
                        <td><span className="font-mono">{r.name}</span></td>
                        <td><span className="badge badge-gray">{r.record_type}</span></td>
                        <td><span className="font-mono">{r.value}</span></td>
                        <td>{r.zone}</td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            ) : !dnsLoading && <p className="text-muted" style={{ fontSize: '0.8125rem' }}>No matches.</p>}
          </div>
        </>
      )}

      {!q && (
        <div className="empty-state">
          Type an IP address, MAC address, or hostname to search across all sources.
        </div>
      )}
    </div>
  )
}
