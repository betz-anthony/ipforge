import { useQuery } from '@tanstack/react-query'
import { Link } from 'react-router-dom'
import { subnetsApi, addressesApi } from '../api/client'

interface StatCardProps {
  label: string
  value: number | string
}

function StatCard({ label, value }: StatCardProps) {
  return (
    <div style={{
      border: '1px solid #e0e0e0',
      borderRadius: '6px',
      padding: '1rem 1.25rem',
      minWidth: '120px',
      background: '#fafafa',
    }}>
      <div style={{ fontSize: '1.75rem', fontWeight: 700 }}>{value}</div>
      <div style={{ fontSize: '0.8rem', color: '#666', marginTop: '2px' }}>{label}</div>
    </div>
  )
}

interface NavTileProps {
  to: string
  title: string
  desc: string
}

function NavTile({ to, title, desc }: NavTileProps) {
  return (
    <Link to={to} style={{ textDecoration: 'none', color: 'inherit' }}>
      <div style={{
        border: '1px solid #e0e0e0',
        borderRadius: '6px',
        padding: '1.25rem',
        cursor: 'pointer',
        background: '#fff',
        transition: 'border-color 0.15s',
      }}
        onMouseEnter={e => (e.currentTarget.style.borderColor = '#999')}
        onMouseLeave={e => (e.currentTarget.style.borderColor = '#e0e0e0')}
      >
        <div style={{ fontWeight: 600, marginBottom: '0.25rem' }}>{title}</div>
        <div style={{ fontSize: '0.85rem', color: '#666' }}>{desc}</div>
      </div>
    </Link>
  )
}

export default function Dashboard() {
  const { data: subnets } = useQuery({
    queryKey: ['subnets'],
    queryFn: subnetsApi.list,
  })

  const { data: addresses } = useQuery({
    queryKey: ['addresses'],
    queryFn: () => addressesApi.list(),
  })

  const statusCount = (status: string) =>
    addresses?.filter(a => a.status === status).length ?? '—'

  return (
    <div>
      <h1 style={{ fontSize: '1.5rem', marginBottom: '0.25rem' }}>IPAM</h1>
      <p style={{ color: '#888', marginBottom: '1.5rem', fontSize: '0.9rem' }}>
        IP Address Management
      </p>

      <h2 style={{ fontSize: '0.9rem', textTransform: 'uppercase', letterSpacing: '0.05em', color: '#888', marginBottom: '0.75rem' }}>
        Overview
      </h2>
      <div style={{ display: 'flex', gap: '0.75rem', flexWrap: 'wrap', marginBottom: '2rem' }}>
        <StatCard label="Subnets" value={subnets?.length ?? '—'} />
        <StatCard label="Total Addresses" value={addresses?.length ?? '—'} />
        <StatCard label="Available" value={statusCount('available')} />
        <StatCard label="Assigned" value={statusCount('assigned')} />
        <StatCard label="Reserved" value={statusCount('reserved')} />
        <StatCard label="Deprecated" value={statusCount('deprecated')} />
      </div>

      <h2 style={{ fontSize: '0.9rem', textTransform: 'uppercase', letterSpacing: '0.05em', color: '#888', marginBottom: '0.75rem' }}>
        Sections
      </h2>
      <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fill, minmax(180px, 1fr))', gap: '0.75rem' }}>
        <NavTile to="/subnets"  title="Subnets"    desc="Manage IP subnets and CIDRs" />
        <NavTile to="/addresses" title="Addresses"  desc="Track IP address assignments" />
        <NavTile to="/dhcp"     title="DHCP"        desc="Scopes, leases, and reservations" />
        <NavTile to="/dns"      title="DNS"         desc="Zones and resource records" />
        <NavTile to="/search"   title="Search"      desc="Find by IP, MAC, or hostname" />
      </div>
    </div>
  )
}
