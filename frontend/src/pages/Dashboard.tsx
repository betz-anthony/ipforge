import { useQuery } from '@tanstack/react-query'
import { Link } from 'react-router-dom'
import { Network, List, Server, Globe, Search } from 'lucide-react'
import { statsApi } from '../api/client'

const TILES = [
  { to: '/subnets',   icon: Network, title: 'Subnets',   desc: 'Manage IP subnets and CIDRs' },
  { to: '/addresses', icon: List,    title: 'Addresses', desc: 'Track IP address assignments' },
  { to: '/dhcp',      icon: Server,  title: 'DHCP',      desc: 'Scopes, leases, and reservations' },
  { to: '/dns',       icon: Globe,   title: 'DNS',        desc: 'Zones and resource records' },
  { to: '/search',    icon: Search,  title: 'Search',    desc: 'Find by IP, MAC, or hostname' },
]

function count(val: number | undefined) {
  return val === undefined ? '—' : val.toLocaleString()
}

export default function Dashboard() {
  const { data: stats } = useQuery({ queryKey: ['stats'], queryFn: statsApi.get })

  return (
    <div>
      <div className="page-header">
        <h1>Dashboard</h1>
      </div>

      <p className="section-label">Overview</p>
      <div className="stats-grid">
        <div className="stat-card">
          <div className="stat-value">{count(stats?.dns_zones)}</div>
          <div className="stat-label">DNS Zones</div>
        </div>
        <div className="stat-card">
          <div className="stat-value">{count(stats?.dns_records)}</div>
          <div className="stat-label">DNS Records</div>
        </div>
        <div className="stat-card">
          <div className="stat-value">{count(stats?.dhcp_scopes)}</div>
          <div className="stat-label">DHCP Scopes</div>
        </div>
        <div className="stat-card">
          <div className="stat-value accent">{count(stats?.dhcp_leases)}</div>
          <div className="stat-label">DHCP Leases</div>
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
