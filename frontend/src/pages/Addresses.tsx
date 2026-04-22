import { useQuery } from '@tanstack/react-query'
import { addressesApi, type IPAddress } from '../api/client'

export default function Addresses() {
  const { data, isLoading, error } = useQuery({
    queryKey: ['addresses'],
    queryFn: () => addressesApi.list(),
  })

  if (isLoading) return <p>Loading...</p>
  if (error) return <p>Failed to load addresses.</p>

  return (
    <div>
      <h1>IP Addresses</h1>
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
          {data?.map((a: IPAddress) => (
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
    </div>
  )
}
