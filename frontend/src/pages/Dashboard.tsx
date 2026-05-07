import { useState } from 'react'
import { useQuery } from '@tanstack/react-query'
import { Link } from 'react-router-dom'
import { Network, List, Server, Globe, Search } from 'lucide-react'
import { statsApi, dnsApi, dhcpApi } from '../api/client'
import SlidePanel from '../components/SlidePanel'

const TILES = [
  { to: '/subnets',   icon: Network, title: 'Subnets',   desc: 'Manage IP subnets and CIDRs' },
  { to: '/addresses', icon: List,    title: 'Addresses', desc: 'Track IP address assignments' },
  { to: '/dhcp',      icon: Server,  title: 'DHCP',      desc: 'Scopes, leases, and reservations' },
  { to: '/dns',       icon: Globe,   title: 'DNS',        desc: 'Zones and resource records' },
  { to: '/search',    icon: Search,  title: 'Search',    desc: 'Find by IP, MAC, or hostname' },
]

const SOURCE_LABEL: Record<string, string> = {
  msdhcp: 'MS DHCP', pihole: 'Pi-hole', keadhcp: 'Kea',
  msdns: 'MS DNS', bind: 'BIND',
}

type PanelKey = 'dns_zones' | 'dns_records' | 'dhcp_scopes' | 'dhcp_leases'

function count(val: number | undefined) {
  return val === undefined ? '—' : val.toLocaleString()
}

export default function Dashboard() {
  const [openPanel, setOpenPanel] = useState<PanelKey | null>(null)

  const { data: stats } = useQuery({ queryKey: ['stats'], queryFn: statsApi.get })

  const { data: zones } = useQuery({
    queryKey: ['dns-zones'],
    queryFn: dnsApi.listZones,
    enabled: openPanel === 'dns_zones' || openPanel === 'dns_records',
  })

  const { data: scopes } = useQuery({
    queryKey: ['dhcp-scopes'],
    queryFn: dhcpApi.listScopes,
    enabled: openPanel === 'dhcp_scopes' || openPanel === 'dhcp_leases',
  })

  const toggle = (key: PanelKey) =>
    setOpenPanel(prev => (prev === key ? null : key))

  return (
    <div>
      <div className="page-header">
        <h1>Dashboard</h1>
      </div>

      <p className="section-label">Overview</p>
      <div className="stats-grid">
        <div
          className="stat-card"
          style={{ cursor: 'pointer' }}
          onClick={() => toggle('dns_zones')}
        >
          <div className="stat-value">{count(stats?.dns_zones)}</div>
          <div className="stat-label">DNS Zones</div>
        </div>
        <div
          className="stat-card"
          style={{ cursor: 'pointer' }}
          onClick={() => toggle('dns_records')}
        >
          <div className="stat-value">{count(stats?.dns_records)}</div>
          <div className="stat-label">DNS Records</div>
        </div>
        <div
          className="stat-card"
          style={{ cursor: 'pointer' }}
          onClick={() => toggle('dhcp_scopes')}
        >
          <div className="stat-value">{count(stats?.dhcp_scopes)}</div>
          <div className="stat-label">DHCP Scopes</div>
        </div>
        <div
          className="stat-card"
          style={{ cursor: 'pointer' }}
          onClick={() => toggle('dhcp_leases')}
        >
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

      {(openPanel === 'dns_zones' || openPanel === 'dns_records') && (
        <SlidePanel
          title={openPanel === 'dns_zones' ? 'DNS Zones' : 'DNS Records'}
          subtitle={
            openPanel === 'dns_zones'
              ? `${stats?.dns_zones ?? '—'} zones`
              : `${stats?.dns_records ?? '—'} records across ${stats?.dns_zones ?? '—'} zones`
          }
          onClose={() => setOpenPanel(null)}
        >
          <div>
            {!zones ? (
              <p className="loading">Loading…</p>
            ) : zones.length === 0 ? (
              <p style={{ fontSize: '0.8rem', color: 'var(--text-muted)' }}>No zones found.</p>
            ) : (
              <div className="detail-fields">
                {zones.map((z, i) => (
                  <div key={i} className="detail-field">
                    <span className="detail-field-label font-mono" style={{ fontSize: '0.78rem' }}>
                      {z.zone}
                    </span>
                    <span className="detail-field-value">
                      <span className="badge badge-gray" style={{ fontSize: '0.6rem' }}>
                        {SOURCE_LABEL[z.source] ?? z.source}
                      </span>
                    </span>
                  </div>
                ))}
              </div>
            )}
            <div style={{ marginTop: '1rem' }}>
              <Link to="/dns" className="btn-ghost btn-sm" onClick={() => setOpenPanel(null)}>
                View all in DNS →
              </Link>
            </div>
          </div>
        </SlidePanel>
      )}

      {(openPanel === 'dhcp_scopes' || openPanel === 'dhcp_leases') && (
        <SlidePanel
          title={openPanel === 'dhcp_scopes' ? 'DHCP Scopes' : 'DHCP Leases'}
          subtitle={
            openPanel === 'dhcp_scopes'
              ? `${stats?.dhcp_scopes ?? '—'} scopes`
              : `${stats?.dhcp_leases ?? '—'} total reservations`
          }
          onClose={() => setOpenPanel(null)}
        >
          <div>
            {!scopes ? (
              <p className="loading">Loading…</p>
            ) : scopes.length === 0 ? (
              <p style={{ fontSize: '0.8rem', color: 'var(--text-muted)' }}>No scopes found.</p>
            ) : (
              <div className="detail-fields">
                {scopes.map((s, i) => (
                  <div key={i} className="detail-field">
                    <span className="detail-field-label" style={{ fontSize: '0.78rem' }}>
                      <span className={`badge ${s.active ? 'badge-green' : 'badge-gray'}`}
                        style={{ fontSize: '0.55rem', marginRight: '0.3rem' }}>
                        IPv{s.ip_version}
                      </span>
                      {s.name || s.scope_id}
                    </span>
                    <span className="detail-field-value font-mono" style={{ fontSize: '0.75rem' }}>
                      {s.scope_id}
                    </span>
                  </div>
                ))}
              </div>
            )}
            <div style={{ marginTop: '1rem' }}>
              <Link to="/dhcp" className="btn-ghost btn-sm" onClick={() => setOpenPanel(null)}>
                View all in DHCP →
              </Link>
            </div>
          </div>
        </SlidePanel>
      )}
    </div>
  )
}
