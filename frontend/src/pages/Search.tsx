import { useState, useEffect } from 'react'
import { useQuery } from '@tanstack/react-query'
import { Search } from 'lucide-react'
import { searchApi } from '../api/client'

export default function SearchPage() {
  const [input, setInput]           = useState('')
  const [debouncedQ, setDebouncedQ] = useState('')

  useEffect(() => {
    const t = setTimeout(() => setDebouncedQ(input.trim()), 250)
    return () => clearTimeout(t)
  }, [input])

  const { data, isLoading, isError } = useQuery({
    queryKey: ['search', debouncedQ],
    queryFn:  () => searchApi.search(debouncedQ),
    enabled:  debouncedQ.length >= 2,
  })

  const active = debouncedQ.length >= 2

  return (
    <div>
      <div className="page-header">
        <h1>Search</h1>
      </div>

      <div className="search-wrap">
        <Search size={16} className="search-icon" />
        <input
          aria-label="Search"
          placeholder="Search by IP, CIDR, MAC, or hostname…"
          value={input}
          onChange={e => setInput(e.target.value)}
          autoFocus
        />
      </div>

      {isError && (
        <p className="feedback-error">
          Search failed. Try again.
        </p>
      )}

      {!active && (
        <div className="empty-state">
          Type at least 2 characters to search across subnets, addresses, DHCP leases, and DNS records.
        </div>
      )}

      {active && isLoading && <p className="loading">Searching…</p>}

      {active && data && (
        <>
          {/* Subnets */}
          <div className="search-results-section">
            <h2>Subnets ({data.subnets.length}{data.subnets.length === 50 ? '+' : ''})</h2>
            {data.subnets.length > 0 ? (
              <div className="table-wrap">
                <table>
                  <thead>
                    <tr><th>CIDR</th><th>Name</th><th>Version</th><th>Description</th></tr>
                  </thead>
                  <tbody>
                    {data.subnets.map(s => (
                      <tr key={s.id}>
                        <td><span className="font-mono">{s.cidr}</span></td>
                        <td>{s.name}</td>
                        <td><span className="badge badge-blue">IPv{s.ip_version}</span></td>
                        <td>{s.description ?? <span className="text-muted">—</span>}</td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            ) : <p className="text-muted" style={{ fontSize: '0.8125rem' }}>No matches.</p>}
          </div>

          {/* IP Addresses */}
          <div className="search-results-section">
            <h2>IP Addresses ({data.addresses.length}{data.addresses.length === 50 ? '+' : ''})</h2>
            {data.addresses.length > 0 ? (
              <div className="table-wrap">
                <table>
                  <thead>
                    <tr><th>IP</th><th>Hostname</th><th>Status</th><th>MAC</th></tr>
                  </thead>
                  <tbody>
                    {data.addresses.map(a => (
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

          {/* DHCP Leases */}
          <div className="search-results-section">
            <h2>DHCP Leases / Reservations ({data.leases.length}{data.leases.length === 50 ? '+' : ''})</h2>
            {data.leases.length > 0 ? (
              <div className="table-wrap">
                <table>
                  <thead>
                    <tr><th>IP</th><th>Hostname</th><th>MAC</th><th>Scope</th></tr>
                  </thead>
                  <tbody>
                    {data.leases.map(l => (
                      <tr key={`${l.source}:${l.ip_address}`}>
                        <td><span className="font-mono">{l.ip_address}</span></td>
                        <td>{l.name ?? <span className="text-muted">—</span>}</td>
                        <td><span className="font-mono">{l.mac_address ?? <span className="text-muted">—</span>}</span></td>
                        <td><span className="font-mono">{l.scope_id}</span></td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            ) : <p className="text-muted" style={{ fontSize: '0.8125rem' }}>No matches.</p>}
          </div>

          {/* DNS Records */}
          <div className="search-results-section">
            <h2>DNS Records ({data.records.length}{data.records.length === 50 ? '+' : ''})</h2>
            {data.records.length > 0 ? (
              <div className="table-wrap">
                <table>
                  <thead>
                    <tr><th>Name</th><th>Type</th><th>Value</th><th>Zone</th></tr>
                  </thead>
                  <tbody>
                    {data.records.map(r => (
                      <tr key={`${r.zone}:${r.record_type}:${r.name}:${r.value}`}>
                        <td><span className="font-mono">{r.name}</span></td>
                        <td><span className="badge badge-gray">{r.record_type}</span></td>
                        <td><span className="font-mono">{r.value}</span></td>
                        <td>{r.zone}</td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            ) : <p className="text-muted" style={{ fontSize: '0.8125rem' }}>No matches.</p>}
          </div>
        </>
      )}
    </div>
  )
}
