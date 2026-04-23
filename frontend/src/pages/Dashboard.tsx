import { useQuery } from '@tanstack/react-query'
import { Link } from 'react-router-dom'
import { Network, List, Server, Globe, Search } from 'lucide-react'
import { subnetsApi, addressesApi } from '../api/client'

const TILES = [
  { to: '/subnets',   icon: Network, title: 'Subnets',   desc: 'Manage IP subnets and CIDRs' },
  { to: '/addresses', icon: List,    title: 'Addresses', desc: 'Track IP address assignments' },
  { to: '/dhcp',      icon: Server,  title: 'DHCP',      desc: 'Scopes, leases, and reservations' },
  { to: '/dns',       icon: Globe,   title: 'DNS',        desc: 'Zones and resource records' },
  { to: '/search',    icon: Search,  title: 'Search',    desc: 'Find by IP, MAC, or hostname' },
]

function count(val: number | undefined) {
  return val === undefined ? '—' : val
}

export default function Dashboard() {
  const { data: subnets }   = useQuery({ queryKey: ['subnets'],   queryFn: subnetsApi.list })
  const { data: addresses } = useQuery({ queryKey: ['addresses'], queryFn: () => addressesApi.list() })

  const byStatus = (s: string) => addresses?.filter(a => a.status === s).length

  return (
    <div>
      <div className="page-header">
        <h1>Dashboard</h1>
      </div>

      <p className="section-label">Overview</p>
      <div className="stats-grid">
        <div className="stat-card">
          <div className="stat-value">{count(subnets?.length)}</div>
          <div className="stat-label">Subnets</div>
        </div>
        <div className="stat-card">
          <div className="stat-value">{count(addresses?.length)}</div>
          <div className="stat-label">Total Addresses</div>
        </div>
        <div className="stat-card">
          <div className="stat-value accent">{count(byStatus('available'))}</div>
          <div className="stat-label">Available</div>
        </div>
        <div className="stat-card">
          <div className="stat-value">{count(byStatus('assigned'))}</div>
          <div className="stat-label">Assigned</div>
        </div>
        <div className="stat-card">
          <div className="stat-value">{count(byStatus('reserved'))}</div>
          <div className="stat-label">Reserved</div>
        </div>
        <div className="stat-card">
          <div className="stat-value">{count(byStatus('deprecated'))}</div>
          <div className="stat-label">Deprecated</div>
        </div>
      </div>

      <p className="section-label">Sections</p>
      <div className="nav-tiles">
        {TILES.map(({ to, icon: Icon, title, desc }) => (
          <Link key={to} to={to} className="nav-tile">
            <div className="nav-tile-icon"><Icon size={18} strokeWidth={1.75} /></div>
            <div className="nav-tile-title">{title}</div>
            <div className="nav-tile-desc">{desc}</div>
          </Link>
        ))}
      </div>
    </div>
  )
}
