import { useState } from 'react'
import { useQuery } from '@tanstack/react-query'
import { dnsApi, type DNSRecord } from '../api/client'

export default function DNS() {
  const [selectedZone, setSelectedZone] = useState<string | null>(null)
  const [filter, setFilter] = useState('')

  const { data: zones, isLoading: loadingZones } = useQuery({
    queryKey: ['dns-zones'],
    queryFn: dnsApi.listZones,
  })

  const { data: records, isLoading: loadingRecords } = useQuery({
    queryKey: ['dns-records', selectedZone],
    queryFn: () => dnsApi.listRecords(selectedZone!),
    enabled: !!selectedZone,
  })

  const q = filter.toLowerCase()
  const filtered: DNSRecord[] = records?.filter(r =>
    !q ||
    r.name.toLowerCase().includes(q) ||
    r.value.toLowerCase().includes(q) ||
    r.record_type.toLowerCase().includes(q)
  ) ?? []

  return (
    <div style={{ display: 'flex', gap: '2rem' }}>
      <div style={{ minWidth: '220px' }}>
        <h2>Zones</h2>
        {loadingZones && <p>Loading…</p>}
        <ul style={{ listStyle: 'none', padding: 0, margin: 0 }}>
          {zones?.map(z => (
            <li
              key={z}
              onClick={() => { setSelectedZone(z); setFilter('') }}
              style={{
                cursor: 'pointer',
                fontWeight: selectedZone === z ? 'bold' : 'normal',
                padding: '4px 0',
                borderBottom: '1px solid #eee',
              }}
            >
              {z}
            </li>
          ))}
        </ul>
      </div>

      <div style={{ flex: 1 }}>
        {selectedZone ? (
          <>
            <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: '0.75rem' }}>
              <h2 style={{ margin: 0 }}>{selectedZone}</h2>
              <input
                placeholder="Filter by name, type, or value…"
                value={filter}
                onChange={e => setFilter(e.target.value)}
                style={{ width: '280px' }}
              />
            </div>

            {loadingRecords ? (
              <p>Loading records…</p>
            ) : (
              <table>
                <thead>
                  <tr>
                    <th>Name</th>
                    <th>Type</th>
                    <th>Value</th>
                    <th>TTL</th>
                  </tr>
                </thead>
                <tbody>
                  {filtered.length === 0 && (
                    <tr><td colSpan={4} style={{ color: '#999' }}>No records.</td></tr>
                  )}
                  {filtered.map((r, i) => (
                    <tr key={i}>
                      <td>{r.name}</td>
                      <td>{r.record_type}</td>
                      <td>{r.value}</td>
                      <td>{r.ttl}</td>
                    </tr>
                  ))}
                </tbody>
              </table>
            )}
          </>
        ) : (
          <p style={{ color: '#999' }}>Select a zone.</p>
        )}
      </div>
    </div>
  )
}
