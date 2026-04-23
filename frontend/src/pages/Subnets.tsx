import { useQuery } from '@tanstack/react-query'
import { subnetsApi, type Subnet } from '../api/client'

export default function Subnets() {
  const { data, isLoading, error } = useQuery({
    queryKey: ['subnets'],
    queryFn: subnetsApi.list,
  })

  return (
    <div>
      <div className="page-header">
        <h1>Subnets</h1>
      </div>

      {isLoading && <p className="loading">Loading…</p>}
      {error    && <p className="feedback-error">Failed to load subnets.</p>}

      {data && (
        <div className="table-wrap">
          <table>
            <thead>
              <tr>
                <th>Name</th>
                <th>CIDR</th>
                <th>Version</th>
                <th>VLAN</th>
                <th>Description</th>
              </tr>
            </thead>
            <tbody>
              {data.length === 0 && (
                <tr><td colSpan={5} className="empty-state">No subnets defined.</td></tr>
              )}
              {data.map((s: Subnet) => (
                <tr key={s.id}>
                  <td>{s.name}</td>
                  <td><span className="font-mono">{s.cidr}</span></td>
                  <td><span className="badge badge-blue">IPv{s.ip_version}</span></td>
                  <td>{s.vlan_id ?? <span className="text-muted">—</span>}</td>
                  <td>{s.description ?? <span className="text-muted">—</span>}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}
    </div>
  )
}
