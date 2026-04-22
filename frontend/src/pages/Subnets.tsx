import { useQuery } from '@tanstack/react-query'
import { subnetsApi, type Subnet } from '../api/client'

export default function Subnets() {
  const { data, isLoading, error } = useQuery({
    queryKey: ['subnets'],
    queryFn: subnetsApi.list,
  })

  if (isLoading) return <p>Loading...</p>
  if (error) return <p>Failed to load subnets.</p>

  return (
    <div>
      <h1>Subnets</h1>
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
          {data?.map((s: Subnet) => (
            <tr key={s.id}>
              <td>{s.name}</td>
              <td>{s.cidr}</td>
              <td>IPv{s.ip_version}</td>
              <td>{s.vlan_id ?? '—'}</td>
              <td>{s.description ?? '—'}</td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  )
}
