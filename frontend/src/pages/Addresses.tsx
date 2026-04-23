import { useQuery } from '@tanstack/react-query'
import { addressesApi, type IPAddress } from '../api/client'

const STATUS_BADGE: Record<string, string> = {
  available:  'badge-green',
  assigned:   'badge-blue',
  reserved:   'badge-yellow',
  deprecated: 'badge-gray',
}

export default function Addresses() {
  const { data, isLoading, error } = useQuery({
    queryKey: ['addresses'],
    queryFn: () => addressesApi.list(),
  })

  return (
    <div>
      <div className="page-header">
        <h1>IP Addresses</h1>
      </div>

      {isLoading && <p className="loading">Loading…</p>}
      {error    && <p className="feedback-error">Failed to load addresses.</p>}

      {data && (
        <div className="table-wrap">
          <table>
            <thead>
              <tr>
                <th>Address</th>
                <th>Hostname</th>
                <th>Status</th>
                <th>MAC</th>
                <th>Description</th>
              </tr>
            </thead>
            <tbody>
              {data.length === 0 && (
                <tr><td colSpan={5} className="empty-state">No addresses tracked.</td></tr>
              )}
              {data.map((a: IPAddress) => (
                <tr key={a.id}>
                  <td><span className="font-mono">{a.address}</span></td>
                  <td>{a.hostname ?? <span className="text-muted">—</span>}</td>
                  <td>
                    <span className={`badge ${STATUS_BADGE[a.status] ?? 'badge-gray'}`}>
                      {a.status}
                    </span>
                  </td>
                  <td><span className="font-mono">{a.mac_address ?? <span className="text-muted">—</span>}</span></td>
                  <td>{a.description ?? <span className="text-muted">—</span>}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}
    </div>
  )
}
