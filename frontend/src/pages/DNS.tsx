import { useState } from 'react'
import { useQuery } from '@tanstack/react-query'
import { SlidersHorizontal } from 'lucide-react'
import { dnsApi, type DNSRecord } from '../api/client'

const TYPE_BADGE: Record<string, string> = {
  A:     'badge-green',
  AAAA:  'badge-blue',
  CNAME: 'badge-yellow',
  PTR:   'badge-gray',
  MX:    'badge-red',
  TXT:   'badge-gray',
  NS:    'badge-gray',
}

export default function DNS() {
  const [selectedZone, setSelectedZone] = useState<string | null>(null)
  const [filter, setFilter]             = useState('')

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
    !q || r.name.toLowerCase().includes(q) || r.value.toLowerCase().includes(q) || r.record_type.toLowerCase().includes(q)
  ) ?? []

  return (
    <div>
      <div className="page-header">
        <h1>DNS</h1>
      </div>

      <div className="two-panel">
        <div className="panel-list">
          <div className="panel-list-header">Zones</div>
          {loadingZones && <p className="loading" style={{ padding: '0.75rem' }}>Loading…</p>}
          {zones?.map(z => (
            <div
              key={z}
              className={'panel-list-item' + (selectedZone === z ? ' active' : '')}
              onClick={() => { setSelectedZone(z); setFilter('') }}
            >
              {z}
            </div>
          ))}
          {zones?.length === 0 && <p className="loading" style={{ padding: '0.75rem' }}>No zones found.</p>}
        </div>

        <div className="panel-main">
          {selectedZone ? (
            <>
              <div className="page-header">
                <h1>{selectedZone}</h1>
                <div className="filter-bar" style={{ margin: 0 }}>
                  <SlidersHorizontal size={14} style={{ color: 'var(--text-muted)', flexShrink: 0 }} />
                  <input
                    placeholder="Filter records…"
                    value={filter}
                    onChange={e => setFilter(e.target.value)}
                    style={{ width: '220px' }}
                  />
                </div>
              </div>

              {loadingRecords ? (
                <p className="loading">Loading records…</p>
              ) : (
                <div className="table-wrap">
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
                        <tr><td colSpan={4} className="empty-state">No records{filter ? ' matching filter' : ''}.</td></tr>
                      )}
                      {filtered.map((r, i) => (
                        <tr key={i}>
                          <td><span className="font-mono">{r.name}</span></td>
                          <td>
                            <span className={`badge ${TYPE_BADGE[r.record_type] ?? 'badge-gray'}`}>
                              {r.record_type}
                            </span>
                          </td>
                          <td><span className="font-mono">{r.value}</span></td>
                          <td><span className="text-muted">{r.ttl}</span></td>
                        </tr>
                      ))}
                    </tbody>
                  </table>
                </div>
              )}
            </>
          ) : (
            <div className="empty-state">Select a zone from the list.</div>
          )}
        </div>
      </div>
    </div>
  )
}
